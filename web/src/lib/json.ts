/** Pretty-print a value for an editable text area. */
export function toEditable(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * Read an edited value back. Valid JSON is parsed; anything else is kept as a
 * plain string, so prompts can be typed without quoting. Empty means null.
 */
export function fromEditable(text: string): unknown {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return text;
  }
}

/** One-line preview of a value for table cells. */
export function preview(value: unknown, max = 140): string {
  if (value === null || value === undefined) return "—";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max)}…` : text;
}
