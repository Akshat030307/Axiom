import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.graph.nodes._prompts import load_prompt
from app.llm.provider import LLMProvider
from app.models.db_models import Evidence as EvidenceRow

SYSTEM_PROMPT = load_prompt("reranker.md")
logger = logging.getLogger(__name__)

WINDOW_SIZE = 20
EXCERPT_PREVIEW_CHARS = 300


class _RankedItem(BaseModel):
    index: int
    relevance_score: float = Field(ge=0, le=1)


class _RerankResult(BaseModel):
    ranked: list[_RankedItem]


@dataclass
class RerankUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None


def _build_prompt(sub_question: str, window: list[EvidenceRow]) -> str:
    lines = [f"Sub-question: {sub_question}", "", "Candidates:"]
    for i, row in enumerate(window):
        excerpt = (row.relevant_excerpt or "")[:EXCERPT_PREVIEW_CHARS]
        lines.append(f"[{i}] claim: {row.claim}\n    excerpt: {excerpt}")
    return "\n".join(lines)


async def rerank(
    llm: LLMProvider, sub_question: str, candidates: list[EvidenceRow], top_k: int
) -> tuple[list[EvidenceRow], RerankUsage]:
    """Listwise LLM rerank per PRD §3.3.

    - The model returns **indices into the window it was shown**, never
      rewritten text — the schema has no text field, so it's structurally
      impossible for the model to substitute its own content.
    - Windows of `WINDOW_SIZE` (~20) so a single oversized candidate list
      doesn't degrade ranking quality; results are merged by global index.
    - Any failure for a window (malformed/truncated output, an out-of-range
      or duplicate index) falls back to that window's original (RRF) order
      rather than raising — reranking must never abort a run. Fallback items
      are scored below every real (0-1) relevance_score so a partially-failed
      call still prefers genuinely-scored candidates first.
    """
    if not candidates:
        return [], RerankUsage()

    scored: dict[int, float] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    model_used: str | None = None

    for window_start in range(0, len(candidates), WINDOW_SIZE):
        window = candidates[window_start : window_start + WINDOW_SIZE]
        try:
            response = await llm.generate_structured(
                "reranking",
                system=SYSTEM_PROMPT,
                user=_build_prompt(sub_question, window),
                schema=_RerankResult,
            )
            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens
            model_used = response.model

            seen_local_indices: set[int] = set()
            for item in response.parsed.ranked:
                if not (0 <= item.index < len(window)) or item.index in seen_local_indices:
                    continue
                seen_local_indices.add(item.index)
                scored[window_start + item.index] = item.relevance_score

            if not seen_local_indices:
                raise ValueError("rerank response had no valid indices")
        except Exception as exc:
            logger.warning("reranker: window at offset %d fell back to RRF order: %s", window_start, exc)
            for local_i in range(len(window)):
                global_i = window_start + local_i
                scored.setdefault(global_i, -1.0 - local_i)

    ranked_indices = sorted(scored.keys(), key=lambda i: scored[i], reverse=True)[:top_k]
    return [candidates[i] for i in ranked_indices], RerankUsage(total_input_tokens, total_output_tokens, model_used)
