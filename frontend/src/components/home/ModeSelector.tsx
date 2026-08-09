"use client";

import { RESEARCH_MODES } from "@/lib/tokens";
import type { ResearchMode } from "@/types/api";

interface ModeSelectorProps {
  value: ResearchMode;
  onChange: (mode: ResearchMode) => void;
}

export function ModeSelector({ value, onChange }: ModeSelectorProps) {
  return (
    <div className="flex flex-wrap gap-3">
      {RESEARCH_MODES.map(({ value: modeValue, label, icon: Icon }) => {
        const active = modeValue === value;
        return (
          <button
            key={modeValue}
            type="button"
            onClick={() => onChange(modeValue)}
            aria-pressed={active}
            className={`flex items-center gap-2 rounded-pill border px-4 py-2.5 text-sm transition-colors ${
              active
                ? "border-border-strong bg-surface-raised font-medium text-fg"
                : "border-border text-fg-muted hover:text-fg"
            }`}
          >
            <Icon size={16} strokeWidth={1.75} />
            {label}
          </button>
        );
      })}
    </div>
  );
}
