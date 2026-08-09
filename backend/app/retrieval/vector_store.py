import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Evidence as EvidenceRow


async def vector_search(
    db: AsyncSession,
    run_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int,
) -> list[EvidenceRow]:
    """pgvector HNSW cosine search (§10 step 1), filtered by run_id only.

    Source-type/date filtering for plan.primary_source_required_for isn't
    applied — every source is source_type="web" until academic/data
    researchers exist (Phase 3+), so it would be a no-op today. The parameter
    is intentionally not on this function yet; add it alongside those
    researchers rather than plumbing an inert filter through now.
    """
    stmt = (
        select(EvidenceRow)
        .where(EvidenceRow.run_id == run_id, EvidenceRow.embedding.is_not(None))
        .order_by(EvidenceRow.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    rows = (await db.scalars(stmt)).all()
    return list(rows)
