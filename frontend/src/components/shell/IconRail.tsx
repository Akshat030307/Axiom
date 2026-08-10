"use client";

import { BarChart3, FolderClosed, Home, Search, Settings, Star, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Avatar } from "@/components/ui/Avatar";
import { Tooltip } from "@/components/ui/Tooltip";
import { useAuth } from "@/hooks/useAuth";

import { Logo } from "./Logo";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  match: (pathname: string) => boolean;
}

// Route mapping per PRD §15.1: Projects → history, Analytics → evaluation,
// Saved → saved reports, Search → cross-run evidence search. The latter
// three (plus Search) are out of scope for Phase 4 and land on placeholder
// pages so the rail never dead-ends into a 404.
const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Home", icon: Home, match: (p) => p === "/" },
  { href: "/search", label: "Search", icon: Search, match: (p) => p.startsWith("/search") },
  { href: "/history", label: "Projects", icon: FolderClosed, match: (p) => p.startsWith("/history") },
  { href: "/evaluation", label: "Analytics", icon: BarChart3, match: (p) => p.startsWith("/evaluation") },
  { href: "/saved", label: "Saved", icon: Star, match: (p) => p.startsWith("/saved") },
  { href: "/settings", label: "Settings", icon: Settings, match: (p) => p.startsWith("/settings") },
];

export function IconRail() {
  const pathname = usePathname() ?? "";
  const { user, logout } = useAuth();

  return (
    <nav className="fixed inset-y-0 left-0 z-40 flex w-[110px] flex-col items-center gap-8 border-r border-border bg-black py-7">
      <Tooltip label="Axiom — Research, without the noise.">
        <Link href="/" aria-label="Axiom home">
          <Logo size={34} />
        </Link>
      </Tooltip>

      <ul className="flex flex-col items-center gap-2">
        {NAV_ITEMS.map(({ href, label, icon: Icon, match }) => {
          const active = match(pathname);
          return (
            <li key={href}>
              <Tooltip label={label}>
                <Link
                  href={href}
                  aria-label={label}
                  aria-current={active ? "page" : undefined}
                  className={`flex h-11 w-11 items-center justify-center rounded-xl transition-colors ${
                    active ? "bg-surface-raised text-fg" : "text-fg-muted hover:text-fg"
                  }`}
                >
                  <Icon size={20} strokeWidth={1.75} />
                </Link>
              </Tooltip>
            </li>
          );
        })}
      </ul>

      <div className="flex-1" />

      {user && (
        <Tooltip label={`Log out (${user.display_name ?? user.email})`}>
          <button onClick={logout} aria-label="Log out" className="rounded-full">
            <Avatar name={user.display_name ?? user.email} size={38} />
          </button>
        </Tooltip>
      )}
    </nav>
  );
}
