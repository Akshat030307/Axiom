import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_run
from app.db.session import get_db
from app.models.db_models import Figure, ResearchRun, User

research_figures_router = APIRouter(prefix="/api/v1/research", tags=["figures"])
figures_router = APIRouter(prefix="/api/v1/figures", tags=["figures"])


class FigureResponse(BaseModel):
    id: uuid.UUID
    kind: str
    caption: str
    alt_text: str
    mime_type: str
    evidence_ids: list[uuid.UUID]


@research_figures_router.get("/{run_id}/figures", response_model=list[FigureResponse])
async def list_figures(
    run: ResearchRun = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
) -> list[FigureResponse]:
    rows = (await db.scalars(select(Figure).where(Figure.run_id == run.id))).all()
    return [
        FigureResponse(
            id=f.id, kind=f.kind, caption=f.caption, alt_text=f.alt_text,
            mime_type=f.mime_type, evidence_ids=f.evidence_ids,
        )
        for f in rows
    ]


@figures_router.get("/{figure_id}/file")
async def get_figure_file(
    figure_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Not nested under /research/{run_id}/ (PRD §7.2's own top-level path),
    so ownership is checked by joining through the figure's run rather than
    via get_owned_run — same 404-not-403 contract as everywhere else: a
    figure belonging to another user's run doesn't reveal that it exists."""
    figure = await db.get(Figure, figure_id)
    if figure is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Figure not found")
    run = await db.get(ResearchRun, figure.run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Figure not found")
    return FileResponse(figure.file_path, media_type=figure.mime_type)
