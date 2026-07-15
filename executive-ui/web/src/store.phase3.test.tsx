import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor, act } from "@testing-library/react";
import { AppProvider, useApp } from "./store";
import type { AppState } from "./store";
import { overviewFixture } from "./test/fixtures";
import type { CopilotChatResult } from "./types";

vi.mock("./lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
  isLive: () => true,
}));

const chatMock = vi.fn();
const deleteConversationMock = vi.fn(async () => true);
vi.mock("./lib/copilotApi", () => ({
  copilotApi: {
    chat: (...args: unknown[]) => chatMock(...args),
    deleteConversation: (...args: unknown[]) => deleteConversationMock(...args),
  },
}));

function baseResult(overrides: Partial<CopilotChatResult> = {}): CopilotChatResult {
  return {
    conversationId: "conv_x", messageId: "msg_x", answerMarkdown: "answer",
    answerType: "analysis", confidence: { level: "low", basis: "" },
    citations: [], assumptions: [], unknowns: [], recommendedNextActions: [],
    warnings: [], unavailable: false,
    ...overrides,
  };
}

function Harness({ onReady }: { onReady: (s: AppState) => void }) {
  const s = useApp();
  onReady(s);
  return null;
}

async function mount() {
  let state!: AppState;
  render(
    <AppProvider>
      <Harness onReady={(s) => { state = s; }} />
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
  return () => state;
}

beforeEach(() => {
  window.localStorage.clear();
  chatMock.mockReset();
  deleteConversationMock.mockClear();
});

describe("new-product stub gate (Phase 3)", () => {
  it("clarification does not create a stub or navigate away from home", async () => {
    chatMock.mockResolvedValue(baseResult({ answerType: "clarification", answerMarkdown: "Tell me more…" }));
    const get = await mount();
    await act(async () => { await get().analyzeNew("Hello"); });
    expect(get().generated).toEqual([]);
    expect(get().view).toBe("home");
    expect(get().activeProjectId).toBeNull();
  });

  it("a monitoring-routed reply does not create a stub", async () => {
    chatMock.mockResolvedValue(baseResult({ answerType: "change_summary" }));
    const get = await mount();
    await act(async () => { await get().analyzeNew("Show recent monitoring updates"); });
    expect(get().generated).toEqual([]);
    expect(get().view).toBe("home");
  });

  it("a methodology reply (answer_type analysis) does not create a stub", async () => {
    chatMock.mockResolvedValue(baseResult({ answerType: "analysis" }));
    const get = await mount();
    await act(async () => { await get().analyzeNew("How does scoring work?"); });
    expect(get().generated).toEqual([]);
    expect(get().view).toBe("home");
  });

  it("a genuine new_opportunity_analysis creates exactly one stub and navigates", async () => {
    chatMock.mockResolvedValue(baseResult({ answerType: "new_opportunity_analysis", conversationId: "conv_new" }));
    const get = await mount();
    await act(async () => { await get().analyzeNew("A card for supplier payments"); });
    expect(get().generated).toHaveLength(1);
    expect(get().view).toBe("project");
    expect(get().activeProjectId).toBe("conv_new");
  });

  it("calling analyzeNew twice for two different genuine ideas creates exactly two stubs, not duplicates", async () => {
    chatMock
      .mockResolvedValueOnce(baseResult({ answerType: "new_opportunity_analysis", conversationId: "conv_1" }))
      .mockResolvedValueOnce(baseResult({ answerType: "new_opportunity_analysis", conversationId: "conv_2" }));
    const get = await mount();
    await act(async () => { await get().analyzeNew("idea one"); });
    await act(async () => { await get().analyzeNew("idea two"); });
    expect(get().generated).toHaveLength(2);
  });
});

describe("stale-conversation recovery at the store level (Phase 3)", () => {
  it("overwrites the mapping when copilotApi reports staleConversationRecovered, with no duplicate messages", async () => {
    const get = await mount();
    // Seed a stale mapping for OPP-001 by sending once normally.
    chatMock.mockResolvedValueOnce(baseResult({ conversationId: "conv_old" }));
    await act(async () => { await get().send("hi", "OPP-001"); });
    expect(get().conversations["OPP-001"]).toHaveLength(2); // user + assistant

    // Next send recovers from a stale id transparently (copilotApi's own
    // concern) and reports it back via staleConversationRecovered.
    chatMock.mockResolvedValueOnce(baseResult({ conversationId: "conv_recovered", staleConversationRecovered: true }));
    await act(async () => { await get().send("still there?", "OPP-001"); });

    // Exactly one more user+assistant pair — never duplicated.
    expect(get().conversations["OPP-001"]).toHaveLength(4);
  });

  it("does not touch an unrelated project's conversation mapping", async () => {
    const get = await mount();
    chatMock.mockResolvedValueOnce(baseResult({ conversationId: "conv_opp1" }));
    await act(async () => { await get().send("hi", "OPP-001"); });
    chatMock.mockResolvedValueOnce(baseResult({ conversationId: "conv_opp2" }));
    await act(async () => { await get().send("hi", "OPP-002"); });

    // Now recover OPP-001's (simulated) stale conversation.
    chatMock.mockResolvedValueOnce(baseResult({ conversationId: "conv_opp1_new", staleConversationRecovered: true }));
    await act(async () => { await get().send("again", "OPP-001"); });

    // OPP-002's conversation history must be completely untouched.
    expect(get().conversations["OPP-002"]).toHaveLength(2);
  });
});
