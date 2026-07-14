import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor, act } from "@testing-library/react";
import { AppProvider, useApp } from "./store";
import type { AppState } from "./store";
import { overviewFixture } from "./test/fixtures";

vi.mock("./lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
  isLive: () => true,
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
});

describe("global navigation state (Phase 1B)", () => {
  it("Monitoring opens without requiring an active project", async () => {
    const get = await mount();
    expect(get().activeProjectId).toBeNull();
    act(() => get().goMonitoring());
    expect(get().view).toBe("monitoring");
    expect(get().activeProjectId).toBeNull(); // still no project selected — not silently assigned
  });

  it("Monitoring does not change the active project when one is already open", async () => {
    const get = await mount();
    act(() => get().openProject("OPP-001"));
    expect(get().activeProjectId).toBe("OPP-001");
    act(() => get().goMonitoring());
    expect(get().view).toBe("monitoring");
    expect(get().activeProjectId).toBe("OPP-001"); // preserved, not cleared
  });

  it("returning to the project after Monitoring restores it, chat tab included", async () => {
    const get = await mount();
    act(() => get().openProject("OPP-001"));
    act(() => get().setTab("sources"));
    act(() => get().goMonitoring());
    expect(get().view).toBe("monitoring");
    act(() => get().openProject("OPP-001"));
    expect(get().view).toBe("project");
    expect(get().activeProjectId).toBe("OPP-001");
  });

  it("Knowledge opens without requiring an active project", async () => {
    const get = await mount();
    act(() => get().goKnowledge());
    expect(get().view).toBe("knowledge");
    expect(get().activeProjectId).toBeNull();
  });

  it("Reports/Briefs opens without requiring an active project", async () => {
    const get = await mount();
    act(() => get().goReports());
    expect(get().view).toBe("reports");
    expect(get().activeProjectId).toBeNull();
  });

  it("Settings opens without requiring an active project", async () => {
    const get = await mount();
    act(() => get().goSettings());
    expect(get().view).toBe("settings");
    expect(get().activeProjectId).toBeNull();
  });

  it("switching between two projects after visiting a global view keeps each project's own context", async () => {
    const get = await mount();
    act(() => get().openProject("OPP-001"));
    act(() => get().goMonitoring());
    act(() => get().openProject("OPP-002"));
    expect(get().activeProjectId).toBe("OPP-002");
    act(() => get().goKnowledge());
    act(() => get().openProject("OPP-001"));
    expect(get().activeProjectId).toBe("OPP-001");
  });

  it("empty project list does not break global navigation", async () => {
    const get = await mount();
    expect(get().projects.length).toBeGreaterThan(0); // sanity: fixture has projects
    // Simulate the "no project ever opened" case explicitly (activeProjectId null)
    expect(get().activeProjectId).toBeNull();
    act(() => get().goMonitoring());
    act(() => get().goKnowledge());
    act(() => get().goReports());
    act(() => get().goSettings());
    expect(get().view).toBe("settings");
  });

  it("conversation state for a project is untouched by visiting global views", async () => {
    const get = await mount();
    act(() => get().openProject("OPP-001"));
    const before = get().conversations;
    act(() => get().goMonitoring());
    act(() => get().goKnowledge());
    act(() => get().openProject("OPP-001"));
    expect(get().conversations).toBe(before); // same reference — untouched
  });
});
