"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { RunSubNav } from "@/components/run/RunSubNav";
import { StatusIcon, type Status } from "@/components/ui/StatusIcon";
import type { FactCheckStatus } from "@/types/api";

const FACT_CHECK_META: Record<FactCheckStatus, { label: string; state: Status }> = {
  supported: { label: "Supported", state: "complete" },
  unsupported: { label: "Unsupported", state: "pending" },
  unverified: { label: "Unverified", state: "pending" },
  outdated: { label: "Outdated", state: "pending" },
};

export default function EvidencePage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const { accessToken } = useAuth();

  const { data: evidence, isLoading } = useQuery({
    queryKey: ["evidence", runId],
    queryFn: () => api.listEvidence(accessToken!, runId),
    enabled: !!accessToken && !!runId,
  });

  const { data: contradictions } = useQuery({
    queryKey: ["contradictions", runId],
    queryFn: () => api.listContradictions(accessToken!, runId),
    enabled: !!accessToken && !!runId,
  });

  const [topicFilter, setTopicFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const topics = useMemo(
    () => Array.from(new Set((evidence ?? []).map((e) => e.topic).filter((t): t is string => Boolean(t)))),
    [evidence]
  );

  const filtered = useMemo(() => {
    return (evidence ?? []).filter((e) => {
      if (topicFilter && e.topic !== topicFilter) return false;
      if (statusFilter && e.fact_check_status !== statusFilter) return false;
      return true;
    });
  }, [evidence, topicFilter, statusFilter]);

  return (
    <main className="mx-auto max-w-5xl px-10 py-10">
      <RunSubNav runId={runId} />
      <h1 className="mb-6 font-[family-name:var(--font-display)] text-2xl font-semibold text-fg">Evidence</h1>

      <div className="mb-4 flex flex-wrap gap-3">
        <select
          value={topicFilter}
          onChange={(e) => setTopicFilter(e.target.value)}
          className="rounded-input border border-border bg-surface px-3 py-2 text-sm text-fg"
        >
          <option value="">All topics</option>
          {topics.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-input border border-border bg-surface px-3 py-2 text-sm text-fg"
        >
          <option value="">All fact-check statuses</option>
          {(Object.keys(FACT_CHECK_META) as FactCheckStatus[]).map((s) => (
            <option key={s} value={s}>
              {FACT_CHECK_META[s].label}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-fg-muted">Loading…</p>}
      {!isLoading && filtered.length === 0 && <p className="text-sm text-fg-muted">No evidence matches these filters.</p>}

      {filtered.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-fg-muted">
                <th className="px-4 py-3 font-medium">Claim</th>
                <th className="px-4 py-3 font-medium">Topic</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Fact check</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => {
                const fc = e.fact_check_status ? FACT_CHECK_META[e.fact_check_status] : null;
                return (
                  <tr key={e.id} className="border-b border-border align-top last:border-0">
                    <td className="max-w-md px-4 py-3 text-fg">{e.claim}</td>
                    <td className="px-4 py-3 text-fg-muted">{e.topic ?? "—"}</td>
                    <td className="px-4 py-3 text-fg-muted">{e.source?.domain ?? "—"}</td>
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-2 text-fg-muted">
                        <StatusIcon state={fc?.state ?? "pending"} size={11} />
                        {fc?.label ?? "Unverified"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {contradictions && contradictions.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-4 font-[family-name:var(--font-display)] text-lg font-semibold text-fg">Contradictions</h2>
          <ul className="flex flex-col gap-4">
            {contradictions.map((c) => (
              <li key={c.id} className="rounded-card border border-border bg-surface p-4">
                <p className="mb-2 text-xs uppercase tracking-wide text-fg-muted">{c.topic ?? "Untitled topic"}</p>
                <p className="mb-1 text-sm text-fg">A: {c.evidence_a_claim}</p>
                <p className="mb-2 text-sm text-fg">B: {c.evidence_b_claim}</p>
                {c.explanation && <p className="text-sm text-fg-muted">{c.explanation}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
