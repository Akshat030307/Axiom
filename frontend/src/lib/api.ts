import type {
  ContradictionResponse,
  CreateRunResponse,
  EvalConfigResponse,
  EvalListResponse,
  EvalRunResponse,
  EvalStatusResponse,
  EvidenceResponse,
  FigureResponse,
  NodeTraceResponse,
  RefreshResponse,
  ReportResponse,
  ResearchMode,
  RunHistoryResponse,
  RunStatusResponse,
  SourceResponse,
  TokenResponse,
  User,
} from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function register(
  email: string,
  password: string,
  displayName?: string
): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName || null }),
  });
  return handleResponse<TokenResponse>(res);
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse<TokenResponse>(res);
}

export async function refresh(refreshToken: string): Promise<RefreshResponse> {
  const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  return handleResponse<RefreshResponse>(res);
}

export async function me(token: string): Promise<User> {
  const res = await fetch(`${API_URL}/api/v1/auth/me`, { headers: authHeaders(token) });
  return handleResponse<User>(res);
}

export async function logout(refreshToken: string): Promise<void> {
  await fetch(`${API_URL}/api/v1/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function createResearch(
  token: string,
  query: string,
  mode: ResearchMode,
  highlightEnabled = true
): Promise<CreateRunResponse> {
  const res = await fetch(`${API_URL}/api/v1/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ query, mode, highlight_enabled: highlightEnabled }),
  });
  return handleResponse<CreateRunResponse>(res);
}

export async function listResearchHistory(
  token: string,
  limit = 20,
  offset = 0
): Promise<RunHistoryResponse> {
  const res = await fetch(`${API_URL}/api/v1/research?limit=${limit}&offset=${offset}`, {
    headers: authHeaders(token),
  });
  return handleResponse<RunHistoryResponse>(res);
}

export async function getResearchStatus(token: string, runId: string): Promise<RunStatusResponse> {
  const res = await fetch(`${API_URL}/api/v1/research/${runId}`, {
    headers: authHeaders(token),
  });
  return handleResponse<RunStatusResponse>(res);
}

export async function getReport(token: string, runId: string): Promise<ReportResponse> {
  const res = await fetch(`${API_URL}/api/v1/research/${runId}/report`, {
    headers: authHeaders(token),
  });
  return handleResponse<ReportResponse>(res);
}

export async function listSources(token: string, runId: string): Promise<SourceResponse[]> {
  const res = await fetch(`${API_URL}/api/v1/research/${runId}/sources`, {
    headers: authHeaders(token),
  });
  return handleResponse<SourceResponse[]>(res);
}

export async function listEvidence(token: string, runId: string): Promise<EvidenceResponse[]> {
  const res = await fetch(`${API_URL}/api/v1/research/${runId}/evidence`, {
    headers: authHeaders(token),
  });
  return handleResponse<EvidenceResponse[]>(res);
}

export async function listContradictions(token: string, runId: string): Promise<ContradictionResponse[]> {
  const res = await fetch(`${API_URL}/api/v1/research/${runId}/contradictions`, {
    headers: authHeaders(token),
  });
  return handleResponse<ContradictionResponse[]>(res);
}

export async function listTrace(token: string, runId: string): Promise<NodeTraceResponse[]> {
  const res = await fetch(`${API_URL}/api/v1/research/${runId}/trace`, {
    headers: authHeaders(token),
  });
  return handleResponse<NodeTraceResponse[]>(res);
}

export async function getEvalConfig(token: string): Promise<EvalConfigResponse> {
  const res = await fetch(`${API_URL}/api/v1/eval/config`, { headers: authHeaders(token) });
  return handleResponse<EvalConfigResponse>(res);
}

export async function listEvals(token: string, limit = 20): Promise<EvalListResponse> {
  const res = await fetch(`${API_URL}/api/v1/eval?limit=${limit}`, { headers: authHeaders(token) });
  return handleResponse<EvalListResponse>(res);
}

export async function getEval(token: string, evalId: string): Promise<EvalStatusResponse> {
  const res = await fetch(`${API_URL}/api/v1/eval/${evalId}`, { headers: authHeaders(token) });
  return handleResponse<EvalStatusResponse>(res);
}

export async function startEval(token: string): Promise<EvalRunResponse> {
  const res = await fetch(`${API_URL}/api/v1/eval/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({}),
  });
  return handleResponse<EvalRunResponse>(res);
}

// PRD §7.2 / §14: POST returns {download_url} once the export finishes
// server-side. As of this build the backend has no /export module and
// routes_reports.py exposes no /report/pdf route — this is written to the
// documented contract so the backend piece is a drop-in later; today it
// will 404 until that exists.
export interface ExportPdfResponse {
  download_url: string;
}

export async function exportReportPdf(token: string, runId: string): Promise<ExportPdfResponse> {
  const res = await fetch(`${API_URL}/api/v1/research/${runId}/report/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
  });
  return handleResponse<ExportPdfResponse>(res);
}

// Downloads happen via an authenticated fetch-then-blob rather than a plain
// <a href> navigation, since a browser navigation can't attach the Bearer
// token — consistent with every other protected resource in this app
// (PRD's figures route is described the same way: "auth-checked", never a
// static directory).
export async function downloadFile(token: string, url: string, filename: string): Promise<void> {
  const fullUrl = url.startsWith("http") ? url : `${API_URL}${url}`;
  const res = await fetch(fullUrl, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

export async function listFigures(token: string, runId: string): Promise<FigureResponse[]> {
  const res = await fetch(`${API_URL}/api/v1/research/${runId}/figures`, { headers: authHeaders(token) });
  return handleResponse<FigureResponse[]>(res);
}

// Same reasoning as downloadFile: a plain <img src> can't carry a Bearer
// token, so the bytes are fetched authenticated and handed back as a blob
// URL for the caller to set as the image source.
export async function fetchFigureObjectUrl(token: string, figureId: string): Promise<string> {
  const res = await fetch(`${API_URL}/api/v1/figures/${figureId}/file`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`Failed to load figure (${res.status})`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
