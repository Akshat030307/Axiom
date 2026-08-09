from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["web", "academic", "data"]
ResearchMode = Literal["quick", "deep", "academic", "competitive"]
AgentName = Literal["web_researcher", "academic_researcher", "data_researcher"]


class ResearchPlan(BaseModel):
    objective: str
    sub_questions: list[str]
    required_sources: list[SourceType]
    estimated_depth: ResearchMode
    primary_source_required_for: list[str]
    expected_figures: list[str]


class Source(BaseModel):
    id: str
    url: str
    title: str
    domain: str
    source_type: SourceType
    publication_date: str | None = None
    credibility_score: float
    fetched_at: str


class Evidence(BaseModel):
    id: str
    source_id: str
    claim: str
    relevant_excerpt: str
    confidence: float
    agent: AgentName
    topic: str
    # Which plan.sub_questions[i] this evidence was extracted for. topic is
    # LLM-assigned free text and too fragile to group on reliably (a one-word
    # paraphrase means an evidence item silently matches no group) — this is
    # the stable key retriever/fact_checker/contradiction_detector group on.
    # Not persisted as its own DB column (kept in the metadata JSONB instead,
    # see evidence_extractor.py) since nothing needs to query by it in SQL.
    sub_question_index: int | None = None
    numeric_value: float | None = None
    numeric_unit: str | None = None
    time_period: str | None = None
    metadata: dict = Field(default_factory=dict)


# Phase 2+ shapes — not populated by any Phase 1 node, but ResearchState (PRD §5)
# declares fields typed against them, so they must exist for the state schema to
# construct at all.
class FactCheckResult(BaseModel):
    evidence_id: str
    status: Literal["supported", "unsupported", "unverified", "outdated"]
    verifying_source_url: str | None = None
    notes: str | None = None


class Contradiction(BaseModel):
    topic: str
    evidence_a_id: str
    evidence_b_id: str
    explanation: str | None = None
    resolved: bool = False


class Figure(BaseModel):
    id: str
    kind: Literal["chart", "diagram", "source_image"]
    caption: str
    alt_text: str
    file_path: str
    mime_type: str
    spec: dict | None = None
    evidence_ids: list[str]
    source_id: str | None = None
    license_note: str | None = None


class Citation(BaseModel):
    marker: int
    evidence_id: str
    source_id: str
