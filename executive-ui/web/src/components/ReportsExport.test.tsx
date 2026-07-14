import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import { ReportsPanel } from "./panels";

vi.mock("../lib/api", () => ({
  api: {
    overview: vi.fn(() => Promise.resolve(overviewFixture)),
    journal: vi.fn(() => Promise.resolve({ predictions: [], calibration: null })),
  },
  isLive: () => true,
}));

let state: AppState;
function Harness() {
  const s = useApp();
  state = s;
  return <ReportsPanel />;
}

beforeEach(() => window.localStorage.clear());

// Phase 1F — Brief content must remain reachable and its existing export must
// keep working exactly as before; this phase only adds discoverability.
describe("Reports & Briefs — existing content and export remain wired (Phase 1F)", () => {
  it("shows the existing brief content untouched", async () => {
    render(
      <AppProvider>
        <Harness />
      </AppProvider>,
    );
    await waitFor(() => expect(state.loading).toBe(false));
    expect(await screen.findByText(/Reports & briefs/)).toBeInTheDocument();
    expect(await screen.findByText(/Test Opportunity One.*recommendation/)).toBeInTheDocument();
  });

  it("the brief Export action still triggers a real download (Blob + object URL)", async () => {
    render(
      <AppProvider>
        <Harness />
      </AppProvider>,
    );
    await waitFor(() => expect(state.loading).toBe(false));
    const createObjectURL = vi.fn(() => "blob:fixture");
    const revokeObjectURL = vi.fn();
    (URL as any).createObjectURL = createObjectURL;
    (URL as any).revokeObjectURL = revokeObjectURL;

    const exportBtn = await screen.findByRole("button", { name: /Export/i });
    const user = userEvent.setup();
    await user.click(exportBtn);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blobArg = createObjectURL.mock.calls[0][0] as Blob;
    expect(blobArg).toBeInstanceOf(Blob);
  });
});
