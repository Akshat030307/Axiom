import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.eval.runner import DATASET_VERSION, run_eval_dataset
from app.models.db_models import EvalRun, User

router = APIRouter(prefix="/api/v1/eval", tags=["eval"])


class EvalRunRequest(BaseModel):
    # Provide to resume a prior "running"/"aborted_cost_ceiling" eval rather
    # than starting a fresh one — see eval/runner.py's resumability note.
    eval_id: uuid.UUID | None = None
    # {question_id: run_id} — score an already-completed run instead of
    # executing a fresh one for that question. See eval/runner.py's
    # run_eval_dataset docstring; any question_id not present here still
    # gets a fresh run.
    existing_run_ids: dict[str, str] | None = None


class EvalRunResponse(BaseModel):
    eval_id: uuid.UUID


class EvalStatusResponse(BaseModel):
    id: uuid.UUID
    dataset_version: str | None
    created_at: datetime
    metrics: dict

    model_config = {"from_attributes": True}


@router.post("/run", response_model=EvalRunResponse, status_code=status.HTTP_201_CREATED)
async def start_eval(
    background_tasks: BackgroundTasks,
    body: EvalRunRequest | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvalRunResponse:
    requested_id = body.eval_id if body else None
    if requested_id is not None:
        eval_run = await db.get(EvalRun, requested_id)
        if eval_run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
        eval_id = eval_run.id
    else:
        eval_id = uuid.uuid4()
        db.add(EvalRun(id=eval_id, dataset_version=DATASET_VERSION, metrics={"status": "running", "per_question": {}}))
        await db.commit()

    # Same fire-and-forget BackgroundTasks pattern as POST /research — see
    # graph/runner.py's docstring on why the task opens its own DB session
    # rather than reusing this request-scoped one.
    existing_run_ids = body.existing_run_ids if body else None
    background_tasks.add_task(run_eval_dataset, eval_id, user.id, existing_run_ids)
    return EvalRunResponse(eval_id=eval_id)


@router.get("/{eval_id}", response_model=EvalStatusResponse)
async def get_eval(
    eval_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EvalStatusResponse:
    eval_run = await db.get(EvalRun, eval_id)
    if eval_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
    return EvalStatusResponse(
        id=eval_run.id, dataset_version=eval_run.dataset_version, created_at=eval_run.created_at, metrics=eval_run.metrics or {}
    )
