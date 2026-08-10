import logging
import uuid

from app.config import get_settings
from app.figures.storage import store_png
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Figure as FigureRow
from app.models.schemas import Figure, ImagePrompt, IllustrationRequest
from app.observability.tracer import estimate_cost, traced

settings = get_settings()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("image_prompt_writer.md")

AI_GENERATED_NOTE = "AI-generated illustration — not derived from evidence"


async def _generate_one(ctx: RunContext, request: IllustrationRequest) -> tuple[Figure | None, int, int, str | None, float]:
    """Returns (figure, prompt_call_input_tokens, prompt_call_output_tokens,
    prompt_call_model, image_cost_usd) — the image generation call itself is
    flat-priced (settings.IMAGE_COST_PER_IMAGE_USD), not token-based, so it's
    tracked separately from the prompt-writing call's token cost."""
    user_prompt = f"Intent: {request.intent}\nCaption: {request.caption}"
    try:
        response = await ctx.llm.generate_structured(
            "image_prompt", system=SYSTEM_PROMPT, user=user_prompt, schema=ImagePrompt
        )
    except Exception as exc:
        logger.warning("image_generator[%s]: image_prompt call failed: %s", ctx.run_id, exc)
        return None, 0, 0, None, 0.0

    image_prompt = response.parsed
    try:
        png_bytes = await ctx.llm.generate_image(image_prompt.prompt)
    except Exception as exc:
        logger.warning("image_generator[%s]: image generation failed for %r: %s", ctx.run_id, image_prompt.caption, exc)
        return None, response.input_tokens, response.output_tokens, response.model, 0.0

    file_path = store_png(str(ctx.run_id), png_bytes)
    figure = Figure(
        id=str(uuid.uuid4()),
        kind="illustration",
        # Deliberately no disclaimer baked in here — "AI-generated, not
        # derived from evidence" is a rendering concern applied by every
        # surface that displays kind="illustration" (ReportFigure.tsx,
        # html_renderer.py's PDF inlining), not stored content. Keeping
        # caption/alt_text clean means it stays correct if this figure is
        # ever surfaced somewhere new without having to strip a suffix back
        # out.
        caption=image_prompt.caption,
        alt_text=image_prompt.caption,
        file_path=file_path,
        mime_type="image/png",
        spec=None,
        evidence_ids=request.evidence_ids,
        source_id=None,
        license_note=AI_GENERATED_NOTE,
    )
    return figure, response.input_tokens, response.output_tokens, response.model, settings.IMAGE_COST_PER_IMAGE_USD


@traced("image_generator")
async def image_generator_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """One image_prompt call + one image generation call per accepted
    illustration request (sequential, matching every other figure-producing
    node in this codebase). A rejected or failed illustration is dropped and
    logged, never aborts the run."""
    requests: list[IllustrationRequest] = state.get("illustration_requests") or []

    if not requests:
        return NodeResult(state_update={"figures": []}, trace_input={"note": "no illustration requests"})

    figures: list[Figure] = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    failed = 0

    for request in requests:
        figure, in_tokens, out_tokens, model, image_cost = await _generate_one(ctx, request)
        total_input += in_tokens
        total_output += out_tokens
        if model:
            total_cost += estimate_cost(model, in_tokens, out_tokens)
        total_cost += image_cost
        if figure is None:
            failed += 1
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
        trace_input={"requested": len(requests), "generated": len(figures), "failed": failed},
    )
