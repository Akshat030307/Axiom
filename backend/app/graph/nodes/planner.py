from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.db_models import ResearchRun
from app.models.schemas import ResearchPlan
from app.observability.tracer import traced

SYSTEM_PROMPT = load_prompt("planner.md")

SUBQUESTION_TARGET = {
    "quick": "3-5",
    "deep": "8-12",
    "academic": "6-10",
    "competitive": "8-12",
}


@traced("planner")
async def planner_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    mode = state["mode"]
    user_prompt = (
        f"Research query: {state['query']}\n"
        f"Mode: {mode} (target {SUBQUESTION_TARGET[mode]} sub-questions)\n"
    )
    response = await ctx.llm.generate_structured(
        "planning", system=SYSTEM_PROMPT, user=user_prompt, schema=ResearchPlan
    )

    # research_runs.plan already existed (JSONB) but nothing ever wrote to
    # it — the only place html_renderer.py can read a real title from at
    # export time, since that path only has the ResearchRun row, not the
    # graph's in-memory state.
    plan_dict = response.parsed.model_dump()
    run = await ctx.db.get(ResearchRun, ctx.run_id)
    if run is not None:
        run.plan = plan_dict
    ctx.events.plan_ready(plan=plan_dict)

    return NodeResult(
        state_update={"plan": response.parsed, "status": "planning_complete"},
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        model=response.model,
    )
