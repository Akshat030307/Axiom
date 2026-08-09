"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { RunSubNav } from "@/components/run/RunSubNav";
import { CredibilityMeter } from "@/components/ui/CredibilityMeter";
import { relativeTime } from "@/lib/format";

export default function SourcesPage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const { accessToken } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ["sources", runId],
    queryFn: () => api.listSources(accessToken!, runId),
    enabled: !!accessToken && !!runId,
  });

  return (
    <main className="mx-auto max-w-5xl px-10 py-10">
      <RunSubNav runId={runId} />
      <h1 className="mb-6 font-[family-name:var(--font-display)] text-2xl font-semibold text-fg">Sources</h1>

      {isLoading && <p className="text-sm text-fg-muted">Loading…</p>}
      {!isLoading && (!data || data.length === 0) && <p className="text-sm text-fg-muted">No sources yet.</p>}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-fg-muted">
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Domain</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Credibility</th>
                <th className="px-4 py-3 font-medium">Evidence</th>
                <th className="px-4 py-3 font-medium">Fetched</th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0">
                  <td className="max-w-xs truncate px-4 py-3">
                    <a href={s.url} target="_blank" rel="noreferrer" className="text-fg underline underline-offset-2">
                      {s.title || s.url}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-fg-muted">{s.domain ?? "—"}</td>
                  <td className="px-4 py-3 text-fg-muted">{s.source_type ?? "—"}</td>
                  <td className="px-4 py-3">
                    <CredibilityMeter score={s.credibility_score} />
                  </td>
                  <td className="px-4 py-3 tabular-nums text-fg-muted">{s.evidence_count}</td>
                  <td className="px-4 py-3 text-fg-muted">{relativeTime(s.fetched_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
