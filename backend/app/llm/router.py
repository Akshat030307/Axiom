from dataclasses import dataclass
from typing import Literal

from app.config import Settings

Tier = Literal["reasoning", "fast"]


@dataclass(frozen=True)
class Route:
    tier: Tier
    effort_field: str
    max_completion_tokens: int


# PRD §13 ROUTES, trimmed to the tasks Phase 1 nodes actually issue, extended
# with a per-task max_completion_tokens cap. A single global cap can't serve
# both a ~200-token planner call and a full multi-citation report — and since
# reasoning tokens bill at output rates, this is a cost/latency knob as much
# as a truncation guard (PRD §13: "a slightly different prompt can 10x that
# [reasoning-token] number"). citation_validator is pure Python (no LLM call),
# so it has no entry here.
ROUTES: dict[str, Route] = {
    "planning": Route(tier="reasoning", effort_field="EFFORT_PLANNING", max_completion_tokens=2000),
    "synthesis": Route(tier="reasoning", effort_field="EFFORT_SYNTHESIS", max_completion_tokens=16000),
    "extraction": Route(tier="fast", effort_field="EFFORT_EXTRACTION", max_completion_tokens=3000),
    # Phase 2 additions —
    "reranking": Route(tier="fast", effort_field="EFFORT_EXTRACTION", max_completion_tokens=1500),
    "fact_check_verification": Route(tier="fast", effort_field="EFFORT_VERIFICATION", max_completion_tokens=800),
    "classification": Route(tier="fast", effort_field="EFFORT_EXTRACTION", max_completion_tokens=1000),
    "contradiction_resolution": Route(tier="reasoning", effort_field="EFFORT_CONTRADICTION", max_completion_tokens=1500),
    # Phase 3 eval — one batched call per report (§17 citation_accuracy), not
    # a call per citation, so a report with dozens of markers stays cheap.
    "citation_judgment": Route(tier="fast", effort_field="EFFORT_EXTRACTION", max_completion_tokens=2000),
    # Figures (PRD §8) — figure_planner reasons about which figures the
    # report needs (same tier as planning/synthesis); chart_spec is one
    # fast-tier call per planned figure, capped by MAX_FIGURES_PER_REPORT.
    # 1500 was observed to be too low in practice: the reasoning-tier model
    # spent its entire budget on internal reasoning tokens (PRD §3.1's
    # warning) and never reached the structured output, failing with
    # finish_reason=length on a real 44-evidence-item test. Raised to give
    # the reasoning process headroom before it has to emit anything.
    "figure_planning": Route(tier="reasoning", effort_field="EFFORT_PLANNING", max_completion_tokens=4000),
    "chart_spec": Route(tier="fast", effort_field="EFFORT_EXTRACTION", max_completion_tokens=1200),
}


@dataclass
class ModelChoice:
    model: str
    tier: Tier
    reasoning_effort: str | None  # None means: do not pass reasoning_effort at all
    max_completion_tokens: int


def resolve(task: str, settings: Settings) -> ModelChoice:
    route = ROUTES[task]
    model = settings.OPENAI_MODEL_REASONING if route.tier == "reasoning" else settings.OPENAI_MODEL_FAST
    effort = getattr(settings, route.effort_field)
    return ModelChoice(
        model=model,
        tier=route.tier,
        reasoning_effort=None if effort == "none" else effort,
        max_completion_tokens=route.max_completion_tokens,
    )
