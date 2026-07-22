// Verified-source market-sizing client (Phase C2) — talks to executive-ui/api's
// /research/runs/{id}/figures + /extract-figures and /market-sizing routes
// (shared/contracts/{research,market-sizing}.schema.md). Honest failure shape
// everywhere: {ok:false, error}. The server extracts, corroborates, and computes
// every number; the client never does arithmetic and never invents a figure.

import type { CalcEnvelope } from "./calculatorsApi";

const BASE = import.meta.env.VITE_EXECUTIVE_API_BASE_URL || "/executive-api";

export type MszResult<T> = { ok: true; data: T } | { ok: false; error: string };

// A verified numeric figure persisted on a run (research schema v7). Its tier is
// derived from the human-curated registry, never inferred by a model.
export type ResearchFigure = {
  id: string;
  run_id: string;
  source_id: string;
  quantity: string;
  value: number;
  unit: string | null;
  tier: string | null;
  supporting_quote: string | null;
  created_at: string;
};

export type MszConfidence = "verified" | "low_confidence";

// The composed sizing envelope stored on a candidate (see market-sizing.schema.md).
export type SizingEnvelope = {
  method: string;
  calculator: string;
  envelope: CalcEnvelope; // C1 shown-working; sourced inputs carry source_id + F/A label
  inputs_meta: Record<string, unknown>;
  run_id: string;
  overall_confidence: MszConfidence;
  confidence_basis: string;
};

export type MarketSizing = {
  id: string;
  opportunity_id: string;
  status: "pending_review" | "approved" | "rejected";
  calculator: string;
  run_id: string | null;
  confidence: MszConfidence;
  sizing: SizingEnvelope;
  reviewed_at: string | null;
  reviewer: string | null;
  review_note: string | null;
  owner_user_id: string | null;
  created_at: string;
};

// what the build form sends per input: a sourced figure (by quantity) or an
// analyst assumption (a bare value + optional note).
export type SourcedInput = { quantity: string };
export type AssumptionInput = { value: number; note?: string };
export type BuildInput = SourcedInput | AssumptionInput;

async function request<T>(path: string, init?: RequestInit): Promise<MszResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      return { ok: false, error: "malformed response from the market-sizing API" };
    }
    if (!res.ok) {
      const msg = (body as { error?: string })?.error || `HTTP ${res.status}`;
      return { ok: false, error: msg };
    }
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, error: "the market-sizing API is unreachable" };
  }
}

export const marketSizingApi = {
  listFigures(runId: string) {
    return request<{ figures: ResearchFigure[] }>(
      `/research/runs/${encodeURIComponent(runId)}/figures`,
    );
  },

  // Server-side extraction (model proposes, deterministic verification disposes).
  // Requires a configured provider; returns an honest error otherwise.
  extractFigures(runId: string) {
    return request<{ run_id: string; proposed: number; accepted: number; rejected: unknown[]; figures: ResearchFigure[] }>(
      `/research/runs/${encodeURIComponent(runId)}/extract-figures`,
      { method: "POST", body: "{}" },
    );
  },

  buildSizing(opportunityId: string, payload: {
    run_id: string;
    method: string;
    inputs: Record<string, BuildInput>;
  }) {
    return request<{ market_sizing: MarketSizing }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/market-sizing`,
      { method: "POST", body: JSON.stringify(payload) },
    );
  },

  listSizings(opportunityId?: string) {
    const qs = opportunityId ? `?opportunity_id=${encodeURIComponent(opportunityId)}` : "";
    return request<{ market_sizings: MarketSizing[] }>(`/market-sizing${qs}`);
  },

  getSizing(id: string) {
    return request<{ market_sizing: MarketSizing }>(`/market-sizing/${encodeURIComponent(id)}`);
  },

  reviewSizing(id: string, action: "approve" | "reject", note?: string) {
    return request<{ market_sizing: MarketSizing }>(
      `/market-sizing/${encodeURIComponent(id)}/review`,
      { method: "POST", body: JSON.stringify({ action, note }) },
    );
  },
};
