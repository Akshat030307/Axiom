// The only permitted color anywhere in the app (PRD §15.1) — the presence
// dot on the avatar. Everything else in the chrome stays monochrome.
const PRESENCE_COLOR = "#34d399";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0] + parts[parts.length - 1]![0]).toUpperCase();
}

interface AvatarProps {
  name: string;
  size?: number;
  online?: boolean;
  className?: string;
}

export function Avatar({ name, size = 36, online = true, className }: AvatarProps) {
  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center rounded-full border border-border-strong bg-surface-raised text-fg-muted ${className ?? ""}`}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
    >
      <span className="font-medium">{initials(name)}</span>
      {online && (
        <span
          className="absolute rounded-full ring-2 ring-black"
          style={{ width: size * 0.26, height: size * 0.26, right: -1, bottom: -1, background: PRESENCE_COLOR }}
          aria-hidden
        />
      )}
    </span>
  );
}
