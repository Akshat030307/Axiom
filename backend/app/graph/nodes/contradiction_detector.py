import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Contradiction as ContradictionRow
from app.models.db_models import Evidence as EvidenceRow
from app.models.db_models import Source as SourceRow
from app.models.schemas import Contradiction, Evidence
from app.observability.tracer import estimate_cost, traced
from app.retrieval.embeddings import cluster_by_similarity

settings = get_settings()
logger = logging.getLogger(__name__)

CLASSIFIER_PROMPT = load_prompt("contradiction_classifier.md")
RESOLVER_PROMPT = load_prompt("contradiction_resolver.md")


class _ClassifierPair(BaseModel):
    index_a: int
    index_b: int
    reason_hint: str


class _ClassifierResult(BaseModel):
    candidates: list[_ClassifierPair]


class _ResolutionVerdict(BaseModel):
    genuinely_contradictory: bool
    # Optional on purpose: an unexplained-but-confirmed contradiction
    # (nothing in the supplied data explicitly distinguishes the two claims)
    # must be expressible without forcing the model to invent a reason —
    # see contradiction_resolver.md.
    explanation: str | None = None


@dataclass
class LLMCallUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None


@dataclass
class ResolutionOutcome:
    genuinely_contradictory: bool
    explanation: str | None
    contradiction: Contradiction | None  # set iff genuinely_contradictory and the call succeeded
    llm_call_failed: bool = False


def _group_label(group: list[Evidence]) -> str:
    """A group can now span more than one sub-question (numeric clusters
    aren't sub-question-scoped) — label it by however many distinct
    sub-questions actually contributed, for logging/trace readability only."""
    topics = list(dict.fromkeys(ev.topic for ev in group))
    return topics[0] if len(topics) == 1 else f"{len(topics)} sub-questions"


def _numeric_conflicts(group: list[Evidence], threshold: float) -> set[tuple[int, int]]:
    """Tier 1 — free. Same numeric_unit, relative difference > threshold."""
    flagged: set[tuple[int, int]] = set()
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            a, b = group[i], group[j]
            if a.numeric_value is None or b.numeric_value is None or not a.numeric_unit:
                continue
            if a.numeric_unit != b.numeric_unit:
                continue
            denom = max(abs(a.numeric_value), abs(b.numeric_value))
            if denom == 0:
                continue
            if abs(a.numeric_value - b.numeric_value) / denom > threshold:
                flagged.add((i, j))
    return flagged


def _build_classifier_prompt(group: list[Evidence]) -> str:
    lines = ["Claims (each shown with the sub-question it was extracted for):", ""]
    lines.extend(f"[{i}] (sub-question: {ev.topic}) {ev.claim}" for i, ev in enumerate(group))
    return "\n".join(lines)


async def _classify_group(llm, group: list[Evidence]) -> tuple[set[tuple[int, int]], LLMCallUsage]:
    """Tier 2 — one fast-tier batched call per group (O(groups), not
    O(pairs)), scanning all of that group's claims at once for candidate
    contradictions."""
    if len(group) < 2:
        return set(), LLMCallUsage()
    try:
        response = await llm.generate_structured(
            "classification",
            system=CLASSIFIER_PROMPT,
            user=_build_classifier_prompt(group),
            schema=_ClassifierResult,
        )
    except Exception as exc:
        logger.warning("contradiction_detector: classification failed for group %r: %s", _group_label(group), exc)
        return set(), LLMCallUsage()

    pairs: set[tuple[int, int]] = set()
    for candidate in response.parsed.candidates:
        if (
            0 <= candidate.index_a < len(group)
            and 0 <= candidate.index_b < len(group)
            and candidate.index_a != candidate.index_b
        ):
            pairs.add(tuple(sorted((candidate.index_a, candidate.index_b))))
    return pairs, LLMCallUsage(response.input_tokens, response.output_tokens, response.model)


def _side_context(ev: Evidence, source: SourceRow | None) -> str:
    title = source.title if source else "unknown source"
    published = source.publication_date if source and source.publication_date else "unknown"
    return (
        f"(sub-question: {ev.topic})\n"
        f"    claim: {ev.claim}\n"
        f"    excerpt: {ev.relevant_excerpt}\n"
        f"    time_period: {ev.time_period or 'not specified'}\n"
        f"    source: {title} — published: {published}"
    )


async def _resolve_pair(
    llm, a: Evidence, b: Evidence, sources_by_id: dict[str, SourceRow]
) -> tuple[ResolutionOutcome, LLMCallUsage]:
    """Tier 3 — reasoning-tier, one call per flagged pair (small set by
    construction). Constrained (contradiction_resolver.md) to resolve using
    only what's explicitly in the supplied fields — no outside knowledge
    about how specs/products typically change over time. A pair with no
    textual distinguishing signal comes back genuinely_contradictory=true,
    explanation=None: an unexplained contradiction, surfaced, rather than an
    invented explanation."""
    prompt = (
        f"Claim A {_side_context(a, sources_by_id.get(a.source_id))}\n\n"
        f"Claim B {_side_context(b, sources_by_id.get(b.source_id))}"
    )
    try:
        response = await llm.generate_structured(
            "contradiction_resolution", system=RESOLVER_PROMPT, user=prompt, schema=_ResolutionVerdict
        )
    except Exception as exc:
        logger.warning("contradiction_detector: resolution failed for a flagged pair: %s", exc)
        return ResolutionOutcome(genuinely_contradictory=False, explanation=None, contradiction=None, llm_call_failed=True), LLMCallUsage()

    usage = LLMCallUsage(response.input_tokens, response.output_tokens, response.model)
    verdict = response.parsed

    contradiction = None
    if verdict.genuinely_contradictory:
        topic = a.topic if a.topic == b.topic else f"{a.topic} / {b.topic}"
        contradiction = Contradiction(
            topic=topic, evidence_a_id=a.id, evidence_b_id=b.id, explanation=verdict.explanation, resolved=False
        )
    return ResolutionOutcome(
        genuinely_contradictory=verdict.genuinely_contradictory,
        explanation=verdict.explanation,
        contradiction=contradiction,
    ), usage


def _numeric_clusters(retrieved: list[Evidence], embeddings_by_id: dict[str, list[float]]) -> list[list[Evidence]]:
    """Groups numeric-claim evidence by embedding similarity of the claim
    text (loose threshold — same *subject*, not near-duplicates), regardless
    of which sub-question it came from. Replaces sub-question-index grouping
    for numeric claims: sub-question origin is an arbitrary partition for
    "are these two numbers about the same thing" — a real 33% battery-
    capacity conflict was missed in testing because the two claims came from
    different sub-questions and so were never in the same group to compare."""
    numeric_evidence = [ev for ev in retrieved if ev.numeric_value is not None]
    return cluster_by_similarity(numeric_evidence, embeddings_by_id, settings.CONTRADICTION_CLUSTER_THRESHOLD)


def _nonnumeric_groups_by_subquestion(retrieved: list[Evidence], num_subquestions: int) -> tuple[list[list[Evidence]], int]:
    """Non-numeric claims keep the original sub-question-index grouping —
    there's no numeric_unit to key a subject-cluster on, and comparing
    completely unrelated non-numeric claims across sub-questions would just
    inflate the pair count without a matching signal to filter on."""
    nonnumeric = [ev for ev in retrieved if ev.numeric_value is None]
    groups: dict[int, list[Evidence]] = defaultdict(list)
    unmatched = 0
    for ev in nonnumeric:
        idx = ev.sub_question_index
        if idx is None or not (0 <= idx < num_subquestions):
            unmatched += 1
            continue
        groups[idx].append(ev)
    return list(groups.values()), unmatched


@traced("contradiction_detector")
async def contradiction_detector_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    retrieved = state.get("retrieved_evidence") or []
    plan = state["plan"]

    if len(retrieved) < 2:
        return NodeResult(state_update={"contradictions": []}, trace_input={"note": "fewer than 2 retrieved evidence items"})

    evidence_ids = [uuid.UUID(ev.id) for ev in retrieved]
    rows = (await ctx.db.scalars(select(EvidenceRow).where(EvidenceRow.id.in_(evidence_ids)))).all()
    embeddings_by_id = {str(row.id): row.embedding for row in rows if row.embedding is not None}

    sources = (await ctx.db.scalars(select(SourceRow).where(SourceRow.run_id == ctx.run_id))).all()
    sources_by_id = {str(s.id): s for s in sources}

    numeric_groups = _numeric_clusters(retrieved, embeddings_by_id)
    nonnumeric_groups, unmatched = _nonnumeric_groups_by_subquestion(retrieved, len(plan.sub_questions))
    if unmatched:
        logger.warning(
            "contradiction_detector[%s]: %d non-numeric evidence item(s) had no valid sub_question_index, excluded",
            ctx.run_id,
            unmatched,
        )
    all_groups = numeric_groups + nonnumeric_groups

    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    stage1_count = 0
    stage2_count = 0

    flagged_pairs: list[tuple[Evidence, Evidence]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for group in all_groups:
        stage1 = _numeric_conflicts(group, settings.CONTRADICTION_NUMERIC_THRESHOLD)
        stage1_count += len(stage1)

        stage2, usage = await _classify_group(ctx.llm, group)
        total_input_tokens += usage.input_tokens
        total_output_tokens += usage.output_tokens
        if usage.model:
            total_cost += estimate_cost(usage.model, usage.input_tokens, usage.output_tokens)
        stage2_count += len(stage2)

        for i, j in stage1 | stage2:
            a, b = group[i], group[j]
            key = tuple(sorted((a.id, b.id)))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            flagged_pairs.append((a, b))

    contradictions: list[Contradiction] = []
    # Every flagged pair's outcome is logged here — confirmed AND rejected —
    # so a wrong rejection is debuggable from the trace without re-running.
    # Only confirmed ones get a persisted Contradiction row.
    resolution_log: list[dict] = []
    for a, b in flagged_pairs:
        outcome, usage = await _resolve_pair(ctx.llm, a, b, sources_by_id)
        total_input_tokens += usage.input_tokens
        total_output_tokens += usage.output_tokens
        if usage.model:
            total_cost += estimate_cost(usage.model, usage.input_tokens, usage.output_tokens)

        resolution_log.append(
            {
                "claim_a": a.claim[:150],
                "claim_b": b.claim[:150],
                "genuinely_contradictory": outcome.genuinely_contradictory,
                "explanation": outcome.explanation,
                "confirmed": outcome.contradiction is not None,
                "llm_call_failed": outcome.llm_call_failed,
            }
        )

        if outcome.contradiction is None:
            continue
        contradictions.append(outcome.contradiction)
        ctx.db.add(
            ContradictionRow(
                id=uuid.uuid4(),
                run_id=ctx.run_id,
                topic=outcome.contradiction.topic,
                evidence_a_id=uuid.UUID(outcome.contradiction.evidence_a_id),
                evidence_b_id=uuid.UUID(outcome.contradiction.evidence_b_id),
                explanation=outcome.contradiction.explanation,
                resolved=outcome.contradiction.resolved,
            )
        )
        ctx.events.contradiction_found(
            topic=outcome.contradiction.topic,
            evidence_a_id=outcome.contradiction.evidence_a_id,
            evidence_b_id=outcome.contradiction.evidence_b_id,
        )

    return NodeResult(
        state_update={"contradictions": contradictions},
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        cost_override=total_cost,
        trace_input={
            # If stage2 flags nearly everything, stage 3's reasoning-tier
            # calls (the expensive tier) become the real cost center — that
            # should be visible here, not discovered from the bill.
            "stage1_numeric_flagged_pairs": stage1_count,
            "stage2_llm_flagged_pairs": stage2_count,
            "stage3_pairs_sent_for_explanation": len(flagged_pairs),
            "stage3_confirmed_contradictions": len(contradictions),
            "numeric_clusters": len(numeric_groups),
            "nonnumeric_groups": len(nonnumeric_groups),
            "unmatched_nonnumeric_evidence_count": unmatched,
            "resolution_log": resolution_log,
        },
    )
