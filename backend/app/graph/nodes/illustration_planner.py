import logging

from pydantic import BaseModel

from app.config import get_settings
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.schemas import Evidence, IllustrationRequest
from app.observability.tracer import traced

settings = get_settings()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("illustration_planner.md")


class _IllustrationPlan(BaseModel):
    illustrations: list[IllustrationRequest]


def _format_evidence_list(evidence: list[Evidence]) -> str:
    return "\n".join(f"[{ev.id}] {ev.claim}" for ev in evidence) if evidence else "(no evidence)"


@traced("illustration_planner")
async def illustration_planner_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """Reasoning-tier, structured -> list[IllustrationRequest], capped by
    MAX_ILLUSTRATIONS_PER_REPORT (deliberately much lower than
    MAX_FIGURES_PER_REPORT — see config.py). Every cited evidence_id is
    checked against the actual retrieved-evidence set, same defensive
    pattern as figure_planner, even though illustrations only use these ids
    for attribution rather than grounding."""
    plan = state["plan"]
    evidence = state.get("retrieved_evidence") or []
    valid_ids = {ev.id for ev in evidence}

    if not evidence:
        return NodeResult(state_update={"illustration_requests": []}, trace_input={"note": "no retrieved evidence"})

    user_prompt = (
        f"Research objective: {plan.objective}\n\n"
        f"Evidence (for attribution only):\n{_format_evidence_list(evidence)}"
    )

    try:
        response = await ctx.llm.generate_structured(
            "illustration_planning", system=SYSTEM_PROMPT, user=user_prompt, schema=_IllustrationPlan
        )
    except Exception as exc:
        logger.warning("illustration_planner[%s]: planning call failed, proceeding with zero illustrations: %s", ctx.run_id, exc)
        return NodeResult(state_update={"illustration_requests": []}, trace_input={"error": str(exc)})

    accepted: list[IllustrationRequest] = []
    dropped_bad_ids = 0
    for req in response.parsed.illustrations:
        bad_ids = [eid for eid in req.evidence_ids if eid not in valid_ids]
        if bad_ids:
            logger.warning(
                "illustration_planner[%s]: dropping request citing unknown evidence id(s): %s", ctx.run_id, bad_ids
            )
            dropped_bad_ids += 1
            continue
        if not req.evidence_ids:
            # figures.evidence_ids has a DB CheckConstraint requiring at
            # least one id (figure_must_be_attributed) — drop here rather
            # than let image_generator's INSERT fail later.
            dropped_bad_ids += 1
            continue
        accepted.append(req)
        if len(accepted) >= settings.MAX_ILLUSTRATIONS_PER_REPORT:
            break

    return NodeResult(
        state_update={"illustration_requests": accepted},
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        model=response.model,
        trace_input={
            "requested": len(response.parsed.illustrations),
            "accepted": len(accepted),
            "dropped_unknown_evidence_ids": dropped_bad_ids,
        },
    )
