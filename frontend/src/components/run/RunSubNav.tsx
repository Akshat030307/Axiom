"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { key: "report", label: "Report" },
  { key: "sources", label: "Sources" },
  { key: "evidence", label: "Evidence" },
  { key: "trace", label: "Trace" },
] as const;

export function RunSubNav({ runId, className = "" }: { runId: string; className?: string }) {
  const pathname = usePathname() ?? "";

  return (
    <nav className={`mb-8 flex gap-1 border-b border-border ${className}`}>
      {TABS.map((tab) => {
        const href = `/research/${runId}/${tab.key}`;
        const active = pathname === href;
        return (
          <Link
            key={tab.key}
            href={href}
            className={`border-b-2 px-4 py-2.5 text-sm transition-colors ${
              active ? "border-fg text-fg" : "border-transparent text-fg-muted hover:text-fg"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
