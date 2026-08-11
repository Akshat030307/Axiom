from typing import Awaitable, Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.citation_validator import (
    citation_validator_node,
    force_finalize_node,
    route_after_validation,
)
from app.graph.nodes.chart_generator import chart_generator_node
from app.graph.nodes.contradiction_detector import contradiction_detector_node
from app.graph.nodes.credibility_scorer import credibility_scorer_node
from app.graph.nodes.diagram_generator import diagram_generator_node
from app.graph.nodes.evidence_extractor import evidence_extractor_node
from app.graph.nodes.fact_checker import fact_checker_node
from app.graph.nodes.figure_planner import figure_planner_node
from app.graph.nodes.illustration_planner import illustration_planner_node
from app.graph.nodes.image_generator import image_generator_node
from app.graph.nodes.planner import planner_node
from app.graph.nodes.retriever import retriever_node
from app.graph.nodes.synthesizer import synthesizer_node
from app.graph.nodes.web_image_fetcher import web_image_fetcher_node
from app.graph.nodes.web_researcher import web_researcher_node
from app.graph.run_context import RunContext
from app.graph.state import ResearchState

NodeFn = Callable[[ResearchState, RunContext], Awaitable[dict]]


def _bind(node_fn: NodeFn, ctx: RunContext) -> Callable[[ResearchState], Awaitable[dict]]:
    """LangGraph calls nodes as `fn(state)`. Our node functions are
    `fn(state, ctx)` so the per-run RunContext (DB session, LLM provider,
    trace seq counter) can be threaded in without putting runtime objects into
    ResearchState, which must stay plain data."""

    async def bound(state: ResearchState) -> dict:
        return await node_fn(state, ctx)

    return bound


def build_graph(ctx: RunContext, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    """Rebuilt per run (cheap — no I/O) so each run's node closures capture
    that run's own RunContext/DB session (see RunContext's docstring on why a
    request-scoped session can't be reused here). The checkpointer instance
    itself is long-lived and shared across runs.

    Phase 2 topology, matching PRD §8's node listing order: credibility_scorer
    runs before retriever because corroboration-based scoring needs evidence
    embeddings and is the first node that needs them (retriever reuses them —
    ensure_evidence_embeddings is idempotent); fact_checker and
    contradiction_detector run on retrieved_evidence, before synthesizer, so
    their output can inform the report (contradictions get their own section).

    figure_planner/chart_generator also run before synthesizer, for the same
    reason: the synthesizer needs the finished `figures` list (ids + captions)
    to place `figure://{id}` markers while it writes, not after.

    illustration_planner/image_generator run right after chart_generator, one
    hop later in the same "before synthesizer" region — same reason, but kept
    as a fully separate node pair (not folded into figure_planner/
    chart_generator) because illustrations have no equivalent to
    chart_generator's value-grounding check: there's no way to verify a
    generated image doesn't misrepresent the evidence, so that pipeline is
    deliberately isolated rather than sharing types/validation with the
    chart pipeline. diagram_generator remains out of scope.

    web_image_fetcher runs right after image_generator, pairing each AI
    illustration with a real photo found via Tavily image search — a
    lightweight stand-in for the PRD's original image_harvester (which
    scraped <img> tags from already-fetched pages and was never built).
    Depends on image_generator's output (it pairs against the illustrations
    that node just produced), so it can't run any earlier in this region.

    diagram_generator sits right after chart_generator, both consuming
    figure_planner's output (chart_generator filters to kind="chart",
    diagram_generator to kind="diagram") — grouped with the
    evidence-grounded figure pipeline rather than the illustration/photo
    pipeline, since a diagram is Mermaid source the model wrote (rendered
    deterministically by mmdc, not by an image-generation model) and is
    meant to be factually accurate, unlike an illustration.
    """
    builder = StateGraph(ResearchState)

    builder.add_node("planner", _bind(planner_node, ctx))
    builder.add_node("web_researcher", _bind(web_researcher_node, ctx))
    builder.add_node("evidence_extractor", _bind(evidence_extractor_node, ctx))
    builder.add_node("credibility_scorer", _bind(credibility_scorer_node, ctx))
    builder.add_node("retriever", _bind(retriever_node, ctx))
    builder.add_node("fact_checker", _bind(fact_checker_node, ctx))
    builder.add_node("contradiction_detector", _bind(contradiction_detector_node, ctx))
    builder.add_node("figure_planner", _bind(figure_planner_node, ctx))
    builder.add_node("chart_generator", _bind(chart_generator_node, ctx))
    builder.add_node("diagram_generator", _bind(diagram_generator_node, ctx))
    builder.add_node("illustration_planner", _bind(illustration_planner_node, ctx))
    builder.add_node("image_generator", _bind(image_generator_node, ctx))
    builder.add_node("web_image_fetcher", _bind(web_image_fetcher_node, ctx))
    builder.add_node("synthesizer", _bind(synthesizer_node, ctx))
    builder.add_node("citation_validator", _bind(citation_validator_node, ctx))
    builder.add_node("force_finalize", _bind(force_finalize_node, ctx))

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "web_researcher")
    builder.add_edge("web_researcher", "evidence_extractor")
    builder.add_edge("evidence_extractor", "credibility_scorer")
    builder.add_edge("credibility_scorer", "retriever")
    builder.add_edge("retriever", "fact_checker")
    builder.add_edge("fact_checker", "contradiction_detector")
    builder.add_edge("contradiction_detector", "figure_planner")
    builder.add_edge("figure_planner", "chart_generator")
    builder.add_edge("chart_generator", "diagram_generator")
    builder.add_edge("diagram_generator", "illustration_planner")
    builder.add_edge("illustration_planner", "image_generator")
    builder.add_edge("image_generator", "web_image_fetcher")
    builder.add_edge("web_image_fetcher", "synthesizer")
    builder.add_edge("synthesizer", "citation_validator")
    builder.add_conditional_edges(
        "citation_validator",
        route_after_validation,
        {"done": END, "retry": "synthesizer", "finalize": "force_finalize"},
    )
    builder.add_edge("force_finalize", END)

    return builder.compile(checkpointer=checkpointer)
