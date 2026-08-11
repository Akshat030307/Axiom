"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState, type ReactNode } from "react";

import { AuthProvider } from "@/hooks/useAuth";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      {/* Framer Motion's own reduced-motion auto-detection can misfire on the
          very first SSR hydration paint (animations silently skip to their end
          state). We already gate every animation on our own useReducedMotion()
          checks, so disable the library's internal handling entirely — ours is
          the single source of truth. */}
      <MotionConfig reducedMotion="never">
        <AuthProvider>{children}</AuthProvider>
      </MotionConfig>
    </QueryClientProvider>
  );
}
