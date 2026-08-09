import uuid
from collections import defaultdict

from sqlalchemy import select

from app.config import get_settings
from app.credibility.scorer import CredibilitySignals, score_source
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import Evidence as EvidenceRow
from app.models.db_models import Source as SourceRow
from app.observability.tracer import traced
from app.retrieval.embeddings import cosine_similarity, ensure_evidence_embeddings

settings = get_settings()


def _count_corroborating_sources(
    source_id: uuid.UUID, evidence_by_source: dict[uuid.UUID, list[EvidenceRow]]
) -> int:
    """Number of OTHER sources with at least one evidence claim cosine-similar
    to one of this source's claims — Correction #8's whole reason `sources`
    was normalized out of `evidence` in the first place."""
    this_evidence = evidence_by_source.get(source_id, [])
    if not this_evidence:
        return 0
    count = 0
    for other_id, other_evidence in evidence_by_source.items():
        if other_id == source_id:
            continue
        if any(
            cosine_similarity(a.embedding, b.embedding) >= settings.CLAIM_SIMILARITY_THRESHOLD
            for a in this_evidence
            for b in other_evidence
        ):
            count += 1
    return count


@traced("credibility_scorer")
async def credibility_scorer_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """Runs before `retriever` — corroboration-based scoring needs evidence
    embeddings to exist, and this is the first node that needs them, so it's
    the one that pays for computing them. `retriever` reuses the same
    embeddings via the same idempotent ensure_evidence_embeddings() call."""
    emb_usage = await ensure_evidence_embeddings(ctx)

    sources = (await ctx.db.scalars(select(SourceRow).where(SourceRow.run_id == ctx.run_id))).all()
    evidence_rows = (
        await ctx.db.scalars(
            select(EvidenceRow).where(EvidenceRow.run_id == ctx.run_id, EvidenceRow.embedding.is_not(None))
        )
    ).all()

    evidence_by_source: dict[uuid.UUID, list[EvidenceRow]] = defaultdict(list)
    for row in evidence_rows:
        evidence_by_source[row.source_id].append(row)

    scored_count = 0
    total_score = 0.0
    for source in sources:
        corroboration_count = _count_corroborating_sources(source.id, evidence_by_source)
        signals = CredibilitySignals(
            domain=source.domain or "",
            url=source.url,
            source_type=source.source_type or "web",
            publication_date=source.publication_date,
            corroboration_count=corroboration_count,
        )
        source.credibility_score = score_source(signals)
        scored_count += 1
        total_score += source.credibility_score

    return NodeResult(
        state_update={},
        input_tokens=emb_usage.input_tokens,
        model=emb_usage.model,
        trace_input={
            "sources_scored": scored_count,
            "average_credibility_score": (total_score / scored_count) if scored_count else None,
            "evidence_embedded_this_call": emb_usage.input_tokens,
        },
    )
