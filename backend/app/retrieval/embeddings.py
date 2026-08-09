from dataclasses import dataclass

import numpy as np
from sqlalchemy import select

from app.graph.run_context import RunContext
from app.models.db_models import Evidence as EvidenceRow
from app.models.schemas import Evidence


@dataclass
class EmbeddingUsage:
    input_tokens: int = 0
    model: str | None = None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Shared by credibility_scorer (corroboration counting), fact_checker,
    and contradiction_detector (both cluster claims) — all compare evidence
    embeddings pairwise."""
    va, vb = np.array(a), np.array(b)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def cluster_by_similarity(
    evidence: list[Evidence], embeddings_by_id: dict[str, list[float]], threshold: float
) -> list[list[Evidence]]:
    """Greedy clustering: each item joins the first existing cluster whose
    representative (first member) it's cosine-similar to at or above
    threshold; otherwise it starts a new cluster. O(n^2) — fine for the small
    evidence sets this runs over (retrieved_evidence, bounded by
    TOP_K_PER_SUBQUESTION x len(sub_questions)).

    Shared by fact_checker (near-duplicate claim clustering, tight threshold
    — collapsing restatements of the same fact) and contradiction_detector
    (claim-subject clustering, loose threshold — "battery capacity is 30.2
    kWh" and "... is 45 kWh" are semantically near but not identical). Same
    mechanism, different threshold, different input subset and purpose.
    """
    clusters: list[list[Evidence]] = []
    for ev in evidence:
        emb = embeddings_by_id.get(ev.id)
        placed = False
        if emb is not None:
            for cluster in clusters:
                rep_emb = embeddings_by_id.get(cluster[0].id)
                if rep_emb is not None and cosine_similarity(emb, rep_emb) >= threshold:
                    cluster.append(ev)
                    placed = True
                    break
        if not placed:
            clusters.append([ev])
    return clusters


async def ensure_evidence_embeddings(ctx: RunContext) -> EmbeddingUsage:
    """Batch-embeds any of this run's evidence rows missing an embedding,
    updating them in place. Idempotent — safe to call from more than one node
    (credibility_scorer and retriever both need embeddings); a second call
    after the first has already embedded everything does one cheap SELECT
    that finds nothing missing and returns zero usage."""
    rows = (
        await ctx.db.scalars(
            select(EvidenceRow).where(EvidenceRow.run_id == ctx.run_id, EvidenceRow.embedding.is_(None))
        )
    ).all()
    if not rows:
        return EmbeddingUsage()

    result = await ctx.llm.embed([row.claim for row in rows])
    for row, vector in zip(rows, result.vectors):
        row.embedding = vector

    return EmbeddingUsage(input_tokens=result.input_tokens, model=result.model)
