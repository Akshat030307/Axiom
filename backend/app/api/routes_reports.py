from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_run
from app.config import get_settings
from app.db.session import get_db
from app.export.html_renderer import render_report_html
from app.export.pdf_exporter import render_pdf
from app.models.db_models import Report, ResearchRun

router = APIRouter(prefix="/api/v1/research", tags=["reports"])
settings = get_settings()


class ReportResponse(BaseModel):
    markdown: str
    citations: list
    figures: list = []


class ExportPdfResponse(BaseModel):
    download_url: str


async def _get_report_or_404(run: ResearchRun, db: AsyncSession) -> Report:
    report = await db.scalar(select(Report).where(Report.run_id == run.id).order_by(Report.created_at.desc()))
    if report is None:
        detail = "Report not ready yet" if run.status in ("pending", "running") else "No report was produced for this run"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return report


def _pdf_path(run_id) -> Path:
    return Path(settings.EXPORTS_DIR) / f"{run_id}.pdf"


@router.get("/{run_id}/report", response_model=ReportResponse)
async def get_report(
    run: ResearchRun = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    report = await _get_report_or_404(run, db)
    return ReportResponse(markdown=report.content_markdown, citations=report.citations, figures=[])


@router.post("/{run_id}/report/pdf", response_model=ExportPdfResponse)
async def export_report_pdf(
    run: ResearchRun = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
) -> ExportPdfResponse:
    """Synchronous, not a Celery task, matching the rest of this codebase's
    single-process simplification (see events.py's module docstring) —
    there is no worker process to hand this off to. Rendering a report this
    size takes a couple of seconds, well within a normal request timeout."""
    report = await _get_report_or_404(run, db)
    html = await render_report_html(db, run, report.content_markdown)
    await render_pdf(html, _pdf_path(run.id))
    return ExportPdfResponse(download_url=f"/api/v1/research/{run.id}/report/pdf/file")


@router.get("/{run_id}/report/pdf/file")
async def get_report_pdf_file(run: ResearchRun = Depends(get_owned_run)) -> FileResponse:
    path = _pdf_path(run.id)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF not generated yet — export it first")
    return FileResponse(path, media_type="application/pdf", filename=f"research-{run.id}.pdf")
