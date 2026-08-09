import logging
import re
import uuid

from app.config import get_settings
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Report
from app.models.schemas import Citation
from app.observability.tracer import traced

settings = get_settings()
logger = logging.getLogger(__name__)

CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")
# A fragment that is *only* one or more citation markers, e.g. "[2][3]" —
# see _split_sentences for why this needs special handling.
MARKER_ONLY_RE = re.compile(r"^(\[\d+\]\s*)+$")
# A sentence boundary: [.!?], optionally followed by directly-glued marker(s)
# and/or an "(unverified)" tag (the format synthesizer.md now instructs —
# no space before either), then whitespace or end-of-string. See
# _split_sentences for why matching only bare [.!?] isn't enough.
SENTENCE_END_RE = re.compile(r"[.!?](?:\[\d+\])*(?:\s*\(unverified\))?(?=\s|$)", re.IGNORECASE)
# Matches either of synthesizer.py's two programmatically-appended sections
# (Sources, Contradictions Noted) — both are structured data, never
# LLM-authored prose, so neither belongs in the claim/marker heuristic below.
APPENDED_SECTION_HEADING_RE = re.compile(r"^#{1,6}\s*(Sources|Contradictions(\s+Noted)?)\s*$", re.IGNORECASE)
MIN_FLAGGED_SENTENCE_LEN = 40


def _strip_appended_sections(markdown: str) -> str:
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        if APPENDED_SECTION_HEADING_RE.match(line.strip()):
            return "\n".join(lines[:i])
    return markdown


def _is_structural_line(line: str) -> bool:
    """Excludes headings, list items, and table rows from the claim/marker
    check (amendment: the unsoftened heuristic was flagging these as
    unmarked claims, which isn't what it's for)."""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith(("-", "*", "+")):
        return True
    if re.match(r"^\d+\.\s", stripped):
        return True
    if stripped.count("|") >= 2:
        return True
    return False


def _split_sentences(text: str) -> list[str]:
    """Splits on sentence-ending punctuation, treating directly-glued
    marker(s) and/or an "(unverified)" tag as part of the boundary rather
    than letting them strand the next sentence.

    Investigation finding (2026-08-10, coral-bleaching run
    f9319935-3cbe-4e2b-aa8c-67a82f9a1800): the synthesizer originally wrote a
    space before a sentence's trailing citation markers — "...beneath.
    [2][3]" rather than "...beneath.[2][3]" — which made a naive split on
    `(?<=[.!?])\\s+` treat that space as a sentence boundary, orphaning the
    markers into their own fragment and making the sentence they belonged to
    look unmarked. 28/28 of that run's flagged sentences turned out to be
    exactly this false positive, not the model failing to cite.

    synthesizer.md now instructs the model to glue markers directly with no
    space — but that revealed a second, worse bug: with no space anywhere
    after the period, the naive regex never finds a boundary at all inside a
    multi-sentence paragraph, so the *entire paragraph* collapses into one
    "sentence". Since it always contains a marker somewhere, it always
    "passes" — a false negative that would silently wave through a genuinely
    uncited trailing sentence in the same paragraph. Confirmed on the
    verification run (45e032a8-fa77-4f2b-b760-dee63d3ee2b7): every one of its
    6 paragraphs collapsed to 1 "sentence" under the old regex.

    SENTENCE_END_RE fixes this by matching the punctuation plus any directly
    -glued marker/unverified tag as a single boundary token. The MARKER_ONLY
    merge pass below stays as a second line of defense for a model that
    reverts to a space before the bracket despite the instruction — it can
    only ever reattach a marker-only fragment to the sentence immediately
    before it, never credit an earlier, genuinely-uncited one."""
    raw: list[str] = []
    start = 0
    for m in SENTENCE_END_RE.finditer(text):
        raw.append(text[start : m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        raw.append(tail)
    raw = [s for s in raw if s]

    merged: list[str] = []
    for fragment in raw:
        if merged and MARKER_ONLY_RE.match(fragment):
            merged[-1] = f"{merged[-1]} {fragment}"
        else:
            merged.append(fragment)
    return merged


def _find_flagged_sentences(markdown: str) -> list[str]:
    """Sentences outside headings/lists/tables/the Sources section that look
    claim-bearing (contain a digit, or are simply long) but carry neither a
    [n] marker nor an explicit (unverified) tag. A heuristic approximation of
    PRD §8's citation_validator check (b), not a semantic judgment."""
    flagged = []
    for line in _strip_appended_sections(markdown).splitlines():
        if _is_structural_line(line):
            continue
        for sentence in _split_sentences(line):
            if "(unverified)" in sentence.lower():
                continue
            if CITATION_MARKER_RE.search(sentence):
                continue
            if any(ch.isdigit() for ch in sentence) or len(sentence) > MIN_FLAGGED_SENTENCE_LEN:
                flagged.append(sentence)
    return flagged


def _find_unresolved_markers(markdown: str, marker_count: int) -> list[int]:
    """PRD §8 check (a): every [n] must resolve to a real evidence_id — i.e.
    a marker within the range of evidence actually handed to the synthesizer."""
    found = {int(m) for m in CITATION_MARKER_RE.findall(markdown)}
    return sorted(m for m in found if not (1 <= m <= marker_count))


def _tag_unverified(markdown: str, flagged_sentences: list[str]) -> str:
    tagged = markdown
    for sentence in flagged_sentences:
        if sentence and sentence in tagged:
            tagged = tagged.replace(sentence, f"{sentence} (unverified)")
    return tagged


def _build_citations(markdown: str, evidence: list) -> list[Citation]:
    evidence_by_marker = {i: ev for i, ev in enumerate(evidence, start=1)}
    citations: list[Citation] = []
    seen_markers: set[int] = set()
    for marker_str in CITATION_MARKER_RE.findall(markdown):
        marker = int(marker_str)
        if marker in seen_markers or marker not in evidence_by_marker:
            continue
        seen_markers.add(marker)
        ev = evidence_by_marker[marker]
        citations.append(Citation(marker=marker, evidence_id=ev.id, source_id=ev.source_id))
    return citations


def _persist_report(ctx: RunContext, markdown: str, citations: list[Citation]) -> None:
    ctx.db.add(
        Report(
            id=uuid.uuid4(),
            run_id=ctx.run_id,
            content_markdown=markdown,
            citations=[c.model_dump() for c in citations],
            figure_ids=[],
        )
    )


@traced("citation_validator")
async def citation_validator_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    markdown = state.get("report_markdown", "")
    # retrieved_evidence is the selected/reordered subset the synthesizer's
    # [n] markers actually refer to (see synthesizer.py) — not the full,
    # differently-ordered `evidence` list. Falls back to `evidence` only as a
    # defensive no-op; citation_validator always runs after synthesizer, so
    # retrieved_evidence is expected to be set.
    evidence = state.get("retrieved_evidence") or state.get("evidence", [])

    unresolved = _find_unresolved_markers(markdown, len(evidence))
    flagged = _find_flagged_sentences(markdown)
    for marker in unresolved:
        logger.warning("citation_validator[%s]: [%d] does not resolve to a known evidence item", ctx.run_id, marker)
    for sentence in flagged:
        logger.warning("citation_validator[%s]: unmarked claim-like sentence: %r", ctx.run_id, sentence[:160])

    # Armed for real as of Phase 2 (was forced to True in Phase 1 — see the
    # commit history if you need the old bypass). Headings, list items, table
    # rows, and both appended sections (Sources, Contradictions Noted) are
    # excluded from the check above, so this shouldn't false-positive on
    # structural or programmatic content — only on genuinely unmarked prose.
    passed = not unresolved and not flagged
    # Persisted regardless of outcome (not just logged) so this is debuggable
    # from node_traces/the Trace UI without grepping container logs —
    # previously the only record of what got flagged was a logger.warning
    # that vanishes on container restart.
    trace_input = {"unresolved_markers": unresolved, "flagged_sentences": flagged}

    if passed:
        citations = _build_citations(markdown, evidence)
        _persist_report(ctx, markdown, citations)
        return NodeResult(
            state_update={
                "citation_validation_passed": True,
                "citations": citations,
                "citation_flagged_sentences": [],
                "citation_unresolved_markers": [],
            },
            trace_input=trace_input,
        )

    retry_count = state.get("citation_retry_count", 0) + 1
    return NodeResult(
        state_update={
            "citation_validation_passed": False,
            "citation_retry_count": retry_count,
            "citation_flagged_sentences": flagged,
            "citation_unresolved_markers": unresolved,
        },
        trace_input=trace_input,
    )


def route_after_validation(state: ResearchState) -> str:
    if state.get("citation_validation_passed"):
        return "done"
    if state.get("citation_retry_count", 0) >= settings.MAX_CITATION_RETRIES:
        return "finalize"
    return "retry"


@traced("force_finalize")
async def force_finalize_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """Reached only when citation_validation_passed is still False after
    MAX_CITATION_RETRIES retries — unreachable in Phase 1 since the gate above
    is forced to pass, but implemented correctly per PRD §8/Correction #10 for
    when Phase 2 arms the real check."""
    markdown = state.get("report_markdown", "")
    evidence = state.get("retrieved_evidence") or state.get("evidence", [])

    tagged = _tag_unverified(markdown, _find_flagged_sentences(markdown))
    citations = _build_citations(tagged, evidence)
    _persist_report(ctx, tagged, citations)

    return NodeResult(
        state_update={
            "report_markdown": tagged,
            "citation_validation_passed": True,
            "citations": citations,
        }
    )
