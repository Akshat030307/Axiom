import uuid
from urllib.parse import urlparse

from app.config import get_settings
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.guardrails.sanitize import sanitize_text, wrap_fetched_content
from app.models.db_models import Source
from app.observability.tracer import traced
from app.retrieval.chunking import select_relevant_chunks
from app.tools.web_fetch import fetch_clean_text
from app.tools.web_search import search

settings = get_settings()

RESULTS_PER_SUBQUESTION = 3
# Placeholder until credibility_scorer runs later in this same graph and
# UPDATEs every source's real score (corroboration counting needs evidence
# to exist first, so it can't happen this early).
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

    for sub_question_index, sub_question in enumerate(plan.sub_questions):
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

            text = select_relevant_chunks(text, sub_question)

            seen_urls.add(url)
            source_id = uuid.uuid4()
            title = result.get("title") or url
            domain = urlparse(url).netloc
            ctx.db.add(
                Source(
                    id=source_id,
                    run_id=ctx.run_id,
                    url=url,
                    title=title,
                    domain=domain,
                    source_type="web",
                    publication_date=result.get("published_date"),
                    credibility_score=DEFAULT_CREDIBILITY,
                )
            )
            # Credibility here is still the placeholder (credibility_scorer
            # hasn't run yet) — the WS client sees the real score later via
            # the `stat`/REST paths once scoring completes; this event is
            # about "a source was found", not the final score.
            ctx.events.source_found(
                source_id=str(source_id),
                title=title,
                domain=domain,
                source_type="web",
                credibility_score=DEFAULT_CREDIBILITY,
            )

            raw_findings.append(
                {
                    "source_id": str(source_id),
                    "topic": sub_question,
                    "sub_question_index": sub_question_index,
                    "fetched_content": wrap_fetched_content(text, str(source_id)),
                }
            )

    return NodeResult(state_update={"raw_findings": raw_findings, "errors": errors})
