import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_run
from app.db.session import get_db
from app.graph.runner import execute_research_run
from app.models.db_models import ResearchRun, User
from app.models.schemas import ResearchMode

router = APIRouter(prefix="/api/v1/research", tags=["research"])


class CreateRunRequest(BaseModel):
    query: str
    mode: ResearchMode = "quick"


class CreateRunResponse(BaseModel):
    run_id: uuid.UUID


class RunStatusResponse(BaseModel):
    run_id: uuid.UUID
    status: str
    mode: str
    query: str
    started_at: datetime
    completed_at: datetime | None
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: float
    latency_seconds: float | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_run(cls, run: ResearchRun) -> "RunStatusResponse":
        return cls(
            run_id=run.id,
            status=run.status,
            mode=run.mode,
            query=run.query,
            started_at=run.started_at,
            completed_at=run.completed_at,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            cost_estimate_usd=float(run.cost_estimate_usd),
            latency_seconds=float(run.latency_seconds) if run.latency_seconds is not None else None,
        )


@router.post("", response_model=CreateRunResponse, status_code=status.HTTP_201_CREATED)
async def create_research(
    body: CreateRunRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateRunResponse:
    run_id = uuid.uuid4()
    db.add(ResearchRun(id=run_id, user_id=user.id, query=body.query, mode=body.mode, status="pending"))
    await db.commit()

    # Runs entirely detached from this request's DB session — see
    # app/graph/runner.py's docstring for why it opens its own.
    background_tasks.add_task(execute_research_run, run_id, user.id, body.query, body.mode)
    return CreateRunResponse(run_id=run_id)


@router.get("/{run_id}", response_model=RunStatusResponse)
async def get_research_status(run: ResearchRun = Depends(get_owned_run)) -> RunStatusResponse:
    return RunStatusResponse.from_run(run)
