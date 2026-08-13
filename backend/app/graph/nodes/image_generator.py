import logging
import uuid
from urllib.parse import urlparse

from app.config import get_settings
from app.figures.image_fetcher import fetch_and_validate_image
from app.figures.storage import store_image
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Figure as FigureRow
from app.models.schemas import DiagramSearchQuery, Figure, IllustrationRequest
from app.observability.tracer import estimate_cost, traced
from app.tools.web_search import search_commons_images

settings = get_settings()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("diagram_search_writer.md")


def _domain_of(url: str) -> str:
    return urlparse(url).hostname or "Wikimedia Commons"


async def _find_one(ctx: RunContext, request: IllustrationRequest) -> tuple[Figure | None, int, int, str | None]:
    """Returns (figure, prompt_call_input_tokens, prompt_call_output_tokens,
    prompt_call_model). No per-image generation cost anymore — this finds
    and downloads a real, existing diagram instead of generating pixels, so
    the only LLM spend left is the small search-query-writing call."""
    user_prompt = f"Intent: {request.intent}\nCaption: {request.caption}"
    try:
        response = await ctx.llm.generate_structured(
            "image_prompt", system=SYSTEM_PROMPT, user=user_prompt, schema=DiagramSearchQuery
        )
    except Exception as exc:
        logger.warning("image_generator[%s]: search query call failed: %s", ctx.run_id, exc)
        return None, 0, 0, None

    query = response.parsed
    try:
        candidates = await search_commons_images(query.query, max_results=settings.WEB_IMAGE_SEARCH_CANDIDATES)
    except Exception as exc:
        logger.warning("image_generator[%s]: Commons search failed for %r: %s", ctx.run_id, query.query, exc)
        return None, response.input_tokens, response.output_tokens, response.model

    for candidate in candidates:
        url = candidate.get("url")
        if not url:
            continue
        result = await fetch_and_validate_image(url)
        if result is None:
            continue
        data, content_type, ext = result
        file_path = store_image(str(ctx.run_id), data, ext)
        license_note = (
            f"Diagram via Wikimedia Commons ({candidate['license']})"
            if candidate.get("license")
            else f"Diagram via {_domain_of(url)}"
        )
        figure = Figure(
            id=str(uuid.uuid4()),
            kind="reference_diagram",
            caption=query.caption,
            alt_text=candidate.get("description") or query.caption,
            file_path=file_path,
            mime_type=content_type,
            spec=None,
            evidence_ids=request.evidence_ids,
            source_id=None,
            license_note=license_note,
        )
        return figure, response.input_tokens, response.output_tokens, response.model

    return None, response.input_tokens, response.output_tokens, response.model


@traced("image_generator")
async def image_generator_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """One search-query-writing call + one Wikimedia Commons search (trying
    up to WEB_IMAGE_SEARCH_CANDIDATES results, in ranked order) per accepted
    illustration request — finds a real, existing diagram instead of
    generating one (sequential, matching every other figure-producing node
    in this codebase). A rejected or failed request is dropped and logged,
    never aborts the run."""
    requests: list[IllustrationRequest] = state.get("illustration_requests") or []

    if not requests:
        return NodeResult(state_update={"figures": []}, trace_input={"note": "no illustration requests"})

    figures: list[Figure] = []
    total_input = 0
    total_output = 0
    total_cost = 0.0
    failed = 0

    for request in requests:
        figure, in_tokens, out_tokens, model = await _find_one(ctx, request)
        total_input += in_tokens
        total_output += out_tokens
        if model:
            total_cost += estimate_cost(model, in_tokens, out_tokens)
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
        trace_input={"requested": len(requests), "found": len(figures), "failed": failed},
    )
