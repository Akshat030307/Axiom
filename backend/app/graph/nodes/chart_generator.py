import logging
import uuid

from app.figures.chart_renderer import render_chart_png
from app.figures.storage import store_png
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Figure as FigureRow
from app.models.schemas import ChartSpec, Evidence, Figure, FigureRequest
from app.observability.tracer import estimate_cost, traced

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("chart_generator.md")

# Relative tolerance on top of an absolute floor -- generous enough to survive
# a model re-stating "45.0" as "45", not generous enough to let a fabricated
# nearby number slip through.
_ABS_TOLERANCE = 1e-6
_REL_TOLERANCE = 1e-6


def _format_evidence_for_request(evidence_by_id: dict[str, Evidence], evidence_ids: list[str]) -> str:
    lines = []
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        lines.append(
            f"[{ev.id}] {ev.claim}\n"
            f"    numeric_value={ev.numeric_value} numeric_unit={ev.numeric_unit} time_period={ev.time_period}"
        )
    return "\n".join(lines)


def _values_are_grounded(spec: ChartSpec, evidence_by_id: dict[str, Evidence]) -> bool:
    """PRD §11.1: 'the validator rejects any spec whose values don't appear
    in the referenced evidence.' The real security/integrity boundary — the
    model is never trusted to have followed the prompt's no-invention rule
    on its own; every plotted number must trace back to a real
    Evidence.numeric_value from one of the spec's own cited evidence_ids."""
    available = {
        ev.numeric_value
        for eid in spec.evidence_ids
        if (ev := evidence_by_id.get(eid)) is not None and ev.numeric_value is not None
    }
    if not available:
        return False
    for series in spec.series:
        for value in series.values:
            if not any(abs(value - v) <= max(_ABS_TOLERANCE, abs(v) * _REL_TOLERANCE) for v in available):
                return False
    return True


async def _generate_one(
    ctx: RunContext, request: FigureRequest, evidence_by_id: dict[str, Evidence]
) -> tuple[Figure | None, int, int, str | None]:
    user_prompt = (
        f"Intent: {request.intent}\n"
        f"Caption: {request.caption}\n\n"
        f"Evidence:\n{_format_evidence_for_request(evidence_by_id, request.evidence_ids)}"
    )
    try:
        response = await ctx.llm.generate_structured(
            "chart_spec", system=SYSTEM_PROMPT, user=user_prompt, schema=ChartSpec
        )
    except Exception as exc:
        logger.warning("chart_generator[%s]: chart_spec call failed: %s", ctx.run_id, exc)
        return None, 0, 0, None

    spec = response.parsed
    if not _values_are_grounded(spec, evidence_by_id):
        logger.warning(
            "chart_generator[%s]: rejected spec %r — contains a value not present in its referenced evidence",
            ctx.run_id,
            spec.title,
        )
        return None, response.input_tokens, response.output_tokens, response.model

    try:
        png_bytes = render_chart_png(spec)
    except Exception as exc:
        logger.warning("chart_generator[%s]: matplotlib rendering failed for %r: %s", ctx.run_id, spec.title, exc)
        return None, response.input_tokens, response.output_tokens, response.model

    file_path = store_png(str(ctx.run_id), png_bytes)
    figure = Figure(
        id=str(uuid.uuid4()),
        kind="chart",
        caption=request.caption,
        alt_text=spec.title,
        file_path=file_path,
        mime_type="image/png",
        spec=spec.model_dump(),
        evidence_ids=spec.evidence_ids,
        source_id=None,
        license_note=None,
    )
    return figure, response.input_tokens, response.output_tokens, response.model


@traced("chart_generator")
async def chart_generator_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """One fast-tier call per figure request (sequential, not Send()-based
    fan-out — matching every other node in this codebase, see
    web_researcher.py's docstring on the same simplification). A rejected or
    failed figure is dropped, logged, and does not abort the run; the
    synthesizer only ever sees figures that made it into `figures`."""
    requests: list[FigureRequest] = state.get("figure_requests") or []
    evidence: list[Evidence] = state.get("retrieved_evidence") or []
    evidence_by_id = {ev.id: ev for ev in evidence}

    if not requests:
        return NodeResult(state_update={"figures": []}, trace_input={"note": "no figure requests"})

    figures: list[Figure] = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    rejected = 0

    for request in requests:
        figure, in_tokens, out_tokens, model = await _generate_one(ctx, request, evidence_by_id)
        total_input += in_tokens
        total_output += out_tokens
        if model:
            total_cost += estimate_cost(model, in_tokens, out_tokens)
        if figure is None:
            rejected += 1
            continue

        figures.append(figure)
        ctx.db.add(
            FigureRow(
                id=uuid.UUID(figure.id),
                run_id=ctx.run_id,
                kind=figure.kind,
                caption=figure.caption,
                alt_text=figure.alt_text,
                file_path=figure.file_path,
                mime_type=figure.mime_type,
                spec=figure.spec,
                evidence_ids=[uuid.UUID(eid) for eid in figure.evidence_ids],
                source_id=None,
                license_note=figure.license_note,
            )
        )

    return NodeResult(
        state_update={"figures": figures},
        input_tokens=total_input,
        output_tokens=total_output,
        cost_override=total_cost,
        trace_input={"requested": len(requests), "generated": len(figures), "rejected": rejected},
    )
