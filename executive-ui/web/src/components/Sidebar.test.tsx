import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import Sidebar from "./Sidebar";

vi.mock("../lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
  isLive: () => true,
}));

function Harness({ onReady }: { onReady: (s: AppState) => void }) {
  const s = useApp();
  onReady(s);
  return <Sidebar />;
}

beforeEach(() => window.localStorage.clear());

describe("Sidebar global navigation (Phase 1B/1F)", () => {
  it('exposes a discoverable "Reports & Briefs" entry (Phase 1F)', async () => {
    let state!: AppState;
    render(
      <AppProvider>
        <Harness onReady={(s) => { state = s; }} />
      </AppProvider>,
    );
    await waitFor(() => expect(state.loading).toBe(false));
    expect(screen.getByText("Reports & Briefs")).toBeInTheDocument();
  });

  it("clicking Monitoring in the sidebar does not open a project chat", async () => {
    let state!: AppState;
    render(
      <AppProvider>
        <Harness onReady={(s) => { state = s; }} />
      </AppProvider>,
    );
    await waitFor(() => expect(state.loading).toBe(false));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Monitoring" }));
    expect(state.view).toBe("monitoring");
    expect(state.activeProjectId).toBeNull();
  });

  it("clicking a project, then Monitoring, then the same project again restores the project view", async () => {
    let state!: AppState;
    render(
      <AppProvider>
        <Harness onReady={(s) => { state = s; }} />
      </AppProvider>,
    );
    await waitFor(() => expect(state.loading).toBe(false));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Test Opportunity One" }));
    expect(state.view).toBe("project");
    await user.click(screen.getByRole("button", { name: "Monitoring" }));
    expect(state.view).toBe("monitoring");
    await user.click(screen.getByRole("button", { name: "Test Opportunity One" }));
    expect(state.view).toBe("project");
    expect(state.activeProjectId).toBe("OPP-001");
  });
});
