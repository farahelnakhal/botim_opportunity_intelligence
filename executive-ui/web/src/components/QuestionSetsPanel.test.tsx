import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QuestionSetsPanel from "./QuestionSetsPanel";
import type { QuestionSet } from "../types";

const draftSet: QuestionSet = {
  id: "RQSET-aaaaaaaaaaaa", opportunity_id: "OPP-001", status: "draft",
  questions: [{
    question_id: "RQSET-aaaaaaaaaaaa-Q1",
    text: "What do you do today when a supplier payment is late?",
    purpose: "behaviour", question_type: "open_text", follow_up_prompts: ["How often?"],
    linked_assumption: "ASM-OPP-001-workaround_cost", signals: ["open_gap"],
    source_weak_link_rank: 1,
  }],
  provenance: { model: "stub", gap_profile_weak_links: [] },
  rejected_count: 2, note: null, owner_user_id: null, created_at: "2026-07-20T10:00:00Z",
};

const approvedSet: QuestionSet = { ...draftSet, id: "RQSET-bbbbbbbbbbbb", status: "approved" };

function fetchMockFor(handlers: ((url: string, init?: RequestInit) => unknown | undefined)[]) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    for (const h of handlers) {
      const body = h(url, init);
      if (body !== undefined) return { ok: true, json: async () => body } as Response;
    }
    return { ok: false, status: 404, json: async () => ({ error: "not found" }) } as Response;
  });
}

describe("QuestionSetsPanel (Phase R10 / PR10c)", () => {
  const realFetch = global.fetch;
  afterEach(() => { global.fetch = realFetch; });

  it("shows an honest empty state", async () => {
    global.fetch = fetchMockFor([(u) => u.includes("/question-sets") ? { question_sets: [] } : undefined]) as unknown as typeof fetch;
    render(<QuestionSetsPanel />);
    await waitFor(() => expect(screen.getByText(/No question sets yet/)).toBeInTheDocument());
  });

  it("renders a draft set with its questions and the no-auto-send boundary", async () => {
    global.fetch = fetchMockFor([(u) => u.includes("/question-sets") ? { question_sets: [draftSet] } : undefined]) as unknown as typeof fetch;
    render(<QuestionSetsPanel />);
    await waitFor(() => expect(screen.getByText(/supplier payment is late/)).toBeInTheDocument());
    expect(screen.getByText("OPP-001")).toBeInTheDocument();
    expect(screen.getByText(/2 rejected in drafting/)).toBeInTheDocument();
    // the review hint states the hard boundary
    expect(screen.getByText(/never creates a Merchant Voice guide/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("posts an approve review and reloads", async () => {
    const calls: { url: string; body: string }[] = [];
    global.fetch = fetchMockFor([
      (u, init) => {
        if (u.includes("/review")) { calls.push({ url: u, body: String(init?.body) }); return { question_set: { ...draftSet, status: "approved" } }; }
        return undefined;
      },
      (u) => u.includes("/question-sets") ? { question_sets: [draftSet] } : undefined,
    ]) as unknown as typeof fetch;
    render(<QuestionSetsPanel />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: /^Approve$/ })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /^Approve$/ }));
    await waitFor(() => {
      expect(calls.length).toBeGreaterThan(0);
      expect(JSON.parse(calls[0].body).action).toBe("approve");
    });
  });

  it("loads the Merchant Voice hand-off for an approved set with the proposal-only boundary", async () => {
    global.fetch = fetchMockFor([
      (u) => u.includes("/handoff") ? {
        question_set_id: approvedSet.id, opportunity_id: "OPP-001",
        handoff: { markdown: "# Merchant Voice hand-off\n> Proposal only.", mv_guide_payload: [] },
      } : undefined,
      (u) => u.includes("/question-sets") ? { question_sets: [approvedSet] } : undefined,
    ]) as unknown as typeof fetch;
    render(<QuestionSetsPanel />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("button", { name: "Merchant Voice hand-off" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Merchant Voice hand-off" }));
    await waitFor(() => expect(screen.getByTestId("qset-handoff-md")).toHaveTextContent("Proposal only"));
    // the boundary that a human creates the guide themselves is stated
    expect(screen.getByText(/paste this into Merchant\s+Voice yourself/)).toBeInTheDocument();
  });
});
