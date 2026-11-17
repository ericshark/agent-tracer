import { describe, expect, it } from "vitest";

import { fromEditable, preview, toEditable } from "../lib/json";

describe("editable JSON helpers", () => {
  it("round-trips structured values", () => {
    const value = { question: "hi", n: [1, 2] };
    expect(fromEditable(toEditable(value))).toEqual(value);
  });

  it("keeps plain text as a string and treats empty as null", () => {
    expect(fromEditable("What is the capital of France?")).toBe("What is the capital of France?");
    expect(fromEditable("   ")).toBeNull();
    expect(toEditable(null)).toBe("");
  });

  it("truncates long previews", () => {
    expect(preview("x".repeat(200), 10)).toBe(`${"x".repeat(10)}…`);
    expect(preview(undefined)).toBe("—");
    expect(preview({ a: 1 })).toBe('{"a":1}');
  });
});
