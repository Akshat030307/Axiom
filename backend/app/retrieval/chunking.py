import re

from app.retrieval.bm25 import score_texts

CHUNK_SIZE_CHARS = 600
TOP_K_CHUNKS = 5

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS) -> list[str]:
    """Paragraph-aware windows: split on blank lines first (trafilatura's
    output is already paragraph-separated), then pack consecutive paragraphs
    into ~chunk_size-char windows so a single-sentence paragraph doesn't
    become its own tiny, context-free chunk."""
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if current and current_len + len(para) > chunk_size:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def select_relevant_chunks(text: str, query: str, top_k: int = TOP_K_CHUNKS) -> str:
    """Trims a fetched page down to the sections most relevant to the
    sub-question it was fetched for, before it reaches evidence_extractor —
    the Phase 1 smoke test measured extraction at 51% of run cost because
    full (already 8000-char-capped) page text was batched in verbatim.

    BM25-scores each paragraph-window against `query` (free — no LLM or
    embedding call, reuses rank_bm25) and keeps the top_k, restored to
    original reading order so extraction still sees coherent context rather
    than a shuffled bag of fragments. Pages already shorter than top_k chunks
    are returned unchanged — no point filtering something already small.

    This is keyword matching, not semantic — a fact stated in vocabulary that
    doesn't overlap the sub-question's wording can still be dropped. Verify
    empirically (evidence count before/after) before trusting this blindly.
    """
    chunks = chunk_text(text)
    if len(chunks) <= top_k:
        return text

    scores = score_texts(chunks, query)
    ranked_indices = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:top_k]
    ranked_indices.sort()
    return "\n\n".join(chunks[i] for i in ranked_indices)
