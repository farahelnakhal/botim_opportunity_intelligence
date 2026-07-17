// Analysis-workspace client (Phase R5, PR4-UI) — talks to executive-ui/api's
// /user-opportunities/{id}/workspace* routes
// (shared/contracts/workspace.schema.md). Same honest failure shape as
// researchApi: {ok:false, error} — the UI shows unavailable/empty states,
// never a fabricated analysis.

import type { WorkspaceDiff, WorkspaceVersion, WorkspaceVersionSummary } from "../types";

const BASE = import.meta.env.VITE_EXECUTIVE_API_BASE_URL || "/executive-api";

export type WorkspaceResult<T> = { ok: true; data: T } | { ok: false; error: string };

async function request<T>(path: string, init?: RequestInit): Promise<WorkspaceResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      return { ok: false, error: "malformed response from the workspace API" };
    }
    if (!res.ok) {
      const msg = (body as { error?: string })?.error || `HTTP ${res.status}`;
      return { ok: false, error: msg };
    }
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, error: "the workspace API is unreachable" };
  }
}

export const workspaceApi = {
  // latest complete version, or {workspace: null, note} when none exists
  get(oppId: string) {
    return request<{ workspace: WorkspaceVersion | null; note?: string }>(
      `/user-opportunities/${encodeURIComponent(oppId)}/workspace`,
    );
  },

  // runs the full chain server-side (KB context → research → extraction →
  // preliminary score); returns the finished version. This is the ONLY way
  // the chain runs from the UI — reading never triggers a build.
  refresh(oppId: string, question?: string) {
    return request<WorkspaceVersion>(
      `/user-opportunities/${encodeURIComponent(oppId)}/workspace/refresh`,
      { method: "POST", body: JSON.stringify(question ? { question } : {}) },
    );
  },

  versions(oppId: string) {
    return request<{ versions: WorkspaceVersionSummary[] }>(
      `/user-opportunities/${encodeURIComponent(oppId)}/workspace/versions`,
    );
  },

  // deterministic diff of the two newest complete versions (seed of R6)
  diff(oppId: string) {
    return request<{ diff: WorkspaceDiff | null; note?: string }>(
      `/user-opportunities/${encodeURIComponent(oppId)}/workspace/diff`,
    );
  },
};
