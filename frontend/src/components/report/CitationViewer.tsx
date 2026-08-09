import { CredibilityMeter } from "@/components/ui/CredibilityMeter";
import { StatusIcon, type Status } from "@/components/ui/StatusIcon";
import type { EvidenceResponse, FactCheckStatus } from "@/types/api";

const FACT_CHECK_META: Record<FactCheckStatus, { label: string; state: Status }> = {
  supported: { label: "Supported", state: "complete" },
  unsupported: { label: "Unsupported", state: "pending" },
  unverified: { label: "Unverified", state: "pending" },
  outdated: { label: "Outdated", state: "pending" },
};

interface CitationViewerProps {
  marker: number;
  evidence: EvidenceResponse | null;
}

export function CitationViewer({ marker, evidence }: CitationViewerProps) {
  if (!evidence) {
    return (
      <p className="text-sm text-fg-muted">
        Citation [{marker}] could not be resolved to a stored evidence record.
      </p>
    );
  }

  const factCheck = evidence.fact_check_status ? FACT_CHECK_META[evidence.fact_check_status] : null;

  return (
    <div className="flex flex-col gap-4">
      <blockquote className="border-l-2 border-border-strong pl-4 text-sm italic text-fg">
        “{evidence.relevant_excerpt || evidence.claim}”
      </blockquote>

      <div className="flex flex-col gap-3 border-t border-border pt-4 text-sm">
        {evidence.source && (
          <div className="flex items-center justify-between gap-4">
            <span className="text-fg-muted">Source</span>
            <a
              href={evidence.source.url}
              target="_blank"
              rel="noreferrer"
              className="max-w-[65%] truncate text-right text-fg underline underline-offset-2"
            >
              {evidence.source.title || evidence.source.domain || evidence.source.url}
            </a>
          </div>
        )}
        {evidence.source?.credibility_score != null && (
          <div className="flex items-center justify-between">
            <span className="text-fg-muted">Credibility</span>
            <CredibilityMeter score={evidence.source.credibility_score} />
          </div>
        )}
        <div className="flex items-center justify-between">
          <span className="text-fg-muted">Fact check</span>
          <span className="flex items-center gap-2 text-fg">
            <StatusIcon state={factCheck?.state ?? "pending"} size={12} />
            {factCheck?.label ?? "Unverified"}
          </span>
        </div>
        {evidence.fact_check_notes && <p className="text-xs text-fg-muted">{evidence.fact_check_notes}</p>}
      </div>
    </div>
  );
}
