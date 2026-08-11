import logging
import uuid
from urllib.parse import urlparse

from app.config import get_settings
from app.figures.image_fetcher import fetch_and_validate_image
from app.figures.storage import store_image
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Figure as FigureRow
from app.models.schemas import Figure
from app.observability.tracer import traced
from app.tools.web_search import search_images

settings = get_settings()
logger = logging.getLogger(__name__)


def _domain_of(url: str) -> str:
    return urlparse(url).hostname or "web"


async def _fetch_one(ctx: RunContext, illustration: Figure) -> Figure | None:
    """Tries up to WEB_IMAGE_SEARCH_CANDIDATES Tavily image results, in
    ranked order, for the illustration's caption — returns the first one
    that passes SSRF + content-type + dimension validation, or None if none
    do (or the search itself fails). Non-fatal either way: the illustration
    stands alone without a paired photo."""
    try:
        candidates = await search_images(illustration.caption, max_results=settings.WEB_IMAGE_SEARCH_CANDIDATES)
    except Exception as exc:
        logger.warning(
            "web_image_fetcher[%s]: image search failed for %r: %s", ctx.run_id, illustration.caption, exc
        )
        return None

    for candidate in candidates:
        url = candidate.get("url")
        if not url:
            continue
        result = await fetch_and_validate_image(url)
        if result is None:
            continue
        data, content_type, ext = result
        file_path = store_image(str(ctx.run_id), data, ext)
        return Figure(
            id=str(uuid.uuid4()),
            kind="source_image",
            caption=illustration.caption,
            alt_text=candidate.get("description") or illustration.caption,
            file_path=file_path,
            mime_type=content_type,
            spec=None,
            evidence_ids=illustration.evidence_ids,
            source_id=None,
            license_note=f"Photo via {_domain_of(url)}",
            paired_figure_id=illustration.id,
        )
    return None


@traced("web_image_fetcher")
async def web_image_fetcher_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """For every AI illustration image_generator produced this run, finds a
    real, relevant photo via Tavily image search and pairs it (kind=
    "source_image", paired_figure_id=<illustration id>) so the frontend can
    render both together at a similar size. Excluded from the figure list
    synthesizer sees (see synthesizer.py's _format_figure_list) — the
    illustration's own figure:// marker is enough; the paired photo renders
    automatically alongside it rather than needing its own marker the model
    might place somewhere unrelated or skip entirely."""
    illustrations = [f for f in state.get("figures") or [] if f.kind == "illustration"]

    if not illustrations:
        return NodeResult(state_update={"figures": []}, trace_input={"note": "no illustrations to pair"})

    figures: list[Figure] = []
    failed = 0
    for illustration in illustrations:
        figure = await _fetch_one(ctx, illustration)
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
                paired_figure_id=uuid.UUID(figure.paired_figure_id),
            )
        )

    return NodeResult(
        state_update={"figures": figures},
        trace_input={"illustrations": len(illustrations), "paired": len(figures), "failed": failed},
    )
