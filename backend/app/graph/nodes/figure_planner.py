import logging

from pydantic import BaseModel

from app.config import get_settings
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.schemas import Evidence, FigureRequest
from app.observability.tracer import traced

settings = get_settings()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("figure_planner.md")


class _FigurePlan(BaseModel):
    figures: list[FigureRequest]


def _format_evidence_list(evidence: list[Evidence]) -> str:
    lines = []
    for ev in evidence:
        quant = ""
        if ev.numeric_value is not None:
            quant = f" | numeric_value={ev.numeric_value} numeric_unit={ev.numeric_unit or '?'} time_period={ev.time_period or '?'}"
        lines.append(f"[{ev.id}] {ev.claim}{quant}")
    return "\n".join(lines) if lines else "(no evidence)"


@traced("figure_planner")
async def figure_planner_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """Reasoning-tier, structured -> list[FigureRequest] (PRD §8), capped by
    MAX_FIGURES_PER_REPORT. Every evidence_id the model cites is checked
    against the actual retrieved-evidence set before being trusted forward
    to chart_generator — an invented id there would otherwise surface much
    later as a confusing KeyError instead of a clean, logged drop here."""
    plan = state["plan"]
    evidence = state.get("retrieved_evidence") or []
    valid_ids = {ev.id for ev in evidence}

    if not evidence:
        return NodeResult(state_update={"figure_requests": []}, trace_input={"note": "no retrieved evidence"})

    user_prompt = (
        f"Research objective: {plan.objective}\n"
        f"Sub-questions expected to need a figure: {', '.join(plan.expected_figures) or '(none specified)'}\n\n"
        f"Evidence:\n{_format_evidence_list(evidence)}"
    )

    try:
        response = await ctx.llm.generate_structured(
            "figure_planning", system=SYSTEM_PROMPT, user=user_prompt, schema=_FigurePlan
        )
    except Exception as exc:
        logger.warning("figure_planner[%s]: planning call failed, proceeding with zero figures: %s", ctx.run_id, exc)
        return NodeResult(state_update={"figure_requests": []}, trace_input={"error": str(exc)})

    accepted: list[FigureRequest] = []
    dropped_bad_ids = 0
    for req in response.parsed.figures:
        bad_ids = [eid for eid in req.evidence_ids if eid not in valid_ids]
        if bad_ids:
            logger.warning(
                "figure_planner[%s]: dropping figure request citing unknown evidence id(s): %s", ctx.run_id, bad_ids
            )
            dropped_bad_ids += 1
            continue
        if len(req.evidence_ids) < 2:
            continue
        accepted.append(req)
        if len(accepted) >= settings.MAX_FIGURES_PER_REPORT:
            break

    return NodeResult(
        state_update={"figure_requests": accepted},
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        model=response.model,
        trace_input={
            "requested": len(response.parsed.figures),
            "accepted": len(accepted),
            "dropped_unknown_evidence_ids": dropped_bad_ids,
        },
    )
