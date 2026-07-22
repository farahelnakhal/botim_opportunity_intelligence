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
      "/figures": { figures: [] },
      "/market-sizing": { market_sizings: [] },
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

  it("marks a synthesized (constructed) source link and shows its recorded rating", async () => {
    const withSynthesized: ResearchRun = {
      ...runDetail,
      sources: [{
        ...runDetail.sources![0],
        title: "Payouts are slow",
        canonical_url: "https://apps.apple.com/ae/app/id12345?reviewId=111",
        domain: "apps.apple.com",
        quality_signals: { rating: "2", url_synthesized: true },
        freshness_status: undefined, freshness_reason: undefined,
      }],
    };
    global.fetch = fetchMockFor({
      "/figures": { figures: [] },
      "/market-sizing": { market_sizings: [] },
      "/research/runs/RRUN-aaaaaaaaaaaa": withSynthesized,
      "/research/runs": { runs: [withSynthesized] },
    }) as unknown as typeof fetch;
    render(<ResearchPanel />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText("UAE SME sizing")).toBeInTheDocument());
    await user.click(screen.getByText("UAE SME sizing"));

    await waitFor(() => expect(screen.getByText("Payouts are slow")).toBeInTheDocument());
    // the link is honestly labelled "open linked page" (not "open source")
    // and carries an explicit "(not a direct link)" note
    expect(screen.getByRole("link", { name: /open linked page/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^open source$/ })).toBeNull();
    expect(screen.getByTestId("synthesized-link-note")).toHaveTextContent("not a direct link");
    // the real feed rating is shown
    expect(screen.getByTestId("source-rating")).toHaveTextContent("2");
  });

  it("approving a candidate posts the review action", async () => {
    const fetchMock = fetchMockFor({
      "/review": { ...runDetail.candidate_evidence![0], status: "approved" },
      "/figures": { figures: [] },
      "/market-sizing": { market_sizings: [] },
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

describe("source revalidation (Phase R4b)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });

  it("revalidate posts, shows the summary, outcome badges, and candidate health warning", async () => {
    const revalidated = {
      ...runDetail,
      sources: [{
        ...runDetail.sources![0],
        last_revalidation: { id: "RREV-aaaaaaaaaaa1", source_id: "RSRC-aaaaaaaaaaa1",
          outcome: "unreachable" as const, http_status: null, new_content_hash: null,
          note: "fetch failed after retry (OSError)", checked_at: "2026-07-16T09:00:00Z" },
      }],
      candidate_evidence: [{ ...runDetail.candidate_evidence![0], source_health: "unreachable" as const }],
      revalidation_summary: { run_id: runDetail.id, checked: 1, skipped: 0,
        unchanged: 0, changed: 0, unreachable: 1 },
    };
    const fetchMock = fetchMockFor({
      "/revalidate": revalidated,
      "/figures": { figures: [] },
      "/market-sizing": { market_sizings: [] },
      "/research/runs/RRUN-aaaaaaaaaaaa": runDetail,
      "/research/runs": { runs: [runDetail] },
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<ResearchPanel />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByText("UAE SME sizing")).toBeInTheDocument());
    await user.click(screen.getByText("UAE SME sizing"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Revalidate sources" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Revalidate sources" }));

    await waitFor(() => expect(screen.getByTestId("revalidation-summary"))
      .toHaveTextContent("Re-checked 1 source: 0 unchanged, 0 changed, 1 unreachable."));
    expect(screen.getByTestId("revalidation-badge")).toHaveTextContent("unreachable");
    expect(screen.getByTestId("candidate-source-health"))
      .toHaveTextContent("failed revalidation (unreachable)");
    const post = fetchMock.mock.calls.find(([u]) => String(u).includes("/revalidate"));
    expect(post).toBeTruthy();
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
