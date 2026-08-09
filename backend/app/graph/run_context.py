import itertools
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.provider import LLMProvider


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
    """

    db: AsyncSession
    run_id: uuid.UUID
    llm: LLMProvider
    _seq: itertools.count = field(default_factory=lambda: itertools.count(1))

    def next_seq(self) -> int:
        return next(self._seq)


@dataclass
class NodeResult:
    """What a node's business-logic function returns to the @traced wrapper —
    the LangGraph-visible state update, plus token/model bookkeeping the tracer
    needs but that must never itself become part of ResearchState."""

    state_update: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None
