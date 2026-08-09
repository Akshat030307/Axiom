"use client";

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

// Built to the PRD §7.2/§14 contract (POST .../report/pdf -> {download_url},
// implemented server-side as a Celery task). The backend piece doesn't
// exist yet (no app/export/, no route on routes_reports.py) — this will
// surface a real error until that's built; see lib/api.ts's exportReportPdf.
type ExportState = "idle" | "exporting" | "error";

export function ExportPdfButton({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const [state, setState] = useState<ExportState>("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    if (!accessToken || state === "exporting") return;
    setState("exporting");
    setError(null);
    try {
      const { download_url } = await api.exportReportPdf(accessToken, runId);
      await api.downloadFile(accessToken, download_url, `research-${runId}.pdf`);
      setState("idle");
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  return (
    <div className="flex flex-col items-end gap-1.5">
      <button
        type="button"
        onClick={handleExport}
        disabled={state === "exporting"}
        className="flex items-center gap-2 rounded-pill border border-border-strong px-4 py-2 text-sm text-fg transition-colors hover:bg-surface-raised disabled:opacity-60"
      >
        {state === "exporting" ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
        {state === "exporting" ? "Exporting…" : "Export PDF"}
      </button>
      {state === "error" && error && <p className="max-w-56 text-right text-xs text-fg-muted">{error}</p>}
    </div>
  );
}
