"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { Modal } from "@/components/ui/Modal";
import { StatusIcon, type Status } from "@/components/ui/StatusIcon";
import { relativeTime } from "@/lib/format";
import type { EvalQuestionResult, EvalRunStatus } from "@/types/api";

function pct(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function seconds(value: number | null | undefined): string {
  if (value == null) return "—";
  return value < 60 ? `${value.toFixed(1)}s` : `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

function usd(value: number | null | undefined): string {
  return value == null ? "—" : `$${value.toFixed(4)}`;
}

const RUN_STATUS_META: Record<EvalRunStatus, { label: string; state: Status }> = {
  running: { label: "Running", state: "active" },
  completed: { label: "Completed", state: "complete" },
  aborted_cost_ceiling: { label: "Stopped — cost ceiling", state: "pending" },
};

export default function EvaluationPage() {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [selectedEvalId, setSelectedEvalId] = useState<string | null>(null);

  const { data: config } = useQuery({
    queryKey: ["eval-config"],
    queryFn: () => api.getEvalConfig(accessToken!),
    enabled: !!accessToken,
  });

  const { data: evalList } = useQuery({
    queryKey: ["eval-list"],
    queryFn: () => api.listEvals(accessToken!, 20),
    enabled: !!accessToken,
  });

  const activeEvalId = selectedEvalId ?? evalList?.items[0]?.id ?? null;

  const { data: evalStatus, isLoading: evalLoading } = useQuery({
    queryKey: ["eval", activeEvalId],
    queryFn: () => api.getEval(accessToken!, activeEvalId!),
    enabled: !!accessToken && !!activeEvalId,
    refetchInterval: (query) => (query.state.data?.metrics.status === "running" ? 3000 : false),
  });

  const metrics = evalStatus?.metrics;
  const perQuestion = useMemo(
    () => Object.entries(metrics?.per_question ?? {}) as [string, EvalQuestionResult][],
    [metrics]
  );
  const completedCount = perQuestion.filter(([, q]) => !q.error).length;

  async function handleConfirmRun() {
    if (!accessToken) return;
    setStarting(true);
    setStartError(null);
    try {
      const res = await api.startEval(accessToken);
      setSelectedEvalId(res.eval_id);
      setConfirmOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["eval-list"] });
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Failed to start evaluation");
    } finally {
      setStarting(false);
    }
  }

  const hasAnyEval = !!activeEvalId;
  const statusMeta = metrics?.status ? RUN_STATUS_META[metrics.status] : null;

  return (
    <main className="mx-auto max-w-5xl px-10 py-10">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-fg">Evaluation</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Measured against the {config ? config.dataset_size : "…"}-question benchmark dataset — no placeholder numbers.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          className="shrink-0 rounded-pill bg-accent px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90"
        >
          Run evaluation
        </button>
      </div>

      {!hasAnyEval && !evalLoading && (
        <div className="flex flex-col items-center gap-2 rounded-card border border-border bg-surface py-16 text-center">
          <p className="text-sm text-fg">No evaluation has been run yet.</p>
          <p className="text-sm text-fg-muted">Run one to measure citation accuracy, claim verification, and task completion.</p>
        </div>
      )}

      {hasAnyEval && metrics && (
        <div className="flex flex-col gap-8">
          <div className="flex items-center gap-3 text-sm text-fg-muted">
            {statusMeta && <StatusIcon state={statusMeta.state} size={11} />}
            <span className="text-fg">{statusMeta?.label ?? metrics.status ?? "Unknown"}</span>
            {metrics.status === "running" && (
              <span>
                — {completedCount} / {config?.dataset_size ?? "?"} questions done
              </span>
            )}
            {evalStatus?.created_at && <span>• started {relativeTime(evalStatus.created_at)}</span>}
          </div>

          <div className="grid grid-cols-3 gap-px overflow-hidden rounded-card border border-border bg-border sm:grid-cols-6">
            {[
              { label: "Citation Accuracy", value: pct(metrics.citation_accuracy) },
              { label: "Claim Verification", value: pct(metrics.claim_verification) },
              { label: "Task Completion", value: pct(metrics.task_completion) },
              { label: "Avg Latency", value: seconds(metrics.avg_latency_seconds) },
              { label: "Avg Cost", value: usd(metrics.avg_cost_usd) },
              { label: "Avg Sources", value: metrics.avg_sources != null ? metrics.avg_sources.toFixed(1) : "—" },
            ].map((stat) => (
              <div key={stat.label} className="flex flex-col items-center gap-1 bg-surface px-2 py-5 text-center">
                <span className="font-[family-name:var(--font-display)] text-xl font-semibold tabular-nums text-fg">
                  {stat.value}
                </span>
                <span className="text-[11px] text-fg-muted">{stat.label}</span>
              </div>
            ))}
          </div>

          <section className="flex flex-col gap-4">
            <h2 className="font-[family-name:var(--font-display)] text-lg font-semibold text-fg">Per-question breakdown</h2>
            {perQuestion.length === 0 ? (
              <p className="text-sm text-fg-muted">No questions scored yet.</p>
            ) : (
              <div className="overflow-x-auto rounded-card border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-fg-muted">
                      <th className="px-4 py-3 font-medium">Question</th>
                      <th className="px-4 py-3 font-medium">Sources</th>
                      <th className="px-4 py-3 font-medium">Citation Acc.</th>
                      <th className="px-4 py-3 font-medium">Claim Verif.</th>
                      <th className="px-4 py-3 font-medium">Task Compl.</th>
                      <th className="px-4 py-3 font-medium">Latency</th>
                      <th className="px-4 py-3 font-medium">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {perQuestion.map(([questionId, q]) => (
                      <tr key={questionId} className="border-b border-border align-top last:border-0">
                        <td className="px-4 py-3 text-fg">
                          {questionId}
                          {q.error && <span className="block text-xs text-fg-muted">{q.error}</span>}
                        </td>
                        {q.error ? (
                          <td className="px-4 py-3 text-fg-subtle" colSpan={6}>
                            —
                          </td>
                        ) : (
                          <>
                            <td className="px-4 py-3 tabular-nums text-fg-muted">{q.sources ?? "—"}</td>
                            <td className="px-4 py-3 tabular-nums text-fg-muted">{pct(q.citation_accuracy)}</td>
                            <td className="px-4 py-3 tabular-nums text-fg-muted">{pct(q.claim_verification)}</td>
                            <td className="px-4 py-3 tabular-nums text-fg-muted">{pct(q.task_completion)}</td>
                            <td className="px-4 py-3 tabular-nums text-fg-muted">{seconds(q.latency_seconds)}</td>
                            <td className="px-4 py-3 tabular-nums text-fg-muted">{usd(q.cost_usd)}</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}

      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Run evaluation?">
        <div className="flex flex-col gap-4 text-sm">
          <p className="text-fg-muted">
            This runs all <strong className="text-fg">{config?.dataset_size ?? "…"}</strong> questions in the evaluation
            dataset through the live research pipeline — real, billed API calls, not a simulation.
          </p>
          <p className="text-fg-muted">
            Spend is capped at <strong className="text-fg">${config?.max_eval_cost_usd?.toFixed(2) ?? "…"}</strong>. If the
            cap is hit partway through, the run stops cleanly and keeps every question already scored rather than
            discarding them.
          </p>
          {startError && <p className="text-fg-muted">{startError}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => setConfirmOpen(false)}
              className="rounded-pill border border-border-strong px-4 py-2 text-fg transition-colors hover:bg-surface-raised"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleConfirmRun}
              disabled={starting || !config}
              className="rounded-pill bg-accent px-4 py-2 font-medium text-black disabled:opacity-40"
            >
              {starting ? "Starting…" : "Run evaluation"}
            </button>
          </div>
        </div>
      </Modal>
    </main>
  );
}
