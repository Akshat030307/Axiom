import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.session import async_session_maker
from app.graph.checkpointer import get_checkpointer
from app.graph.graph_builder import build_graph
from app.graph.run_context import RunContext
from app.llm.provider import LLMProvider
from app.models.db_models import NodeTrace, ResearchRun
from app.observability.events import RunEvents, run_event_bus
from app.observability.tracer import publish_final_stat

logger = logging.getLogger(__name__)


async def execute_research_run(run_id: uuid.UUID, user_id: uuid.UUID, query: str, mode: str) -> None:
    """Entry point for the FastAPI BackgroundTask that runs a research graph.

    Phase 1 has no Celery worker (see the compose scope: postgres, redis,
    backend, frontend — no `worker`), so this runs in the backend process
    after the HTTP response for POST /research has already been sent. It
    opens and owns a single DB session for the run's entire duration — never
    the request-scoped `Depends(get_db)` session, which closes the instant
    the response goes out, before the graph has done any work.
    """
    async with async_session_maker() as db:
        run = await db.get(ResearchRun, run_id)
        if run is None:
            logger.error("execute_research_run: run %s not found at start", run_id)
            return

        run.status = "running"
        await db.commit()

        events = RunEvents(run_event_bus, str(run_id), run.started_at)
        events.understanding_query()

        ctx = RunContext(db=db, run_id=run_id, llm=LLMProvider(), events=events)
        graph = build_graph(ctx, get_checkpointer())

        initial_state = {
            "run_id": str(run_id),
            "user_id": str(user_id),
            "query": query,
            "mode": mode,
            "raw_findings": [],
            "evidence": [],
            "figures": [],
            "errors": [],
            "citation_retry_count": 0,
        }

        try:
            await graph.ainvoke(initial_state, config={"configurable": {"thread_id": str(run_id)}})
        except Exception as exc:
            logger.exception("execute_research_run: run %s failed", run_id)
            await db.rollback()
            failed_run = await db.get(ResearchRun, run_id)
            if failed_run is not None:
                failed_run.status = "error"
                failed_run.completed_at = datetime.now(timezone.utc)
                await db.commit()
            # No node in this graph distinguishes a recoverable failure from a
            # fatal one today (a bad domain, a failed search, etc. are caught
            # inside the node and appended to `errors` without raising) — only
            # truly fatal exceptions (including CostCeilingExceeded) reach
            # here, so recoverable is always False.
            events.error(message=str(exc), recoverable=False)
            return

        await _finalize_run(db, run_id)
        await publish_final_stat(ctx)
        events.done(report_url=f"/api/v1/research/{run_id}/report")


async def _finalize_run(db, run_id: uuid.UUID) -> None:
    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(NodeTrace.input_tokens), 0),
                func.coalesce(func.sum(NodeTrace.output_tokens), 0),
                func.coalesce(func.sum(NodeTrace.cost_usd), 0),
            ).where(NodeTrace.run_id == run_id)
        )
    ).one()
    input_tokens, output_tokens, cost_estimate = totals

    run = await db.get(ResearchRun, run_id)
    if run is None:
        return
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.input_tokens = int(input_tokens)
    run.output_tokens = int(output_tokens)
    run.cost_estimate_usd = cost_estimate
    run.latency_seconds = (run.completed_at - run.started_at).total_seconds()
    await db.commit()
