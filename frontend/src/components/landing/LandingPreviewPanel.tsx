import { BookOpenCheck, Compass, FileSearch, Gauge, GitCompareArrows, Globe, PenLine } from "lucide-react";

import { Logo } from "@/components/shell/Logo";
import { StatusIcon } from "@/components/ui/StatusIcon";

// A static, illustrative recreation of the real live-run experience
// (components/run/ActivityFeed.tsx + ProgressTimeline.tsx) — not wired to
// a live run, since this page renders for logged-out visitors. Every piece
// of UI here (the feed row shape, the icon set, the checklist) matches the
// real product exactly; only the example query and numbers are staged.
const FEED = [
  { icon: Compass, label: "Planning research strategy", detail: "Decomposing question into sub-questions", done: true },
  { icon: Globe, label: "Searching academic literature (OpenAlex)", detail: "Found 1,247 papers", done: true },
  { icon: Globe, label: "Searching the web (Tavily)", detail: "Found 358 sources", done: true },
  { icon: FileSearch, label: "Extracting evidence", detail: "Extracted 186 claims", done: true },
  { icon: BookOpenCheck, label: "Fact-checking & verifying", detail: "Verified 163 claims", done: false },
];

const STAGES = ["Plan", "Research", "Extract", "Fact-check", "Contradictions", "Resolve", "Synthesize"];

const CHART_BARS = [
  { label: "Amine Absorption", value: 62 },
  { label: "Solid Sorbents", value: 88 },
  { label: "Membrane Separation", value: 54 },
  { label: "Cryogenic Distillation", value: 91 },
];

export function LandingPreviewPanel() {
  return (
    <div className="overflow-hidden rounded-card border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-2.5">
          <Logo size={22} />
          <span className="flex items-center gap-1.5 text-xs font-medium text-fg-muted">
            <span className="hero-breathing inline-block h-1.5 w-1.5 rounded-full bg-fg" />
            Research in progress
          </span>
        </div>
        <span className="rounded-pill border border-border px-2.5 py-1 text-[11px] tabular-nums text-fg-subtle">
          00:04:12
        </span>
      </div>

      <div className="border-b border-border px-6 py-5">
        <h3 className="font-[family-name:var(--font-display)] text-lg font-semibold text-fg">
          What are the most effective carbon capture technologies for industrial applications?
        </h3>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-fg-muted">
          <span className="rounded-pill border border-border px-2.5 py-1">Mode: Deep Research</span>
          <span className="rounded-pill border border-border px-2.5 py-1">Sub-questions: 12</span>
          <span className="rounded-pill border border-border px-2.5 py-1">Depth: High</span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1.3fr_1fr]">
        <div className="flex flex-col gap-3">
          <p className="text-xs font-medium uppercase tracking-[0.08em] text-fg-subtle">Live Activity Feed</p>
          <ul className="flex flex-col gap-3">
            {FEED.map((row, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm">
                <StatusIcon state={row.done ? "complete" : "active"} size={15} className="mt-0.5" />
                <row.icon size={14} className="mt-0.5 shrink-0 text-fg-subtle" />
                <div>
                  <p className="text-fg">{row.label}</p>
                  <p className="text-xs text-fg-subtle">{row.detail}</p>
                </div>
              </li>
            ))}
            <li className="flex items-start gap-2.5 text-sm text-fg-subtle">
              <GitCompareArrows size={14} className="mt-0.5 shrink-0" />
              <PenLine size={14} className="mt-0.5 shrink-0" />
              <span>Resolving conflicts, then synthesizing…</span>
            </li>
          </ul>
        </div>

        <div className="flex flex-col gap-5">
          <div>
            <p className="mb-2 flex items-center justify-between text-xs font-medium uppercase tracking-[0.08em] text-fg-subtle">
              <span>Progress</span>
              <span className="tabular-nums text-fg-muted">5 / 7 stages</span>
            </p>
            <div className="h-1.5 w-full overflow-hidden rounded-pill bg-surface-raised">
              <div className="h-full w-[71%] rounded-pill bg-fg" />
            </div>
            <ul className="mt-3 flex flex-col gap-1.5">
              {STAGES.map((s, i) => (
                <li key={s} className="flex items-center gap-2 text-xs text-fg-muted">
                  <StatusIcon state={i < 5 ? "complete" : "pending"} size={11} />
                  {s}
                </li>
              ))}
            </ul>
          </div>

          <div className="border-t border-border pt-4">
            <p className="text-xs font-medium uppercase tracking-[0.08em] text-fg-subtle">Sources Found</p>
            <p className="mt-1 font-[family-name:var(--font-display)] text-3xl font-semibold tabular-nums text-fg">
              1,575
            </p>
            <div className="mt-2 flex flex-col gap-1 text-xs text-fg-muted">
              <span>1,247 Academic (OpenAlex)</span>
              <span>258 Web (Tavily)</span>
              <span>70 Other</span>
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-border p-6">
        <p className="mb-3 text-xs font-medium uppercase tracking-[0.08em] text-fg-subtle">Live Preview — Report</p>
        <p className="mb-4 text-sm leading-relaxed text-fg-muted">
          Post-combustion amine absorption remains the most mature and widely deployed carbon
          capture technology, while solid sorbents and membrane-based approaches show promising
          potential for lower energy use in industrial applications.
          <sup className="ml-0.5 text-fg-subtle">[1][2][3]</sup>
        </p>
        <p className="mb-2 text-xs text-fg-subtle">Cost of CO&#8322; Captured (USD / ton)</p>
        <div className="flex items-end gap-4 border-b border-border pb-3">
          {CHART_BARS.map((bar) => (
            <div key={bar.label} className="flex flex-1 flex-col items-center gap-2">
              <div className="flex h-24 w-full items-end">
                <div
                  className="w-full rounded-t-sm bg-fg-muted"
                  style={{ height: `${bar.value}%` }}
                />
              </div>
              <span className="text-center text-[10px] leading-tight text-fg-subtle">{bar.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
