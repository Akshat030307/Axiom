import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.guardrails.sanitize import FETCHED_CONTENT_INSTRUCTION, wrap_fetched_content
from app.models.db_models import Evidence as EvidenceRow
from app.models.db_models import FactCheckResult as FactCheckResultRow
from app.models.db_models import Source as SourceRow
from app.models.schemas import Evidence, FactCheckResult
from app.observability.tracer import traced
from app.retrieval.embeddings import cluster_by_similarity
from app.tools.web_search import search

settings = get_settings()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("fact_checker.md")
SEARCH_RESULTS_PER_VERIFICATION = 3


class _Verdict(BaseModel):
    status: Literal["supported", "unsupported", "outdated"]
    notes: str | None = None


@dataclass
class VerificationOutcome:
    result: FactCheckResult
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None


def _max_fact_checks(mode: str) -> int:
    return settings.MAX_FACT_CHECKS_QUICK if mode == "quick" else settings.MAX_FACT_CHECKS_DEEP


def _pick_representative(cluster: list[Evidence]) -> Evidence:
    return max(cluster, key=lambda ev: ev.confidence)


async def _verify(ctx: RunContext, representative: Evidence) -> VerificationOutcome:
    try:
        results = await search(representative.claim, max_results=SEARCH_RESULTS_PER_VERIFICATION)
    except Exception as exc:
        return VerificationOutcome(
            FactCheckResult(evidence_id=representative.id, status="unverified", notes=f"verification search failed: {exc}")
        )
    if not results:
        return VerificationOutcome(
            FactCheckResult(evidence_id=representative.id, status="unverified", notes="verification search returned no results")
        )

    verifying_url = results[0].get("url")
    combined = "\n\n".join(
        f"{r.get('title', '')}\n{r.get('url', '')}\n{r.get('content') or r.get('raw_content') or ''}" for r in results
    )
    user_prompt = (
        f"Claim to verify: {representative.claim}\n"
        f"Original excerpt it was extracted from: {representative.relevant_excerpt}\n\n"
        f"{FETCHED_CONTENT_INSTRUCTION}\n\n{wrap_fetched_content(combined, 'fact_check_search')}"
    )

    try:
        response = await ctx.llm.generate_structured(
            "fact_check_verification", system=SYSTEM_PROMPT, user=user_prompt, schema=_Verdict
        )
    except Exception as exc:
        return VerificationOutcome(
            FactCheckResult(evidence_id=representative.id, status="unverified", notes=f"verification LLM call failed: {exc}"),
        )

    verdict = response.parsed
    return VerificationOutcome(
        result=FactCheckResult(
            evidence_id=representative.id,
            status=verdict.status,
            verifying_source_url=verifying_url,
            notes=verdict.notes,
        ),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        model=response.model,
    )


@traced("fact_checker")
async def fact_checker_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """§9 cost control: cluster retrieved_evidence (already the survived-
    rerank set, so no separate filter step is needed), prioritize by
    (is_numeric, low_credibility, topic_centrality), verify only the top
    MAX_FACT_CHECKS_{QUICK,DEEP} representatives with one search + one
    fast-tier LLM call each, propagate to every cluster member. Every
    retrieved_evidence item gets a FactCheckResult row — verified ones get a
    real status, everything else gets an explicit "unverified", never a
    silent gap."""
    retrieved = state.get("retrieved_evidence") or []
    if not retrieved:
        return NodeResult(state_update={"fact_check_results": []}, trace_input={"clusters_total": 0})

    evidence_ids = [uuid.UUID(ev.id) for ev in retrieved]
    rows = (await ctx.db.scalars(select(EvidenceRow).where(EvidenceRow.id.in_(evidence_ids)))).all()
    embeddings_by_id = {str(row.id): row.embedding for row in rows if row.embedding is not None}

    sources = (await ctx.db.scalars(select(SourceRow).where(SourceRow.run_id == ctx.run_id))).all()
    credibility_by_source_id = {
        str(s.id): (s.credibility_score if s.credibility_score is not None else 0.5) for s in sources
    }

    # §9 steps 1-2. PRD describes a text-normalize-then-cluster pipeline; this
    # clusters directly on the evidence embeddings retriever already computed
    # instead of a separate lowercase/strip-hedges/canonicalize pass over
    # text — semantic embeddings are already fairly robust to surface
    # differences, and reusing them avoids a second embedding call purely to
    # re-derive something already close to what's in hand.
    clusters = cluster_by_similarity(retrieved, embeddings_by_id, settings.CLAIM_SIMILARITY_THRESHOLD)

    topic_frequency = Counter(ev.sub_question_index for ev in retrieved)
    max_topic_frequency = max(topic_frequency.values(), default=1)

    def _priority(cluster: list[Evidence]) -> float:
        rep = _pick_representative(cluster)
        is_numeric = rep.numeric_value is not None
        credibility = credibility_by_source_id.get(rep.source_id, 0.5)
        centrality = topic_frequency.get(rep.sub_question_index, 0) / max_topic_frequency
        return (2.0 if is_numeric else 0.0) + (1.0 - credibility) + centrality

    ranked_clusters = sorted(clusters, key=_priority, reverse=True)
    cap = _max_fact_checks(state["mode"])
    to_verify, unreached = ranked_clusters[:cap], ranked_clusters[cap:]

    fact_check_results: list[FactCheckResult] = []
    total_input_tokens = 0
    total_output_tokens = 0
    model_used: str | None = None

    for cluster in to_verify:
        representative = _pick_representative(cluster)
        outcome = await _verify(ctx, representative)
        total_input_tokens += outcome.input_tokens
        total_output_tokens += outcome.output_tokens
        if outcome.model:
            model_used = outcome.model

        for member in cluster:
            fcr = FactCheckResult(
                evidence_id=member.id,
                status=outcome.result.status,
                verifying_source_url=outcome.result.verifying_source_url,
                notes=outcome.result.notes,
            )
            fact_check_results.append(fcr)
            ctx.db.add(
                FactCheckResultRow(
                    id=uuid.uuid4(),
                    run_id=ctx.run_id,
                    evidence_id=uuid.UUID(member.id),
                    status=fcr.status,
                    verifying_source_url=fcr.verifying_source_url,
                    notes=fcr.notes,
                )
            )

    for cluster in unreached:
        for member in cluster:
            fcr = FactCheckResult(evidence_id=member.id, status="unverified", notes="not reached within MAX_FACT_CHECKS cap")
            fact_check_results.append(fcr)
            ctx.db.add(
                FactCheckResultRow(
                    id=uuid.uuid4(),
                    run_id=ctx.run_id,
                    evidence_id=uuid.UUID(member.id),
                    status=fcr.status,
                    verifying_source_url=None,
                    notes=fcr.notes,
                )
            )

    # NOTE: no cost_override here, unlike retriever/contradiction_detector.
    # Those mix models within one node (embedding + fast-tier, or fast-tier +
    # reasoning-tier) so a single `model` field would misattribute cost. This
    # node only ever calls one priced model — "fact_check_verification"
    # (always fast-tier) — per representative; the web_search.search() calls
    # in between carry no token cost at all (Tavily isn't in PRICING). If a
    # future phase adds a second priced call here (e.g. a reasoning-tier
    # re-check), it needs cost_override too — don't assume single-model just
    # because this comment says so today.
    return NodeResult(
        state_update={"fact_check_results": fact_check_results},
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        model=model_used,
        trace_input={
            "clusters_total": len(clusters),
            "clusters_verified": len(to_verify),
            "clusters_unreached": len(unreached),
            "max_fact_checks_cap": cap,
            "retrieved_evidence_count": len(retrieved),
        },
    )
