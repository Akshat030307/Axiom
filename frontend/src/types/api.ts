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

// AccessTokenResponse in the backend, but /auth/refresh rotates and returns a
// NEW refresh token too (see routes_auth.py's comment on why) — the field
// name kept as refresh_token to match the wire shape exactly.
export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
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

export interface RunHistoryResponse {
  items: RunStatusResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface SourceResponse {
  id: string;
  url: string;
  title: string | null;
  domain: string | null;
  source_type: string | null;
  publication_date: string | null;
  credibility_score: number | null;
  fetched_at: string;
  evidence_count: number;
}

export interface EvidenceSource {
  id: string;
  url: string;
  title: string | null;
  domain: string | null;
  source_type: string | null;
  credibility_score: number | null;
}

export type FactCheckStatus = "supported" | "unsupported" | "unverified" | "outdated";

export interface EvidenceResponse {
  id: string;
  claim: string;
  relevant_excerpt: string;
  confidence: number | null;
  agent: string | null;
  topic: string | null;
  sub_question_index: number | null;
  numeric_value: number | null;
  numeric_unit: string | null;
  time_period: string | null;
  source: EvidenceSource | null;
  fact_check_status: FactCheckStatus | null;
  fact_check_notes: string | null;
  verifying_source_url: string | null;
}

export interface ContradictionResponse {
  id: string;
  topic: string | null;
  evidence_a_id: string | null;
  evidence_a_claim: string | null;
  evidence_b_id: string | null;
  evidence_b_claim: string | null;
  explanation: string | null;
  resolved: boolean;
}

export interface NodeTraceResponse {
  id: string;
  node_name: string;
  seq: number;
  input: unknown;
  output: unknown;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number | null;
  cost_usd: number | null;
  status: string | null;
  error: string | null;
  started_at: string | null;
  ended_at: string | null;
}
