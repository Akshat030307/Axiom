"use client";

import { useParams } from "next/navigation";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import * as api from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { RunSubNav } from "@/components/run/RunSubNav";
import { ReportView } from "@/components/report/ReportView";
import { ExportPdfButton } from "@/components/report/ExportPdfButton";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const { accessToken } = useAuth();

  const {
    data: report,
    isLoading: reportLoading,
    error: reportError,
  } = useQuery({
    queryKey: ["report", runId],
    queryFn: () => api.getReport(accessToken!, runId),
    enabled: !!accessToken && !!runId,
    retry: false,
  });

  const { data: evidence } = useQuery({
    queryKey: ["evidence", runId],
    queryFn: () => api.listEvidence(accessToken!, runId),
    enabled: !!accessToken && !!runId,
  });

  const { data: figures } = useQuery({
    queryKey: ["figures", runId],
    queryFn: () => api.listFigures(accessToken!, runId),
    enabled: !!accessToken && !!runId,
  });

  const evidenceById = useMemo(() => new Map((evidence ?? []).map((e) => [e.id, e])), [evidence]);
  const figuresById = useMemo(() => new Map((figures ?? []).map((f) => [f.id, f])), [figures]);

  return (
    <main className="mx-auto max-w-3xl px-10 py-10">
      <div className="flex items-start justify-between gap-4">
        <RunSubNav runId={runId} className="flex-1" />
        {report && <ExportPdfButton runId={runId} />}
      </div>

      {reportLoading && <p className="text-sm text-fg-muted">Loading report…</p>}

      {reportError && (
        <p className="text-sm text-fg-muted">
          {reportError instanceof Error ? reportError.message : "Report not available."}
        </p>
      )}

      {report && (
        <ReportView
          markdown={report.markdown}
          citations={report.citations}
          evidenceById={evidenceById}
          figuresById={figuresById}
        />
      )}
    </main>
  );
}
