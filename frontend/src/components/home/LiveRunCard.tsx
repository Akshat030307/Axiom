"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useResearchSocket } from "@/hooks/useResearchSocket";
import { modeLabel } from "@/lib/tokens";
import { relativeTime } from "@/lib/format";
import { StatusIcon, type Status } from "@/components/ui/StatusIcon";
import { ActivityFeed } from "@/components/run/ActivityFeed";
import { ProgressTimeline } from "@/components/run/ProgressTimeline";
import { StatStrip } from "@/components/run/StatStrip";

export function LiveRunCard({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const state = useResearchSocket(runId);

  // The socket's snapshot carries mode/query/stat but not started_at; one
  // cheap REST fetch fills that in and doubles as a fallback before the
  // first WS frame lands.
  const { data: runStatus } = useQuery({
    queryKey: ["run-status", runId],
    queryFn: () => api.getResearchStatus(accessToken!, runId),
    enabled: !!accessToken,
    staleTime: Infinity,
  });

  const status = state.status ?? runStatus?.status ?? "pending";
  const mode = state.mode ?? runStatus?.mode ?? "quick";
  const query = state.query ?? runStatus?.query ?? "Untitled research";
  // Upgrades from the raw query to a real report title the moment planning
  // finishes (plan_ready, or snapshot on a reconnect after it already has) —
  // whatever the user actually typed ("make a report on semiconductors")
  // isn't what should sit here once something better exists.
  const title = state.plan?.title ?? query;
  const isDone = status === "completed";
  const isError = status === "error";

  const headerLabel = isError ? "Research failed" : isDone ? "Research complete" : "Live research";
  const headerState: Status = isDone ? "complete" : isError ? "pending" : "active";
  const reportHref = isDone ? `/research/${runId}/report` : `/research/${runId}`;

  return (
    <section className="relative overflow-hidden rounded-card border border-border bg-surface">
      <div className="flex flex-col gap-6 p-7">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.08em] text-fg-muted">
            <StatusIcon state={headerState} size={9} />
            {headerLabel}
          </div>
          <Link
            href={reportHref}
            className="flex items-center gap-1.5 rounded-pill border border-border-strong px-4 py-2 text-sm text-fg transition-colors hover:bg-surface-raised"
          >
            View Report
            <ArrowRight size={14} />
          </Link>
        </div>

        <div>
          <h2 className="font-[family-name:var(--font-display)] text-2xl font-semibold tracking-[-0.01em] text-fg">
            {title}
          </h2>
          <p className="mt-1 text-sm text-fg-muted">
            {modeLabel(mode)} mode
            {state.sources.length > 0 && ` • ${state.sources.length} sources`}
            {runStatus?.started_at && ` • Started ${relativeTime(runStatus.started_at)}`}
          </p>
        </div>

        <div className="flex flex-col gap-6 rounded-2xl border border-border p-7">
          <ActivityFeed status={status} currentNode={state.currentNode} activity={state.activity} />
          <div className="border-t border-border pt-6">
            <ProgressTimeline stage={state.stage} status={status} stat={state.stat} />
          </div>
        </div>

        <StatStrip stat={state.stat} />
      </div>
    </section>
  );
}
