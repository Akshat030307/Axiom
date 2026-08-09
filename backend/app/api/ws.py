"""WebSocket streaming (PRD §7.3), publishing straight from the in-process
event bus in app/observability/events.py — see that module's NOTE on why the
Redis Pub/Sub bridge is skipped for now.
"""

import asyncio
import logging
import uuid

import jwt as pyjwt
from fastapi import APIRouter, WebSocket
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.auth.jwt import decode_access_token
from app.config import get_settings
from app.db.session import async_session_maker
from app.models.db_models import Contradiction, NodeTrace, Report, ResearchRun, Source
from app.observability.events import STAGE_ORDER, make_frame, run_event_bus
from app.observability.stat import compute_run_stat_counts

router = APIRouter(prefix="/api/v1/ws", tags=["ws"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _authenticate(token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        return uuid.UUID(payload["sub"])
    except (pyjwt.PyJWTError, ValueError, KeyError):
        return None


async def _build_snapshot_data(db, run: ResearchRun) -> dict:
    """Merges DB-committed state (authoritative for anything a node has
    already finished and committed) with the event bus's in-memory rolling
    state (fresher for the currently-active node — e.g. partial report text
    mid-stream, or the current stage before its node has committed). Together
    this is enough for a client connecting mid-run or reconnecting after a
    refresh to render correctly with no event-replay buffer (PRD §7.3)."""
    channel = run_event_bus.channel_state(str(run.id))

    sources = (await db.scalars(select(Source).where(Source.run_id == run.id).order_by(Source.fetched_at))).all()
    contradictions = (
        await db.scalars(select(Contradiction).where(Contradiction.run_id == run.id))
    ).all()
    node_traces = (
        await db.scalars(select(NodeTrace).where(NodeTrace.run_id == run.id).order_by(NodeTrace.seq))
    ).all()

    if channel is not None and channel.stat is not None:
        stat = channel.stat
    else:
        stat = {**(await compute_run_stat_counts(db, run.id)), "eta_seconds": None}

    report_markdown = ""
    if run.status == "completed":
        report = await db.scalar(select(Report).where(Report.run_id == run.id).order_by(Report.created_at.desc()))
        report_markdown = report.content_markdown if report else ""
    elif channel is not None:
        report_markdown = channel.report_text  # partial, in-memory, mid-synthesis

    return {
        "status": run.status,
        "mode": run.mode,
        "query": run.query,
        "plan": run.plan,
        "stage": channel.stage if channel is not None else None,
        "stage_order": STAGE_ORDER,
        "stat": stat,
        "sources": [
            {
                "source_id": str(s.id),
                "title": s.title,
                "domain": s.domain,
                "source_type": s.source_type,
                "credibility_score": s.credibility_score,
            }
            for s in sources
        ],
        "contradictions": [
            {"topic": c.topic, "evidence_a_id": str(c.evidence_a_id), "evidence_b_id": str(c.evidence_b_id)}
            for c in contradictions
        ],
        "node_traces": [
            {"node": t.node_name, "seq": t.seq, "status": t.status, "latency_ms": t.latency_ms, "cost_usd": float(t.cost_usd) if t.cost_usd is not None else None}
            for t in node_traces
        ],
        "report_markdown": report_markdown,
    }


async def _writer(websocket: WebSocket, queue: asyncio.Queue) -> str:
    while True:
        frame = await queue.get()
        try:
            await websocket.send_json(frame)
        except (WebSocketDisconnect, RuntimeError) as exc:
            return f"writer: {type(exc).__name__}: {exc}"


async def _reader(websocket: WebSocket, idle_timeout: float) -> str:
    """The client's only outbound message is {"type":"ping"} (PRD §7.3) sent
    on a ~20s cadence — that IS the heartbeat. This loop doesn't care what
    the message contains, only that one arrives; any inbound text resets the
    idle clock by looping back into a fresh wait_for. No message within
    idle_timeout closes the connection."""
    while True:
        try:
            await asyncio.wait_for(websocket.receive_text(), timeout=idle_timeout)
        except asyncio.TimeoutError:
            return "reader: idle timeout"
        except WebSocketDisconnect as exc:
            return f"reader: WebSocketDisconnect: {exc}"


@router.websocket("/research/{run_id}")
async def research_ws(websocket: WebSocket, run_id: uuid.UUID) -> None:
    # Custom close codes (4401/4403) are only reliably observable by a
    # browser client if the WS handshake actually completes first — an ASGI
    # app that sends `websocket.close` *before* `websocket.accept` causes the
    # server to reject the handshake at the HTTP level, and the JS
    # WebSocket API does not expose that rejection's detail to `onclose`
    # (it just reports the generic abnormal-closure code 1006). So: accept
    # first, then immediately close with the intended code if auth fails —
    # this still guarantees no run data is ever sent to an unauthorized
    # client (nothing is sent between accept and the auth-failure close),
    # while making PRD §7.3's 4401 vs 4403 distinction actually reach the
    # client's reconnect logic.
    await websocket.accept()

    user_id = _authenticate(websocket.query_params.get("token"))
    if user_id is None:
        await websocket.close(code=4401)
        return

    async with async_session_maker() as db:
        run = await db.get(ResearchRun, run_id)
        if run is None or run.user_id != user_id:
            await websocket.close(code=4403)
            return

        snapshot_data = await _build_snapshot_data(db, run)
        terminal_frame = None
        if run.status in ("completed", "error"):
            channel = run_event_bus.channel_state(str(run.id))
            if channel is not None and channel.terminal_frame is not None:
                terminal_frame = channel.terminal_frame
            elif run.status == "completed":
                terminal_frame = make_frame("done", str(run.id), {"report_url": f"/api/v1/research/{run.id}/report"})
            else:
                last_error = await db.scalar(
                    select(NodeTrace.error)
                    .where(NodeTrace.run_id == run.id, NodeTrace.status == "error")
                    .order_by(NodeTrace.seq.desc())
                    .limit(1)
                )
                terminal_frame = make_frame("error", str(run.id), {"message": last_error or "Run failed", "recoverable": False})

    queue = run_event_bus.subscribe(str(run_id))
    try:
        await websocket.send_json(make_frame("snapshot", str(run_id), snapshot_data))
        if terminal_frame is not None:
            await websocket.send_json(terminal_frame)

        writer_task = asyncio.create_task(_writer(websocket, queue))
        reader_task = asyncio.create_task(_reader(websocket, settings.WS_IDLE_TIMEOUT_SECONDS))
        done, pending = await asyncio.wait({writer_task, reader_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            exc = task.exception()
            if exc is not None:
                logger.warning("research_ws[%s]: task ended with unexpected exception: %r", run_id, exc)
            else:
                logger.info("research_ws[%s]: closing — %s", run_id, task.result())
    except (WebSocketDisconnect, RuntimeError) as exc:
        logger.info("research_ws[%s]: closing — outer %s: %s", run_id, type(exc).__name__, exc)
    finally:
        run_event_bus.unsubscribe(str(run_id), queue)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
