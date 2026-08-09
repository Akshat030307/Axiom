import functools
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select

from app.config import build_pricing, get_settings
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import NodeTrace

settings = get_settings()
PRICING = build_pricing(settings)

MAX_SNAPSHOT_CHARS = 4000

NodeFn = Callable[[ResearchState, RunContext], Awaitable[NodeResult]]


class CostCeilingExceeded(RuntimeError):
    pass


def _truncate(value: Any) -> Any:
    try:
        s = json.dumps(value, default=str)
    except TypeError:
        s = str(value)
    if len(s) > MAX_SNAPSHOT_CHARS:
        s = s[:MAX_SNAPSHOT_CHARS] + "...<truncated>"
    return s


def estimate_cost(model: str | None, input_tokens: int, output_tokens: int) -> float:
    if model is None:
        return 0.0
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    return input_tokens * rates["input"] + output_tokens * rates["output"]


async def _run_cost_so_far(ctx: RunContext) -> float:
    total = await ctx.db.scalar(
        select(func.coalesce(func.sum(NodeTrace.cost_usd), 0)).where(NodeTrace.run_id == ctx.run_id)
    )
    return float(total or 0)


def traced(node_name: str) -> Callable[[NodeFn], Callable[[ResearchState, RunContext], Awaitable[dict]]]:
    """Wraps a node's business logic (state, ctx) -> NodeResult. Handles:
    - cost-ceiling enforcement before the node runs (Correction #12 — must not
      reintroduce the "ceiling defined but never enforced" bug), at per-node
      granularity (checked once before each node, not before every internal
      LLM call — Phase 1's nodes make at most a couple of calls each, so this
      is a fine enough grain not to overspend the ceiling meaningfully)
    - node_traces persistence: seq, timing, tokens, cost, status/error
    - returning a plain state-update dict, the shape LangGraph expects
    """

    def decorator(fn: NodeFn) -> Callable[[ResearchState, RunContext], Awaitable[dict]]:
        @functools.wraps(fn)
        async def wrapper(state: ResearchState, ctx: RunContext) -> dict:
            seq = ctx.next_seq()
            started_at = datetime.now(timezone.utc)
            t0 = time.monotonic()

            cost_so_far = await _run_cost_so_far(ctx)
            if cost_so_far >= settings.MAX_RUN_COST_USD:
                trace = NodeTrace(
                    id=uuid.uuid4(),
                    run_id=ctx.run_id,
                    node_name=node_name,
                    seq=seq,
                    status="error",
                    error=f"MAX_RUN_COST_USD ({settings.MAX_RUN_COST_USD}) exceeded before this node ran",
                    started_at=started_at,
                    ended_at=datetime.now(timezone.utc),
                )
                ctx.db.add(trace)
                await ctx.db.commit()
                raise CostCeilingExceeded(f"run {ctx.run_id} exceeded MAX_RUN_COST_USD before node {node_name}")

            status = "ok"
            error_text: str | None = None
            result = NodeResult(state_update={})
            try:
                result = await fn(state, ctx)
                return result.state_update
            except Exception as exc:
                status = "error"
                error_text = str(exc)
                raise
            finally:
                latency_ms = int((time.monotonic() - t0) * 1000)
                cost = (
                    result.cost_override
                    if result.cost_override is not None
                    else estimate_cost(result.model, result.input_tokens, result.output_tokens)
                )
                ctx.db.add(
                    NodeTrace(
                        id=uuid.uuid4(),
                        run_id=ctx.run_id,
                        node_name=node_name,
                        seq=seq,
                        input=_truncate(result.trace_input) if result.trace_input else None,
                        output=_truncate(result.state_update) if status == "ok" else None,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        latency_ms=latency_ms,
                        cost_usd=cost,
                        status=status,
                        error=error_text,
                        started_at=started_at,
                        ended_at=datetime.now(timezone.utc),
                    )
                )
                await ctx.db.commit()

        return wrapper

    return decorator
