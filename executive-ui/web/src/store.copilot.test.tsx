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

let nextConvId = 0;
const chatMock = vi.fn(
  async (message: string, conversationId: string | null, _context?: unknown): Promise<CopilotChatResult> => ({
    conversationId: conversationId ?? `conv_test${++nextConvId}`,
    messageId: "msg_test",
    answerMarkdown: `answer to: ${message}`,
    // Phase 3: analyzeNew only creates a project/stub and navigates when the
    // backend confirms a genuine new-product analysis — these lifecycle
    // tests exercise that path deliberately. The stub-gating behavior itself
    // (non-product messages) is covered in Home.newProductGate.test.tsx.
    answerType: "new_opportunity_analysis",
    confidence: { level: "medium", basis: "test" },
    citations: [],
    assumptions: [],
    unknowns: [],
    recommendedNextActions: [],
    warnings: [],
    unavailable: false,
  }),
);
const deleteConversationMock = vi.fn(async () => true);

vi.mock("./lib/copilotApi", () => ({
  copilotApi: {
    chat: (...args: Parameters<typeof chatMock>) => chatMock(...args),
    deleteConversation: (...args: Parameters<typeof deleteConversationMock>) => deleteConversationMock(...args),
  },
}));

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
  chatMock.mockClear();
  deleteConversationMock.mockClear();
  nextConvId = 0;
});

describe("copilot conversation lifecycle (Phase 2I)", () => {
  it("a new chat (analyzeNew) always starts with conversation_id: null", async () => {
    const get = await mount();
    await act(async () => {
      await get().analyzeNew("Invoice financing for logistics SMEs");
    });
    expect(chatMock).toHaveBeenCalledWith("Invoice financing for logistics SMEs", null, {});
  });

  it("a follow-up in the same chat reuses the same conversation_id", async () => {
    const get = await mount();
    await act(async () => {
      await get().analyzeNew("A new idea");
    });
    const pid = get().activeProjectId!;
    await act(async () => {
      await get().send("tell me more", pid);
    });
    // the conversation id returned by the first call must be reused as the
    // second call's conversation_id argument
    const firstResult = await chatMock.mock.results[0].value;
    const secondCallConvId = chatMock.mock.calls[1][1];
    expect(secondCallConvId).toBe(firstResult.conversationId);
  });

  it("switching to a different project does not leak the first project's conversation id", async () => {
    const get = await mount();
    await act(async () => {
      await get().send("hi OPP-001", "OPP-001");
    });
    await act(async () => {
      await get().send("hi OPP-002", "OPP-002");
    });
    // second send's conversation_id argument must be null (a fresh conversation
    // for the newly-active project), not OPP-001's conversation id
    const secondCallConvId = chatMock.mock.calls[1][1];
    expect(secondCallConvId).toBeNull();
  });

  it("an existing committed opportunity is passed as selected context", async () => {
    const get = await mount();
    await act(async () => {
      await get().send("what are the risks?", "OPP-001");
    });
    const context = chatMock.mock.calls[0][2];
    expect(context).toEqual({ opportunity_id: "OPP-001" });
  });

  it("clearConversation deletes the remote conversation and clears local state", async () => {
    const get = await mount();
    await act(async () => {
      await get().send("hi", "OPP-001");
    });
    expect(get().conversations["OPP-001"]?.length).toBeGreaterThan(0);
    await act(async () => {
      await get().clearConversation("OPP-001");
    });
    expect(deleteConversationMock).toHaveBeenCalled();
    expect(get().conversations["OPP-001"]).toBeUndefined();
  });
});
