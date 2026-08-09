"use client";

import { useParams } from "next/navigation";

import { useResearchSocket } from "@/hooks/useResearchSocket";

// TEMPORARY: bare debug harness for verifying useResearchSocket against a
// real run (frame log in the console, raw state dumped below) before the
// designed Live Workspace (PRD §15.2) is built on top of it in Milestone 3.
export default function ResearchWorkspacePage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? null;
  const state = useResearchSocket(runId);

  return (
    <main className="flex flex-col gap-4 p-6 font-[family-name:var(--font-mono)] text-sm text-fg">
      <h1 className="font-[family-name:var(--font-display)] text-xl font-semibold">
        Workspace debug — run {runId}
      </h1>
      <div className="flex flex-wrap gap-4 text-fg-muted">
        <span>connected: {String(state.connected)}</span>
        <span>status: {state.status ?? "—"}</span>
        <span>stage: {state.stage ?? "—"}</span>
      </div>
      <pre className="overflow-auto rounded-input border border-border bg-surface p-4 text-xs">
        {JSON.stringify(
          {
            mode: state.mode,
            query: state.query,
            stageOrder: state.stageOrder,
            stat: state.stat,
            sources: state.sources,
            contradictions: state.contradictions,
            citations: state.citations,
            terminalError: state.terminalError,
            reportMarkdownLength: state.reportMarkdown.length,
          },
          null,
          2
        )}
      </pre>
      <div>
        <h2 className="mb-2 font-semibold text-fg">Report preview</h2>
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-input border border-border bg-surface p-4 text-xs">
          {state.reportMarkdown || "(empty)"}
        </pre>
      </div>
    </main>
  );
}
