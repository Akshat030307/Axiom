"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { IconRail } from "@/components/shell/IconRail";
import { useAuth } from "@/hooks/useAuth";

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, bootstrapping } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!bootstrapping && !user) router.replace("/login");
  }, [bootstrapping, user, router]);

  if (bootstrapping) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <span className="text-sm text-fg-subtle">Loading…</span>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="min-h-screen bg-bg">
      <IconRail />
      <div className="pl-[110px]">{children}</div>
    </div>
  );
}
