// Magnitude via fill amount, never hue — credibility is not a status, so it
// doesn't go through StatusIcon, but it follows the same monochrome rule.
const SEGMENTS = 5;

export function CredibilityMeter({ score }: { score: number | null }) {
  const filled = score == null ? 0 : Math.round(score * SEGMENTS);

  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-0.5" role="img" aria-label={score != null ? `Credibility ${score.toFixed(2)}` : "Credibility unknown"}>
        {Array.from({ length: SEGMENTS }, (_, i) => (
          <span
            key={i}
            className={`h-2.5 w-1.5 rounded-sm ${i < filled ? "bg-fg" : "border border-border bg-transparent"}`}
          />
        ))}
      </div>
      <span className="tabular-nums text-xs text-fg-muted">{score != null ? score.toFixed(2) : "—"}</span>
    </div>
  );
}
