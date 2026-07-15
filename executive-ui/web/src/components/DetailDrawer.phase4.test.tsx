// Phase 4 — evidence provenance in the DetailDrawer: complete/partial
// provenance, safe external links, honest no-source and unknown-freshness
// states, stale badge, excerpt, and linked opportunity/assumption chips.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import DetailDrawer from "./DetailDrawer";

vi.mock("../lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
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

describe("DetailDrawer evidence provenance (Phase 4)", () => {
  it("shows complete provenance: source, publisher, dates, excerpt, freshness", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-001"));
    expect(screen.getByText("Trustpilot — Telr")).toBeInTheDocument();
    expect(screen.getByText("Trustpilot")).toBeInTheDocument();
    expect(screen.getByText("2026-06-30")).toBeInTheDocument(); // publication date
    expect(screen.getByText("2026-07-10")).toBeInTheDocument(); // retrieved
    expect(screen.getByText("2026-07-11")).toBeInTheDocument(); // last verified
    expect(screen.getByTestId("evidence-excerpt")).toHaveTextContent("Funds held for more than 2 months");
    expect(screen.getByTestId("freshness-badge")).toHaveTextContent("Fresh");
    expect(screen.getByTestId("freshness-reason")).toHaveTextContent("Last verified 4 days ago.");
  });

  it("renders a safe external source link (new tab, noopener noreferrer)", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-001"));
    const link = screen.getByTestId("external-source-link");
    expect(link).toHaveAttribute("href", "https://trustpilot.com/review/telr.example");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders linked opportunities and assumptions as working chips", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-001"));
    const user = userEvent.setup();
    const oppChip = screen.getByRole("button", { name: /Open linked opportunity: Test Opportunity Two/ });
    await user.click(oppChip);
    expect(state.drawerOppId).toBe("OPP-002");
    act(() => state.openDetail("evidence", "EV-2026-W28-001"));
    const asmChip = screen.getByRole("button", { name: /Open linked assumption: Willingness To Pay/ });
    await user.click(asmChip);
    expect(state.detailTarget).toEqual(
      expect.objectContaining({ type: "assumption", id: "OPP-001::willingness_to_pay" }),
    );
  });

  it("shows the stale badge and reason for stale evidence", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-002"));
    expect(screen.getByTestId("freshness-badge")).toHaveTextContent("Stale");
    expect(screen.getByTestId("freshness-reason")).toHaveTextContent("Last verified 214 days ago");
  });

  it("explains honestly when there is no external source URL", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-002"));
    expect(screen.getByTestId("no-source-note")).toHaveTextContent(
      "internal repository record and has no external source URL",
    );
    expect(screen.queryByTestId("external-source-link")).not.toBeInTheDocument();
    expect(screen.getByText("Internal record")).toBeInTheDocument();
  });

  it("never renders an unsafe URL as a link, and handles unknown freshness + absent fields", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-003"));
    expect(screen.queryByTestId("external-source-link")).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(screen.getByTestId("no-source-note")).toHaveTextContent("not a safe web address");
    expect(screen.getByTestId("freshness-badge")).toHaveTextContent("Freshness unknown");
    // absent optional fields render honest placeholders, no crash
    expect(screen.getAllByText("Not recorded").length).toBeGreaterThan(0);
  });

  it("shows the contradiction field when recorded", async () => {
    await mount();
    act(() => state.openDetail("evidence", "EV-2026-W28-001"));
    expect(screen.getByText("None found this run")).toBeInTheDocument();
  });
});
