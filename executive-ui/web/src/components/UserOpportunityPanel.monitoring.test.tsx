import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UserMonitoringPanel } from "./UserOpportunityPanel";

const OPP = "UOPP-abcabcabcabc";

const configuredBody = {
  id: "MCFG-111111111111", opportunity_id: OPP, status: "never_run", enabled: true,
  cadence: "weekly", topics: ["grocery settlement"], keywords: [], entities: [],
  source_categories: [], preferred_domains: [], excluded_domains: [],
  geographic_scope: null, language: null, notes: null,
  last_error: null, consecutive_failure_count: 0, last_run_at: null, next_run_at: null,
};

function fetchMockFor(routes: [string, string, unknown][]) {
  // routes: [method, url-fragment, body]; first match wins
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    for (const [m, fragment, body] of routes) {
      if (m === method && url.includes(fragment)) {
        return { ok: true, json: async () => body } as Response;
      }
    }
    return { ok: false, status: 404, json: async () => ({ error: `no route ${method} ${url}` }) } as Response;
  });
}

describe("UserMonitoringPanel manual run (Phase R4a)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });

  it("shows the honest never-run state and an enabled Run button", async () => {
    global.fetch = fetchMockFor([
      ["GET", "/monitoring/events", { events: [] }],
      ["GET", "/monitoring", configuredBody],
    ]) as unknown as typeof fetch;
    render(<UserMonitoringPanel oppId={OPP} />);
    await waitFor(() => expect(screen.getByTestId("monitoring-no-events")).toBeInTheDocument());
    expect(screen.getByTestId("monitoring-no-events")).toHaveTextContent("has not run yet");
    const btn = screen.getByRole("button", { name: "Run monitoring now" });
    expect(btn).toBeEnabled();
  });

  it("a run posts to /monitoring/run and renders the note and new events verbatim", async () => {
    const runResult = {
      run_id: "RRUN-222222222222", run_status: "complete", events_created: 1,
      new_events: [{ id: "MEVT-333333333333", opportunity_id: OPP,
        config_id: "MCFG-111111111111", research_run_id: "RRUN-222222222222",
        source_id: "RSRC-444444444444", title: "Settlement news",
        canonical_url: "https://news.example.com/a", domain: "news.example.com",
        published_at: "2026-07-01", detected_at: "2026-07-15T10:00:00Z" }],
      note: "1 new development(s) recorded.",
      config: { ...configuredBody, status: "active", last_run_at: "2026-07-15T10:00:00Z" },
    };
    const fetchMock = fetchMockFor([
      ["POST", "/monitoring/run", runResult],
      ["GET", "/monitoring/events", { events: runResult.new_events }],
      ["GET", "/monitoring", configuredBody],
    ]);
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<UserMonitoringPanel oppId={OPP} />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: "Run monitoring now" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Run monitoring now" }));

    await waitFor(() => expect(screen.getByTestId("monitoring-run-note"))
      .toHaveTextContent("1 new development(s) recorded."));
    expect(screen.getByTestId("monitoring-event")).toHaveTextContent("Settlement news");
    expect(screen.getByTestId("monitoring-event")).toHaveTextContent("RRUN-222222222222"); // traceable
    const postCall = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "POST");
    expect(String(postCall![0])).toContain(`/user-opportunities/${OPP}/monitoring/run`);
  });

  it("a failed run shows the honest failure note — no fabricated events", async () => {
    const failed = {
      run_id: "RRUN-555555555555", run_status: "failed", events_created: 0,
      new_events: [], note: "Monitoring run failed: no search provider configured (set RESEARCH_SEARCH_PROVIDER)",
      config: { ...configuredBody, status: "error",
        last_error: "no search provider configured (set RESEARCH_SEARCH_PROVIDER)",
        consecutive_failure_count: 1 },
    };
    global.fetch = fetchMockFor([
      ["POST", "/monitoring/run", failed],
      ["GET", "/monitoring/events", { events: [] }],
      ["GET", "/monitoring", configuredBody],
    ]) as unknown as typeof fetch;
    render(<UserMonitoringPanel oppId={OPP} />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: "Run monitoring now" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Run monitoring now" }));
    await waitFor(() => expect(screen.getByTestId("monitoring-run-note"))
      .toHaveTextContent("Monitoring run failed: no search provider configured"));
    expect(screen.queryByTestId("monitoring-event")).toBeNull();
  });

  it("the Run button is disabled while paused", async () => {
    global.fetch = fetchMockFor([
      ["GET", "/monitoring/events", { events: [] }],
      ["GET", "/monitoring", { ...configuredBody, enabled: false, status: "paused" }],
    ]) as unknown as typeof fetch;
    render(<UserMonitoringPanel oppId={OPP} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Run monitoring now" })).toBeDisabled());
  });
});
