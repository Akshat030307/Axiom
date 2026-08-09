import { StatusIcon } from "@/components/ui/StatusIcon";
import type { StatFrameData } from "@/lib/ws-schema";

// Fixed at exactly seven rows, permanently (PRD §15.1) — this mirrors the
// backend's STAGE_ORDER/STAGE_LABELS (events.py) exactly. Figure generation
// deliberately has no row of its own; it reports under "generating_report".
const STAGES = [
  "understanding_query",
  "creating_plan",
  "searching_sources",
  "extracting_evidence",
  "fact_checking",
  "resolving_conflicts",
  "generating_report",
] as const;

type Stage = (typeof STAGES)[number];

const STAGE_LABELS: Record<Stage, string> = {
  understanding_query: "Understanding your query",
  creating_plan: "Creating research plan",
  searching_sources: "Searching across sources",
  extracting_evidence: "Extracting key evidence",
  fact_checking: "Fact checking claims",
  resolving_conflicts: "Resolving conflicts",
  generating_report: "Generating report",
};

// Only the counts the backend actually streams today — no fabricated
// denominators (e.g. a "32/42 sources" target the server never sends).
function rowDetail(key: Stage, stat: StatFrameData | null): string {
  if (!stat) return "—";
  switch (key) {
    case "searching_sources":
      return `${stat.sources} sources`;
    case "extracting_evidence":
      return `${stat.evidence_items} items`;
    case "fact_checking":
      return `${stat.claims_verified} / ${stat.evidence_items}`;
    case "resolving_conflicts":
      return `${stat.conflicts} found`;
    default:
      return "—";
  }
}

interface ProgressTimelineProps {
  stage: string | null;
  status: string | null;
  stat: StatFrameData | null;
}

export function ProgressTimeline({ stage, status, stat }: ProgressTimelineProps) {
  const currentIndex = stage ? STAGES.indexOf(stage as Stage) : -1;
  const allComplete = status === "completed";

  return (
    <ol className="flex flex-col gap-3">
      {STAGES.map((key, index) => {
        const isComplete = allComplete || index < currentIndex;
        const isActive = !allComplete && index === currentIndex;
        const reached = allComplete || index <= currentIndex;
        const iconState = isComplete ? "complete" : isActive ? "active" : "pending";

        return (
          <li key={key} className="flex items-center justify-between gap-6 text-sm">
            <span className="flex items-center gap-2.5">
              <StatusIcon state={iconState} size={15} />
              <span className={`transition-colors duration-300 ${isActive || isComplete ? "text-fg" : "text-fg-muted"}`}>
                {STAGE_LABELS[key]}
              </span>
            </span>
            <span className="tabular-nums text-fg-muted">{reached ? rowDetail(key, stat) : "—"}</span>
          </li>
        );
      })}
    </ol>
  );
}
