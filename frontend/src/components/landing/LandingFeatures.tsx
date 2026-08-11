"use client";

import {
  Search,
  ShieldCheck,
  Scale,
  ChartNoAxesColumn,
  FileCheck,
  Lock,
  Compass,
  Globe,
  FileSearch,
  BookOpenCheck,
  GitCompareArrows,
  PenLine,
} from "lucide-react";
import { motion, useReducedMotion, type Variants } from "motion/react";

const FEATURES = [
  {
    icon: Search,
    title: "Real sources",
    body: "Searches the web and academic literature (OpenAlex, 250M+ works) — never a single search, always the mode-appropriate one.",
  },
  {
    icon: ShieldCheck,
    title: "Fact-checked",
    body: "Independently verifies claims against a fresh search, with confidence scores and a real supported / unsupported / outdated verdict.",
  },
  {
    icon: Scale,
    title: "Contradictions",
    body: "Actively detects and explains genuine conflicts between credible sources — never silently picks a winner.",
  },
  {
    icon: ChartNoAxesColumn,
    title: "Evidence-first charts",
    body: "Charts are generated from real numeric evidence, never invented. The model never writes plotting code.",
  },
  {
    icon: FileCheck,
    title: "Cited reports",
    body: "Every sentence is cited or explicitly marked unverified. Export the finished report to PDF, figures included.",
  },
  {
    icon: Lock,
    title: "Private by design",
    body: "Research stays scoped to your account. API calls to model providers aren't used to train anything.",
  },
];

const STEPS = [
  { icon: Compass, label: "Plan" },
  { icon: Globe, label: "Search" },
  { icon: FileSearch, label: "Extract" },
  { icon: BookOpenCheck, label: "Fact-check" },
  { icon: GitCompareArrows, label: "Resolve conflicts" },
  { icon: PenLine, label: "Synthesize & cite" },
];

const TECH = ["LangGraph", "OpenAI", "Groq", "Tavily", "OpenAlex", "PostgreSQL", "Next.js"];

const grid: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};

const card: Variants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
};

export function LandingFeatures() {
  const reduceMotion = useReducedMotion();
  const viewport = { once: true, amount: 0.3 as const };

  return (
    <>
      <section id="features" className="mx-auto max-w-[1400px] px-8 py-20">
        <motion.div
          variants={reduceMotion ? undefined : grid}
          initial={reduceMotion ? false : "hidden"}
          whileInView={reduceMotion ? undefined : "show"}
          viewport={viewport}
          className="grid grid-cols-1 gap-px overflow-hidden rounded-card border border-border bg-border sm:grid-cols-2 lg:grid-cols-3"
        >
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <motion.div key={title} variants={card} className="flex flex-col gap-3 bg-bg p-7">
              <Icon size={18} className="text-fg-muted" />
              <h3 className="font-[family-name:var(--font-display)] text-base font-semibold text-fg">{title}</h3>
              <p className="text-sm leading-relaxed text-fg-muted">{body}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <section id="how-it-works" className="mx-auto max-w-[1400px] px-8 py-20">
        <motion.h2
          initial={reduceMotion ? false : { opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={viewport}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="mb-2 font-[family-name:var(--font-display)] text-3xl font-semibold tracking-[-0.01em] text-fg"
        >
          How it works
        </motion.h2>
        <motion.p
          initial={reduceMotion ? false : { opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={viewport}
          transition={{ duration: 0.5, ease: "easeOut", delay: 0.05 }}
          className="mb-10 max-w-xl text-sm text-fg-muted"
        >
          Fourteen graph nodes, six visible stages — every run moves through the same pipeline,
          streamed live so you can watch it happen.
        </motion.p>
        <motion.div
          variants={reduceMotion ? undefined : grid}
          initial={reduceMotion ? false : "hidden"}
          whileInView={reduceMotion ? undefined : "show"}
          viewport={viewport}
          className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-6"
        >
          {STEPS.map(({ icon: Icon, label }, i) => (
            <motion.div key={label} variants={card} className="flex flex-col gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-border-strong text-fg-muted">
                <Icon size={18} />
              </div>
              <p className="text-xs text-fg-subtle">Step {i + 1}</p>
              <p className="text-sm text-fg">{label}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <section id="architecture" className="border-t border-border py-16">
        <div className="mx-auto max-w-[1400px] px-8 text-center">
          <p className="mb-8 text-xs font-medium uppercase tracking-[0.12em] text-fg-subtle">
            Built with
          </p>
          <motion.div
            variants={reduceMotion ? undefined : grid}
            initial={reduceMotion ? false : "hidden"}
            whileInView={reduceMotion ? undefined : "show"}
            viewport={viewport}
            className="flex flex-wrap items-center justify-center gap-x-10 gap-y-5"
          >
            {TECH.map((name) => (
              <motion.span
                key={name}
                variants={card}
                className="font-[family-name:var(--font-display)] text-lg font-medium text-fg-muted transition-colors hover:text-fg"
              >
                {name}
              </motion.span>
            ))}
          </motion.div>
        </div>
      </section>

      <section className="border-t border-border py-20">
        <motion.div
          initial={reduceMotion ? false : { opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={viewport}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="mx-auto flex max-w-[1400px] flex-col items-center gap-5 px-8 text-center"
        >
          <h2 className="font-[family-name:var(--font-display)] text-3xl font-semibold tracking-[-0.01em] text-fg">
            Ask something real.
          </h2>
          <a
            href="/register"
            className="rounded-pill bg-accent px-6 py-3 text-sm font-medium text-black transition-[opacity,transform] hover:scale-[1.02] hover:opacity-90 active:scale-[0.98]"
          >
            Start Researching
          </a>
        </motion.div>
      </section>
    </>
  );
}
