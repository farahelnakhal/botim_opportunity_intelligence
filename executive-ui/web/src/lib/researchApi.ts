// Research-platform client (Phases R1-R3) — talks to executive-ui/api's
// /research/* routes (shared/contracts/research.schema.md). Honest failure
// shape everywhere: {ok:false, error} — the UI shows unavailable/empty
// states, never fabricated runs or sources.

import type {
  ResearchCandidate,
  ResearchRun,
  ResearchRunSummary,
} from "../types";

const BASE = import.meta.env.VITE_EXECUTIVE_API_BASE_URL || "/executive-api";

export type ResearchResult<T> = { ok: true; data: T } | { ok: false; error: string };

async function request<T>(path: string, init?: RequestInit): Promise<ResearchResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      return { ok: false, error: "malformed response from the research API" };
    }
    if (!res.ok) {
      const msg = (body as { error?: string })?.error || `HTTP ${res.status}`;
      return { ok: false, error: msg };
    }
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, error: "the research API is unreachable" };
  }
}

export const researchApi = {
  listRuns(filters?: { opportunityRef?: string; status?: string }) {
    const params = new URLSearchParams();
    if (filters?.opportunityRef) params.set("opportunity_ref", filters.opportunityRef);
    if (filters?.status) params.set("status", filters.status);
    const qs = params.toString();
    return request<{ runs: ResearchRunSummary[] }>(`/research/runs${qs ? `?${qs}` : ""}`);
  },

  getRun(runId: string) {
    return request<ResearchRun>(`/research/runs/${encodeURIComponent(runId)}`);
  },

  createRun(payload: {
    title: string;
    profile?: string;
    context?: { market?: string; segment?: string; product?: string };
    queries?: string[];
    objective?: string;
    opportunity_ref?: string;
  }) {
    return request<ResearchRun>("/research/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  executeRun(runId: string) {
    return request<ResearchRun>(`/research/runs/${encodeURIComponent(runId)}/execute`, {
      method: "POST",
      body: "{}",
    });
  },

  // Phase R4b — re-check the run's sources; append-only outcomes, nothing
  // auto-applied. Returns the refreshed run detail with revalidation_summary.
  revalidateRun(runId: string) {
    return request<ResearchRun>(`/research/runs/${encodeURIComponent(runId)}/revalidate`, {
      method: "POST",
      body: "{}",
    });
  },

  addCandidate(runId: string, payload: { claim: string; source_ids: string[]; contradicts?: string }) {
    return request<ResearchCandidate>(`/research/runs/${encodeURIComponent(runId)}/candidates`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  reviewCandidate(candidateId: string, action: "approve" | "reject", note?: string) {
    return request<ResearchCandidate>(
      `/research/candidates/${encodeURIComponent(candidateId)}/review`,
      { method: "POST", body: JSON.stringify({ action, note }) },
    );
  },

  listCandidates(filters?: { status?: string; opportunityRef?: string }) {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.opportunityRef) params.set("opportunity_ref", filters.opportunityRef);
    const qs = params.toString();
    return request<{ candidates: ResearchCandidate[] }>(
      `/research/candidates${qs ? `?${qs}` : ""}`,
    );
  },
};
