import type { Span } from "./types";

export interface SpanNode {
  span: Span;
  children: SpanNode[];
  depth: number;
}

/** Build a depth-annotated tree from a flat span list (orphans become roots). */
export function buildSpanTree(spans: Span[]): SpanNode[] {
  const byId = new Map<string, SpanNode>();
  for (const span of spans) {
    byId.set(span.span_id, { span, children: [], depth: 0 });
  }
  const roots: SpanNode[] = [];
  for (const node of byId.values()) {
    const parent = node.span.parent_span_id ? byId.get(node.span.parent_span_id) : undefined;
    if (parent && parent !== node) parent.children.push(node);
    else roots.push(node);
  }
  const byTime = (a: SpanNode, b: SpanNode) =>
    new Date(a.span.started_at).getTime() - new Date(b.span.started_at).getTime();
  const assignDepth = (nodes: SpanNode[], depth: number) => {
    nodes.sort(byTime);
    for (const node of nodes) {
      node.depth = depth;
      assignDepth(node.children, depth + 1);
    }
  };
  assignDepth(roots, 0);
  return roots;
}

/** Pre-order flatten for rendering as indented rows. */
export function flattenTree(roots: SpanNode[]): SpanNode[] {
  const out: SpanNode[] = [];
  const walk = (nodes: SpanNode[]) => {
    for (const node of nodes) {
      out.push(node);
      walk(node.children);
    }
  };
  walk(roots);
  return out;
}

/**
 * Which span should the inspector open on?
 *
 * Prefer the *innermost* failure — an error span with no errored descendants.
 * When an exception propagates, every ancestor is also marked errored, and the
 * root's wrapper message says far less than the leaf that actually failed.
 * Falls back to the root span, then to the first span.
 */
export function pickDefaultSpan(spans: Span[]): Span | null {
  if (spans.length === 0) return null;

  const errored = spans.filter((s) => s.status === "error");
  if (errored.length > 0) {
    const erroredParentIds = new Set(
      errored.map((s) => s.parent_span_id).filter((id): id is string => id !== null),
    );
    const innermost = errored.filter((s) => !erroredParentIds.has(s.span_id));
    const candidates = innermost.length > 0 ? innermost : errored;
    return candidates.reduce((a, b) =>
      new Date(a.started_at).getTime() <= new Date(b.started_at).getTime() ? a : b,
    );
  }

  return spans.find((s) => s.parent_span_id === null) ?? spans[0];
}

export interface TimeExtent {
  start: number;
  end: number;
}

/** Overall time window covered by a span list (for waterfall scaling). */
export function timeExtent(spans: Span[], nowFallback = Date.now()): TimeExtent {
  let start = Infinity;
  let end = -Infinity;
  for (const span of spans) {
    const s = new Date(span.started_at).getTime();
    const e = span.ended_at ? new Date(span.ended_at).getTime() : nowFallback;
    if (s < start) start = s;
    if (e > end) end = e;
  }
  if (!isFinite(start)) return { start: nowFallback, end: nowFallback + 1 };
  if (end <= start) end = start + 1;
  return { start, end };
}
