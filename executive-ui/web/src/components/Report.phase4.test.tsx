// Phase 4 — the web report route: clickable report title (/report/OPP-nnn),
// direct navigation, URL-driven mounting (refresh behavior), unknown-report
// state, click-through to evidence/assumption/prediction/monitoring details,
// and the sources appendix with safe links only.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import type { BriefPayload } from "../types";
import Report from "./Report";
import DetailDrawer from "./DetailDrawer";
import { ReportsPanel } from "./panels";

const briefFixture: BriefPayload = {
  opportunity_id: "OPP-001",
  title: "Test Opportunity One",
  generated_at: "2026-07-15T09:00:00Z",
  classification: "promising",
  classification_label: "Promising",
  is_archived: false,
  segment: "Test segment",
  jtbd: "Test JTBD",
  hypothesis: "Merchants will pay for faster settlement.",
  confidence: "medium",
  score_summary: { raw_score: 42, raw_max: 85, composite: 3.4, assumption_count: 6, critical_flags: [] },
  brief_envelope: {
    decision_requested: { text: "Approve a customer-validation sprint, not product development." },
    recommended_action: { text: "Run VE-001 before any build decision." },
  },
  brief_markdown: "# Recommendation\n\nValidate before building.",
  evidence: [overviewFixture.evidence[0], overviewFixture.evidence[1]],
  contradictory_evidence: "—",
  assumptions: overviewFixture.assumptions,
  predictions: [
    {
      id: "PRED-001", statement: "VE-001 reaches a conclusive verdict", p: 0.5,
      made: "2026-07-11", resolve_by: "2026-08-31", outcome: null, resolved_on: null,
      resolution_note: "", rationale: "base rates", links: ["VE-001", "OPP-001"],
      brier: null, excluded_from_calibration: false,
    },
  ],
  monitoring: {
    state: {
      status: "active", status_note: "Internal knowledge-base changes only.",
      last_checked: null, latest_event_at: "2026-07-12", event_count: 1,
      open_alert_count: 0, unresolved_warning_count: 0, monitored_entity_count: 7,
      external_source_count: 0, internal_only: true,
    },
    events: [{
      id: "EVT-2026-W28-010", entity: "OPP-001", detected_at: "2026-07-12",
      adapter: "kb-watcher", signal_type: "new_opportunity", title: "New backlog proposition OPP-001",
      scores: { impact: 3, urgency: 3, confidence: 4, relevance: 5, novelty: 4 },
      tier: "important", status: "new", kb_links: ["OPP-001"],
    }],
  },
  merchant_voice: { available: false, findings: [], note: "Merchant Voice has not published any findings in this environment." },
  risks: ["Funded competitor may capture the segment first."],
  unknowns: ["Is willingness to pay observed, not just stated?"],
  recommended_next_actions: ["Run VE-001 before any build decision."],
  sources: [
    { source_title: "Trustpilot — Telr", publisher: "Trustpilot",
      source_url: "https://trustpilot.com/review/telr.example", retrieved_at: "2026-07-10",
      access_label: "search-snippet", evidence_ids: ["EV-2026-W28-001"] },
    { source_title: "Internal desk research", publisher: null, source_url: null,
      retrieved_at: null, access_label: null, evidence_ids: ["EV-2026-W28-002"] },
  ],
  decision_banner: "No product or build decision has been made.",
};

vi.mock("../lib/api", () => ({
  api: {
    overview: vi.fn(() => Promise.resolve(overviewFixture)),
    brief: vi.fn((id: string) => Promise.resolve(id === "OPP-001" ? briefFixture : null)),
    journal: vi.fn(() => Promise.resolve({ predictions: briefFixture.predictions, calibration: null })),
    monitoring: vi.fn(() => Promise.resolve({ events: briefFixture.monitoring.events, alerts: [], summaries: [], summary_state: null })),
    monitoringSummary: vi.fn(() => Promise.resolve(null)),
  },
  isLive: () => true,
}));

let state: AppState;
function Harness() {
  const s = useApp();
  state = s;
  return (
    <>
      {s.view === "reports" && <ReportsPanel />}
      {s.view === "report" && <Report />}
      <DetailDrawer />
    </>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

async function mount() {
  render(
    <AppProvider>
      <Harness />
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
}

describe("Web report route (Phase 4)", () => {
  it("a report title in Reports & Briefs is a button that opens /report/OPP-001", async () => {
    await mount();
    act(() => state.goReports());
    const user = userEvent.setup();
    const titleBtn = await screen.findByRole("button", { name: /Open web report: Test Opportunity One/ });
    await user.click(titleBtn);
    expect(window.location.pathname).toBe("/report/OPP-001");
    await waitFor(() => expect(screen.getByTestId("report-title")).toHaveTextContent("Test Opportunity One"));
  });

  it("mounts directly into the report view from the URL (refresh / direct navigation)", async () => {
    window.history.replaceState({}, "", "/report/OPP-001");
    await mount();
    expect(state.view).toBe("report");
    await waitFor(() => expect(screen.getByTestId("report-title")).toHaveTextContent("Test Opportunity One"));
    expect(screen.getByText(/generated 2026-07-15/)).toBeInTheDocument();
    expect(screen.getByText("No product or build decision has been made.")).toBeInTheDocument();
  });

  it("renders a safe not-found state for an unknown opportunity", async () => {
    window.history.replaceState({}, "", "/report/OPP-099");
    await mount();
    await waitFor(() => expect(screen.getByTestId("report-not-found")).toBeInTheDocument());
    expect(screen.getByTestId("report-not-found")).toHaveTextContent("Report not found");
  });

  it("evidence in the report opens the evidence drawer with provenance", async () => {
    window.history.replaceState({}, "", "/report/OPP-001");
    await mount();
    const user = userEvent.setup();
    const row = await screen.findByRole("button", { name: /Open evidence detail: Merchants report slow settlement/ });
    await user.click(row);
    expect(state.detailTarget).toEqual(expect.objectContaining({ type: "evidence", id: "EV-2026-W28-001" }));
    // the drawer's own source link renders alongside the appendix links
    await waitFor(() => {
      const links = screen.getAllByTestId("external-source-link");
      expect(links.some((l) => l.closest(".drawer") !== null)).toBe(true);
    });
  });

  it("assumptions, predictions, and monitoring events click through to their details", async () => {
    window.history.replaceState({}, "", "/report/OPP-001");
    await mount();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Open assumption detail: Willingness To Pay/ }));
    expect(state.detailTarget).toEqual(expect.objectContaining({ type: "assumption", id: "OPP-001::willingness_to_pay" }));
    await user.click(screen.getByRole("button", { name: /Open prediction detail/ }));
    expect(state.detailTarget).toEqual(expect.objectContaining({ type: "prediction", id: "PRED-001" }));
    await user.click(screen.getByRole("button", { name: /Open monitoring event/ }));
    expect(state.detailTarget).toEqual(expect.objectContaining({ type: "monitoring_update", id: "EVT-2026-W28-010" }));
  });

  it("the sources appendix renders safe links and honest internal-record rows", async () => {
    window.history.replaceState({}, "", "/report/OPP-001");
    await mount();
    const sources = await screen.findByTestId("report-sources");
    const link = sources.querySelector('a[href="https://trustpilot.com/review/telr.example"]');
    expect(link).not.toBeNull();
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(sources).toHaveTextContent("Internal desk research");
    expect(sources.textContent).toContain("internal repository record");
  });

  it("shows the honest Merchant Voice unavailable note and partial-brief sections", async () => {
    window.history.replaceState({}, "", "/report/OPP-001");
    await mount();
    await screen.findByTestId("report-title");
    expect(screen.getByText(/Merchant Voice has not published any findings/)).toBeInTheDocument();
    expect(screen.getByText(/No contradictory evidence is recorded/)).toBeInTheDocument();
    expect(screen.getByTestId("report-brief-markdown")).toHaveTextContent("Validate before building.");
  });
});
