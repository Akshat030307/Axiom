"use client";

export function CitationMarker({ marker, onClick }: { marker: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mx-0.5 inline-flex h-4 min-w-4 translate-y-[-4px] items-center justify-center rounded px-1 text-[10px] font-medium text-fg-muted underline decoration-dotted underline-offset-2 transition-colors hover:text-fg"
      aria-label={`View citation ${marker}`}
    >
      {marker}
    </button>
  );
}
