import re
import uuid

from sqlalchemy import select

from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Source as SourceRow
from app.models.schemas import Contradiction, Evidence
from app.observability.tracer import traced

SYSTEM_PROMPT = load_prompt("synthesizer.md")

# Matches either of the two sections this module appends after the model's
# response — used both to strip a model-authored attempt at either (models
# don't reliably honor negative instructions) and, in citation_validator.py,
# to exclude both from the armed citation heuristic.
APPENDED_SECTION_HEADING_RE = re.compile(r"^#{1,6}\s*(Sources|Contradictions(\s+Noted)?)\s*$", re.IGNORECASE | re.MULTILINE)


async def _fetch_sources_by_id(ctx: RunContext, source_ids: set[str]) -> dict[str, SourceRow]:
    if not source_ids:
        return {}
    rows = (
        await ctx.db.scalars(select(SourceRow).where(SourceRow.id.in_([uuid.UUID(s) for s in source_ids])))
    ).all()
    return {str(row.id): row for row in rows}


def _describe_source(source: SourceRow | None) -> str:
    if source is None:
        return "unknown source"
    title = source.title or source.domain
    return f"{title} ({source.domain})"


def _format_evidence_list(evidence: list[Evidence], sources_by_id: dict[str, SourceRow]) -> str:
    lines = []
    for i, ev in enumerate(evidence, start=1):
        source = sources_by_id.get(ev.source_id)
        lines.append(
            f"[{i}] topic: {ev.topic}\n"
            f"    claim: {ev.claim}\n"
            f"    excerpt: {ev.relevant_excerpt}\n"
            f"    source: {_describe_source(source)}"
        )
    return "\n".join(lines) if lines else "(no evidence was collected)"


def _strip_model_appended_sections(content: str) -> str:
    """Defensive, not just prompt-based: the model is instructed not to write
    a Sources or Contradictions section, but a negative instruction to a
    reasoning model isn't reliable enough on its own — observed in testing
    writing a Sources section anyway, with truncated/invented URLs. Strip
    anything from the first such heading onward; _build_sources_section and
    _build_contradictions_section below are the only ones that survive."""
    match = APPENDED_SECTION_HEADING_RE.search(content)
    if match:
        return content[: match.start()].rstrip()
    return content.rstrip()


def _build_sources_section(evidence: list[Evidence], sources_by_id: dict[str, SourceRow]) -> str:
    """Built entirely from real `sources` rows — the model never writes this
    section (it has no reliable way to produce correct titles/URLs and, left
    to it, invents "not provided" placeholders instead). Numbered to match
    the same 1-indexed positions the evidence list above used, so a citation
    marker and its Sources entry always refer to the same item."""
    lines = ["## Sources"]
    for i, ev in enumerate(evidence, start=1):
        source = sources_by_id.get(ev.source_id)
        if source is None:
            continue
        title = source.title or source.domain
        lines.append(f"{i}. {title} ({source.domain}) — {source.url}")
    return "\n".join(lines)


def _build_contradictions_section(contradictions: list[Contradiction], evidence_by_id: dict[str, Evidence]) -> str | None:
    """Same pattern as Sources — built from contradiction_detector's actual
    output, never LLM-authored, so it can't invent or mischaracterize a
    contradiction the detector didn't find."""
    if not contradictions:
        return None
    lines = ["## Contradictions Noted"]
    for c in contradictions:
        a = evidence_by_id.get(c.evidence_a_id)
        b = evidence_by_id.get(c.evidence_b_id)
        a_desc = f'"{a.claim}"' if a else "one evidence item"
        b_desc = f'"{b.claim}"' if b else "another evidence item"
        explanation = c.explanation or "no explanation recorded"
        lines.append(f"- **{c.topic}** — {a_desc} vs. {b_desc}: {explanation}")
    return "\n".join(lines)


@traced("synthesizer")
async def synthesizer_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    plan = state["plan"]
    # Already the reranked top-K per sub-question, deduped, in citation-marker
    # order — retriever.py populated this; synthesizer only consumes it now.
    selected = state.get("retrieved_evidence") or []
    contradictions = state.get("contradictions", [])
    sources_by_id = await _fetch_sources_by_id(ctx, {ev.source_id for ev in selected})
    evidence_by_id = {ev.id: ev for ev in selected}

    user_prompt = (
        f"Research objective: {plan.objective}\n\n"
        "Sub-questions:\n" + "\n".join(f"- {q}" for q in plan.sub_questions) + "\n\n"
        f"Evidence (cite each by its bracketed number below):\n{_format_evidence_list(selected, sources_by_id)}\n"
    )

    # Streams report_chunk frames as tokens arrive (design streams the report
    # as it writes) rather than one blocking call. The post-processing below
    # — stripping a spurious model-authored Sources heading, appending the
    # programmatic Sources/Contradictions sections — runs on the fully
    # accumulated text after the stream ends, same as it always did on
    # generate()'s return value. That means a client's live-accumulated
    # report_chunk text can transiently include a few tokens that get
    # stripped server-side before persistence; accepted as a documented
    # cosmetic gap for this phase (frontend should re-fetch the canonical
    # report on `done` rather than trusting accumulated chunks).
    stream = await ctx.llm.generate_stream("synthesis", system=SYSTEM_PROMPT, user=user_prompt)
    async for delta in stream:
        ctx.events.report_chunk(delta)
    response = stream.response

    sections = [_strip_model_appended_sections(response.content)]
    contradictions_section = _build_contradictions_section(contradictions, evidence_by_id)
    if contradictions_section:
        sections.append(contradictions_section)
    sections.append(_build_sources_section(selected, sources_by_id))
    report_markdown = "\n\n".join(sections) + "\n"

    return NodeResult(
        state_update={
            "report_markdown": report_markdown,
            "status": "synthesis_complete",
        },
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        model=response.model,
    )
