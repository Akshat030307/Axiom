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


async def _fetch_one(ctx: RunContext, diagram: Figure) -> Figure | None:
    """Tries up to WEB_IMAGE_SEARCH_CANDIDATES Tavily image results, in
    ranked order, for the diagram's caption — returns the first one that
    passes SSRF + content-type + dimension validation, or None if none do
    (or the search itself fails). Non-fatal either way: the diagram stands
    alone without a paired photo."""
    try:
        candidates = await search_images(diagram.caption, max_results=settings.WEB_IMAGE_SEARCH_CANDIDATES)
    except Exception as exc:
        logger.warning(
            "web_image_fetcher[%s]: image search failed for %r: %s", ctx.run_id, diagram.caption, exc
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
            caption=diagram.caption,
            alt_text=candidate.get("description") or diagram.caption,
            file_path=file_path,
            mime_type=content_type,
            spec=None,
            evidence_ids=diagram.evidence_ids,
            source_id=None,
            license_note=f"Photo via {_domain_of(url)}",
            paired_figure_id=diagram.id,
        )
    return None


@traced("web_image_fetcher")
async def web_image_fetcher_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """For every real reference diagram image_generator found this run,
    finds a real, relevant photo via Tavily image search and pairs it (kind=
    "source_image", paired_figure_id=<diagram id>) so the frontend can
    render both together — e.g. a real photo of a battery pack next to a
    real cross-section diagram of its internals. Excluded from the figure
    list synthesizer sees (see synthesizer.py's _format_figure_list) — the
    diagram's own figure:// marker is enough; the paired photo renders
    automatically alongside it rather than needing its own marker the model
    might place somewhere unrelated or skip entirely."""
    diagrams = [f for f in state.get("figures") or [] if f.kind == "reference_diagram"]

    if not diagrams:
        return NodeResult(state_update={"figures": []}, trace_input={"note": "no diagrams to pair"})

    figures: list[Figure] = []
    failed = 0
    for diagram in diagrams:
        figure = await _fetch_one(ctx, diagram)
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
        trace_input={"diagrams": len(diagrams), "paired": len(figures), "failed": failed},
    )
