"""Phase 3 minimal eval metrics (PRD §17, trimmed to the demo-critical
subset — faithfulness and reranker_effectiveness are out of scope for this
phase; see the implementation plan for why). Every function here computes a
real number from a completed run's persisted rows — none of them are
placeholders. A function returns `None` when there's nothing to measure
(e.g. a report with zero citations), and callers must treat `None` as
"excluded from the average", never as 0.
"""

import re
import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.nodes._prompts import load_prompt
from app.llm.provider import LLMProvider
from app.models.db_models import Evidence, FactCheckResult, Report, ResearchRun
from app.observability.tracer import estimate_cost

CITATION_JUDGE_PROMPT = load_prompt("citation_judge.md")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MARKER_RE = re.compile(r"\[(\d+)\]")


class _JudgeItem(BaseModel):
    index: int
    supported: bool


class _JudgeResult(BaseModel):
    judgments: list[_JudgeItem]


def _sentence_for_marker(markdown: str, marker: int) -> str | None:
    """First sentence in the report containing this citation's [n] marker,
    with the marker itself stripped — the "claim_sentence" the citation
    judge checks against. Line-based, not full-document sentence splitting:
    good enough for eval, where citation_validator.py's stricter machinery
    (which already ran during the actual graph execution) isn't needed."""
    needle = f"[{marker}]"
    for line in markdown.splitlines():
        if needle not in line:
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(line):
            if needle in sentence:
                return _MARKER_RE.sub("", sentence).strip()
    return None


async def citation_accuracy(db: AsyncSession, llm: LLMProvider, report: Report) -> tuple[float | None, float]:
    """% of citations whose excerpt genuinely supports its adjacent claim
    sentence — judged, not structural. A structural check (does [n] resolve
    to a real evidence_id) is already guaranteed 100% by citation_validator
    and would be a degenerate metric; this is one batched fast-tier LLM call
    per report, same index-validate-and-fallback discipline as
    retrieval/reranker.py's listwise rerank (PRD §3.3 caveats).

    Returns `(score, judge_cost_usd)` — the cost is broken out separately
    because it's the ONLY real spend when scoring an already-completed run
    (eval/runner.py's existing-run mode reuses a run's sunk retrieval/
    verification cost and pays for nothing but this one call)."""
    citations = report.citations or []
    if not citations:
        return None, 0.0

    evidence_ids = [uuid.UUID(c["evidence_id"]) for c in citations]
    rows = (await db.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids)))).all()
    excerpt_by_id = {str(r.id): r.relevant_excerpt for r in rows}

    items: list[tuple[str, str]] = []
    for c in citations:
        sentence = _sentence_for_marker(report.content_markdown, c["marker"])
        excerpt = excerpt_by_id.get(c["evidence_id"])
        if sentence and excerpt:
            items.append((sentence, excerpt))
    if not items:
        return None, 0.0

    lines = ["Citations:"]
    for i, (sentence, excerpt) in enumerate(items):
        lines.append(f"[{i}] claim_sentence: {sentence}\n    excerpt: {excerpt}")

    try:
        response = await llm.generate_structured(
            "citation_judgment", system=CITATION_JUDGE_PROMPT, user="\n".join(lines), schema=_JudgeResult
        )
    except Exception:
        return None, 0.0

    cost = estimate_cost(response.model, response.input_tokens, response.output_tokens)

    seen: set[int] = set()
    supported_count = 0
    valid_count = 0
    for j in response.parsed.judgments:
        if not (0 <= j.index < len(items)) or j.index in seen:
            continue
        seen.add(j.index)
        valid_count += 1
        if j.supported:
            supported_count += 1

    return (supported_count / valid_count) if valid_count else None, cost


async def claim_verification(db: AsyncSession, report: Report) -> float | None:
    """% of the report's cited evidence with FactCheckResult.status ==
    'supported' (PRD §17: "% of report claims with status=supported")."""
    citations = report.citations or []
    if not citations:
        return None
    evidence_ids = [uuid.UUID(c["evidence_id"]) for c in citations]
    statuses = (
        await db.scalars(select(FactCheckResult.status).where(FactCheckResult.evidence_id.in_(evidence_ids)))
    ).all()
    if not statuses:
        return None
    return sum(1 for s in statuses if s == "supported") / len(statuses)


async def task_completion(db: AsyncSession, run: ResearchRun, report: Report) -> float | None:
    """% of plan.sub_questions with >=1 cited evidence item at that
    sub_question_index (stored in Evidence.metadata_ — see
    evidence_extractor.py)."""
    plan = run.plan or {}
    sub_questions = plan.get("sub_questions") or []
    if not sub_questions:
        return None
    citations = report.citations or []
    if not citations:
        return 0.0
    evidence_ids = [uuid.UUID(c["evidence_id"]) for c in citations]
    rows = (await db.scalars(select(Evidence).where(Evidence.id.in_(evidence_ids)))).all()
    addressed = {
        (r.metadata_ or {}).get("sub_question_index")
        for r in rows
        if (r.metadata_ or {}).get("sub_question_index") is not None
    }
    return len(addressed) / len(sub_questions)


def mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return (sum(present) / len(present)) if present else None
