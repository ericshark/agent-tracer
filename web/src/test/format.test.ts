import { describe, expect, it } from "vitest";

import {
  formatCost,
  formatDuration,
  formatPercent,
  formatTokens,
} from "../lib/format";

describe("formatDuration", () => {
  it("handles the full range", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(0.4)).toBe("<1ms");
    expect(formatDuration(250)).toBe("250ms");
    expect(formatDuration(2500)).toBe("2.50s");
    expect(formatDuration(12_500)).toBe("12.5s");
    expect(formatDuration(95_000)).toBe("1m 35s");
  });
});

describe("formatTokens", () => {
  it("compacts large counts", () => {
    expect(formatTokens(null)).toBe("—");
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(1500)).toBe("1.5K");
    expect(formatTokens(2_400_000)).toBe("2.4M");
  });
});

describe("formatCost", () => {
  it("keeps small LLM costs readable", () => {
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(0.0042)).toBe("$0.0042");
    expect(formatCost(1.5)).toBe("$1.50");
    expect(formatCost(1234)).toBe("$1,234");
  });
});

describe("formatPercent", () => {
  it("avoids misleading zero", () => {
    expect(formatPercent(0)).toBe("0.0%");
    expect(formatPercent(0.0004)).toBe("<0.1%");
    expect(formatPercent(0.055)).toBe("5.5%");
    expect(formatPercent(0.31)).toBe("31%");
  });
});
