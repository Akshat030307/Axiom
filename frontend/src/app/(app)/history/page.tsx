"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { modeLabel } from "@/lib/tokens";
import { relativeTime } from "@/lib/format";
import { StatusIcon, type Status } from "@/components/ui/StatusIcon";

const PAGE_SIZE = 15;

const STATUS_META: Record<string, Status> = {
  completed: "complete",
  running: "active",
  pending: "pending",
  error: "pending",
};

export default function HistoryPage() {
  const { accessToken } = useAuth();
  const [offset, setOffset] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["history", "page", offset],
    queryFn: () => api.listResearchHistory(accessToken!, PAGE_SIZE, offset),
    enabled: !!accessToken,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <main className="mx-auto max-w-4xl px-10 py-10">
      <h1 className="mb-6 font-[family-name:var(--font-display)] text-2xl font-semibold text-fg">Research History</h1>

      {isLoading && <p className="text-sm text-fg-muted">Loading…</p>}
      {!isLoading && items.length === 0 && <p className="text-sm text-fg-muted">No research yet.</p>}

      {items.length > 0 && (
        <ul className="flex flex-col divide-y divide-border rounded-card border border-border bg-surface">
          {items.map((run) => (
            <li key={run.run_id}>
              <Link
                href={run.status === "completed" ? `/research/${run.run_id}/report` : `/research/${run.run_id}`}
                className="flex items-center justify-between gap-4 px-5 py-4"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-fg">{run.query}</p>
                  <p className="text-xs text-fg-muted">
                    {modeLabel(run.mode)} • {relativeTime(run.started_at)}
                  </p>
                </div>
                <span className="flex shrink-0 items-center gap-2 text-xs text-fg-muted">
                  <StatusIcon state={STATUS_META[run.status] ?? "pending"} size={10} />
                  {run.status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {total > PAGE_SIZE && (
        <div className="mt-6 flex items-center justify-between text-sm text-fg-muted">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="rounded-pill border border-border-strong px-4 py-2 disabled:opacity-40"
          >
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="rounded-pill border border-border-strong px-4 py-2 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </main>
  );
}
