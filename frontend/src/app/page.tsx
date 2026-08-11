"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { LandingFeatures } from "@/components/landing/LandingFeatures";
import { LandingHero } from "@/components/landing/LandingHero";
import { LandingNav } from "@/components/landing/LandingNav";
import { useAuth } from "@/hooks/useAuth";

// The marketing page for logged-out visitors, and the redirect point for
// logged-in ones — this replaces the old split where `/` went straight to
// the (app) dashboard (hard-redirecting anyone unauthenticated to /login)
// and the landing page lived at the separate /welcome path. The dashboard
// itself now lives at /home.
export default function RootPage() {
  const { user, bootstrapping } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!bootstrapping && user) router.replace("/home");
  }, [bootstrapping, user, router]);

  if (bootstrapping || user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <span className="text-sm text-fg-subtle">Loading…</span>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-bg">
      <LandingNav />
      <LandingHero />
      <LandingFeatures />
    </main>
  );
}
