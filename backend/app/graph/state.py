import operator
from typing import Annotated, Literal, TypedDict

from app.models.schemas import (
    Citation,
    Contradiction,
    Evidence,
    FactCheckResult,
    Figure,
    FigureRequest,
    IllustrationRequest,
    ResearchPlan,
)


class ResearchState(TypedDict, total=False):
    run_id: str
    user_id: str
    query: str
    mode: Literal["quick", "deep", "academic", "competitive"]
    highlight_enabled: bool
    plan: ResearchPlan

    # --- fan-in keys: MUST have reducers — Phase 1 has no concurrent writers,
    # but the reducers are kept per PRD §5 so the shape doesn't change when
    # Phase 3 adds parallel researcher fan-out via Send(). ---
    raw_findings: Annotated[list[dict], operator.add]
    evidence: Annotated[list[Evidence], operator.add]
    figures: Annotated[list[Figure], operator.add]
    errors: Annotated[list[str], operator.add]

    # --- sequential keys: last-write-wins is correct ---
    deduped_evidence: list[Evidence]
    retrieved_evidence: list[Evidence]
    fact_check_results: list[FactCheckResult]
    contradictions: list[Contradiction]
    figure_requests: list[FigureRequest]
    illustration_requests: list[IllustrationRequest]
    report_markdown: str
    citations: list[Citation]
    citation_retry_count: int
    citation_validation_passed: bool
    # Populated by citation_validator on failure so a retry is a targeted
    # correction instead of a blind re-roll of an identical prompt — see
    # synthesizer.py's _format_retry_feedback for how these are consumed.
    citation_flagged_sentences: list[str]
    citation_unresolved_markers: list[int]
    status: str
