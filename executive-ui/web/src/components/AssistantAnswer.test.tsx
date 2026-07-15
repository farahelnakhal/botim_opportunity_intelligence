import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AssistantAnswer, { fromCopilotResult } from "./AssistantAnswer";
import type { CopilotChatResult } from "../types";

function baseResult(overrides: Partial<CopilotChatResult> = {}): CopilotChatResult {
  return {
    conversationId: "conv_x", messageId: "msg_x", answerMarkdown: "answer text",
    answerType: "analysis", confidence: { level: "low", basis: "" },
    citations: [], assumptions: [], unknowns: [], recommendedNextActions: [],
    warnings: [], unavailable: false,
    ...overrides,
  };
}

describe("demo-mode indicator (Phase 3)", () => {
  it("is visible when runtimeMode is deterministic_demo", () => {
    render(<AssistantAnswer data={fromCopilotResult(baseResult({ runtimeMode: "deterministic_demo" }))} />);
    expect(screen.getByText(/Demo mode/i)).toBeInTheDocument();
  });

  it("is absent when runtimeMode is live_model", () => {
    render(<AssistantAnswer data={fromCopilotResult(baseResult({ runtimeMode: "live_model" }))} />);
    expect(screen.queryByText(/Demo mode/i)).toBeNull();
  });

  it("is absent when runtimeMode is undefined (backward-compatible, no crash)", () => {
    render(<AssistantAnswer data={fromCopilotResult(baseResult({ runtimeMode: undefined }))} />);
    expect(screen.queryByText(/Demo mode/i)).toBeNull();
  });

  it("does not expose API keys, provider class names, or internal config in the badge or tooltip", () => {
    const { container } = render(
      <AssistantAnswer data={fromCopilotResult(baseResult({ runtimeMode: "deterministic_demo" }))} />,
    );
    const badge = container.querySelector(".demo-mode-badge");
    expect(badge).toBeInTheDocument();
    const blob = badge?.outerHTML ?? "";
    for (const leak of ["api_key", "ANTHROPIC_API_KEY", "MockProvider", "AnthropicProvider", "sk-ant"]) {
      expect(blob).not.toContain(leak);
    }
  });
});
