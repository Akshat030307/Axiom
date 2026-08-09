import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_run
from app.db.session import get_db
from app.models.db_models import Evidence, ResearchRun, Source

router = APIRouter(prefix="/api/v1/research", tags=["sources"])


class SourceResponse(BaseModel):
    id: uuid.UUID
    url: str
    title: str | None
    domain: str | None
    source_type: str | None
    publication_date: str | None
    credibility_score: float | None
    fetched_at: datetime
    evidence_count: int


@router.get("/{run_id}/sources", response_model=list[SourceResponse])
async def list_sources(
    run: ResearchRun = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
) -> list[SourceResponse]:
    rows = (
        await db.execute(
            select(Source, func.count(Evidence.id).label("evidence_count"))
            .outerjoin(Evidence, Evidence.source_id == Source.id)
            .where(Source.run_id == run.id)
            .group_by(Source.id)
            .order_by(Source.credibility_score.desc().nulls_last())
        )
    ).all()

    return [
        SourceResponse(
            id=source.id,
            url=source.url,
            title=source.title,
            domain=source.domain,
            source_type=source.source_type,
            publication_date=source.publication_date,
            credibility_score=source.credibility_score,
            fetched_at=source.fetched_at,
            evidence_count=evidence_count,
        )
        for source, evidence_count in rows
    ]
