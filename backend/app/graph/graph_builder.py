from typing import Awaitable, Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.citation_validator import (
    citation_validator_node,
    force_finalize_node,
    route_after_validation,
)
from app.graph.nodes.evidence_extractor import evidence_extractor_node
from app.graph.nodes.planner import planner_node
from app.graph.nodes.synthesizer import synthesizer_node
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
    itself is long-lived and shared across runs."""
    builder = StateGraph(ResearchState)

    builder.add_node("planner", _bind(planner_node, ctx))
    builder.add_node("web_researcher", _bind(web_researcher_node, ctx))
    builder.add_node("evidence_extractor", _bind(evidence_extractor_node, ctx))
    builder.add_node("synthesizer", _bind(synthesizer_node, ctx))
    builder.add_node("citation_validator", _bind(citation_validator_node, ctx))
    builder.add_node("force_finalize", _bind(force_finalize_node, ctx))

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "web_researcher")
    builder.add_edge("web_researcher", "evidence_extractor")
    builder.add_edge("evidence_extractor", "synthesizer")
    builder.add_edge("synthesizer", "citation_validator")
    builder.add_conditional_edges(
        "citation_validator",
        route_after_validation,
        {"done": END, "retry": "synthesizer", "finalize": "force_finalize"},
    )
    builder.add_edge("force_finalize", END)

    return builder.compile(checkpointer=checkpointer)
