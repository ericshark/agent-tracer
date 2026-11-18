export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
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
  scopes?: string[] | null;
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
  user_id?: string | null;
  tags?: string[] | null;
  environment?: string | null;
  release?: string | null;
  /** score name → mean value, or the latest label for categorical scores */
  scores?: Record<string, number | string> | null;
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
  cache_read_tokens?: number | null;
  cache_creation_tokens?: number | null;
  reasoning_tokens?: number | null;
  ttft_ms?: number | null;
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
  next_cursor?: string | null;
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
  duration_ms: number | null;
  span_count: number;
  error_count: number;
  llm_call_count: number;
  input_tokens: number;
  output_tokens: number;
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

export interface Dataset {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  item_count: number;
}

export interface DatasetItem {
  id: string;
  dataset_id: string;
  input: unknown;
  expected_output: unknown;
  meta: Record<string, unknown> | null;
  source_trace_pk: string | null;
  source_span_pk: string | null;
  archived_at: string | null;
  created_at: string;
}

export interface DatasetItemList {
  items: DatasetItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface TemplateParam {
  name: string;
  type: "string" | "number" | "boolean" | "string_list" | "json" | "select";
  description: string;
  default: unknown;
  required: boolean;
  options: string[];
}

export interface EvaluatorTemplate {
  key: string;
  kind: "code" | "trajectory" | "llm_judge";
  title: string;
  description: string;
  data_type: string;
  needs_expected: boolean;
  needs_trace: boolean;
  params: TemplateParam[];
}

export interface Evaluator {
  id: string;
  name: string;
  template: string;
  config: Record<string, unknown>;
  created_at: string;
}

export interface EvalResult {
  name: string | null;
  value: number | boolean | string | null;
  data_type: string;
  comment: string | null;
  error: string | null;
}

export interface ItemScore {
  value: number | boolean | string | null;
  data_type: string | null;
  comment: string | null;
  source?: string;
  error?: string;
}

export interface ExperimentSummary {
  item_count: number;
  error_count: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  total_cost_usd: number;
  total_tokens: number;
  scores: Record<
    string,
    { data_type: string | null; count: number; mean: number | null; errors: number }
  >;
}

export interface Experiment {
  id: string;
  name: string;
  description: string | null;
  status: "pending" | "running" | "completed" | "failed";
  dataset_id: string | null;
  target: { type?: string; model?: string; system?: string; messages?: unknown[] };
  evaluator_ids: string[];
  summary: ExperimentSummary | null;
  meta: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  item_count: number;
  completed_count: number;
}

export interface ExperimentItem {
  id: string;
  dataset_item_id: string | null;
  input: unknown;
  expected_output: unknown;
  output: unknown;
  status: "pending" | "ok" | "error";
  error: string | null;
  trace_pk: string | null;
  latency_ms: number | null;
  cost_usd: number | null;
  scores: Record<string, ItemScore> | null;
}

export interface CompareScoreEntry {
  experiment_id: string;
  mean: number | null;
  count: number;
  paired?: number;
  delta?: number | null;
  improved?: number;
  regressed?: number;
  unchanged?: number;
  ci_low?: number | null;
  ci_high?: number | null;
}

export interface ExperimentComparison {
  experiments: Experiment[];
  baseline_id: string;
  scores: Record<string, CompareScoreEntry[]>;
  rows: Array<{
    key: string;
    input: unknown;
    expected_output: unknown;
    cells: Record<
      string,
      {
        output: unknown;
        status: string;
        error: string | null;
        scores: Record<string, ItemScore>;
        latency_ms: number | null;
        trace_pk: string | null;
      }
    >;
  }>;
}

export type ScoreDataType = "numeric" | "boolean" | "categorical";

export interface Score {
  id: string;
  trace_pk: string;
  span_pk: string | null;
  name: string;
  data_type: ScoreDataType;
  value: number | null;
  string_value: string | null;
  comment: string | null;
  source: "sdk" | "api" | "human" | "evaluator";
  author_id: string | null;
  created_at: string;
}

export interface ScoreSummary {
  name: string;
  data_type: ScoreDataType;
  count: number;
  mean: number | null;
  min: number | null;
  max: number | null;
  distribution: Record<string, number>;
  series: Array<{ bucket_start: string; count: number; mean: number | null }>;
}

export type LiveEvent =
  | { type: "connected" }
  | { type: "score.created"; trace_pk: string; score: Score }
  | { type: "experiment.updated"; experiment_id: string; status: string }
  | { type: "trace.updated"; trace: TraceSummary }
  | { type: "span.upserted"; trace_pk: string; trace_id: string; span: Span };
