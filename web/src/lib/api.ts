import type {
  ApiKey,
  ApiKeyCreated,
  CompareResult,
  Credential,
  ProjectStats,
  Project,
  PublicTrace,
  Replay,
  ShareLink,
  TokenResponse,
  TraceDetail,
  TraceList,
  User,
} from "./types";

const TOKEN_KEY = "at-token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token === null) localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, token);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(path, { ...options, headers });
  if (response.status === 204) return undefined as T;

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* non-JSON error body */
  }
  if (!response.ok) {
    const detail = (body as { detail?: unknown })?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? (detail[0] as { msg?: string })?.msg ?? "Request failed"
          : `Request failed (${response.status})`;
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      setToken(null);
      window.dispatchEvent(new Event("at-unauthorized"));
    }
    throw new ApiError(response.status, message);
  }
  return body as T;
}

export const api = {
  // auth
  register: (payload: { email: string; name: string; password: string }) =>
    request<TokenResponse>("/api/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload: { email: string; password: string }) =>
    request<TokenResponse>("/api/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  me: () => request<User>("/api/auth/me"),

  // projects
  listProjects: () => request<Project[]>("/api/projects"),
  createProject: (payload: { name: string; description?: string }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),

  // api keys
  listApiKeys: (projectId: string) => request<ApiKey[]>(`/api/projects/${projectId}/api-keys`),
  createApiKey: (projectId: string, name: string) =>
    request<ApiKeyCreated>(`/api/projects/${projectId}/api-keys`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  revokeApiKey: (projectId: string, keyId: string) =>
    request<ApiKey>(`/api/projects/${projectId}/api-keys/${keyId}`, { method: "DELETE" }),

  // replay credentials
  listCredentials: (projectId: string) =>
    request<Credential[]>(`/api/projects/${projectId}/credentials`),
  putCredential: (
    projectId: string,
    payload: { provider: string; api_key: string; base_url?: string | null },
  ) =>
    request<Credential>(`/api/projects/${projectId}/credentials`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteCredential: (projectId: string, provider: string) =>
    request<void>(`/api/projects/${projectId}/credentials/${provider}`, { method: "DELETE" }),

  // traces
  listTraces: (
    projectId: string,
    params: { status?: string; q?: string; session_id?: string; limit?: number; offset?: number },
  ) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") search.set(key, String(value));
    }
    return request<TraceList>(`/api/projects/${projectId}/traces?${search}`);
  },
  getTrace: (tracePk: string) => request<TraceDetail>(`/api/traces/${tracePk}`),
  deleteTrace: (tracePk: string) => request<void>(`/api/traces/${tracePk}`, { method: "DELETE" }),
  projectStats: (projectId: string, hours = 24) =>
    request<ProjectStats>(`/api/projects/${projectId}/stats?hours=${hours}`),

  // replay
  createReplay: (
    spanPk: string,
    payload: {
      provider?: string;
      model?: string;
      messages?: Array<{ role: string; content: unknown }>;
      system?: string;
      params?: Record<string, unknown>;
    },
  ) =>
    request<Replay>(`/api/spans/${spanPk}/replays`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listReplays: (spanPk: string) => request<Replay[]>(`/api/spans/${spanPk}/replays`),

  // compare
  compare: (base: string, other: string) =>
    request<CompareResult>(`/api/compare?base=${base}&other=${other}`),

  // share
  createShare: (tracePk: string, expiresInHours?: number) =>
    request<ShareLink>(`/api/traces/${tracePk}/shares`, {
      method: "POST",
      body: JSON.stringify(expiresInHours ? { expires_in_hours: expiresInHours } : {}),
    }),
  listShares: (tracePk: string) => request<ShareLink[]>(`/api/traces/${tracePk}/shares`),
  revokeShare: (shareId: string) =>
    request<ShareLink>(`/api/shares/${shareId}`, { method: "DELETE" }),
  getSharedTrace: (token: string) => request<PublicTrace>(`/api/share/${token}`),
};
