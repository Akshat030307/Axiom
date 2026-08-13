from typing import Literal

from pydantic import BaseModel, Field, model_validator

SourceType = Literal["web", "academic", "data"]
ResearchMode = Literal["quick", "deep", "academic", "competitive"]
AgentName = Literal["web_researcher", "academic_researcher", "data_researcher"]


class ResearchPlan(BaseModel):
    # A real report title, distinct from the user's raw query — a casual
    # input like "make a report on semiconductors" shouldn't become the
    # PDF's literal <h1> (see html_renderer.py, which reads this rather
    # than run.query for exactly that reason).
    title: str
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
    # "illustration" is kept for backward compatibility with figures rows
    # created before image_generator switched from AI generation to finding
    # a real diagram (see reference_diagram) — no new figure is ever created
    # with kind="illustration" going forward, but old reports still have them.
    kind: Literal["chart", "diagram", "source_image", "illustration", "reference_diagram"]
    caption: str
    alt_text: str
    file_path: str
    mime_type: str
    spec: dict | None = None
    evidence_ids: list[str]
    source_id: str | None = None
    license_note: str | None = None
    # Set only on a kind="source_image" figure fetched to accompany a
    # specific kind="illustration" figure (see web_image_fetcher.py) — points
    # at that illustration's id. Null for every other figure, including a
    # standalone source_image with no illustration pairing.
    paired_figure_id: str | None = None


# kind excludes "source_image" (rather than the full Figure.kind Literal)
# because this build skips image_harvester entirely — OpenAI's strict
# structured-output mode then makes it *impossible* for figure_planner to
# request a source_image, rather than relying on a prompt instruction alone.
class FigureRequest(BaseModel):
    kind: Literal["chart", "diagram"]
    intent: str
    evidence_ids: list[str]
    caption: str


# Deliberately its own type, not a `kind` variant of FigureRequest: chart
# requests validate against real Evidence.numeric_value (see ChartSpec's
# grounding check in chart_generator.py) and illustration requests cannot —
# image_generator finds a real, existing diagram via search rather than
# plotting evidence values, so there's no equivalent way to verify the found
# diagram's every detail matches the evidence, only that it matches the
# search query. Keeping the types apart means grounding-related code can
# keep assuming "chart" without a stray branch quietly forgetting to exclude
# illustrations.
class IllustrationRequest(BaseModel):
    intent: str
    evidence_ids: list[str]
    caption: str


# Structured output of the search-query-writing step (image_generator.py) —
# never passed directly to Wikimedia Commons from the planner, so a second
# LLM call can turn a mood/subject-oriented IllustrationRequest into a
# keyword-oriented search query real diagrams are actually indexed under
# (diagram_search_writer.md).
class DiagramSearchQuery(BaseModel):
    query: str
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


# The LLM emits Mermaid *source* (text), never pixels — figures/diagram_
# renderer.py renders it deterministically with mmdc. That's the entire
# point relative to image_generator's illustrations: a diffusion image model
# reliably mangles rendered text and precise structure, but a diagram
# rendered from the model's own text is exactly the text/boxes/arrows it
# wrote, nothing lost in an image-generation step. The model can still be
# factually wrong about the domain (same risk as any LLM-authored prose in
# the report), but it isn't at risk of the image *renderer* introducing new
# errors on top of that.
class DiagramSpec(BaseModel):
    diagram_type: Literal["flowchart", "sequenceDiagram", "timeline", "mindmap", "quadrantChart"]
    title: str
    mermaid_source: str
    evidence_ids: list[str]


class Citation(BaseModel):
    marker: int
    evidence_id: str
    source_id: str
