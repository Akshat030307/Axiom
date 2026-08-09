import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_run
from app.db.session import get_db
from app.models.db_models import NodeTrace, ResearchRun

router = APIRouter(prefix="/api/v1/research", tags=["trace"])


class NodeTraceResponse(BaseModel):
    id: uuid.UUID
    node_name: str
    seq: int
    input: dict | str | None
    output: dict | str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int | None
    cost_usd: float | None
    status: str | None
    error: str | None
    started_at: datetime | None
    ended_at: datetime | None

    @classmethod
    def from_row(cls, row: NodeTrace) -> "NodeTraceResponse":
        return cls(
            id=row.id,
            node_name=row.node_name,
            seq=row.seq,
            input=row.input,
            output=row.output,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            latency_ms=row.latency_ms,
            cost_usd=float(row.cost_usd) if row.cost_usd is not None else None,
            status=row.status,
            error=row.error,
            started_at=row.started_at,
            ended_at=row.ended_at,
        )


@router.get("/{run_id}/trace", response_model=list[NodeTraceResponse])
async def get_trace(
    run: ResearchRun = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
) -> list[NodeTraceResponse]:
    rows = (
        await db.scalars(select(NodeTrace).where(NodeTrace.run_id == run.id).order_by(NodeTrace.seq))
    ).all()
    return [NodeTraceResponse.from_row(row) for row in rows]
