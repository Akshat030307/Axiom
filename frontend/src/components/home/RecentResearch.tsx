"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { modeLabel } from "@/lib/tokens";
import { relativeTime } from "@/lib/format";

function InitialSquare({ query }: { query: string }) {
  const letter = query.trim().charAt(0).toUpperCase() || "?";
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface-raised text-sm font-semibold text-fg">
      {letter}
    </span>
  );
}

export function RecentResearch() {
  const { accessToken } = useAuth();
  const { data } = useQuery({
    queryKey: ["history", "recent"],
    queryFn: () => api.listResearchHistory(accessToken!, 5, 0),
    enabled: !!accessToken,
  });

  const items = data?.items ?? [];

  return (
    <section className="flex flex-col gap-4 rounded-card border border-border bg-surface p-6">
      <div className="flex items-center justify-between">
        <h2 className="font-[family-name:var(--font-display)] text-lg font-semibold text-fg">Recent Research</h2>
        <Link href="/history" className="flex items-center gap-1 text-sm text-fg-muted transition-colors hover:text-fg">
          View all <ChevronRight size={14} />
        </Link>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-fg-muted">No research yet — ask something to get started.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {items.map((run) => (
            <li key={run.run_id}>
              <Link
                href={run.status === "completed" ? `/research/${run.run_id}/report` : `/research/${run.run_id}`}
                className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
              >
                <InitialSquare query={run.query} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-fg">{run.query}</span>
                  <span className="block text-xs text-fg-muted">
                    {modeLabel(run.mode)} • {relativeTime(run.started_at)}
                  </span>
                </span>
                <ChevronRight size={16} className="shrink-0 text-fg-subtle" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
