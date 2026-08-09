import itertools
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.provider import LLMProvider
from app.observability.events import RunEvents


@dataclass
class RunContext:
    """Per-run dependencies, created once by the background task that executes
    the graph and threaded into every node as a plain function argument (not
    LangGraph state — state is data, this is runtime wiring).

    `db` is a single AsyncSession opened by the background task and owned for
    the entire run (Phase 1's graph is strictly sequential, so one session has
    no concurrent-access hazard). It must never be a request-scoped session —
    that one is closed the moment the HTTP response is sent, before the graph
    has done any work.

    `events` is the run's handle onto the process-wide WS event bus (Phase 3
    §7.3, app/observability/events.py) — nodes call `ctx.events.source_found(...)`
    etc. directly rather than going through a separate worker/broker.
    """

    db: AsyncSession
    run_id: uuid.UUID
    llm: LLMProvider
    events: RunEvents
    _seq: itertools.count = field(default_factory=lambda: itertools.count(1))

    def next_seq(self) -> int:
        return next(self._seq)


@dataclass
class NodeResult:
    """What a node's business-logic function returns to the @traced wrapper —
    the LangGraph-visible state update, plus token/model bookkeeping the tracer
    needs but that must never itself become part of ResearchState.

    `cost_override`: for nodes that call more than one priced model in a
    single execution (e.g. contradiction_detector's fast-tier scan + reasoning
    -tier explanation, or retriever's embedding + fast-tier rerank calls) —
    `input_tokens`/`output_tokens`/`model` can only represent one model's
    pricing, so the node sums its own per-call costs and hands the tracer the
    total directly instead of letting it (mis)compute one from a single model.

    `trace_input`: written verbatim into node_traces.input (a column no
    Phase-1 node ever populated). Retrieval nodes use this for per-stage
    candidate counts (§10) so reranker_effectiveness is measurable later;
    any node can use it for diagnostics that don't belong in ResearchState.
    """

    state_update: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None
    cost_override: float | None = None
    trace_input: dict[str, Any] | None = None
