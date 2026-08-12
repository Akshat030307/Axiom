"use client";

import { Highlighter } from "lucide-react";

interface HighlightToggleProps {
  value: boolean;
  onChange: (value: boolean) => void;
}

// Set once, at submission time, alongside mode — not something that can be
// flipped after the fact, since it controls what the model writes into
// report_markdown, not just how an already-written report renders.
export function HighlightToggle({ value, onChange }: HighlightToggleProps) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      aria-pressed={value}
      title="Highlight the one key sentence per section in the report and its PDF export"
      className={`flex items-center gap-2 rounded-pill border px-4 py-2.5 text-sm transition-colors ${
        value
          ? "border-border-strong bg-surface-raised font-medium text-fg"
          : "border-border text-fg-muted hover:text-fg"
      }`}
    >
      <Highlighter size={16} strokeWidth={1.75} />
      Highlight key sentences
    </button>
  );
}
