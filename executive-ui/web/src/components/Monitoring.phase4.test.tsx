// Phase 4 — monitoring: clickable cards, the current-state overview summary,
// the full detail report (what changed / scores / affected records), the
// internal knowledge-base label, safe external source links, and the honest
// missing-summary state.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import type { MonitoringPayload } from "../types";
import { MonitoringPanel } from "./panels";
import DetailDrawer from "./DetailDrawer";

const monitoringFixture: MonitoringPayload = {
  events: [
    {
      id: "EVT-2026-W28-001",
      entity: "EV-2026-W28-001",
      detected_at: "2026-07-12",
      adapter: "kb-watcher",
      signal_type: "new_evidence_record",
      fingerprint: "abc",
      title: "New evidence record EV-2026-W28-001",
      scores: { impact: 2, urgency: 2, confidence: 3, relevance: 4, novelty: 3 },
      tier: "informative",
      status: "new",
      details: { confidence: "Medium", status: "active", previous_value: "—", current_value: "active" },
      kb_links: ["EV-2026-W28-001", "OPP-001"],
    },
    {
      id: "EVT-2026-W28-002",
      entity: "ENT-wio",
      detected_at: "2026-07-12",
      adapter: "vendor-changelog",
      signal_type: "competitor_launch",
      title: "Competitor launched settlement product",
      scores: { impact: 4, urgency: 3, confidence: 3, relevance: 5, novelty: 4 },
      tier: "important",
      status: "new",
      details: { source_title: "Wio press", source_url: "https://wio.example/press", fetched_at: "2026-07-12" },
      kb_links: ["OPP-002"],
    },
  ],
  alerts: [],
  summaries: [{ id: "EVT-2026-W28-001", available: true }],
  summary_state: {
    status: "active",
    status_note: "Monitoring is running against the internal knowledge base only — all events are internal knowledge-base changes; no external monitoring source is connected yet.",
    last_checked: null,
    latest_event_at: "2026-07-12",
    event_count: 2,
    open_alert_count: 0,
    unresolved_warning_count: 1,
    monitored_entity_count: 7,
    external_source_count: 0,
    internal_only: true,
  },
};

vi.mock("../lib/api", () => ({
  api: {
    overview: vi.fn(() => Promise.resolve(overviewFixture)),
    monitoring: vi.fn(() => Promise.resolve(monitoringFixture)),
    monitoringSummary: vi.fn((id: string) =>
      Promise.resolve(id === "EVT-2026-W28-001"
        ? { markdown: "## EVT-2026-W28-001\n\n**What changed:** a new record landed.", truncated: false }
        : null)),
    journal: vi.fn(() => Promise.resolve({ predictions: [], calibration: null })),
  },
  isLive: () => true,
}));

let state: AppState;
function Harness() {
  const s = useApp();
  state = s;
  return (
    <>
      <MonitoringPanel />
      <DetailDrawer />
    </>
  );
}

beforeEach(() => window.localStorage.clear());

async function mount() {
  render(
    <AppProvider>
      <Harness />
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
  await waitFor(() => expect(screen.getByTestId("monitoring-summary")).toBeInTheDocument());
}

describe("Monitoring (Phase 4)", () => {
  it("shows the current-state summary with honest counts and internal-only label", async () => {
    await mount();
    const card = screen.getByTestId("monitoring-summary");
    expect(card).toHaveTextContent("Monitoring active");
    expect(card).toHaveTextContent("internal knowledge-base changes only");
    expect(card).toHaveTextContent("no run timestamp recorded");
    expect(card).toHaveTextContent("Latest event 2026-07-12");
    expect(card).toHaveTextContent("Monitored entities");
  });

  it("monitoring cards are clickable buttons that open the detail report", async () => {
    await mount();
    const user = userEvent.setup();
    const card = screen.getByRole("button", { name: /Open monitoring detail: New evidence record/ });
    await user.click(card);
    expect(state.detailTarget).toEqual(
      expect.objectContaining({ type: "monitoring_update", id: "EVT-2026-W28-001" }),
    );
  });

  it("the detail report shows what changed, scores, affected records, and the summary", async () => {
    await mount();
    act(() => state.openDetail("monitoring_update", "EVT-2026-W28-001"));
    await waitFor(() => expect(screen.getByTestId("event-details")).toBeInTheDocument());
    const details = screen.getByTestId("event-details");
    expect(details).toHaveTextContent("previous value");
    expect(details).toHaveTextContent("current value");
    expect(screen.getByTestId("event-scores")).toHaveTextContent("impact 2/5");
    expect(screen.getByRole("button", { name: /Open affected opportunity: Test Opportunity One/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open affected evidence: EV-2026-W28-001/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("event-summary")).toBeInTheDocument());
    expect(screen.getByTestId("event-summary")).toHaveTextContent("a new record landed");
  });

  it("an internal KB event is labelled internal with no fabricated external source", async () => {
    await mount();
    act(() => state.openDetail("monitoring_update", "EVT-2026-W28-001"));
    await waitFor(() => expect(screen.getByTestId("internal-kb-note")).toBeInTheDocument());
    expect(screen.getByTestId("internal-kb-note")).toHaveTextContent("Internal knowledge-base change");
    expect(screen.getByTestId("internal-kb-note")).toHaveTextContent("no external source URL applies");
    expect(screen.queryByTestId("external-source-link")).not.toBeInTheDocument();
  });

  it("an external-source event renders a safe source link and fetched date", async () => {
    await mount();
    act(() => state.openDetail("monitoring_update", "EVT-2026-W28-002"));
    await waitFor(() => expect(screen.getByTestId("external-source-link")).toBeInTheDocument());
    const link = screen.getByTestId("external-source-link");
    expect(link).toHaveAttribute("href", "https://wio.example/press");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    // Detected + Fetched both show the (real) date
    expect(screen.getAllByText("2026-07-12", { selector: "dd" }).length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByTestId("internal-kb-note")).not.toBeInTheDocument();
  });

  it("a missing per-event summary renders an honest note, never a crash", async () => {
    await mount();
    act(() => state.openDetail("monitoring_update", "EVT-2026-W28-002"));
    await waitFor(() => expect(screen.getByTestId("no-event-summary")).toBeInTheDocument());
    expect(screen.getByTestId("no-event-summary")).toHaveTextContent("No detailed summary is on file");
  });
});
