from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


# kind is constrained to "chart" only (rather than the full Figure.kind
# Literal) because this build skips image_harvester and diagram_generator
# entirely — OpenAI's strict structured-output mode then makes it
# *impossible* for figure_planner to request anything this codebase can't
# actually produce, rather than relying on a prompt instruction alone.
class FigureRequest(BaseModel):
    kind: Literal["chart"]
    intent: str
    evidence_ids: list[str]
    caption: str


class ChartSeries(BaseModel):
    name: str
    values: list[float]


# PRD §11.1 — the LLM emits this, never plotting code; figures/chart_renderer.py
# renders it with matplotlib. Value-provenance (every number traces to a real
# Evidence.numeric_value) is enforced by chart_generator.py, not here — this
# model only validates internal shape consistency.
class ChartSpec(BaseModel):
    chart_type: Literal["bar", "grouped_bar", "line", "stacked_area", "scatter", "pie", "horizontal_bar"]
    title: str
    x_label: str | None = None
    y_label: str | None = None
    unit: str | None = None
    series: list[ChartSeries]
    categories: list[str]
    source_note: str
    evidence_ids: list[str]

    @model_validator(mode="after")
    def lengths_match(self) -> "ChartSpec":
        for s in self.series:
            if len(s.values) != len(self.categories):
                raise ValueError("series length must equal categories length")
        return self


class Citation(BaseModel):
    marker: int
    evidence_id: str
    source_id: str
