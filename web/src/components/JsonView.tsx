import { useMemo } from "react";

import { CopyButton } from "./ui";

export function JsonView({ value, maxHeight = 320 }: { value: unknown; maxHeight?: number }) {
  const text = useMemo(() => {
    if (value === null || value === undefined) return "null";
    if (typeof value === "string") return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value]);

  return (
    <div className="relative">
      <div className="absolute right-2 top-2 z-10">
        <CopyButton text={text} />
      </div>
      <pre
        className="mono panel-scroll overflow-auto whitespace-pre-wrap break-words rounded-md bg-surface-2 p-3 text-xs leading-relaxed text-ink-secondary"
        style={{ maxHeight }}
      >
        {text}
      </pre>
    </div>
  );
}

interface MessageLike {
  role?: string;
  content?: unknown;
}

export function MessageList({
  messages,
  system,
}: {
  messages: MessageLike[];
  system?: string | null;
}) {
  return (
    <div className="flex flex-col gap-2">
      {system && <MessageBubble role="system" content={system} />}
      {messages.map((message, i) => (
        <MessageBubble key={i} role={message.role ?? "user"} content={message.content} />
      ))}
    </div>
  );
}

export function MessageBubble({ role, content }: { role: string; content: unknown }) {
  const text =
    typeof content === "string" ? content : content == null ? "" : JSON.stringify(content, null, 2);
  const roleStyles: Record<string, string> = {
    system: "border-l-2 border-baseline",
    user: "border-l-2",
    assistant: "border-l-2",
  };
  const roleBorder: Record<string, string> = {
    user: "var(--series-3)",
    assistant: "var(--series-1)",
    system: "var(--baseline)",
    tool: "var(--series-2)",
  };
  return (
    <div
      className={`rounded-md bg-surface-2 px-3 py-2 ${roleStyles[role] ?? "border-l-2"}`}
      style={{ borderLeftColor: roleBorder[role] ?? "var(--series-8)" }}
    >
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
        {role}
      </p>
      <p className="mono whitespace-pre-wrap break-words text-xs leading-relaxed text-ink-secondary">
        {text}
      </p>
    </div>
  );
}

/** Heuristic: does this span input look like an LLM chat payload? */
export function asChatInput(
  value: unknown,
): { messages: MessageLike[]; system: string | null } | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const obj = value as { messages?: unknown; system?: unknown };
    if (Array.isArray(obj.messages)) {
      return {
        messages: obj.messages as MessageLike[],
        system: typeof obj.system === "string" ? obj.system : null,
      };
    }
  }
  if (Array.isArray(value) && value.every((m) => m && typeof m === "object" && "role" in m)) {
    return { messages: value as MessageLike[], system: null };
  }
  return null;
}

/** Heuristic: does this output look like a single assistant message? */
export function asChatOutput(value: unknown): MessageLike | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const obj = value as MessageLike;
    if (typeof obj.role === "string" && "content" in obj) return obj;
  }
  return null;
}
