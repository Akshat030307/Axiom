export function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.max(0, Math.round(diffMs / 60000));
  if (mins < 1) return "just now";
  if (mins === 1) return "1 min ago";
  if (mins < 60) return `${mins} mins ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr${hours > 1 ? "s" : ""} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days > 1 ? "s" : ""} ago`;
  const weeks = Math.round(days / 7);
  return `${weeks} week${weeks > 1 ? "s" : ""} ago`;
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds <= 0) return "Done";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `~${m}:${s.toString().padStart(2, "0")}`;
}
