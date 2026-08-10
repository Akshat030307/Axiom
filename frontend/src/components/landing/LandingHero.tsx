import Link from "next/link";
import { ArrowRight, PlayCircle, ShieldCheck, FileCheck, ChartNoAxesColumn, Lock } from "lucide-react";

import { LandingPreviewPanel } from "./LandingPreviewPanel";

const TRUST_CHIPS = [
  { icon: ShieldCheck, label: "Every claim fact-checked" },
  { icon: FileCheck, label: "100% cited or unverified" },
  { icon: ChartNoAxesColumn, label: "Charts from real evidence" },
  { icon: Lock, label: "Your data stays yours" },
];

export function LandingHero() {
  return (
    <section className="mx-auto grid max-w-[1400px] grid-cols-1 items-center gap-14 px-8 py-20 lg:grid-cols-[1fr_1.15fr] lg:py-28">
      <div className="flex flex-col gap-6">
        <span className="w-fit rounded-pill border border-border-strong px-3.5 py-1.5 text-xs text-fg-muted">
          <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-fg align-middle" />
          Research, without the noise.
        </span>

        <h1 className="font-[family-name:var(--font-display)] text-5xl font-semibold leading-[1.05] tracking-[-0.02em] text-fg lg:text-6xl">
          Ask anything.
          <br />
          Get evidence.
          <br />
          Not hallucinations.
        </h1>

        <p className="max-w-lg text-base leading-relaxed text-fg-muted">
          Axiom runs a 14-step research pipeline to plan, search, extract, fact-check, and
          synthesize real evidence across the web and academic literature — streamed live, fully
          cited, and exportable as PDF.
        </p>

        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/register"
            className="flex items-center gap-2 rounded-pill bg-accent px-5 py-3 text-sm font-medium text-black transition-opacity hover:opacity-90"
          >
            Start Researching
            <ArrowRight size={15} />
          </Link>
          <a
            href="#how-it-works"
            className="flex items-center gap-2 rounded-pill border border-border-strong px-5 py-3 text-sm text-fg transition-colors hover:bg-surface-raised"
          >
            <PlayCircle size={15} />
            View Live Demo
          </a>
        </div>

        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-3">
          {TRUST_CHIPS.map(({ icon: Icon, label }) => (
            <span key={label} className="flex items-center gap-2 text-xs text-fg-muted">
              <Icon size={14} className="text-fg-subtle" />
              {label}
            </span>
          ))}
        </div>
      </div>

      <LandingPreviewPanel />
    </section>
  );
}
