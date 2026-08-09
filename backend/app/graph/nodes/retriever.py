import logging

from app.config import get_settings
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.models.schemas import Evidence
from app.observability.tracer import estimate_cost, traced
from app.retrieval.embeddings import ensure_evidence_embeddings
from app.retrieval.hybrid import hybrid_search_for_subquestion
from app.retrieval.reranker import rerank

settings = get_settings()
logger = logging.getLogger(__name__)


@traced("retriever")
async def retriever_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    """§10 hybrid retrieval, run once per sub-question, searching this run's
    whole evidence pool each time (filtered by run_id only, per §10's literal
    spec — not scoped to a topic/sub_question subset). The same evidence item
    can legitimately rank well for more than one sub-question's query; the
    dedupe-by-id step below is what keeps it out of `retrieved_evidence`
    twice.

    Mixes the embedding model (sub-question + any leftover evidence
    embedding) with the fast model (reranking) in one node execution, so it
    computes and hands the tracer its own summed cost via `cost_override`
    rather than letting the tracer's single-model estimate misattribute it.
    """
    plan = state["plan"]
    evidence = state.get("evidence", [])
    evidence_by_id = {ev.id: ev for ev in evidence}

    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    # Should already be a no-op — credibility_scorer runs first and computes
    # these — but idempotent and cheap to confirm rather than assume.
    emb_usage = await ensure_evidence_embeddings(ctx)
    total_input_tokens += emb_usage.input_tokens
    total_cost += estimate_cost(emb_usage.model, emb_usage.input_tokens, 0)

    if not plan.sub_questions or not evidence:
        return NodeResult(
            state_update={"retrieved_evidence": []},
            input_tokens=total_input_tokens,
            cost_override=total_cost,
            trace_input={"per_subquestion": [], "note": "no sub_questions or no evidence to retrieve from"},
        )

    # One batched embedding call for every sub-question, not one per question.
    subq_embed = await ctx.llm.embed(plan.sub_questions)
    total_input_tokens += subq_embed.input_tokens
    total_cost += estimate_cost(subq_embed.model, subq_embed.input_tokens, 0)

    retrieved: list[Evidence] = []
    seen_ids: set[str] = set()
    per_subquestion_diagnostics = []

    for idx, sub_question in enumerate(plan.sub_questions):
        search_result = await hybrid_search_for_subquestion(
            ctx.db,
            ctx.run_id,
            sub_question,
            subq_embed.vectors[idx],
            rrf_k=settings.RRF_K,
            rerank_candidate_limit=settings.RERANK_CANDIDATE_LIMIT,
        )
        reranked_rows, rerank_usage = await rerank(
            ctx.llm, sub_question, search_result.fused, top_k=settings.TOP_K_PER_SUBQUESTION
        )
        total_input_tokens += rerank_usage.input_tokens
        total_output_tokens += rerank_usage.output_tokens
        total_cost += estimate_cost(rerank_usage.model, rerank_usage.input_tokens, rerank_usage.output_tokens)

        new_count = 0
        for row in reranked_rows:
            row_id = str(row.id)
            if row_id in seen_ids:
                continue
            ev = evidence_by_id.get(row_id)
            if ev is None:
                logger.warning("retriever[%s]: evidence row %s not found in state evidence, skipped", ctx.run_id, row_id)
                continue
            seen_ids.add(row_id)
            retrieved.append(ev)
            new_count += 1

        per_subquestion_diagnostics.append(
            {
                "sub_question_index": idx,
                "vector_count": search_result.vector_count,
                "fts_prefilter_count": search_result.fts_prefilter_count,
                "bm25_count": search_result.bm25_count,
                "fused_count": search_result.fused_count,
                "reranked_count": len(reranked_rows),
                "new_evidence_added": new_count,
            }
        )

    return NodeResult(
        state_update={"retrieved_evidence": retrieved},
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        cost_override=total_cost,
        trace_input={"per_subquestion": per_subquestion_diagnostics},
    )
