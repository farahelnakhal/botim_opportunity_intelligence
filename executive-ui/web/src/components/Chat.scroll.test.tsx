import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
vi.mock("../lib/copilotApi", () => ({
  copilotApi: {
    chat: (...args: unknown[]) => chatMock(...args),
    deleteConversation: vi.fn(async () => true),
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
  conversationId: "conv_scroll", messageId: "msg_scroll",
  answerMarkdown: "A reasonably long grounded answer about OPP-001's assumptions and evidence.",
  answerType: "analysis", confidence: { level: "medium", basis: "test" },
  citations: [], assumptions: [], unknowns: [], recommendedNextActions: [], warnings: [],
  unavailable: false,
};

describe("Chat scroll policy (Phase 3)", () => {
  it("scrolls exactly once per new exchange, not once per stage-update tick", async () => {
    const scrollIntoViewMock = vi.fn();
    // deliverCopilot mutates the SAME message object across several stage
    // ticks (~4 ticks for a normal answer) — msgs.length itself only changes
    // twice per exchange (once when the user+placeholder pair is appended).
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window.HTMLElement.prototype as any).scrollIntoView = scrollIntoViewMock;

    chatMock.mockResolvedValue(richResult);
    await mount();
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/Ask a follow-up/i), "why is this risky?");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(screen.getByText(/reasonably long grounded answer/)).toBeInTheDocument(),
      { timeout: 3000 });

    // One exchange (user message + assistant placeholder appended together)
    // must produce exactly one scrollIntoView call, regardless of how many
    // stage-progress mutations happened while streaming.
    expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
  });

  it("scrolls again exactly once for a second, separate exchange", async () => {
    const scrollIntoViewMock = vi.fn();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window.HTMLElement.prototype as any).scrollIntoView = scrollIntoViewMock;

    chatMock.mockResolvedValue(richResult);
    await mount();
    const user = userEvent.setup();

    await user.type(screen.getByPlaceholderText(/Ask a follow-up/i), "first question");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(scrollIntoViewMock).toHaveBeenCalledTimes(1), { timeout: 3000 });

    await user.type(screen.getByPlaceholderText(/Ask a follow-up/i), "second question");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(scrollIntoViewMock).toHaveBeenCalledTimes(2), { timeout: 3000 });
  });

  it("reopening a chat with existing history does not call scrollIntoView (instant landing, not a scroll storm)", async () => {
    const scrollIntoViewMock = vi.fn();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window.HTMLElement.prototype as any).scrollIntoView = scrollIntoViewMock;

    chatMock.mockResolvedValue(richResult);
    await mount();
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/Ask a follow-up/i), "seed message");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(scrollIntoViewMock).toHaveBeenCalledTimes(1), { timeout: 3000 });

    scrollIntoViewMock.mockClear();
    // A fresh AppProvider + Chat mount for the same project (simulates
    // leaving and returning to the Chat tab) — history persists via
    // localStorage, so this reflects a genuine "reopen with history" case.
    const { unmount } = render(
      <AppProvider>
        <Chat projectId="OPP-001" />
      </AppProvider>,
    );
    await waitFor(() => expect(screen.getAllByText(/seed message/).length).toBeGreaterThan(0));
    // No new exchange started, so no scrollIntoView call should fire.
    expect(scrollIntoViewMock).not.toHaveBeenCalled();
    unmount();
  });
});
