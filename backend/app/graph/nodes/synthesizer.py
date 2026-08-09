import re
import uuid

from sqlalchemy import select

from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Source as SourceRow
from app.models.schemas import Evidence
from app.observability.tracer import traced

SYSTEM_PROMPT = load_prompt("synthesizer.md")

SOURCES_HEADING_RE = re.compile(r"^#{1,6}\s*Sources\s*$", re.IGNORECASE | re.MULTILINE)

# Uncapped evidence into synthesis is what truncated a real run (53 items
# blew through even a raised token budget). Sort by extractor confidence and
# take the top N per mode until real retrieval exists.
# TODO(phase-2): replace with the hybrid retriever's reranked top-K per
# sub-question (§10) — this ignores topic coverage/diversity, it's a stopgap.
TOP_N_EVIDENCE_BY_MODE = {"quick": 25, "deep": 40, "academic": 40, "competitive": 40}


def _select_evidence(evidence: list[Evidence], mode: str) -> list[Evidence]:
    cap = TOP_N_EVIDENCE_BY_MODE.get(mode, TOP_N_EVIDENCE_BY_MODE["deep"])
    return sorted(evidence, key=lambda e: e.confidence, reverse=True)[:cap]


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


def _strip_model_sources_section(content: str) -> str:
    """Defensive, not just prompt-based: the model is instructed not to write
    a Sources section, but a negative instruction to a reasoning model isn't
    reliable enough on its own — observed in testing writing one anyway, with
    truncated/invented URLs. Strip anything from the first Sources-like
    heading onward so the model can never place its own citation targets
    into the report; _build_sources_section below is the only one that
    survives."""
    match = SOURCES_HEADING_RE.search(content)
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


@traced("synthesizer")
async def synthesizer_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    plan = state["plan"]
    evidence = state.get("evidence", [])
    # Selected (and re-ordered) evidence, in the exact order the [n] markers
    # below refer to — persisted as `retrieved_evidence` so citation_validator
    # resolves markers against the same numbering the synthesizer actually
    # used, not the full unfiltered `evidence` list.
    selected = _select_evidence(evidence, state["mode"])
    sources_by_id = await _fetch_sources_by_id(ctx, {ev.source_id for ev in selected})

    user_prompt = (
        f"Research objective: {plan.objective}\n\n"
        "Sub-questions:\n" + "\n".join(f"- {q}" for q in plan.sub_questions) + "\n\n"
        f"Evidence (cite each by its bracketed number below):\n{_format_evidence_list(selected, sources_by_id)}\n"
    )

    response = await ctx.llm.generate("synthesis", system=SYSTEM_PROMPT, user=user_prompt)

    cleaned_content = _strip_model_sources_section(response.content)
    sources_section = _build_sources_section(selected, sources_by_id)
    report_markdown = f"{cleaned_content}\n\n{sources_section}\n"

    return NodeResult(
        state_update={
            "report_markdown": report_markdown,
            "retrieved_evidence": selected,
            "status": "synthesis_complete",
        },
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        model=response.model,
    )
