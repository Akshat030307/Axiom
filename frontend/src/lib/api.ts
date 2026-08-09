import type {
  CreateRunResponse,
  ReportResponse,
  ResearchMode,
  RunStatusResponse,
  TokenResponse,
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

export async function createResearch(
  token: string,
  query: string,
  mode: ResearchMode
): Promise<CreateRunResponse> {
  const res = await fetch(`${API_URL}/api/v1/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ query, mode }),
  });
  return handleResponse<CreateRunResponse>(res);
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
