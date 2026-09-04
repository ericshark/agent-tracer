export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  key: string;
}

export interface Credential {
  provider: "anthropic" | "openai";
  masked_key: string;
  base_url: string | null;
  updated_at: string;
}

export type TraceStatus = "running" | "ok" | "error";

export type SpanKind =
  | "AGENT"
  | "LLM"
  | "TOOL"
  | "CHAIN"
  | "RETRIEVER"
  | "EMBEDDING"
  | "GUARDRAIL"
  | "UNKNOWN";

export interface TraceSummary {
  id: string;
  trace_id: string;
  name: string;
  status: TraceStatus;
  session_id: string | null;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  span_count: number;
  error_count: number;
  llm_call_count: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  meta: Record<string, unknown> | null;
}

export interface Span {
  id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: SpanKind;
  status: TraceStatus;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  input: unknown;
  output: unknown;
  attributes: Record<string, unknown> | null;
  events: Array<{ name: string; timestamp: string; attributes?: Record<string, unknown> }> | null;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  error_type: string | null;
  error_message: string | null;
  error_stacktrace: string | null;
}

export interface TraceDetail extends TraceSummary {
  spans: Span[];
}

export interface TraceList {
  items: TraceSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface StatsBucket {
  bucket_start: string;
  trace_count: number;
  error_count: number;
  avg_duration_ms: number | null;
  total_tokens: number;
  cost_usd: number;
}

export interface ProjectStats {
  window_hours: number;
  trace_count: number;
  error_count: number;
  error_rate: number;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  buckets: StatsBucket[];
}

export interface Replay {
  id: string;
  span_pk: string;
  provider: string;
  model: string;
  input: {
    messages: Array<{ role: string; content: unknown }>;
    system: string | null;
    model: string;
    params: Record<string, unknown>;
  };
  output: { role?: string; content?: string; simulated?: boolean; stop_reason?: string } | null;
  status: "ok" | "error";
  error_message: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface ShareLink {
  id: string;
  token: string;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface PublicTrace {
  trace: TraceSummary;
  spans: Span[];
  project_name: string;
}

export interface SpanBrief {
  id: string;
  span_id: string;
  name: string;
  kind: SpanKind;
  status: TraceStatus;
  duration_ms: number | null;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  error_message: string | null;
}

export interface DiffDelta {
  status_changed: boolean;
  input_changed: boolean;
  output_changed: boolean;
  duration_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
}

export interface DiffNode {
  change: "matched" | "added" | "removed";
  base: SpanBrief | null;
  other: SpanBrief | null;
  delta: DiffDelta | null;
  children: DiffNode[];
}

export interface CompareResult {
  base: TraceSummary;
  other: TraceSummary;
  nodes: DiffNode[];
  summary: { matched: number; added: number; removed: number; changed: number };
}

export type LiveEvent =
  | { type: "connected" }
  | { type: "trace.updated"; trace: TraceSummary }
  | { type: "span.upserted"; trace_pk: string; trace_id: string; span: Span };
