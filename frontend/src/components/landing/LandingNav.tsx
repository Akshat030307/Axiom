import Link from "next/link";
import { Github } from "lucide-react";

import { Logo } from "@/components/shell/Logo";

const NAV_LINKS = [
  { label: "Features", href: "#features" },
  { label: "How it Works", href: "#how-it-works" },
  { label: "Architecture", href: "#architecture" },
  { label: "Evaluation", href: "/evaluation" },
  { label: "Docs", href: "https://github.com/Akshat030307/Axiom#readme" },
];

export function LandingNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/80 backdrop-blur">
      <div className="mx-auto flex max-w-[1400px] items-center justify-between px-8 py-4">
        <Link href="/welcome" className="flex items-center gap-2.5">
          <Logo size={30} />
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold tracking-[-0.01em] text-fg">
            Axiom
          </span>
        </Link>

        <nav className="hidden items-center gap-7 md:flex">
          {NAV_LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm text-fg-muted transition-colors hover:text-fg"
              {...(link.href.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <a
            href="https://github.com/Akshat030307/Axiom"
            target="_blank"
            rel="noreferrer"
            aria-label="View source on GitHub"
            className="flex h-9 w-9 items-center justify-center rounded-full border border-border-strong text-fg-muted transition-colors hover:text-fg"
          >
            <Github size={16} />
          </a>
          <Link
            href="/login"
            className="rounded-pill border border-border-strong px-4 py-2 text-sm text-fg transition-colors hover:bg-surface-raised"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="rounded-pill bg-accent px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90"
          >
            Get Started
          </Link>
        </div>
      </div>
    </header>
  );
}
