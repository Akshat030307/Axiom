import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Integer, cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_owned_run
from app.db.session import get_db
from app.models.db_models import Contradiction, Evidence, FactCheckResult, ResearchRun, Source

router = APIRouter(prefix="/api/v1/research", tags=["evidence"])


class EvidenceSourceResponse(BaseModel):
    id: uuid.UUID
    url: str
    title: str | None
    domain: str | None
    source_type: str | None
    credibility_score: float | None


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    claim: str
    relevant_excerpt: str
    confidence: float | None
    agent: str | None
    topic: str | None
    sub_question_index: int | None
    numeric_value: float | None
    numeric_unit: str | None
    time_period: str | None
    source: EvidenceSourceResponse | None
    fact_check_status: str | None
    fact_check_notes: str | None
    verifying_source_url: str | None


class ContradictionResponse(BaseModel):
    id: uuid.UUID
    topic: str | None
    evidence_a_id: uuid.UUID | None
    evidence_a_claim: str | None
    evidence_b_id: uuid.UUID | None
    evidence_b_claim: str | None
    explanation: str | None
    resolved: bool


@router.get("/{run_id}/evidence", response_model=list[EvidenceResponse])
async def list_evidence(
    run: ResearchRun = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
    sub_question_index: int | None = Query(default=None),
) -> list[EvidenceResponse]:
    # sub_question_index isn't its own DB column (see evidence_extractor.py) —
    # it lives in the metadata JSONB, so the filter casts it out for comparison.
    stmt = (
        select(Evidence, Source, FactCheckResult)
        .outerjoin(Source, Source.id == Evidence.source_id)
        .outerjoin(FactCheckResult, FactCheckResult.evidence_id == Evidence.id)
        .where(Evidence.run_id == run.id)
    )
    if sub_question_index is not None:
        stmt = stmt.where(cast(Evidence.metadata_["sub_question_index"].astext, Integer) == sub_question_index)

    rows = (await db.execute(stmt)).all()

    results = []
    for evidence, source, fact_check in rows:
        results.append(
            EvidenceResponse(
                id=evidence.id,
                claim=evidence.claim,
                relevant_excerpt=evidence.relevant_excerpt,
                confidence=evidence.confidence,
                agent=evidence.agent,
                topic=evidence.topic,
                sub_question_index=(evidence.metadata_ or {}).get("sub_question_index"),
                numeric_value=evidence.numeric_value,
                numeric_unit=evidence.numeric_unit,
                time_period=evidence.time_period,
                source=(
                    EvidenceSourceResponse(
                        id=source.id,
                        url=source.url,
                        title=source.title,
                        domain=source.domain,
                        source_type=source.source_type,
                        credibility_score=source.credibility_score,
                    )
                    if source is not None
                    else None
                ),
                fact_check_status=fact_check.status if fact_check is not None else None,
                fact_check_notes=fact_check.notes if fact_check is not None else None,
                verifying_source_url=fact_check.verifying_source_url if fact_check is not None else None,
            )
        )
    return results


@router.get("/{run_id}/contradictions", response_model=list[ContradictionResponse])
async def list_contradictions(
    run: ResearchRun = Depends(get_owned_run),
    db: AsyncSession = Depends(get_db),
) -> list[ContradictionResponse]:
    EvidenceA = aliased(Evidence)
    EvidenceB = aliased(Evidence)
    rows = (
        await db.execute(
            select(Contradiction, EvidenceA.claim, EvidenceB.claim)
            .outerjoin(EvidenceA, EvidenceA.id == Contradiction.evidence_a_id)
            .outerjoin(EvidenceB, EvidenceB.id == Contradiction.evidence_b_id)
            .where(Contradiction.run_id == run.id)
        )
    ).all()

    return [
        ContradictionResponse(
            id=c.id,
            topic=c.topic,
            evidence_a_id=c.evidence_a_id,
            evidence_a_claim=claim_a,
            evidence_b_id=c.evidence_b_id,
            evidence_b_claim=claim_b,
            explanation=c.explanation,
            resolved=c.resolved,
        )
        for c, claim_a, claim_b in rows
    ]
