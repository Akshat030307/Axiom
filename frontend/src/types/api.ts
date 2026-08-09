export type ResearchMode = "quick" | "deep" | "academic" | "competitive";

export interface User {
  id: string;
  email: string;
  display_name: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  user: User;
}

export interface CreateRunResponse {
  run_id: string;
}

export type RunStatus = "pending" | "running" | "completed" | "error";

export interface RunStatusResponse {
  run_id: string;
  status: RunStatus;
  mode: ResearchMode;
  query: string;
  started_at: string;
  completed_at: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_estimate_usd: number;
  latency_seconds: number | null;
}

export interface Citation {
  marker: number;
  evidence_id: string;
  source_id: string;
}

export interface ReportResponse {
  markdown: string;
  citations: Citation[];
  figures: unknown[];
}
