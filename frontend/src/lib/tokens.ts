import { GraduationCap, Sparkles, SignalHigh, Zap, type LucideIcon } from "lucide-react";

import type { ResearchMode } from "@/types/api";

export interface ModeMeta {
  value: ResearchMode;
  label: string;
  icon: LucideIcon;
}

// Single source of truth for the 4 research modes' display metadata, shared
// by ModeSelector, LiveRunCard, RecentResearch, and History rows.
export const RESEARCH_MODES: ModeMeta[] = [
  { value: "deep", label: "Deep Research", icon: Sparkles },
  { value: "quick", label: "Quick Research", icon: Zap },
  { value: "academic", label: "Academic Research", icon: GraduationCap },
  { value: "competitive", label: "Competitive Intel", icon: SignalHigh },
];

export function modeLabel(mode: string): string {
  return RESEARCH_MODES.find((m) => m.value === mode)?.label ?? mode;
}
