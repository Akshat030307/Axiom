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
  highlight_enabled: boolean;
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
  title: string | null;
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

export interface EvalConfigResponse {
  dataset_size: number;
  max_eval_cost_usd: number;
}

export type EvalRunStatus = "running" | "completed" | "aborted_cost_ceiling";

export interface EvalQuestionResult {
  run_id: string;
  status?: string;
  reused_existing_run?: boolean;
  latency_seconds?: number | null;
  cost_usd?: number;
  new_spend_usd?: number;
  sources?: number;
  citation_accuracy?: number | null;
  claim_verification?: number | null;
  task_completion?: number | null;
  error?: string;
}

export interface EvalMetrics {
  status?: EvalRunStatus;
  per_question?: Record<string, EvalQuestionResult>;
  dataset_size?: number;
  questions_completed?: number;
  citation_accuracy?: number | null;
  claim_verification?: number | null;
  task_completion?: number | null;
  avg_latency_seconds?: number | null;
  avg_cost_usd?: number | null;
  avg_sources?: number | null;
}

export interface EvalStatusResponse {
  id: string;
  dataset_version: string | null;
  created_at: string;
  metrics: EvalMetrics;
}

export interface EvalListItem {
  id: string;
  dataset_version: string | null;
  created_at: string;
  status: string | null;
}

export interface EvalListResponse {
  items: EvalListItem[];
}

export interface EvalRunResponse {
  eval_id: string;
}

export interface FigureResponse {
  id: string;
  kind: string;
  caption: string;
  alt_text: string;
  mime_type: string;
  evidence_ids: string[];
  paired_figure_id: string | null;
}
