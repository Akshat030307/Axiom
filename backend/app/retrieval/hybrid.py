import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Evidence as EvidenceRow
from app.retrieval.bm25 import bm25_rank, tokenize
from app.retrieval.vector_store import vector_search

VECTOR_TOP_K = 50
FTS_PREFILTER_LIMIT = 200
BM25_TOP_K = 50


def _or_tsquery_expr(query_text: str) -> str | None:
    """Builds a `word1 | word2 | ...` expression for to_tsquery. Returns None
    for empty input (nothing to query).

    The bug this replaced: plainto_tsquery ANDs every word in the input.
    Fine for a short, precise query — wrong for a ~20-word sub-question
    matched against short evidence claims, where no single claim's tsvector
    will ever contain all ~15+ AND-ed lexemes simultaneously. Verified
    against the live DB: the exact same plainto_tsquery call, run directly in
    psql (not through SQLAlchemy — this was never a parameter-binding bug),
    returned 0 rows for every real sub-question in a test run. Switching the
    terms to OR and letting ts_rank_cd order by how many/how well they match
    is the correct shape for a "cheap prefilter", per §10 — it's supposed to
    cast a wide net; real ranking is bm25_rank's job on whatever this
    returns. to_tsquery still runs each token through the 'english' text
    search config (stemming, stopword removal) same as to_tsvector, so
    un-stemmed input words are handled correctly without extra work here.
    Tokens are pre-restricted to [a-z0-9]+ by bm25.tokenize(), so the joined
    string can't contain tsquery operator syntax beyond the `|` we insert.
    """
    tokens = list(dict.fromkeys(tokenize(query_text)))  # dedupe, preserve order
    if not tokens:
        return None
    return " | ".join(tokens)


async def fts_prefilter(
    db: AsyncSession, run_id: uuid.UUID, query_text: str, limit: int = FTS_PREFILTER_LIMIT
) -> list[EvidenceRow]:
    """Postgres FTS on the generated search_tsv column — a cheap prefilter
    ONLY (Correction #6: this is ts_rank_cd, not BM25; real BM25 scoring
    happens in bm25.bm25_rank over whatever this returns). search_tsv is
    deliberately not mapped on the Evidence ORM class (it's DB-generated,
    never written to), so it's referenced here via raw column-name SQL
    fragments rather than an ORM attribute.
    """
    tsquery_expr = _or_tsquery_expr(query_text)
    if tsquery_expr is None:
        return []

    match_clause = text("search_tsv @@ to_tsquery('english', :fts_query)")
    rank_clause = text("ts_rank_cd(search_tsv, to_tsquery('english', :fts_query)) DESC")
    stmt = (
        select(EvidenceRow)
        .where(EvidenceRow.run_id == run_id)
        .where(match_clause)
        .order_by(rank_clause)
        .limit(limit)
        .params(fts_query=tsquery_expr)
    )
    rows = (await db.scalars(stmt)).all()
    return list(rows)


def reciprocal_rank_fusion(ranked_lists: list[list[EvidenceRow]], k: int) -> list[EvidenceRow]:
    """score = sum(1 / (k + rank)) across every list a row appears in,
    rank 1-indexed. A row missing from a list simply contributes 0 from it."""
    scores: dict[uuid.UUID, float] = defaultdict(float)
    rows_by_id: dict[uuid.UUID, EvidenceRow] = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked, start=1):
            scores[row.id] += 1 / (k + rank)
            rows_by_id[row.id] = row
    return sorted(rows_by_id.values(), key=lambda row: scores[row.id], reverse=True)


@dataclass
class HybridSearchResult:
    fused: list[EvidenceRow]
    vector_count: int
    fts_prefilter_count: int
    bm25_count: int
    fused_count: int


async def hybrid_search_for_subquestion(
    db: AsyncSession,
    run_id: uuid.UUID,
    query_text: str,
    query_embedding: list[float],
    rrf_k: int,
    rerank_candidate_limit: int,
) -> HybridSearchResult:
    """§10 steps 1-4 for a single sub-question. Step 5 (LLM rerank) is the
    caller's job (retriever.py) — this only fuses and trims to the candidate
    set reranking will see."""
    vector_hits = await vector_search(db, run_id, query_embedding, top_k=VECTOR_TOP_K)
    fts_candidates = await fts_prefilter(db, run_id, query_text, limit=FTS_PREFILTER_LIMIT)
    bm25_hits = bm25_rank(fts_candidates, query_text, top_k=BM25_TOP_K)

    fused = reciprocal_rank_fusion([vector_hits, bm25_hits], k=rrf_k)[:rerank_candidate_limit]

    return HybridSearchResult(
        fused=fused,
        vector_count=len(vector_hits),
        fts_prefilter_count=len(fts_candidates),
        bm25_count=len(bm25_hits),
        fused_count=len(fused),
    )
