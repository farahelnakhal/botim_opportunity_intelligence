import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CalculatorsPanel from "./CalculatorsPanel";
import type { CalcEnvelope, CalculatorSpec } from "../lib/calculatorsApi";

const catalog: CalculatorSpec[] = [
  {
    id: "market_sizing", title: "Market sizing (top-down TAM/SAM/SOM)",
    description: "Top-down annual market value.", version: 1,
    notes: ["Sizes the market, not BOTIM's right to serve it."],
    inputs: [
      { name: "population", unit: "units", kind: "count", required: true, description: "", min: 0, max: null },
      { name: "annual_value_per_unit", unit: "AED/unit/year", kind: "currency", required: true, description: "", min: 0, max: null },
    ],
  },
];

const envelope: CalcEnvelope = {
  calculator_id: "market_sizing", calculator_version: 1,
  title: "Market sizing (top-down TAM/SAM/SOM)",
  normalized_inputs: {
    population: { value: 500000, label: "A", note: "", source_id: null },
    annual_value_per_unit: { value: 12000, label: "A", note: "", source_id: null },
  },
  steps: [{
    output: "tam", op: "mul",
    operands: [{ ref: "population", value: 500000, label: "A" },
               { ref: "annual_value_per_unit", value: 12000, label: "A" }],
    result: 6_000_000_000, result_display: "6,000,000,000", label: "A",
    unit: "AED/year", kind: "currency",
    expression: "population × annual_value_per_unit", substituted: "500,000 × 12,000",
  }],
  outputs: { tam: { value: 6_000_000_000, label: "A", unit: "AED/year", kind: "currency", display: "6,000,000,000" } },
  warnings: [],
  result_label: "A",
  disclaimers: ["Illustrative / preliminary — a calculation over assumed or estimated inputs, not a validated figure."],
};

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method || "GET").toUpperCase();
    if (url.includes("/calculators/results")) return { ok: true, json: async () => ({ saved_calculations: [] }) } as Response;
    if (url.includes("/compute") && method === "POST") return { ok: true, json: async () => ({ calculation: envelope }) } as Response;
    if (url.endsWith("/calculators") || url.includes("/calculators?")) return { ok: true, json: async () => ({ calculators: catalog }) } as Response;
    return { ok: false, status: 404, json: async () => ({ error: "not found" }) } as Response;
  });
}

describe("CalculatorsPanel (Phase C1)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });
  beforeEach(() => { window.localStorage.clear(); });

  it("loads the catalog and lists calculators", async () => {
    global.fetch = mockFetch() as unknown as typeof fetch;
    render(<CalculatorsPanel />);
    await waitFor(() => expect(screen.getByTestId("calc-select")).toBeInTheDocument());
    expect(screen.getByText(/Top-down annual market value/)).toBeInTheDocument();
  });

  it("computes and shows the full working with an illustrative disclaimer", async () => {
    global.fetch = mockFetch() as unknown as typeof fetch;
    const user = userEvent.setup();
    render(<CalculatorsPanel />);
    await waitFor(() => expect(screen.getByTestId("calc-select")).toBeInTheDocument());

    const inputs = screen.getAllByRole("spinbutton"); // number fields
    await user.type(inputs[0], "500000");
    await user.type(inputs[1], "12000");
    await user.click(screen.getByTestId("calc-compute"));

    await waitFor(() => expect(screen.getByTestId("calc-result")).toBeInTheDocument());
    // the computed TAM and the formula are both shown
    expect(screen.getByText("population × annual_value_per_unit")).toBeInTheDocument();
    expect(screen.getAllByText(/6,000,000,000/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("calc-disclaimer")).toHaveTextContent(/Illustrative/);
  });

  it("shows an honest empty state for saved calculations", async () => {
    global.fetch = mockFetch() as unknown as typeof fetch;
    render(<CalculatorsPanel />);
    await waitFor(() => expect(screen.getByText(/No saved calculations yet/)).toBeInTheDocument());
  });
});
