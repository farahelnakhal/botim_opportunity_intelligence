import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import DetailDrawer from "./DetailDrawer";

vi.mock("../lib/api", () => ({
  api: {
    overview: vi.fn(() => Promise.resolve(overviewFixture)),
    // Phase 4 — the drawer lazily loads full monitoring events / journal;
    // empty results exercise the safe feed-item fallback used before.
    monitoring: vi.fn(() => Promise.resolve({ events: [], alerts: [], summaries: [], summary_state: null })),
    monitoringSummary: vi.fn(() => Promise.resolve(null)),
    journal: vi.fn(() => Promise.resolve({ predictions: [], calibration: null })),
  },
  isLive: () => true,
}));

let state: AppState;
function Harness() {
  const s = useApp();
  state = s;
  return <DetailDrawer />;
}

beforeEach(() => window.localStorage.clear());

async function mount() {
  render(
    <AppProvider>
      <Harness />
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
}

describe("DetailDrawer (Phase 1C/1D/1E)", () => {
  it("renders a safe unavailable state for an unknown evidence id, without crashing", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-DOES-NOT-EXIST"));
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText(/not on file/)).toBeInTheDocument();
  });

  it("renders real evidence fields for a known evidence id", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-001"));
    expect(screen.getByText("Merchants report slow settlement")).toBeInTheDocument();
    expect(screen.getByText("EV-2026-W28-001")).toBeInTheDocument();
  });

  it("renders real assumption fields for a known assumption id", async () => {
    await mount();
    act(() => state.openDetail("assumption", "OPP-001::willingness_to_pay"));
    expect(screen.getByText(/Merchants will pay a monthly fee/)).toBeInTheDocument();
  });

  it("renders a safe unavailable state for an unknown assumption id", async () => {
    await mount();
    act(() => state.openDetail("assumption", "OPP-999::nonexistent_key"));
    expect(screen.getByText("Not available")).toBeInTheDocument();
  });

  it("a monitoring update with a related opportunity id offers to open it, without fabricating a diff", async () => {
    await mount();
    act(() => state.openDetail("monitoring_update", "EVT-003"));
    // Phase 4 — full events load first (empty in this mock), then the safe
    // feed-item fallback renders exactly as before.
    await waitFor(() =>
      expect(screen.getByText(/New monitoring information was received/)).toBeInTheDocument());
    const openRelated = screen.getByRole("button", { name: /Open related opportunity/ });
    const user = userEvent.setup();
    await user.click(openRelated);
    expect(state.drawerOppId).toBe("OPP-001");
  });

  it("closes on Escape", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-001"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.keyboard("{Escape}");
    expect(state.detailTarget).toBeNull();
  });
});
