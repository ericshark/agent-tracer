import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { asChatInput, asChatOutput, MessageList } from "../components/JsonView";
import { StatusBadge } from "../components/ui";

describe("chat payload heuristics", () => {
  it("detects the native SDK llm input shape", () => {
    const chat = asChatInput({
      messages: [{ role: "user", content: "hi" }],
      system: "be nice",
    });
    expect(chat).not.toBeNull();
    expect(chat!.system).toBe("be nice");
    expect(chat!.messages).toHaveLength(1);
  });

  it("detects a bare message array", () => {
    const chat = asChatInput([{ role: "user", content: "hi" }]);
    expect(chat).not.toBeNull();
    expect(chat!.system).toBeNull();
  });

  it("rejects non-chat payloads", () => {
    expect(asChatInput({ query: "SELECT 1" })).toBeNull();
    expect(asChatInput("plain text")).toBeNull();
    expect(asChatOutput({ result: 42 })).toBeNull();
    expect(asChatOutput({ role: "assistant", content: "yo" })).not.toBeNull();
  });
});

describe("MessageList", () => {
  it("renders roles and content including the system prompt", () => {
    render(
      <MessageList
        system="You are terse."
        messages={[
          { role: "user", content: "What is 2+2?" },
          { role: "assistant", content: "4" },
        ]}
      />,
    );
    expect(screen.getByText("system")).toBeInTheDocument();
    expect(screen.getByText("You are terse.")).toBeInTheDocument();
    expect(screen.getByText("What is 2+2?")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("always pairs an icon with a label (never color alone)", () => {
    render(<StatusBadge status="error" />);
    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByText("✕")).toBeInTheDocument();
  });
});
