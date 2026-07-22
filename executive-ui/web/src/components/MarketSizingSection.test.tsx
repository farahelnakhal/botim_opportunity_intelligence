// Phase C2 / PR3 — the market-sizing UI. These tests assert the phase's hard
// constraint at the RENDERED-DOM level, not just in the data model: a
// low-confidence / assumption number must never LOOK like a corroborated /
// fact one. We assert the badges differ in BOTH text content AND class name
// when they appear side by side in the same rendered output.
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MarketSizingSection from "./MarketSizingSection";
import type { CalcEnvelope } from "../lib/calculatorsApi";
import type { MarketSizing, ResearchFigure } from "../lib/marketSizingApi";

const RUN = "RRUN-aaaaaaaaaaaa";

const figures: ResearchFigure[] = [
  { id: "RFIG-000000000001", run_id: RUN, source_id: "RSRC-000000000001",
    quantity: "population", value: 500000, unit: "businesses", tier: "T1",
    supporting_quote: "There are 500,000 SMEs.", created_at: "2026-07-20T00:00:00Z" },
  { id: "RFIG-000000000002", run_id: RUN, source_id: "RSRC-000000000002",
    quantity: "spend", value: 12000, unit: "aed", tier: "T3",
    supporting_quote: "Average spend is 12,000.", created_at: "2026-07-20T00:00:00Z" },
];

function envelope(popLabel: string): CalcEnvelope {
  return {
    calculator_id: "market_sizing", calculator_version: 1, title: "Market sizing",
    normalized_inputs: {
      population: { value: 500000, label: popLabel, note: "corroborated", source_id: "RSRC-000000000001" },
      annual_value_per_unit: { value: 12000, label: "A", note: "low-confidence", source_id: "RSRC-000000000002" },
      serviceable_fraction: { value: 0.4, label: "A", note: "analyst assumption", source_id: null },
      obtainable_share: { value: 0.1, label: "A", note: "analyst assumption", source_id: null },
    },
    steps: [], result_label: popLabel,
    outputs: {
      tam: { value: 6e9, label: popLabel, unit: "aed", kind: "number", display: "6,000,000,000" },
      sam: { value: 2.4e9, label: popLabel, unit: "aed", kind: "number", display: "2,400,000,000" },
      som: { value: 2.4e8, label: popLabel, unit: "aed", kind: "number", display: "240,000,000" },
    },
    warnings: [], disclaimers: ["Sizes a market, not BOTIM's right to serve it."],
  };
}

function sizing(id: string, confidence: "verified" | "low_confidence",
                status: MarketSizing["status"] = "pending_review"): MarketSizing {
  return {
    id, opportunity_id: "OPP-013", status, calculator: "market_sizing", run_id: RUN,
    confidence,
    sizing: {
      method: "top_down", calculator: "market_sizing",
      envelope: envelope(confidence === "verified" ? "F" : "A"),
      inputs_meta: {}, run_id: RUN, overall_confidence: confidence,
      confidence_basis: confidence === "verified"
        ? "all source-verified inputs are corroborated by >=2 independent T1/T2 sources"
        : "at least one source-verified input is low-confidence — not validated",
    },
    reviewed_at: status === "pending_review" ? null : "2026-07-21T00:00:00Z",
    reviewer: null, review_note: null, owner_user_id: null, created_at: "2026-07-20T00:00:00Z",
  };
}

// method-aware fetch mock: match GET vs POST and the most specific fragment.
function mockFetch(opts: {
  figures?: ResearchFigure[];
  sizings?: MarketSizing[];
  onBuild?: () => { ok: boolean; body: unknown };
  onReview?: () => { ok: boolean; body: unknown };
  onExtract?: () => { ok: boolean; body: unknown };
}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || "GET").toUpperCase();
    const reply = (ok: boolean, body: unknown, status = ok ? 200 : 400) =>
      ({ ok, status, json: async () => body } as Response);

    if (method === "POST" && url.includes("/extract-figures")) {
      const r = opts.onExtract?.() ?? { ok: true, body: { run_id: RUN, proposed: 0, accepted: 0, rejected: [], figures: [] } };
      return reply(r.ok, r.body);
    }
    if (method === "POST" && url.includes("/review")) {
      const r = opts.onReview?.() ?? { ok: true, body: { market_sizing: sizing("MSZ-000000000001", "verified", "approved") } };
      return reply(r.ok, r.body);
    }
    if (method === "POST" && url.includes("/market-sizing")) {
      const r = opts.onBuild?.() ?? { ok: true, body: { market_sizing: sizing("MSZ-000000000009", "verified") } };
      return reply(r.ok, r.body, r.ok ? 201 : 422);
    }
    if (url.includes("/figures")) return reply(true, { figures: opts.figures ?? [] });
    if (url.includes("/market-sizing")) return reply(true, { market_sizings: opts.sizings ?? [] });
    return reply(false, { error: "not found" }, 404);
  });
}

describe("MarketSizingSection (Phase C2)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });

  it("renders figures with their source-tier chips", async () => {
    global.fetch = mockFetch({ figures }) as unknown as typeof fetch;
    render(<MarketSizingSection runId={RUN} opportunityRef="OPP-013" hasSources />);
    await waitFor(() => expect(screen.getByTestId("tier-T1")).toBeInTheDocument());
    expect(screen.getByTestId("tier-T1")).toHaveTextContent("T1");
    expect(screen.getByTestId("tier-T3")).toHaveTextContent("T3");
    // different tiers get different class names
    expect(screen.getByTestId("tier-T1").className).not.toEqual(screen.getByTestId("tier-T3").className);
  });

  // THE constraint, at the DOM level: within one rendered sizing result, a Fact
  // input and an Assumption input differ in BOTH text and class name.
  it("renders Fact and Assumption inputs with different text AND class in the same result", async () => {
    global.fetch = mockFetch({ figures, sizings: [sizing("MSZ-000000000001", "verified")] }) as unknown as typeof fetch;
    render(<MarketSizingSection runId={RUN} opportunityRef="OPP-013" hasSources />);
    await waitFor(() => expect(screen.getByTestId("msz-result")).toBeInTheDocument());

    const result = screen.getByTestId("msz-result");
    const factChip = within(within(result).getByTestId("msz-input-population")).getByTestId("basis-F");
    const assumeChip = within(within(result).getByTestId("msz-input-serviceable_fraction")).getByTestId("basis-A");

    expect(factChip).toHaveTextContent("Fact");
    expect(assumeChip).toHaveTextContent("Assumption");
    expect(factChip.textContent).not.toEqual(assumeChip.textContent);   // different words
    expect(factChip.className).not.toEqual(assumeChip.className);        // different classes
  });

  // whole-sizing level: verified vs low_confidence badges side by side differ.
  it("renders Verified and Low-confidence badges with different text AND class", async () => {
    global.fetch = mockFetch({
      figures,
      sizings: [sizing("MSZ-000000000001", "verified"), sizing("MSZ-000000000002", "low_confidence")],
    }) as unknown as typeof fetch;
    render(<MarketSizingSection runId={RUN} opportunityRef="OPP-013" hasSources />);
    await waitFor(() => expect(screen.getAllByTestId("msz-result").length).toBe(2));

    const verified = screen.getByTestId("msz-confidence-verified");
    const low = screen.getByTestId("msz-confidence-low_confidence");
    expect(verified).toHaveTextContent("Verified");
    expect(low).toHaveTextContent("Low confidence");
    expect(verified.textContent).not.toEqual(low.textContent);
    expect(verified.className).not.toEqual(low.className);
    // and the basis sentence is shown, not just the badge
    expect(screen.getAllByTestId("msz-confidence-basis").length).toBe(2);
  });

  it("surfaces an honest error when figure extraction has no provider", async () => {
    global.fetch = mockFetch({
      figures,
      onExtract: () => ({ ok: false, body: { error: "no model provider configured for figure extraction" } }),
    }) as unknown as typeof fetch;
    render(<MarketSizingSection runId={RUN} opportunityRef="OPP-013" hasSources />);
    await waitFor(() => expect(screen.getByTestId("msz-extract")).toBeInTheDocument());
    await userEvent.setup().click(screen.getByTestId("msz-extract"));
    await waitFor(() => expect(screen.getByTestId("msz-extract-note"))
      .toHaveTextContent(/no model provider/));
  });

  it("refuses to build when a sourced input is not mapped to a verified figure", async () => {
    global.fetch = mockFetch({ figures }) as unknown as typeof fetch;
    render(<MarketSizingSection runId={RUN} opportunityRef="OPP-013" hasSources />);
    await waitFor(() => expect(screen.getByTestId("msz-build")).toBeInTheDocument());
    await userEvent.setup().click(screen.getByTestId("msz-build"));
    await waitFor(() => expect(screen.getByTestId("msz-build-error"))
      .toHaveTextContent(/Map a verified figure/));
  });

  it("surfaces the server's 422 (missing figure) verbatim rather than inventing", async () => {
    global.fetch = mockFetch({
      figures,
      onBuild: () => ({ ok: false, body: { error: "no verified figures for 'population' in this run" } }),
    }) as unknown as typeof fetch;
    render(<MarketSizingSection runId={RUN} opportunityRef="OPP-013" hasSources />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByTestId("msz-map-population")).toBeInTheDocument());
    await user.selectOptions(screen.getByTestId("msz-map-population"), "population");
    await user.selectOptions(screen.getByTestId("msz-map-annual_value_per_unit"), "spend");
    await user.type(screen.getByTestId("msz-assume-serviceable_fraction"), "0.4");
    await user.type(screen.getByTestId("msz-assume-obtainable_share"), "0.1");
    await user.click(screen.getByTestId("msz-build"));
    await waitFor(() => expect(screen.getByTestId("msz-build-error"))
      .toHaveTextContent(/no verified figures for 'population'/));
  });

  it("approve posts the review action and refreshes", async () => {
    const fetchMock = mockFetch({ figures, sizings: [sizing("MSZ-000000000001", "verified")] });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<MarketSizingSection runId={RUN} opportunityRef="OPP-013" hasSources />);
    await waitFor(() => expect(screen.getByTestId("msz-approve")).toBeInTheDocument());
    await userEvent.setup().click(screen.getByTestId("msz-approve"));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u, i]) =>
        String(u).includes("/review") && (i as RequestInit)?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as RequestInit).body as string).action).toBe("approve");
    });
  });

  it("a reviewed (terminal) sizing shows no review controls", async () => {
    global.fetch = mockFetch({
      figures, sizings: [sizing("MSZ-000000000003", "verified", "approved")],
    }) as unknown as typeof fetch;
    render(<MarketSizingSection runId={RUN} opportunityRef="OPP-013" hasSources />);
    await waitFor(() => expect(screen.getByTestId("msz-result")).toBeInTheDocument());
    expect(screen.queryByTestId("msz-approve")).toBeNull();
    expect(within(screen.getByTestId("msz-result")).getByText(/never writes a committed score/))
      .toBeInTheDocument();
  });
});
