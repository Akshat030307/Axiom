import { formatEta } from "@/lib/format";
import type { StatFrameData } from "@/lib/ws-schema";

export function StatStrip({ stat }: { stat: StatFrameData | null }) {
  const columns = [
    { label: "Sources Found", value: stat ? String(stat.sources) : "—" },
    { label: "Evidence Items", value: stat ? String(stat.evidence_items) : "—" },
    { label: "Claims Verified", value: stat ? `${stat.claims_verified} / ${stat.evidence_items}` : "—" },
    { label: "Conflicts Found", value: stat ? String(stat.conflicts) : "—" },
    { label: "Est. Completion", value: formatEta(stat?.eta_seconds) },
  ];

  return (
    <div className="grid grid-cols-5 divide-x divide-border border-t border-border pt-5">
      {columns.map((c) => (
        <div key={c.label} className="flex flex-col items-center gap-1 px-2 text-center">
          <span className="font-[family-name:var(--font-display)] text-[26px] font-semibold tabular-nums text-fg">
            {c.value}
          </span>
          <span className="text-[12px] text-fg-muted">{c.label}</span>
        </div>
      ))}
    </div>
  );
}
