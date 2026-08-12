"use client";

import { Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { Greeting } from "@/components/home/Greeting";
import { ResearchInput } from "@/components/home/ResearchInput";
import { ModeSelector } from "@/components/home/ModeSelector";
import { HighlightToggle } from "@/components/home/HighlightToggle";
import { LiveRunCard } from "@/components/home/LiveRunCard";
import { RecentResearch } from "@/components/home/RecentResearch";
import { QuoteCard } from "@/components/home/QuoteCard";
import type { ResearchMode } from "@/types/api";

export default function HomePage() {
  const { user, accessToken } = useAuth();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<ResearchMode>("deep");
  const [highlightEnabled, setHighlightEnabled] = useState(true);
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initializedRef = useRef(false);

  // On first load, focus the user's most recent run (live or historical) —
  // the same LiveRunCard + useResearchSocket renders both correctly, since
  // the backend's `snapshot` frame fully describes a completed run too.
  const { data: recentHistory } = useQuery({
    queryKey: ["history", "recent"],
    queryFn: () => api.listResearchHistory(accessToken!, 1, 0),
    enabled: !!accessToken,
  });

  useEffect(() => {
    if (!initializedRef.current && recentHistory?.items?.length) {
      setFocusedRunId(recentHistory.items[0].run_id);
      initializedRef.current = true;
    }
  }, [recentHistory]);

  const handleSubmit = useCallback(async () => {
    if (!accessToken || !query.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.createResearch(accessToken, query.trim(), mode, highlightEnabled);
      setFocusedRunId(res.run_id);
      setQuery("");
      void queryClient.invalidateQueries({ queryKey: ["history"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start research");
    } finally {
      setSubmitting(false);
    }
  }, [accessToken, query, mode, highlightEnabled, submitting, queryClient]);

  if (!user) return null;

  const name = user.display_name || user.email.split("@")[0];

  return (
    <main className="mx-auto grid max-w-[1400px] grid-cols-1 gap-10 px-10 py-10 xl:grid-cols-[1fr_400px]">
      <div className="flex flex-col gap-8">
        <Greeting name={name} />

        <div className="flex flex-col gap-4">
          <ResearchInput value={query} onChange={setQuery} onSubmit={handleSubmit} disabled={submitting} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <ModeSelector value={mode} onChange={setMode} />
            <HighlightToggle value={highlightEnabled} onChange={setHighlightEnabled} />
          </div>
          {error && <p className="text-sm text-fg-muted">{error}</p>}
        </div>

        {focusedRunId && <LiveRunCard runId={focusedRunId} />}
      </div>

      <div className="flex flex-col gap-6">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => {
              setFocusedRunId(null);
              setQuery("");
            }}
            className="flex items-center gap-2 rounded-pill border border-border-strong px-4 py-2 text-sm text-fg transition-colors hover:bg-surface-raised"
          >
            <Sparkles size={14} />
            New Research
          </button>
        </div>
        <RecentResearch />
        <QuoteCard />
      </div>
    </main>
  );
}
