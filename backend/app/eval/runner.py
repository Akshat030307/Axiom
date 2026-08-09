"""Minimal eval loop (PRD §17, trimmed to 12 questions and six measured
metrics — see the Phase 3 implementation plan for the full scope note).
Runs each dataset question through the real graph (graph/runner.py's
`execute_research_run`, unchanged) and computes metrics from the resulting
persisted rows. Never mocked — "numbers must be measured, never placeholder".
"""

import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.session import async_session_maker
from app.eval.metrics import citation_accuracy, claim_verification, mean, task_completion
from app.graph.runner import execute_research_run
from app.llm.provider import LLMProvider
from app.models.db_models import EvalRun, Report, ResearchRun
from app.observability.stat import compute_run_stat_counts

settings = get_settings()
logger = logging.getLogger(__name__)

DATASET_PATH = Path(__file__).resolve().parent / "dataset" / "questions.jsonl"
DATASET_VERSION = "v1"


def load_dataset() -> list[dict]:
    rows = []
    with DATASET_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


async def _question_result(db, llm: LLMProvider, run_id: uuid.UUID, *, reused_existing: bool = False) -> dict:
    """`reused_existing=True` means this run_id was NOT executed by this eval
    invocation — it's an already-completed run (e.g. from smoke testing)
    being scored after the fact. `cost_usd` still reports the run's real,
    full cost (that's what avg_cost is supposed to measure — the actual cost
    of producing a report like this, sunk or not). `new_spend_usd` is the
    separate figure the cost-ceiling check in run_eval_dataset actually
    cares about: for a reused run that's just the citation-judge call; for a
    freshly executed one it's the same as cost_usd plus the judge call."""
    run = await db.get(ResearchRun, run_id)
    report = await db.scalar(select(Report).where(Report.run_id == run_id).order_by(Report.created_at.desc()))
    if run is None:
        return {"run_id": str(run_id), "error": "run row missing after execution"}
    if run.status != "completed" or report is None:
        return {"run_id": str(run_id), "error": f"run did not complete a report (status={run.status})"}

    stat_counts = await compute_run_stat_counts(db, run_id)
    run_cost = float(run.cost_estimate_usd)
    accuracy, judge_cost = await citation_accuracy(db, llm, report)
    return {
        "run_id": str(run_id),
        "status": run.status,
        "reused_existing_run": reused_existing,
        "latency_seconds": float(run.latency_seconds) if run.latency_seconds is not None else None,
        "cost_usd": run_cost,
        "new_spend_usd": judge_cost if reused_existing else (run_cost + judge_cost),
        "sources": stat_counts["sources"],
        "citation_accuracy": accuracy,
        "claim_verification": await claim_verification(db, report),
        "task_completion": await task_completion(db, run, report),
    }


async def _save_metrics(eval_id: uuid.UUID, **updates) -> dict:
    async with async_session_maker() as db:
        eval_run = await db.get(EvalRun, eval_id)
        metrics = dict(eval_run.metrics or {})
        metrics.update(updates)
        eval_run.metrics = metrics
        await db.commit()
        return metrics


async def run_eval_dataset(
    eval_id: uuid.UUID, user_id: uuid.UUID, existing_run_ids: dict[str, str] | None = None
) -> None:
    """Sequential (not concurrent — respects each sub-run's own
    MAX_RUN_COST_USD ceiling and avoids hammering the search API in
    parallel), resumable, and cost-capped:

    - Resumable: `metrics.per_question[question_id]` is written immediately
      after *each* question (not batched at the end), and questions already
      present there (without an "error" key) are skipped on re-invocation —
      so calling this again with the same eval_id resumes rather than
      restarts. A crash at question 9 doesn't lose questions 1-8.
    - Cost-capped: the running sum of this eval's own NEW spend (see
      `_question_result`'s `new_spend_usd` — not the same as a reused run's
      full historical cost) is checked against MAX_EVAL_COST_USD *between*
      questions (a question already in flight always finishes). Exceeding it
      stops cleanly with status="aborted_cost_ceiling", keeping every
      per_question result collected so far rather than discarding them.

    `existing_run_ids`: optional {question_id: run_id} map. For a question_id
    present here, an already-completed run is scored instead of executing a
    fresh one — the retrieval/verification cost is sunk, so this question
    costs only its citation-judge call. Any dataset question_id NOT in the
    map still gets a fresh run, so a partial map is fine.
    """
    dataset = load_dataset()
    llm = LLMProvider()
    existing_run_ids = existing_run_ids or {}

    async with async_session_maker() as db:
        eval_run = await db.get(EvalRun, eval_id)
        if eval_run is None:
            logger.error("run_eval_dataset: eval %s not found", eval_id)
            return
        per_question: dict = dict((eval_run.metrics or {}).get("per_question", {}))

    await _save_metrics(eval_id, status="running", per_question=per_question)

    # .get("new_spend_usd", ...cost_usd...) tolerates resuming from
    # per_question entries written before new_spend_usd existed.
    cost_so_far = sum(
        q.get("new_spend_usd", q.get("cost_usd")) or 0 for q in per_question.values() if isinstance(q, dict)
    )

    for row in dataset:
        question_id = row["id"]
        prior = per_question.get(question_id)
        if isinstance(prior, dict) and "error" not in prior:
            continue  # completed on a prior invocation — resume, don't redo

        if cost_so_far >= settings.MAX_EVAL_COST_USD:
            logger.warning(
                "run_eval_dataset: eval %s aborting at MAX_EVAL_COST_USD (%.2f >= %.2f), %d/%d questions done",
                eval_id, cost_so_far, settings.MAX_EVAL_COST_USD, len(per_question), len(dataset),
            )
            await _save_metrics(eval_id, status="aborted_cost_ceiling", per_question=per_question)
            return

        reuse_run_id = existing_run_ids.get(question_id)
        if reuse_run_id is not None:
            async with async_session_maker() as db:
                result = await _question_result(db, llm, uuid.UUID(reuse_run_id), reused_existing=True)
        else:
            run_id = uuid.uuid4()
            async with async_session_maker() as db:
                db.add(ResearchRun(id=run_id, user_id=user_id, query=row["query"], mode=row["mode"], status="pending"))
                await db.commit()

            try:
                await execute_research_run(run_id, user_id, row["query"], row["mode"])
                async with async_session_maker() as db:
                    result = await _question_result(db, llm, run_id)
            except Exception as exc:
                logger.exception("run_eval_dataset: question %s (run %s) failed", question_id, run_id)
                result = {"run_id": str(run_id), "error": str(exc)}

        cost_so_far += result.get("new_spend_usd", result.get("cost_usd")) or 0
        per_question[question_id] = result
        await _save_metrics(eval_id, per_question=per_question)

    completed = [q for q in per_question.values() if isinstance(q, dict) and "error" not in q]
    await _save_metrics(
        eval_id,
        status="completed",
        per_question=per_question,
        dataset_size=len(dataset),
        questions_completed=len(completed),
        citation_accuracy=mean([q.get("citation_accuracy") for q in completed]),
        claim_verification=mean([q.get("claim_verification") for q in completed]),
        task_completion=mean([q.get("task_completion") for q in completed]),
        avg_latency_seconds=mean([q.get("latency_seconds") for q in completed]),
        avg_cost_usd=mean([q.get("cost_usd") for q in completed]),
        avg_sources=mean([q.get("sources") for q in completed]),
    )
    async with async_session_maker() as db:
        eval_run = await db.get(EvalRun, eval_id)
        eval_run.dataset_version = DATASET_VERSION
        await db.commit()
