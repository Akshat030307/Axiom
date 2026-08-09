import { Check } from "lucide-react";

// The one place status→appearance is encoded: filled = complete, breathing
// ring = active, hollow ring = pending. Never a color (PRD §15.1) — every
// status indicator in the app (timeline rows, live-run header, citation
// fact-check state) should render through this component.
export type Status = "complete" | "active" | "pending";

interface StatusIconProps {
  state: Status;
  size?: number;
  className?: string;
}

export function StatusIcon({ state, size = 16, className = "" }: StatusIconProps) {
  const style = { width: size, height: size };

  if (state === "complete") {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-full bg-fg text-black ${className}`}
        style={style}
      >
        <Check size={Math.max(size * 0.65, 8)} strokeWidth={3} />
      </span>
    );
  }

  if (state === "active") {
    return (
      <span
        className={`hero-breathing inline-block shrink-0 rounded-full border border-fg ${className}`}
        style={style}
      />
    );
  }

  return (
    <span
      className={`inline-block shrink-0 rounded-full border border-fg-subtle ${className}`}
      style={style}
    />
  );
}
