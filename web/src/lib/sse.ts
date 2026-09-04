import { getToken } from "./api";
import type { LiveEvent } from "./types";

/**
 * Fetch-based SSE client. Native EventSource cannot send an Authorization
 * header, so we consume the stream with fetch + ReadableStream instead.
 * Reconnects with backoff until aborted.
 */
export function subscribeLive(
  projectId: string,
  onEvent: (event: LiveEvent) => void,
  options: { traceId?: string; onStatus?: (connected: boolean) => void } = {},
): () => void {
  const controller = new AbortController();
  let stopped = false;
  let backoff = 1000;

  const url = new URL(`/api/projects/${projectId}/events`, window.location.origin);
  if (options.traceId) url.searchParams.set("trace_id", options.traceId);

  async function connect(): Promise<void> {
    while (!stopped) {
      try {
        const token = getToken();
        const response = await fetch(url.pathname + url.search, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);
        options.onStatus?.(true);
        backoff = 1000;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          for (const part of parts) {
            const dataLine = part.split("\n").find((line) => line.startsWith("data: "));
            if (!dataLine) continue;
            try {
              onEvent(JSON.parse(dataLine.slice(6)) as LiveEvent);
            } catch {
              /* skip malformed frame */
            }
          }
        }
      } catch {
        if (stopped) return;
      }
      options.onStatus?.(false);
      if (stopped) return;
      await new Promise((resolve) => setTimeout(resolve, backoff));
      backoff = Math.min(backoff * 2, 15_000);
    }
  }

  void connect();
  return () => {
    stopped = true;
    controller.abort();
    options.onStatus?.(false);
  };
}
