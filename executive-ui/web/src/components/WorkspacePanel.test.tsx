import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WorkspacePanel from "./WorkspacePanel";
import type { WorkspaceVersion } from "../types";

const OPP = "UOPP-aaaaaaaaaaa1";

const version: WorkspaceVersion = {
  id: "AWV-aaaaaaaaaaa2", opportunity_id: OPP, version: 2, status: "complete",
  trigger: "manual_refresh", question: "is the pain real?", error: null,
  research_run_id: "RRUN-aaaaaaaaaaa1",
  created_at: "2026-07-17T10:00:00Z", completed_at: "2026-07-17T10:01:00Z",
  kb_evidence: [{ id: "EV-2026-W01-001", title: "Settlement complaints",
                  segment: "SEG-x", status: "active",
                  evidence_confidence: "Medium — survey", match: 3 }],
  claim_ids: ["RCAND-aaaaaaaaaaa1", "RCAND-aaaaaaaaaaa2"],
  preliminary_score: {
    preliminary: true, engine: "opportunity_engine.scoring", composite: 3.0,
    assumption_count: 17, assumption_capped: true, max_classification: "promising",
    classification: "promising (preliminary, unvalidated)", confidence: "low",
    basis_note: "all 17 dimensions are assumption-based defaults in this workspace version",
  },
  gaps: ["claim extraction skipped: no model provider configured"],
  provenance: { trigger: "manual_refresh", research_run_id: "RRUN-aaaaaaaaaaa1" },
  is_stale: false,
  claims: [
    { id: "RCAND-aaaaaaaaaaa1", claim: "The market grew 12% in 2024.",
      status: "pending_review", origin: "extracted", source_ids: ["RSRC-1"] },
    { id: "RCAND-aaaaaaaaaaa2", claim: "Settlement takes 4 days on average.",
      status: "approved", origin: "extracted", source_ids: ["RSRC-2"] },
  ],
};

function fetchMockFor(routes: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    // longest fragment first so /workspace/versions wins over /workspace
    const entries = Object.entries(routes).sort((a, b) => b[0].length - a[0].length);
    for (const [fragment, body] of entries) {
      if (url.includes(fragment)) {
        return { ok: true, json: async () => body } as Response;
      }
    }
    return { ok: false, status: 404, json: async () => ({ error: "not found" }) } as Response;
  });
}

describe("WorkspacePanel (Phase R5 PR4-UI)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });

  it("renders an honest empty state before any analysis has run", async () => {
    global.fetch = fetchMockFor({
      "/workspace/versions": { versions: [] },
      "/workspace/diff": { diff: null, note: "fewer than two complete versions exist" },
      "/workspace": { workspace: null, note: "no analysis workspace exists yet — run a refresh" },
    }) as unknown as typeof fetch;
    render(<WorkspacePanel oppId={OPP} />);
    await waitFor(() =>
      expect(screen.getByTestId("workspace-empty")).toBeInTheDocument());
    expect(screen.getByTestId("refresh-analysis")).toHaveTextContent("Run first analysis");
  });

  it("badges every machine number PRELIMINARY and shows the engine cap", async () => {
    global.fetch = fetchMockFor({
      "/workspace/versions": { versions: [] },
      "/workspace/diff": { diff: null },
      "/workspace": { workspace: version },
    }) as unknown as typeof fetch;
    render(<WorkspacePanel oppId={OPP} />);
    await waitFor(() =>
      expect(screen.getByTestId("workspace-score")).toBeInTheDocument());
    expect(screen.getAllByTestId("preliminary-badge").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/engine-capped at 'promising'/)).toBeInTheDocument();
    expect(screen.getByText("promising (preliminary, unvalidated)")).toBeInTheDocument();
  });

  it("separates approved claims from pending-review ones", async () => {
    global.fetch = fetchMockFor({
      "/workspace/versions": { versions: [] },
      "/workspace/diff": { diff: null },
      "/workspace": { workspace: version },
    }) as unknown as typeof fetch;
    render(<WorkspacePanel oppId={OPP} />);
    await waitFor(() =>
      expect(screen.getByTestId("workspace-claim-pending")).toBeInTheDocument());
    expect(screen.getByTestId("workspace-claim-approved"))
      .toHaveTextContent("Settlement takes 4 days on average.");
    expect(screen.getByTestId("workspace-claim-pending"))
      .toHaveTextContent("The market grew 12% in 2024.");
    expect(screen.getByText("Pending review")).toBeInTheDocument();
    expect(screen.getByText("Approved (human-reviewed)")).toBeInTheDocument();
  });

  it("lists gaps honestly and shows a stale banner", async () => {
    global.fetch = fetchMockFor({
      "/workspace/versions": { versions: [] },
      "/workspace/diff": { diff: null },
      "/workspace": { workspace: { ...version, is_stale: true } },
    }) as unknown as typeof fetch;
    render(<WorkspacePanel oppId={OPP} />);
    await waitFor(() =>
      expect(screen.getByTestId("workspace-stale")).toBeInTheDocument());
    expect(screen.getByTestId("workspace-gaps"))
      .toHaveTextContent("claim extraction skipped: no model provider configured");
  });

  it("renders the diff surface when two versions exist", async () => {
    global.fetch = fetchMockFor({
      "/workspace/versions": { versions: [
        { id: "AWV-aaaaaaaaaaa2", opportunity_id: OPP, version: 2, status: "complete",
          trigger: "manual_refresh", question: null, error: null,
          research_run_id: null, created_at: "2026-07-17T10:00:00Z",
          completed_at: "2026-07-17T10:01:00Z" },
        { id: "AWV-aaaaaaaaaaa1", opportunity_id: OPP, version: 1, status: "complete",
          trigger: "first_analysis", question: null, error: null,
          research_run_id: null, created_at: "2026-07-16T10:00:00Z",
          completed_at: "2026-07-16T10:01:00Z" },
      ] },
      "/workspace/diff": { diff: {
        older_id: "AWV-aaaaaaaaaaa1", newer_id: "AWV-aaaaaaaaaaa2",
        composite_before: 3.0, composite_after: 3.0, composite_delta: 0.0,
        new_claim_ids: ["RCAND-aaaaaaaaaaa2"], removed_claim_ids: [],
        new_gaps: [], resolved_gaps: ["no search provider configured"],
      } },
      "/workspace": { workspace: version },
    }) as unknown as typeof fetch;
    render(<WorkspacePanel oppId={OPP} />);
    await waitFor(() =>
      expect(screen.getByTestId("workspace-diff")).toBeInTheDocument());
    expect(screen.getByTestId("workspace-diff")).toHaveTextContent("RCAND-aaaaaaaaaaa2");
    expect(screen.getByTestId("workspace-diff")).toHaveTextContent("no search provider configured");
    expect(screen.getAllByTestId("workspace-version-row")).toHaveLength(2);
  });

  it("refresh posts to the refresh route and shows the honest running state", async () => {
    let refreshed = false;
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/workspace/refresh") && init?.method === "POST") {
        refreshed = true;
        expect(JSON.parse(String(init.body))).toEqual({ question: "focus here" });
        return { ok: true, json: async () => version } as Response;
      }
      if (url.includes("/workspace/versions")) return { ok: true, json: async () => ({ versions: [] }) } as Response;
      if (url.includes("/workspace/diff")) return { ok: true, json: async () => ({ diff: null }) } as Response;
      return { ok: true, json: async () => ({ workspace: refreshed ? version : null, note: "none yet" }) } as Response;
    }) as unknown as typeof fetch;

    render(<WorkspacePanel oppId={OPP} />);
    await waitFor(() => expect(screen.getByTestId("workspace-empty")).toBeInTheDocument());
    await userEvent.type(screen.getByTestId("workspace-question"), "focus here");
    await userEvent.click(screen.getByTestId("refresh-analysis"));
    await waitFor(() => expect(screen.getByTestId("workspace-score")).toBeInTheDocument());
    expect(refreshed).toBe(true);
  });

  it("shows an honest error when the workspace API is unreachable", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("down")) as unknown as typeof fetch;
    render(<WorkspacePanel oppId={OPP} />);
    await waitFor(() =>
      expect(screen.getByText(/workspace API is unreachable/)).toBeInTheDocument());
  });
});
