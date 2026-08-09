import logging
import uuid

from pydantic import BaseModel, Field

from app.graph.nodes._prompts import load_prompt
from app.graph.run_context import NodeResult, RunContext
from app.graph.state import ResearchState
from app.guardrails.sanitize import FETCHED_CONTENT_INSTRUCTION
from app.models.db_models import Evidence as EvidenceRow
from app.models.schemas import Evidence
from app.observability.tracer import traced

SYSTEM_PROMPT = load_prompt("evidence_extractor.md")
logger = logging.getLogger(__name__)

BATCH_SIZE = 3


class _ExtractedItem(BaseModel):
    source_id: str
    claim: str
    relevant_excerpt: str
    confidence: float = Field(ge=0, le=1)
    numeric_value: float | None = None
    numeric_unit: str | None = None
    time_period: str | None = None


class _ExtractionResult(BaseModel):
    items: list[_ExtractedItem]


def _batches(items: list[dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


@traced("evidence_extractor")
async def evidence_extractor_node(state: ResearchState, ctx: RunContext) -> NodeResult:
    raw_findings = state.get("raw_findings", [])
    source_id_to_topic = {f["source_id"]: f["topic"] for f in raw_findings}

    evidence: list[Evidence] = []
    errors: list[str] = []
    total_input_tokens = 0
    total_output_tokens = 0
    model_used: str | None = None

    for batch_index, batch in enumerate(_batches(raw_findings, BATCH_SIZE)):
        user_prompt = FETCHED_CONTENT_INSTRUCTION + "\n\n" + "\n\n".join(f["fetched_content"] for f in batch)
        if batch_index == 0:
            # Diagnostic only — logs the first batch's full user-turn prompt so the
            # <fetched_content> delimiter contract can be inspected directly.
            logger.info("evidence_extractor first batch prompt (run %s):\n%s", ctx.run_id, user_prompt)
        try:
            response = await ctx.llm.generate_structured(
                "extraction", system=SYSTEM_PROMPT, user=user_prompt, schema=_ExtractionResult
            )
        except Exception as exc:
            errors.append(f"evidence_extractor: extraction failed for a batch: {exc}")
            continue

        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens
        model_used = response.model

        for item in response.parsed.items:
            topic = source_id_to_topic.get(item.source_id)
            if topic is None:
                errors.append(f"evidence_extractor: model returned unknown source_id {item.source_id}, dropped")
                continue

            evidence_id = uuid.uuid4()
            ev = Evidence(
                id=str(evidence_id),
                source_id=item.source_id,
                claim=item.claim,
                relevant_excerpt=item.relevant_excerpt,
                confidence=item.confidence,
                agent="web_researcher",
                topic=topic,
                numeric_value=item.numeric_value,
                numeric_unit=item.numeric_unit,
                time_period=item.time_period,
            )
            evidence.append(ev)
            ctx.db.add(
                EvidenceRow(
                    id=evidence_id,
                    run_id=ctx.run_id,
                    source_id=uuid.UUID(ev.source_id),
                    claim=ev.claim,
                    relevant_excerpt=ev.relevant_excerpt,
                    confidence=ev.confidence,
                    agent=ev.agent,
                    topic=ev.topic,
                    numeric_value=ev.numeric_value,
                    numeric_unit=ev.numeric_unit,
                    time_period=ev.time_period,
                    metadata_=ev.metadata,
                )
            )

    return NodeResult(
        state_update={"evidence": evidence, "errors": errors},
        input_tokens=total_input_tokens,
        output_tokens=total_output_tokens,
        model=model_used,
    )
