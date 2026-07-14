import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppProvider, useApp } from "../store";
import type { AppState } from "../store";
import { overviewFixture } from "../test/fixtures";
import Citations from "./Citations";
import type { Citation } from "../types";

vi.mock("../lib/api", () => ({
  api: { overview: vi.fn(() => Promise.resolve(overviewFixture)) },
  isLive: () => true,
}));

let state: AppState;
function Harness({ citations }: { citations: Citation[] }) {
  const s = useApp();
  state = s;
  return <Citations citations={citations} />;
}

beforeEach(() => window.localStorage.clear());

async function mount(citations: Citation[]) {
  render(
    <AppProvider>
      <Harness citations={citations} />
    </AppProvider>,
  );
  await waitFor(() => expect(state.loading).toBe(false));
}

const target = (v: string) => ({ type: "internal_route", value: v });

describe("Citations rendering (Phase 2K)", () => {
  it("an opportunity citation opens the existing opportunity drawer", async () => {
    await mount([{ id: "OPP-001", type: "opportunity", title: "Test", role: "primary",
                  target: target("/opportunity/OPP-001"), metadata: null }]);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /OPP-001/ }));
    expect(state.drawerOppId).toBe("OPP-001");
  });

  it("an evidence citation opens the evidence detail drawer", async () => {
    await mount([{ id: "EV-2026-W28-001", type: "evidence", title: "Test evidence", role: "primary",
                  target: target("/evidence/EV-2026-W28-001"), metadata: null }]);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /EV-2026-W28-001/ }));
    expect(state.detailTarget).toEqual({ type: "evidence", id: "EV-2026-W28-001", payload: undefined });
  });

  it("a merchant_finding citation opens its detail rendered from the citation payload", async () => {
    const citation: Citation = {
      id: "MEF-abc123", type: "merchant_finding", title: "Suppliers cancel late payments.", role: "weak_lead",
      target: target("/merchant-findings/MEF-abc123"),
      metadata: { campaign_id: "MVC-1", method: "interview", segment_id: null, strength_band: "single_signal",
                 support_count: 1, contradiction_count: 0, denominator: 1, denominator_definition: "included participants" },
    };
    await mount([citation]);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /MEF-abc123/ }));
    expect(state.detailTarget?.type).toBe("merchant_finding");
    expect(state.detailTarget?.payload).toEqual(citation);
  });

  it("an assumption citation maps ASM-OPP-nnn-key to the Phase 1 composite id", async () => {
    await mount([{ id: "ASM-OPP-013-willingness_to_pay", type: "assumption", title: "WTP", role: "contextual",
                  target: target("/assumption/ASM-OPP-013-willingness_to_pay"), metadata: null }]);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /ASM-OPP-013-willingness_to_pay/ }));
    expect(state.detailTarget).toEqual({ type: "assumption", id: "OPP-013::willingness_to_pay", payload: undefined });
  });

  it("an unsupported citation type (segment) renders as a safe, non-clickable reference", async () => {
    await mount([{ id: "SEG-uae-importers", type: "segment", title: "UAE importers", role: "contextual",
                  target: target("/segment/SEG-uae-importers"), metadata: null }]);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/SEG-uae-importers/)).toBeInTheDocument();
  });

  it("renders nothing for an empty citation list", async () => {
    await mount([]);
    expect(screen.queryByText(/citation/i)).toBeNull();
  });
});
