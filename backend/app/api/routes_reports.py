from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_run
from app.db.session import get_db
from app.models.db_models import Report, ResearchRun

router = APIRouter(prefix="/api/v1/research", tags=["reports"])


class ReportResponse(BaseModel):
    markdown: str
    citations: list
    figures: list = []


@router.get("/{run_id}/report", response_model=ReportResponse)
async def get_report(
    run: ResearchRun = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    report = await db.scalar(
        select(Report).where(Report.run_id == run.id).order_by(Report.created_at.desc())
    )
    if report is None:
        detail = "Report not ready yet" if run.status in ("pending", "running") else "No report was produced for this run"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    return ReportResponse(markdown=report.content_markdown, citations=report.citations, figures=[])
