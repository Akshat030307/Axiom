import re

from rank_bm25 import BM25Okapi

from app.models.db_models import Evidence as EvidenceRow

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def score_texts(candidates: list[str], query: str) -> list[float]:
    """Real BM25Okapi score of `query` against each of `candidates`, in the
    same order in/out. Correction #6: this — not Postgres ts_rank_cd — is
    where actual BM25 ranking happens; callers only ever hand this an
    already-narrowed candidate set (FTS prefilter for evidence, or a single
    page's chunks), never the whole evidence table."""
    if not candidates:
        return []
    tokenized_corpus = [tokenize(c) for c in candidates]
    bm25 = BM25Okapi(tokenized_corpus)
    return list(bm25.get_scores(tokenize(query)))


def bm25_rank(candidates: list[EvidenceRow], query: str, top_k: int) -> list[EvidenceRow]:
    """Scores each candidate's claim+excerpt against `query`, returns the
    top_k EvidenceRow objects, best first. `candidates` is expected to already
    be the FTS-prefiltered set (§10 step 2), not the full run's evidence."""
    texts = [f"{c.claim} {c.relevant_excerpt}" for c in candidates]
    scores = score_texts(texts, query)
    ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
    return [row for row, _ in ranked[:top_k]]
