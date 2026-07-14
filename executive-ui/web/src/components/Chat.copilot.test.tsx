import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import Chat from "./Chat";
import type { CopilotChatResult } from "../types";

vi.mock("../lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
  isLive: () => true,
}));

const chatMock = vi.fn();
const deleteConversationMock = vi.fn(async () => true);
vi.mock("../lib/copilotApi", () => ({
  copilotApi: {
    chat: (...args: unknown[]) => chatMock(...args),
    deleteConversation: (...args: unknown[]) => deleteConversationMock(...args),
  },
}));

let state: AppState;
function Harness() {
  const s = useApp();
  state = s;
  return <Chat projectId="OPP-001" />;
}

beforeEach(() => {
  window.localStorage.clear();
  chatMock.mockReset();
  deleteConversationMock.mockClear();
});

async function mount() {
  render(
    <AppProvider>
      <Harness />
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
}

const richResult: CopilotChatResult = {
  conversationId: "conv_rich123456",
  messageId: "msg_rich123456",
  answerMarkdown: "OPP-001 has 6 unresolved assumptions.",
  answerType: "analysis",
  confidence: { level: "medium", basis: "test" },
  citations: [{ id: "OPP-001", type: "opportunity", title: "Test Opportunity One", role: "primary",
               target: { type: "internal_route", value: "/opportunity/OPP-001" }, metadata: null }],
  assumptions: ["6 of 17 scorecard factors remain assumption-based"],
  unknowns: ["UAE-importer willingness to pay is unverified"],
  recommendedNextActions: ["Run VE-004 before any build decision."],
  warnings: ["EV-2026-W28-099 is a weak lead and was not used as primary support"],
  unavailable: false,
};

describe("Chat rendering of copilot answers (Phase 2C/2K)", () => {
  it("renders citations, assumptions, unknowns, warnings, and recommended actions", async () => {
    chatMock.mockResolvedValue(richResult);
    await mount();
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/Ask a follow-up/i), "why is this risky?");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByText(/6 unresolved assumptions/)).toBeInTheDocument(), { timeout: 3000 });
    expect(screen.getByText(/6 of 17 scorecard factors/)).toBeInTheDocument();
    expect(screen.getByText(/UAE-importer willingness to pay/)).toBeInTheDocument();
    expect(screen.getByText(/EV-2026-W28-099 is a weak lead/)).toBeInTheDocument();
    expect(screen.getByText(/Run VE-004 before any build decision/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /OPP-001/ })).toBeInTheDocument();
  });

  it("renders an honest unavailable state instead of a fabricated answer", async () => {
    chatMock.mockResolvedValue({
      conversationId: "", messageId: null, answerMarkdown: "", answerType: "unavailable",
      confidence: null, citations: [], assumptions: [], unknowns: [], recommendedNextActions: [],
      warnings: [], unavailable: true, unavailableReason: "network down",
    } satisfies CopilotChatResult);
    await mount();
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/Ask a follow-up/i), "hello");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getAllByText(/Grounded analysis is temporarily unavailable/).length)
      .toBeGreaterThan(0), { timeout: 3000 });
    // never silently substitutes a fabricated answer
    expect(screen.queryByText(/composite/i)).toBeNull();
  });

  it('"Clear chat" ends the conversation and removes messages from view', async () => {
    chatMock.mockResolvedValue(richResult);
    await mount();
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/Ask a follow-up/i), "hi");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByText("hi")).toBeInTheDocument(), { timeout: 3000 });
    await user.click(screen.getByRole("button", { name: /Clear chat/i }));
    await waitFor(() => expect(deleteConversationMock).toHaveBeenCalledWith("conv_rich123456"));
    expect(screen.queryByText("hi")).toBeNull();
    expect(screen.getByText(/Start the conversation/)).toBeInTheDocument();
  });
});
