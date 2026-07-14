import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import Updates from "./Updates";

vi.mock("../lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
  isLive: () => true,
}));

let state: AppState;
function Harness() {
  const s = useApp();
  state = s;
  return <Updates />;
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

describe("Updates clickability and change explanation (Phase 1E)", () => {
  it("a row without before/after shows a safe fallback explanation, not a fabricated diff", async () => {
    await mount();
    // two fixture rows (EVT-001, EVT-003) have no before_after — both show the fallback
    const fallbacks = screen.getAllByText(/New monitoring information was received/);
    expect(fallbacks.length).toBe(2);
  });

  it("a row with before/after still shows the real values", async () => {
    await mount();
    const row = screen.getByRole("button", { name: /Prediction resolved/ });
    expect(row).toHaveTextContent("p=60%");
    expect(row).toHaveTextContent("true");
  });

  it("clicking a row opens the monitoring-update detail for that row's id", async () => {
    await mount();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Prediction resolved/ }));
    expect(state.detailTarget).toEqual({ type: "monitoring_update", id: "EVT-002" });
  });

  it("every rendered row is a real button (keyboard accessible)", async () => {
    await mount();
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBe(overviewFixture.feed.length);
  });
});
