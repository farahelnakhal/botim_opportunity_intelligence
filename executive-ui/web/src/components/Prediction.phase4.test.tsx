// Phase 4 — clickable predictions: the journal card opens the detail view;
// the detail shows rationale, linked records, completed and unresolved
// states, and stays honest when optional fields are absent.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import type { JournalPayload } from "../types";
import { DecisionJournalEntry } from "./cards";
import DetailDrawer from "./DetailDrawer";

const journalFixture: JournalPayload = {
  predictions: [
    {
      id: "PRED-001",
      statement: "VE-001 reaches a conclusive verdict by 2026-08-31",
      p: 0.5,
      made: "2026-07-11",
      resolve_by: "2026-08-31",
      outcome: null,
      resolved_on: null,
      resolution_note: "",
      rationale: "Waitlist conversions typically 5-15%; wide inconclusive zone",
      links: ["VE-001", "OPP-001"],
      brier: null,
      excluded_from_calibration: false,
    },
    {
      id: "PRED-004",
      statement: "Desk research confirms pricing is viable",
      p: 0.6,
      made: "2026-07-11",
      resolve_by: "2026-08-15",
      outcome: true,
      resolved_on: "2026-07-11",
      resolution_note: "Sits well inside market acceptance",
      rationale: "",
      links: [],
      brier: 0.16,
      excluded_from_calibration: true,
    },
  ],
  calibration: null,
};

vi.mock("../lib/api", () => ({
  api: {
    overview: vi.fn(() => Promise.resolve(overviewFixture)),
    monitoring: vi.fn(() => Promise.resolve({ events: [], alerts: [], summaries: [], summary_state: null })),
    monitoringSummary: vi.fn(() => Promise.resolve(null)),
    journal: vi.fn(() => Promise.resolve(journalFixture)),
  },
  isLive: () => true,
}));

let state: AppState;
function Harness() {
  const s = useApp();
  state = s;
  return (
    <>
      <DecisionJournalEntry data={journalFixture.predictions[0]} />
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
}

describe("Predictions (Phase 4)", () => {
  it("the journal card is a button that opens the prediction detail", async () => {
    await mount();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Open prediction detail/ }));
    expect(state.detailTarget).toEqual(
      expect.objectContaining({ type: "prediction", id: "PRED-001" }),
    );
  });

  it("an unresolved prediction shows statement, rationale, confidence, and linked records", async () => {
    await mount();
    act(() => state.openDetail("prediction", "PRED-001"));
    await waitFor(() => expect(screen.getByTestId("prediction-statement")).toBeInTheDocument());
    expect(screen.getByTestId("prediction-rationale")).toHaveTextContent("Waitlist conversions typically 5-15%");
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("Open")).toBeInTheDocument();
    // linked opportunity opens the opportunity drawer
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Open linked opportunity: Test Opportunity One/ }));
    expect(state.drawerOppId).toBe("OPP-001");
    // linked experiment renders as a safe, informative reference
    act(() => state.openDetail("prediction", "PRED-001"));
    expect(screen.getByText(/validation experiment \(VE-001\)/)).toBeInTheDocument();
  });

  it("a completed prediction shows outcome, resolution note, and Brier; missing rationale is honest", async () => {
    await mount();
    act(() => state.openDetail("prediction", "PRED-004"));
    await waitFor(() => expect(screen.getByTestId("prediction-statement")).toBeInTheDocument());
    expect(screen.getByText("Came true")).toBeInTheDocument();
    expect(screen.getByTestId("prediction-resolution")).toHaveTextContent("Sits well inside market acceptance");
    expect(screen.getByText("0.16")).toBeInTheDocument();
    expect(screen.getByTestId("no-rationale")).toHaveTextContent("No rationale was recorded");
    expect(screen.getByText(/No linked records were recorded/)).toBeInTheDocument();
    expect(screen.getByText(/Excluded from calibration/)).toBeInTheDocument();
  });

  it("an unknown prediction id renders a safe unavailable state", async () => {
    await mount();
    act(() => state.openDetail("prediction", "PRED-999"));
    await waitFor(() => expect(screen.getByText("Not available")).toBeInTheDocument());
  });
});
