"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { RunSubNav } from "@/components/run/RunSubNav";

export default function TracePage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const { accessToken } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ["trace", runId],
    queryFn: () => api.listTrace(accessToken!, runId),
    enabled: !!accessToken && !!runId,
  });

  return (
    <main className="mx-auto max-w-5xl px-10 py-10">
      <RunSubNav runId={runId} />
      <h1 className="mb-6 font-[family-name:var(--font-display)] text-2xl font-semibold text-fg">Agent Trace</h1>

      {isLoading && <p className="text-sm text-fg-muted">Loading…</p>}
      {!isLoading && (!data || data.length === 0) && <p className="text-sm text-fg-muted">No trace recorded yet.</p>}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-fg-muted">
                <th className="px-4 py-3 font-medium">#</th>
                <th className="px-4 py-3 font-medium">Node</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Latency</th>
                <th className="px-4 py-3 font-medium">Cost</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {data.map((t) => (
                <tr key={t.id} className="border-b border-border align-top last:border-0">
                  <td className="px-4 py-3 tabular-nums text-fg-muted">{t.seq}</td>
                  <td className="px-4 py-3 text-fg">{t.node_name}</td>
                  <td className="px-4 py-3 text-fg-muted">{t.status ?? "—"}</td>
                  <td className="px-4 py-3 tabular-nums text-fg-muted">
                    {t.latency_ms != null ? `${t.latency_ms}ms` : "—"}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-fg-muted">
                    {t.cost_usd != null ? `$${t.cost_usd.toFixed(4)}` : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {(t.input != null || t.output != null) && (
                      <details>
                        <summary className="cursor-pointer text-fg-muted">details</summary>
                        <pre className="mt-2 max-w-md overflow-auto rounded-input border border-border bg-surface p-2 text-xs text-fg-muted">
                          {JSON.stringify({ input: t.input, output: t.output }, null, 2)}
                        </pre>
                      </details>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
