import logging
import uuid

from app.figures.diagram_renderer import DiagramValidationError, render_diagram_svg
from app.figures.storage import store_image
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Figure as FigureRow
from app.models.schemas import DiagramSpec, Evidence, Figure, FigureRequest
from app.observability.tracer import estimate_cost, traced

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("diagram_generator.md")


def _format_evidence_for_request(evidence_by_id: dict[str, Evidence], evidence_ids: list[str]) -> str:
    lines = []
    for eid in evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            continue
        lines.append(f"[{ev.id}] {ev.claim}")
    return "\n".join(lines)


async def _generate_one(
    ctx: RunContext, request: FigureRequest, evidence_by_id: dict[str, Evidence]
) -> tuple[Figure | None, int, int, str | None]:
    user_prompt = (
        f"Intent: {request.intent}\n"
        f"Caption: {request.caption}\n\n"
        f"Evidence (attribution only — depict the real structure from what you already know):\n"
        f"{_format_evidence_for_request(evidence_by_id, request.evidence_ids)}"
    )
    try:
        response = await ctx.llm.generate_structured(
            "diagram_spec", system=SYSTEM_PROMPT, user=user_prompt, schema=DiagramSpec
        )
    except Exception as exc:
        logger.warning("diagram_generator[%s]: diagram_spec call failed: %s", ctx.run_id, exc)
        return None, 0, 0, None

    spec = response.parsed
    try:
        svg_bytes = render_diagram_svg(spec)
    except DiagramValidationError as exc:
        logger.warning("diagram_generator[%s]: rejected spec %r — %s", ctx.run_id, spec.title, exc)
        return None, response.input_tokens, response.output_tokens, response.model
    except Exception as exc:
        logger.warning("diagram_generator[%s]: mmdc rendering failed for %r: %s", ctx.run_id, spec.title, exc)
        return None, response.input_tokens, response.output_tokens, response.model

    file_path = store_image(str(ctx.run_id), svg_bytes, "svg")
    figure = Figure(
        id=str(uuid.uuid4()),
        kind="diagram",
        caption=request.caption,
        alt_text=spec.title,
        file_path=file_path,
        mime_type="image/svg+xml",
        spec=spec.model_dump(),
        evidence_ids=spec.evidence_ids,
        source_id=None,
        license_note=None,
    )
    return figure, response.input_tokens, response.output_tokens, response.model


@traced("diagram_generator")
async def diagram_generator_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """One fast-tier call per `kind="diagram"` figure request (sequential,
    matching every other figure-producing node). A rejected or failed
    diagram is dropped and logged, never aborts the run — the synthesizer
    only ever sees figures that made it into `figures`."""
    requests = [r for r in (state.get("figure_requests") or []) if r.kind == "diagram"]
    evidence: list[Evidence] = state.get("retrieved_evidence") or []
    evidence_by_id = {ev.id: ev for ev in evidence}

    if not requests:
        return NodeResult(state_update={"figures": []}, trace_input={"note": "no diagram requests"})

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
