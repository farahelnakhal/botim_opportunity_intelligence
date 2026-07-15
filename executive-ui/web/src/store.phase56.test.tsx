// Phases 5-6 — frontend: mode-aware sidebar (demo badge, labelled demo
// section, neutral identity, empty invite), the unsaved-analysis save flow
// (stub -> persisted UOPP record with conversation remapping), and the
// one-time localStorage stub reset.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { AppProvider, useApp } from "./store";
import type { AppState } from "./store";
import { overviewFixture } from "./test/fixtures";
import Sidebar from "./components/Sidebar";
import type { OverviewPayload, UserOpportunity } from "./types";

const demoOverview: OverviewPayload = {
  ...overviewFixture,
  meta: { ...overviewFixture.meta, app_mode: "demo" },
};
const normalOverview: OverviewPayload = {
  ...overviewFixture,
  meta: { ...overviewFixture.meta, app_mode: "normal" },
  opportunities: [],
  archived: [],
  briefs: [],
  feed: [],
  assumptions: [],
};

let overviewResult: OverviewPayload = demoOverview;

vi.mock("./lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewResult)) },
  isLive: () => true,
}));

const savedRecord: UserOpportunity = {
  id: "UOPP-1234567890ab", title: "My genuine product", status: "saved",
  product_definition: null, problem_statement: null, target_segment: null,
  customer_description: null, value_proposition: null,
  assumptions: [], risks: [], unknowns: [], next_actions: [],
  source_conversation_id: "conv_abcdefabcdef", created_from_analysis: true,
  monitoring_enabled: false, version: 1,
  created_at: "2026-07-15T10:00:00Z", updated_at: "2026-07-15T10:00:00Z",
  archived_at: null, source: "user",
};

const createMock = vi.fn(() => Promise.resolve(savedRecord));
vi.mock("./lib/userOpportunities", () => ({
  userOpportunitiesApi: {
    list: vi.fn(() => Promise.resolve([] as UserOpportunity[])),
    create: (...args: unknown[]) => createMock(...(args as [])),
  },
  UserOpportunityError: class extends Error {},
}));

vi.mock("./lib/copilotApi", () => ({
  copilotApi: {
    chat: vi.fn(() => Promise.resolve({
      conversationId: "conv_abcdefabcdef", messageId: "m1",
      answerMarkdown: "analysis", answerType: "new_opportunity_analysis",
      confidence: null, citations: [], assumptions: [], unknowns: [],
      recommendedNextActions: [], warnings: [], unavailable: false,
    })),
    deleteConversation: vi.fn(() => Promise.resolve(true)),
  },
}));

let state: AppState;
function Harness() {
  state = useApp();
  return <Sidebar />;
}

beforeEach(() => {
  window.localStorage.clear();
  overviewResult = demoOverview;
  createMock.mockClear();
});

async function mount() {
  render(<AppProvider><Harness /></AppProvider>);
  await waitFor(() => expect(state.loading).toBe(false));
}

describe("Phase 5 — mode-aware UI", () => {
  it("demo mode shows the demo badge, a labelled demo section, and the demo persona", async () => {
    await mount();
    expect(state.appMode).toBe("demo");
    expect(screen.getByTestId("demo-data-badge")).toHaveTextContent("Demo data");
    expect(screen.getByTestId("demo-opportunities")).toBeInTheDocument();
    expect(screen.getByText(/Demo opportunities/)).toBeInTheDocument();
    expect(screen.getByText("Strategy Lead")).toBeInTheDocument();
  });

  it("normal mode shows no demo data, no fake identity, and a clean invite", async () => {
    overviewResult = normalOverview;
    await mount();
    expect(state.appMode).toBe("normal");
    expect(screen.queryByTestId("demo-data-badge")).not.toBeInTheDocument();
    expect(screen.queryByTestId("demo-opportunities")).not.toBeInTheDocument();
    expect(screen.queryByText("Strategy Lead")).not.toBeInTheDocument();
    expect(screen.getByText("No account signed in")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-empty-invite")).toHaveTextContent("No opportunities yet");
  });
});

describe("Phase 6 — save flow and stub migration", () => {
  it("a genuine new analysis creates an UNSAVED stub; saving persists it and remaps the conversation", async () => {
    await mount();
    await act(async () => {
      await state.analyzeNew("A genuinely new product idea for UAE chefs");
    });
    const stub = state.generated[0];
    expect(stub.unsaved).toBe(true);
    const stubId = stub.id;
    let created: UserOpportunity | null = null;
    await act(async () => {
      created = await state.saveOpportunity(stubId);
    });
    expect(created!.id).toBe("UOPP-1234567890ab");
    expect(createMock).toHaveBeenCalledWith(expect.objectContaining({
      title: expect.stringContaining("A genuinely new product idea"),
      status: "saved",
      created_from_analysis: true,
      source_conversation_id: "conv_abcdefabcdef",
    }));
    expect(state.generated.find((g) => g.id === stubId)).toBeUndefined();
    expect(state.userOpps[0].id).toBe("UOPP-1234567890ab");
    // conversation history + copilot conversation id moved to the new id
    expect(state.conversations["UOPP-1234567890ab"]).toBeTruthy();
    expect(state.activeProjectId).toBe("UOPP-1234567890ab");
  });

  it("one-time migration discards pre-Phase-6 generated stubs but keeps conversations", async () => {
    window.localStorage.setItem("botim.generated", JSON.stringify([{ id: "old-stub" }]));
    window.localStorage.setItem("botim.conversations", JSON.stringify({ keep: [] }));
    await mount();
    expect(state.generated).toEqual([]);
    expect(window.localStorage.getItem("botim.migration.v1")).toBeTruthy();
    expect(JSON.parse(window.localStorage.getItem("botim.conversations")!)).toEqual({ keep: [] });
    // running again is a no-op (flag set), new stubs are not wiped
  });
});
