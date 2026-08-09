"""In-process WS event bus for live run streaming (PRD §7.3), with one
deliberate simplification: no Redis Pub/Sub bridge.

# NOTE: PRD §7.3 / Correction #13 marks the Redis Pub/Sub bridge as
# mandatory, but that requirement assumes a Celery worker process executes
# the graph while a separate API process holds the WebSocket. That split
# does not exist yet — the graph runs inside the API process via FastAPI
# BackgroundTasks (see graph/runner.py and graph/checkpointer.py, both of
# which already document "single uvicorn process" as a standing Phase 1/2
# assumption). This module is therefore plain in-process pub/sub:
# module-level state, correct only for a single process/replica. The moment
# a worker process (or multiple uvicorn workers/replicas) is introduced,
# this must be replaced by the Redis-backed bridge from PRD §7.3 — it will
# silently stop delivering events across processes otherwise.
"""

import asyncio
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

FrameType = Literal[
    "snapshot",
    "node_started",
    "node_finished",
    "progress",
    "stat",
    "source_found",
    "contradiction_found",
    "report_chunk",
    "done",
    "error",
]

# Fixed seven-value stage enum (PRD §15.1) — do not add an eighth.
Stage = Literal[
    "understanding_query",
    "creating_plan",
    "searching_sources",
    "extracting_evidence",
    "fact_checking",
    "resolving_conflicts",
    "generating_report",
]

STAGE_ORDER: list[Stage] = [
    "understanding_query",
    "creating_plan",
    "searching_sources",
    "extracting_evidence",
    "fact_checking",
    "resolving_conflicts",
    "generating_report",
]

STAGE_LABELS: dict[Stage, str] = {
    "understanding_query": "Understanding your query",
    "creating_plan": "Creating research plan",
    "searching_sources": "Searching across sources",
    "extracting_evidence": "Extracting key evidence",
    "fact_checking": "Fact checking claims",
    "resolving_conflicts": "Resolving conflicts",
    "generating_report": "Generating report",
}

# Interpretive mapping — the PRD fixes the seven stages but doesn't map every
# graph node onto them 1:1. credibility_scorer and retriever both feed the
# evidence set before verification begins (scoring sources, then hybrid
# retrieval/rerank over them), so they're bundled under "extracting_evidence"
# rather than getting their own row, the same way PRD §7.3 already bundles
# figure generation under "generating_report" to keep the row count at seven.
STAGE_BY_NODE: dict[str, Stage] = {
    "planner": "creating_plan",
    "web_researcher": "searching_sources",
    "evidence_extractor": "extracting_evidence",
    "credibility_scorer": "extracting_evidence",
    "retriever": "extracting_evidence",
    "fact_checker": "fact_checking",
    "contradiction_detector": "resolving_conflicts",
    "synthesizer": "generating_report",
    "citation_validator": "generating_report",
    "force_finalize": "generating_report",
}

QUEUE_MAXSIZE = 1000
STAT_MIN_INTERVAL_SECONDS = 2.0


def make_frame(frame_type: FrameType, run_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": frame_type,
        "run_id": run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


class _RunChannel:
    """Per-run fan-out queues plus a rolling snapshot of the latest known
    state, updated on every publish. This is what lets a freshly (re)connected
    WS client render correctly with no event-replay buffer (PRD §7.3: "no
    event replay buffer needed in v1") — it reads the rolling state once
    instead of replaying history."""

    def __init__(self) -> None:
        self.subscribers: set[asyncio.Queue] = set()
        self.stage: Stage | None = None
        self.stat: dict[str, Any] | None = None
        self.sources: list[dict[str, Any]] = []
        self.contradictions: list[dict[str, Any]] = []
        self.report_text: str = ""
        self.terminal_frame: dict[str, Any] | None = None  # the `done`/`error` frame, once sent


class RunEventBus:
    """Module-level singleton (see the module NOTE above on why that's the
    right scope for now). Bounded, drop-oldest subscriber queues: a stalled
    or dead client must never block graph execution, and dropping the oldest
    queued frame is safe specifically because `_RunChannel`'s rolling
    snapshot means a client that misses frames still recovers correctly on
    its next read (reconnect, or a fresh `snapshot`)."""

    def __init__(self) -> None:
        self._channels: dict[str, _RunChannel] = defaultdict(_RunChannel)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        channel = self._channels[run_id]
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        channel.subscribers.add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        channel = self._channels.get(run_id)
        if channel is not None:
            channel.subscribers.discard(queue)

    def channel_state(self, run_id: str) -> _RunChannel | None:
        """Read-only peek at the rolling snapshot — None if nothing has ever
        published for this run_id (e.g. it hasn't started, or the process
        restarted since it ran)."""
        return self._channels.get(run_id)

    def publish(self, run_id: str, frame_type: FrameType, data: dict[str, Any]) -> dict[str, Any]:
        frame = make_frame(frame_type, run_id, data)
        channel = self._channels[run_id]
        self._update_snapshot(channel, frame_type, data, frame)
        for queue in list(channel.subscribers):
            self._offer(queue, frame)
        return frame

    def _offer(self, queue: asyncio.Queue, frame: dict[str, Any]) -> None:
        try:
            queue.put_nowait(frame)
            return
        except asyncio.QueueFull:
            pass
        # Drop-oldest and retry once. report_chunk frames arrive at token
        # rate, so a client that stops draining (dead tab, closed laptop)
        # would otherwise grow this queue without bound.
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(frame)
        except asyncio.QueueFull:
            pass  # lost a concurrent race with another producer; drop silently

    def _update_snapshot(
        self, channel: _RunChannel, frame_type: FrameType, data: dict[str, Any], frame: dict[str, Any]
    ) -> None:
        if frame_type == "progress":
            channel.stage = data.get("stage")
        elif frame_type == "stat":
            channel.stat = data
        elif frame_type == "source_found":
            channel.sources.append(data)
        elif frame_type == "contradiction_found":
            channel.contradictions.append(data)
        elif frame_type == "report_chunk":
            channel.report_text += data.get("delta", "")
        elif frame_type in ("done", "error"):
            channel.terminal_frame = frame


# Single process-wide instance — every run publishes to and every WS
# connection subscribes from this one bus. See the module NOTE for the
# single-process assumption this relies on.
run_event_bus = RunEventBus()


class RunEvents:
    """Bound to one run_id + the process-wide bus. Threaded into RunContext
    (graph/run_context.py) exactly like `db`/`llm` already are, so node code
    calls `ctx.events.source_found(...)` etc. without knowing about the bus."""

    def __init__(self, bus: RunEventBus, run_id: str, run_started_at: datetime) -> None:
        self.bus = bus
        self.run_id = run_id
        self.run_started_at = run_started_at
        self._last_stat_at = 0.0

    def understanding_query(self) -> None:
        """Synthetic first stage — no graph node maps to it (see
        STAGE_BY_NODE's docstring). Emitted once by runner.py right after the
        run's status flips to "running", before the graph starts."""
        self.bus.publish(
            self.run_id,
            "progress",
            {"stage": "understanding_query", "label": STAGE_LABELS["understanding_query"], "current": 1, "total": len(STAGE_ORDER)},
        )

    def node_started(self, node: str) -> None:
        self.bus.publish(self.run_id, "node_started", {"node": node})
        stage = STAGE_BY_NODE.get(node)
        if stage is None:
            return
        channel = self.bus.channel_state(self.run_id)
        if channel is not None and channel.stage == stage:
            return  # unchanged from the previous node — no duplicate progress row
        idx = STAGE_ORDER.index(stage) + 1
        self.bus.publish(
            self.run_id, "progress", {"stage": stage, "label": STAGE_LABELS[stage], "current": idx, "total": len(STAGE_ORDER)}
        )

    def node_finished(self, node: str, latency_ms: int, cost_usd: float) -> None:
        self.bus.publish(self.run_id, "node_finished", {"node": node, "latency_ms": latency_ms, "cost_usd": cost_usd})

    def estimate_eta_seconds(self) -> float | None:
        """Honest, cheap heuristic — a linear projection from elapsed time
        vs. stage progress so far, not a trained estimator. None until the
        first stage transition has happened (nothing to project from yet)."""
        channel = self.bus.channel_state(self.run_id)
        stage = channel.stage if channel else None
        if stage is None:
            return None
        stage_idx = STAGE_ORDER.index(stage) + 1
        if stage_idx >= len(STAGE_ORDER):
            return 0.0
        elapsed = (datetime.now(timezone.utc) - self.run_started_at).total_seconds()
        if elapsed <= 0:
            return None
        remaining_stages = len(STAGE_ORDER) - stage_idx
        return round(elapsed * remaining_stages / stage_idx, 1)

    def stat(
        self,
        *,
        sources: int,
        evidence_items: int,
        claims_verified: int,
        conflicts: int,
        eta_seconds: float | None,
        force: bool = False,
    ) -> None:
        """Throttled to at most once every STAT_MIN_INTERVAL_SECONDS of
        wall-clock time per run, independent of node count, so this doesn't
        become a spam/cost problem if the graph grows more nodes later.
        `force=True` bypasses the throttle for the final stat before `done`."""
        now = time.monotonic()
        if not force and (now - self._last_stat_at) < STAT_MIN_INTERVAL_SECONDS:
            return
        self._last_stat_at = now
        self.bus.publish(
            self.run_id,
            "stat",
            {
                "sources": sources,
                "evidence_items": evidence_items,
                "claims_verified": claims_verified,
                "conflicts": conflicts,
                "eta_seconds": eta_seconds,
            },
        )

    def source_found(self, *, source_id: str, title: str, domain: str, source_type: str, credibility_score: float) -> None:
        self.bus.publish(
            self.run_id,
            "source_found",
            {"source_id": source_id, "title": title, "domain": domain, "source_type": source_type, "credibility_score": credibility_score},
        )

    def contradiction_found(self, *, topic: str, evidence_a_id: str, evidence_b_id: str) -> None:
        self.bus.publish(
            self.run_id, "contradiction_found", {"topic": topic, "evidence_a_id": evidence_a_id, "evidence_b_id": evidence_b_id}
        )

    def report_chunk(self, delta: str) -> None:
        self.bus.publish(self.run_id, "report_chunk", {"delta": delta})

    def done(self, report_url: str) -> None:
        self.bus.publish(self.run_id, "done", {"report_url": report_url})

    def error(self, message: str, recoverable: bool = False) -> None:
        self.bus.publish(self.run_id, "error", {"message": message, "recoverable": recoverable})
