"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import type { RunStatusResponse } from "@/types/api";

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATUSES = new Set(["completed", "error"]);

export default function HomePage() {
  const { user, accessToken, logout } = useAuth();
  const router = useRouter();

  const [query, setQuery] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<RunStatusResponse | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!user) router.replace("/login");
  }, [user, router]);

  // Poll status until the run reaches a terminal state, then fetch the report.
  // No WebSockets in Phase 1 (out of scope) — this is the whole progress UI.
  // Depends only on [runId, accessToken] (not `status`) and self-clears on a
  // terminal result — the interval isn't torn down and recreated every tick.
  useEffect(() => {
    if (!runId || !accessToken) return;

    const timer = setInterval(async () => {
      try {
        const s = await api.getResearchStatus(accessToken, runId);
        setStatus(s);
        if (s.status === "completed") {
          const r = await api.getReport(accessToken, runId);
          setReport(r.markdown);
          clearInterval(timer);
        } else if (s.status === "error") {
          setError("The research run failed. Check backend logs / node_traces for details.");
          clearInterval(timer);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to poll run status");
        clearInterval(timer);
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [runId, accessToken]);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      if (!accessToken || !query.trim()) return;
      setError(null);
      setReport(null);
      setStatus(null);
      setSubmitting(true);
      try {
        const res = await api.createResearch(accessToken, query.trim(), "quick");
        setRunId(res.run_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start research");
      } finally {
        setSubmitting(false);
      }
    },
    [accessToken, query]
  );

  if (!user) return null;

  const runInFlight = status !== null && !TERMINAL_STATUSES.has(status.status);

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Research Agent</h1>
        <button onClick={logout} className="text-sm underline">
          Log out ({user.email})
        </button>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="What do you want to research?"
          rows={3}
          required
          className="rounded border border-gray-300 px-3 py-2"
        />
        <button
          type="submit"
          disabled={submitting || runInFlight}
          className="self-start rounded bg-black px-4 py-2 text-white disabled:opacity-50"
        >
          {submitting ? "Starting..." : runInFlight ? "Research in progress..." : "Research"}
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {status && (
        <p className="text-sm text-gray-600">
          Run {status.run_id.slice(0, 8)} — status: {status.status}
          {status.status === "completed" &&
            ` (cost ~$${status.cost_estimate_usd.toFixed(4)}, ${status.latency_seconds?.toFixed(1)}s)`}
        </p>
      )}

      {report && (
        <article className="flex flex-col gap-3 border-t border-gray-200 pt-4 [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:text-lg [&_h2]:font-semibold [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
        </article>
      )}
    </main>
  );
}
