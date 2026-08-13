import logging
import re
import uuid

from sqlalchemy import select

from app.config import get_settings
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Source as SourceRow
from app.models.schemas import Contradiction, Evidence, Figure
from app.observability.tracer import traced

settings = get_settings()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("synthesizer.md")
# Kept as a separate fragment, appended only when the run's highlight toggle
# is on, rather than baked into synthesizer.md — no point spending the
# model's effort on an instruction that _cap_and_clean_highlights would just
# undo for a run that opted out.
HIGHLIGHTING_PROMPT = load_prompt("synthesizer_highlighting.md")
# Same pattern — appended only for the modes meant to go deeper than a quick
# summary. Quick mode's existing brevity is correct as-is; nothing in
# synthesizer.md pushes the model toward more thorough per-section coverage
# for the other three modes today, so deep/academic/competitive reports were
# only as long as however much evidence happened to be retrieved made them,
# never because anything actually asked for more depth.
DEPTH_PROMPT = load_prompt("synthesizer_depth.md")
DEPTH_MODES = {"deep", "academic", "competitive"}

# Matches either of the two sections this module appends after the model's
# response — used both to strip a model-authored attempt at either (models
# don't reliably honor negative instructions) and, in citation_validator.py,
# to exclude both from the armed citation heuristic.
APPENDED_SECTION_HEADING_RE = re.compile(r"^#{1,6}\s*(Sources|Contradictions(\s+Noted)?)\s*$", re.IGNORECASE | re.MULTILINE)
FIGURE_MARKDOWN_RE = re.compile(r"!\[([^\]]*)\]\(figure://([^)\s]+)\)")
# A highlighted span never crosses a line/paragraph break (excluding \n keeps
# a run-on model from wrapping multiple paragraphs, or a whole section, as
# "one" highlight — see _cap_and_clean_highlights). The span itself is meant
# to hold a short, 2-3 sentence passage, not a single sentence.
HIGHLIGHT_RE = re.compile(r"==([^=\n]+)==")
# ~3 real sentences with a trailing citation marker or two, generously
# sized — see _cap_and_clean_highlights; still well short of a full
# paragraph, which is the actual thing this cap guards against.
MAX_HIGHLIGHT_CHARS = 500


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


def _format_figures_list(figures: list[Figure]) -> str:
    if not figures:
        return "(none were generated for this report — do not reference any figure://)"
    return "\n".join(f"- figure://{fig.id} ({fig.kind}) — {fig.caption}" for fig in figures)


def _strip_invalid_figure_refs(content: str, valid_figure_ids: set[str]) -> str:
    """Defensive, same rationale as _strip_model_appended_sections: citation_
    validator doesn't check figure:// references (PRD §8 check (c) isn't
    wired up in this build), so an id the model got wrong or invented would
    otherwise reach the client as a permanently-broken image reference.
    Dropped rather than left in place — ReportView's placeholder for a
    missing figure is more confusing than the sentence simply not having one."""

    def _replace(match: "re.Match[str]") -> str:
        caption, figure_id = match.group(1), match.group(2)
        if figure_id in valid_figure_ids:
            return match.group(0)
        logger.warning("synthesizer: dropping reference to unknown figure id %r (caption=%r)", figure_id, caption)
        return ""

    return FIGURE_MARKDOWN_RE.sub(_replace, content)


def _cap_and_clean_highlights(content: str, max_highlights: int) -> str:
    """Defensive, same rationale as every other post-processing step here:
    a prompt instruction ("at most one per section") isn't a guarantee, so
    this enforces it in code. Unwraps (strips the delimiters, keeps the
    words) rather than deletes — a highlight past the cap or too long to be
    "a short passage" should still read as normal prose, not vanish."""
    kept = 0

    def _replace(match: "re.Match[str]") -> str:
        nonlocal kept
        text = match.group(1)
        if len(text) > MAX_HIGHLIGHT_CHARS or kept >= max_highlights:
            return text
        kept += 1
        return match.group(0)

    return HIGHLIGHT_RE.sub(_replace, content)


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
    to it, invents "not provided" placeholders instead). One line per unique
    source, not per cited evidence item — `evidence` is often 30-90 items in
    deep mode and the same strong source frequently gets cited several
    times, so a naive one-line-per-citation version repeated the same
    title/domain/url block over and over and was a large share of a
    deep-mode PDF's page count for zero added information. Every citation
    marker number that points to a given source is listed on its line, so a
    reader can still trace any [n] in the body back to exactly one place
    here. Deliberately comma-separated, not bracketed ("3, 7." not
    "[3][7]") — citation_validator.py's marker regex scans the *entire*
    report markdown, this section included, and a literal [n] here would
    register as a phantom in-body citation for evidence the model may never
    have actually referenced in prose.

    Also carries credibility_scorer's score inline — this is now the only
    place that score reaches the reader; the separate PDF-only "Sources (by
    credibility)" appendix (html_renderer.py) duplicated it for every source
    the run ever touched, not just the ones actually cited, and has been
    removed."""
    markers_by_source_id: dict[str, list[int]] = {}
    order: list[str] = []
    for i, ev in enumerate(evidence, start=1):
        if ev.source_id not in sources_by_id:
            continue
        if ev.source_id not in markers_by_source_id:
            markers_by_source_id[ev.source_id] = []
            order.append(ev.source_id)
        markers_by_source_id[ev.source_id].append(i)

    lines = ["## Sources"]
    for source_id in order:
        source = sources_by_id[source_id]
        markers = ", ".join(str(n) for n in markers_by_source_id[source_id])
        title = source.title or source.domain
        score = f"{source.credibility_score:.2f}" if source.credibility_score is not None else "—"
        lines.append(f"{markers}. {title} ({source.domain}, credibility {score}) — {source.url}")
    return "\n".join(lines)


def _format_retry_feedback(state: ResearchState) -> str | None:
    """Built from the previous citation_validator failure so a retry is a
    targeted correction, not a blind re-roll with an identical prompt.

    Investigation finding (2026-08-10): before this existed, `route_after_
    validation`'s "retry" edge sent execution straight back to this node
    with no signal that a previous attempt existed at all, let alone what
    failed in it — same system prompt, same user prompt, so a second
    LangGraph pass through this node was pure sampling variance. Confirmed
    by diffing two real attempts on the same run: the same handful of
    claims recurred, reworded, still failing the same check.

    Deliberately gives the model both ways to satisfy the check (attach a
    marker, or rewrite the sentence so it no longer asserts an uncited
    fact) rather than only "add a citation" — a model told only to fix
    citations will invent one to make the check pass, which is worse than
    an honest (unverified) tag."""
    flagged = state.get("citation_flagged_sentences") or []
    unresolved = state.get("citation_unresolved_markers") or []
    if not flagged and not unresolved:
        return None

    lines = [
        "\nYour previous draft failed citation validation. Fix ONLY the following; "
        "do not introduce new uncited claims elsewhere."
    ]
    if flagged:
        lines.append(
            "\nThese sentences asserted a fact but carried neither a [n] marker nor "
            "an (unverified) tag (quoted verbatim from your previous draft):"
        )
        lines.extend(f'- "{sentence}"' for sentence in flagged)
        lines.append(
            "\nFor each one, either: (a) attach the correct [n] marker(s) — "
            "including more than one, e.g. [2][5], if the sentence draws on "
            "several evidence items — if the evidence list actually supports it, "
            "or (b) rewrite the sentence so it no longer asserts an uncited fact "
            "(generalize it, drop the specific claim, or tag it \"(unverified)\"). "
            "Do not invent or guess a citation just to satisfy this check — an "
            "incorrect marker is worse than an honest (unverified) tag. When you "
            "do attach markers, place them immediately after the sentence's "
            "closing punctuation with no space, e.g. \"...beneath.[2][3]\" not "
            "\"...beneath. [2][3]\"."
        )
    if unresolved:
        marker_list = ", ".join(f"[{m}]" for m in unresolved)
        lines.append(
            f"\nThese marker numbers do not correspond to any evidence item you "
            f"were given and must be removed or corrected: {marker_list}."
        )
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
    # Figures with a paired_figure_id are a real photo web_image_fetcher
    # attached to a specific illustration — ReportFigure.tsx renders that
    # pairing automatically wherever the illustration's own figure:// marker
    # lands, so the model never needs (and isn't offered) the photo's own
    # id. Excluding it here, not just from the prompt text, also keeps it
    # out of valid_figure_ids below — if the model ever did emit a
    # coincidentally-matching reference, it gets stripped rather than
    # rendering the photo a second time.
    figures = [fig for fig in (state.get("figures") or []) if not fig.paired_figure_id]
    sources_by_id = await _fetch_sources_by_id(ctx, {ev.source_id for ev in selected})
    evidence_by_id = {ev.id: ev for ev in selected}
    # Defaults true — every existing caller (and every run created before
    # this toggle existed) keeps today's behavior unless it opts out.
    highlight_enabled = state.get("highlight_enabled", True)
    system_prompt = f"{SYSTEM_PROMPT}\n\n{HIGHLIGHTING_PROMPT}" if highlight_enabled else SYSTEM_PROMPT
    if state["mode"] in DEPTH_MODES:
        system_prompt = f"{system_prompt}\n\n{DEPTH_PROMPT}"

    user_prompt = (
        f"Research objective: {plan.objective}\n\n"
        "Sub-questions:\n" + "\n".join(f"- {q}" for q in plan.sub_questions) + "\n\n"
        f"Evidence (cite each by its bracketed number below):\n{_format_evidence_list(selected, sources_by_id)}\n\n"
        "Figures already generated for this report — place at most one reference to "
        "each, on its own line, exactly as `![caption](figure://{id})`, only where it "
        "genuinely helps (not one per figure just because it exists), and only using "
        f"the ids listed here:\n{_format_figures_list(figures)}\n"
    )

    retry_feedback = _format_retry_feedback(state)
    if retry_feedback:
        user_prompt += retry_feedback

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
    stream = await ctx.llm.generate_stream("synthesis", system=system_prompt, user=user_prompt)
    async for delta in stream:
        ctx.events.report_chunk(delta)
    response = stream.response

    body = _strip_model_appended_sections(response.content)
    body = _strip_invalid_figure_refs(body, {fig.id for fig in figures})
    # Runs the strip pass even when disabled — belt-and-suspenders against a
    # model that highlights anyway despite the instruction simply being
    # absent (same reasoning as every other "don't trust an omitted
    # instruction alone" cleanup in this file).
    body = _cap_and_clean_highlights(body, settings.MAX_HIGHLIGHTS_PER_REPORT if highlight_enabled else 0)
    sections = [body]
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
