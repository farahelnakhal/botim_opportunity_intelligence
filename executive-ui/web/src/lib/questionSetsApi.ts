// Question-sets client (Phase R10) — talks to executive-ui/api's
// /question-sets/* routes (shared/contracts/question-sets.schema.md). Honest
// failure shape everywhere: {ok:false, error}. Draft sets are PROPOSALS ONLY —
// nothing here (or on the server) writes Merchant Voice or contacts a merchant;
// a reviewed set is handed off manually into Merchant Voice's own flow.

import type { QuestionSet, QuestionSetHandoff, QuestionDraft } from "../types";

const BASE = import.meta.env.VITE_EXECUTIVE_API_BASE_URL || "/executive-api";

export type QResult<T> = { ok: true; data: T } | { ok: false; error: string };

async function request<T>(path: string, init?: RequestInit): Promise<QResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      return { ok: false, error: "malformed response from the question-sets API" };
    }
    if (!res.ok) {
      const msg = (body as { error?: string })?.error || `HTTP ${res.status}`;
      return { ok: false, error: msg };
    }
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, error: "the question-sets API is unreachable" };
  }
}

export const questionSetsApi = {
  list(opportunityId?: string) {
    const qs = opportunityId ? `?opportunity_id=${encodeURIComponent(opportunityId)}` : "";
    return request<{ question_sets: QuestionSet[] }>(`/question-sets${qs}`);
  },

  get(setId: string) {
    return request<{ question_set: QuestionSet }>(`/question-sets/${encodeURIComponent(setId)}`);
  },

  generate(opportunityId: string) {
    return request<{ question_set: QuestionSet }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/question-sets`,
      { method: "POST", body: "{}" },
    );
  },

  // Approve (optionally with reviewer-edited questions) or reject a draft set.
  // Edits are re-validated against Merchant Voice's taxonomy server-side.
  review(setId: string, action: "approve" | "reject",
         opts?: { questions?: QuestionDraft[]; note?: string }) {
    return request<{ question_set: QuestionSet }>(
      `/question-sets/${encodeURIComponent(setId)}/review`,
      { method: "POST", body: JSON.stringify({ action, ...opts }) },
    );
  },

  // Merchant Voice hand-off for an APPROVED set (409 otherwise): copy-paste
  // markdown + a MV-guide-shaped payload a human pastes into Merchant Voice.
  handoff(setId: string) {
    return request<{ question_set_id: string; opportunity_id: string; handoff: QuestionSetHandoff }>(
      `/question-sets/${encodeURIComponent(setId)}/handoff`,
    );
  },

  remove(setId: string) {
    return request<{ id: string; deleted: boolean }>(
      `/question-sets/${encodeURIComponent(setId)}`,
      { method: "DELETE" },
    );
  },
};
