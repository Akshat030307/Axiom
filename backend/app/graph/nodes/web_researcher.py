import uuid
from urllib.parse import urlparse

from app.config import get_settings
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.guardrails.sanitize import sanitize_text, wrap_fetched_content
from app.models.db_models import Source
from app.observability.tracer import traced
from app.tools.web_fetch import fetch_clean_text
from app.tools.web_search import search

settings = get_settings()

RESULTS_PER_SUBQUESTION = 3
# No credibility/scorer.py until Phase 2 — neutral placeholder for every source.
DEFAULT_CREDIBILITY = 0.5


@traced("web_researcher")
async def web_researcher_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """Single sequential node covering every sub-question (Phase 1 scope: one
    web researcher, no Send()-based fan-out across sub-questions/agent types —
    that's the Phase 3 'parallel execution' roadmap item). Bounded by
    MAX_TOOL_CALLS_PER_NODE; a failed search or an unfetchable page appends to
    `errors` and the loop continues rather than aborting the run."""
    plan = state["plan"]
    raw_findings: list[dict] = []
    errors: list[str] = []
    seen_urls: set[str] = set()
    tool_calls_used = 0

    for sub_question in plan.sub_questions:
        if tool_calls_used >= settings.MAX_TOOL_CALLS_PER_NODE:
            errors.append("web_researcher: MAX_TOOL_CALLS_PER_NODE reached, remaining sub-questions skipped")
            break

        try:
            results = await search(sub_question, max_results=RESULTS_PER_SUBQUESTION)
        except Exception as exc:
            errors.append(f"web_researcher: search failed for '{sub_question}': {exc}")
            tool_calls_used += 1
            continue
        tool_calls_used += 1

        for result in results:
            url = result.get("url")
            if not url or url in seen_urls:
                continue

            text = result.get("raw_content") or result.get("content")
            text = sanitize_text(text) if text else None

            if not text and tool_calls_used < settings.MAX_TOOL_CALLS_PER_NODE:
                tool_calls_used += 1
                text = await fetch_clean_text(url)

            if not text:
                errors.append(f"web_researcher: no extractable content from {url}")
                continue

            seen_urls.add(url)
            source_id = uuid.uuid4()
            ctx.db.add(
                Source(
                    id=source_id,
                    run_id=ctx.run_id,
                    url=url,
                    title=result.get("title") or url,
                    domain=urlparse(url).netloc,
                    source_type="web",
                    publication_date=result.get("published_date"),
                    credibility_score=DEFAULT_CREDIBILITY,
                )
            )

            raw_findings.append(
                {
                    "source_id": str(source_id),
                    "topic": sub_question,
                    "fetched_content": wrap_fetched_content(text, str(source_id)),
                }
            )

    return NodeResult(state_update={"raw_findings": raw_findings, "errors": errors})
