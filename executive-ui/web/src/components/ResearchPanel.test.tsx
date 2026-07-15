import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResearchPanel from "./ResearchPanel";
import Citations from "./Citations";
import { AppProvider } from "../store";
import type { Citation, ResearchRun } from "../types";

const runDetail: ResearchRun = {
  id: "RRUN-aaaaaaaaaaaa", title: "UAE SME sizing", objective: null, objectives: [],
  profile: "sme-financial-product", opportunity_ref: "OPP-010", status: "partial",
  error: "1 of 2 queries failed", notes: null,
  created_at: "2026-07-15T10:00:00Z", updated_at: "2026-07-15T10:05:00Z",
  started_at: "2026-07-15T10:00:10Z", completed_at: "2026-07-15T10:05:00Z",
  counts: { queries: 2, sources: 1, candidates: 1 },
  queries: [
    { id: "RQRY-aaaaaaaaaaa1", run_id: "RRUN-aaaaaaaaaaaa", objective: "market size",
      query_text: "uae sme count", provider: "mock", status: "executed", error: null,
      result_count: 1, created_at: "", executed_at: "" },
    { id: "RQRY-aaaaaaaaaaa2", run_id: "RRUN-aaaaaaaaaaaa", objective: null,
      query_text: "failing query", provider: "mock", status: "failed",
      error: "429 rate limited", result_count: null, created_at: "", executed_at: "" },
  ],
  sources: [
    { id: "RSRC-aaaaaaaaaaa1", run_id: "RRUN-aaaaaaaaaaaa", query_id: "RQRY-aaaaaaaaaaa1",
      canonical_url: "https://example.com/report", domain: "example.com",
      title: "SME Report 2026", publisher: "Example Institute", author: null,
      published_at: "2024-01-01", retrieved_at: "2026-07-15T10:01:00Z",
      language: null, excerpt: "600k SMEs…", content_hash: "abc", duplicate_of: null,
      quality_signals: { page_fetched: true }, created_at: "",
      freshness_status: "stale", freshness_reason: "Published 900 days ago." },
  ],
  candidate_evidence: [
    { id: "RCAND-aaaaaaaaaaa1", run_id: "RRUN-aaaaaaaaaaaa",
      claim: "UAE has ~600k SMEs", source_ids: ["RSRC-aaaaaaaaaaa1"],
      status: "pending_review", review_note: null, contradicts: null,
      created_at: "", updated_at: "" },
  ],
};

function fetchMockFor(routes: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [fragment, body] of Object.entries(routes)) {
      if (url.includes(fragment)) {
        return { ok: true, json: async () => body } as Response;
      }
    }
    return { ok: false, status: 404, json: async () => ({ error: "not found" }) } as Response;
  });
}

describe("ResearchPanel (Phase R3)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });
  beforeEach(() => { window.localStorage.clear(); });

  it("renders an honest empty state when no runs exist", async () => {
    global.fetch = fetchMockFor({ "/research/runs": { runs: [] } }) as unknown as typeof fetch;
    render(<ResearchPanel />);
    await waitFor(() =>
      expect(screen.getByText(/No research runs yet/)).toBeInTheDocument());
  });

  it("renders an honest unavailable state when the API is down", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("down")) as unknown as typeof fetch;
    render(<ResearchPanel />);
    await waitFor(() =>
      expect(screen.getByText(/research API is unreachable/)).toBeInTheDocument());
  });

  it("run detail shows partial status reason, failed query, stale source, and review controls", async () => {
    global.fetch = fetchMockFor({
      "/research/runs/RRUN-aaaaaaaaaaaa": runDetail,
      "/research/runs": { runs: [runDetail] },
    }) as unknown as typeof fetch;
    render(<ResearchPanel />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText("UAE SME sizing")).toBeInTheDocument());
    await user.click(screen.getByText("UAE SME sizing"));

    await waitFor(() => expect(screen.getByText(/1 of 2 queries failed/)).toBeInTheDocument());
    expect(screen.getByText(/429 rate limited/)).toBeInTheDocument();       // failed query honest
    expect(screen.getByText("stale")).toBeInTheDocument();                   // freshness flag
    expect(screen.getByText("SME Report 2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open source/ })).toHaveAttribute(
      "rel", expect.stringContaining("noopener"));
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    // the review hint states the boundary explicitly
    expect(screen.getByText(/never becomes repository evidence/)).toBeInTheDocument();
  });

  it("approving a candidate posts the review action", async () => {
    const fetchMock = fetchMockFor({
      "/review": { ...runDetail.candidate_evidence![0], status: "approved" },
      "/research/runs/RRUN-aaaaaaaaaaaa": runDetail,
      "/research/runs": { runs: [runDetail] },
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<ResearchPanel />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText("UAE SME sizing")).toBeInTheDocument());
    await user.click(screen.getByText("UAE SME sizing"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => {
      const reviewCall = fetchMock.mock.calls.find(([u]) => String(u).includes("/review"));
      expect(reviewCall).toBeTruthy();
      expect(JSON.parse((reviewCall![1] as RequestInit).body as string).action).toBe("approve");
    });
  });
});

describe("research_candidate citation chip (Phase R3)", () => {
  it("renders a distinct, safe, external-labelled chip with a stale flag from metadata", () => {
    const citation: Citation = {
      id: "RCAND-bbbbbbbbbbbb", type: "research_candidate",
      title: "UAE has ~600k SMEs", role: "external_research",
      target: { type: "internal_route", value: "/research/runs/RRUN-aaaaaaaaaaaa" },
      metadata: { external: true, sources: [{ url: "https://example.com/r", title: "SME Report", freshness_status: "stale" }] },
    };
    render(
      <AppProvider>
        <Citations citations={[citation]} />
      </AppProvider>,
    );
    const chip = screen.getByTestId("citation-research-candidate");
    expect(chip).toHaveTextContent("RCAND-bbbbbbbbbbbb");
    expect(chip).toHaveTextContent("external research");
    expect(screen.getByTestId("citation-stale-flag")).toBeInTheDocument();
    // never a navigable anchor to the external URL from the chip itself
    expect(chip.querySelector("a")).toBeNull();
  });
});
