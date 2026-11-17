import type {
  ApiKey,
  ApiKeyCreated,
  CompareResult,
  Credential,
  Dataset,
  DatasetItem,
  DatasetItemList,
  EvalResult,
  Evaluator,
  EvaluatorTemplate,
  Experiment,
  ExperimentComparison,
  ExperimentItem,
  ProjectStats,
  Project,
  PublicTrace,
  Replay,
  Score,
  ScoreSummary,
  ShareLink,
  TokenResponse,
  TraceDetail,
  TraceList,
  User,
} from "./types";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return apiBaseUrl + path;
}

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

async function request<T>(
  path: string,
  options: RequestInit & { text?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(apiUrl(path), { ...options, headers });
  if (response.status === 204) return undefined as T;

  let body: unknown = null;
  try {
    body = options.text && response.ok ? await response.text() : await response.json();
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

  // datasets
  listDatasets: (projectId: string) => request<Dataset[]>(`/api/projects/${projectId}/datasets`),
  createDataset: (projectId: string, payload: { name: string; description?: string }) =>
    request<Dataset>(`/api/projects/${projectId}/datasets`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getDataset: (datasetId: string) => request<Dataset>(`/api/datasets/${datasetId}`),
  deleteDataset: (datasetId: string) =>
    request<void>(`/api/datasets/${datasetId}`, { method: "DELETE" }),
  listDatasetItems: (datasetId: string, params: { limit?: number; offset?: number } = {}) =>
    request<DatasetItemList>(
      `/api/datasets/${datasetId}/items?limit=${params.limit ?? 50}&offset=${params.offset ?? 0}`,
    ),
  createDatasetItems: (
    datasetId: string,
    items: Array<{ input: unknown; expected_output?: unknown; metadata?: unknown }>,
  ) =>
    request<DatasetItem[]>(`/api/datasets/${datasetId}/items`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  addTracesToDataset: (
    datasetId: string,
    sources: Array<{ trace_pk: string; span_pk?: string | null }>,
  ) =>
    request<DatasetItem[]>(`/api/datasets/${datasetId}/items/from-traces`, {
      method: "POST",
      body: JSON.stringify({ sources }),
    }),
  updateDatasetItem: (
    itemId: string,
    payload: { input?: unknown; expected_output?: unknown; archived?: boolean },
  ) =>
    request<DatasetItem>(`/api/dataset-items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteDatasetItem: (itemId: string) =>
    request<void>(`/api/dataset-items/${itemId}`, { method: "DELETE" }),
  importDataset: (datasetId: string, format: "jsonl" | "csv", content: string) =>
    request<DatasetItem[]>(`/api/datasets/${datasetId}/import`, {
      method: "POST",
      body: JSON.stringify({ format, content }),
    }),
  exportDataset: (datasetId: string) =>
    request<string>(`/api/datasets/${datasetId}/export`, { text: true }),

  // evaluators
  listTemplates: () => request<EvaluatorTemplate[]>("/api/evaluator-templates"),
  listEvaluators: (projectId: string) =>
    request<Evaluator[]>(`/api/projects/${projectId}/evaluators`),
  createEvaluator: (
    projectId: string,
    payload: { name: string; template: string; config: Record<string, unknown> },
  ) =>
    request<Evaluator>(`/api/projects/${projectId}/evaluators`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteEvaluator: (evaluatorId: string) =>
    request<void>(`/api/evaluators/${evaluatorId}`, { method: "DELETE" }),
  evaluateTrace: (tracePk: string, evaluatorIds: string[], spanPk?: string | null) =>
    request<EvalResult[]>(`/api/traces/${tracePk}/evaluate`, {
      method: "POST",
      body: JSON.stringify({ evaluator_ids: evaluatorIds, span_pk: spanPk ?? null }),
    }),

  // experiments
  listExperiments: (projectId: string) =>
    request<Experiment[]>(`/api/projects/${projectId}/experiments`),
  createExperiment: (
    projectId: string,
    payload: {
      name: string;
      dataset_id: string;
      target: { model: string; system?: string; messages?: unknown[] };
      evaluator_ids: string[];
    },
  ) =>
    request<Experiment>(`/api/projects/${projectId}/experiments`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getExperiment: (experimentId: string) =>
    request<Experiment>(`/api/experiments/${experimentId}`),
  listExperimentItems: (experimentId: string) =>
    request<{ items: ExperimentItem[]; total: number }>(
      `/api/experiments/${experimentId}/items?limit=500`,
    ),
  deleteExperiment: (experimentId: string) =>
    request<void>(`/api/experiments/${experimentId}`, { method: "DELETE" }),
  compareExperiments: (ids: string[]) =>
    request<ExperimentComparison>(`/api/experiments/compare?ids=${ids.join(",")}`),

  // scores
  listScores: (tracePk: string) => request<Score[]>(`/api/traces/${tracePk}/scores`),
  createScore: (
    tracePk: string,
    payload: {
      name: string;
      value: number | boolean | string;
      span_pk?: string | null;
      comment?: string;
    },
  ) =>
    request<Score>(`/api/traces/${tracePk}/scores`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteScore: (scoreId: string) => request<void>(`/api/scores/${scoreId}`, { method: "DELETE" }),
  scoreSummary: (projectId: string, hours = 168) =>
    request<ScoreSummary[]>(`/api/projects/${projectId}/scores/summary?hours=${hours}`),

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
