"""Shared `stat` frame count query (PRD §7.3) — used by both the tracer
(after every node, for the live push) and the WS route (as a DB-backed
fallback in the snapshot, when the in-process event bus has no rolling state
for a run — e.g. after a server restart). One definition of "claims_verified"
etc. so the two call sites can't drift apart."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Contradiction, Evidence, FactCheckResult, Source


async def compute_run_stat_counts(db: AsyncSession, run_id) -> dict[str, int]:
    sources, evidence_items, claims_verified, conflicts = (
        await db.execute(
            select(
                select(func.count(Source.id)).where(Source.run_id == run_id).scalar_subquery(),
                select(func.count(Evidence.id)).where(Evidence.run_id == run_id).scalar_subquery(),
                select(func.count(FactCheckResult.id))
                .where(FactCheckResult.run_id == run_id, FactCheckResult.status == "supported")
                .scalar_subquery(),
                select(func.count(Contradiction.id)).where(Contradiction.run_id == run_id).scalar_subquery(),
            )
        )
    ).one()
    return {
        "sources": sources,
        "evidence_items": evidence_items,
        "claims_verified": claims_verified,
        "conflicts": conflicts,
    }
