// Phase 6/7 — client for the runtime user-opportunity store
// (executive-ui/api/user_store.py; contract in
// shared/contracts/user-opportunities.schema.md). These are the ONLY write
// endpoints the frontend calls — the committed knowledge base stays
// read-only, and committed OPP- ids never match these UOPP- routes.
//
// No seed/demo fallback exists here on purpose: a failure is surfaced as an
// error, never replaced with fabricated data.

import type { UserMonitoringConfig, UserMonitoringEvent, UserMonitoringRunResult, UserOpportunity } from "../types";

const BASE = import.meta.env.VITE_EXECUTIVE_API_BASE_URL || "/executive-api";

export class UserOpportunityError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "content-type": "application/json", accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw new UserOpportunityError(String(data?.error ?? `HTTP ${res.status}`), res.status);
  }
  return data as T;
}

export interface UserOpportunityDraftFields {
  title?: string;
  product_definition?: string | null;
  problem_statement?: string | null;
  target_segment?: string | null;
  customer_description?: string | null;
  value_proposition?: string | null;
  assumptions?: string[];
  risks?: string[];
  unknowns?: string[];
  next_actions?: string[];
}

export const userOpportunitiesApi = {
  list: (includeArchived = false) =>
    request<{ user_opportunities: UserOpportunity[] }>(
      "GET", `/user-opportunities${includeArchived ? "?include_archived=1" : ""}`)
      .then((r) => r.user_opportunities),

  create: (payload: UserOpportunityDraftFields & {
    title: string;
    status?: "draft" | "saved";
    source_conversation_id?: string;
    created_from_analysis?: boolean;
  }) => request<UserOpportunity>("POST", "/user-opportunities", payload),

  get: (id: string) => request<UserOpportunity>("GET", `/user-opportunities/${id}`),

  update: (id: string, payload: UserOpportunityDraftFields & {
    status?: "draft" | "saved";
    version?: number;
  }) => request<UserOpportunity>("PATCH", `/user-opportunities/${id}`, payload),

  archive: (id: string) =>
    request<UserOpportunity>("POST", `/user-opportunities/${id}/archive`),

  restore: (id: string) =>
    request<UserOpportunity>("POST", `/user-opportunities/${id}/restore`),

  // deletion policy (documented in the contract): drafts delete permanently;
  // saved must be archived first; archived needs confirm=archived
  deleteDraft: (id: string) =>
    request<{ deleted: boolean; id: string }>("DELETE", `/user-opportunities/${id}`),
  deleteArchived: (id: string) =>
    request<{ deleted: boolean; id: string }>(
      "DELETE", `/user-opportunities/${id}?confirm=archived`),

  monitoringGet: (id: string) =>
    request<UserMonitoringConfig>("GET", `/user-opportunities/${id}/monitoring`),
  // only the fields the backend accepts on PUT (everything else — status,
  // last_run_at, failure counts — is server-owned)
  monitoringPut: (id: string, payload: {
    enabled?: boolean;
    cadence?: "manual" | "daily" | "weekly" | "monthly";
    topics?: string[];
    keywords?: string[];
    entities?: string[];
    source_categories?: string[];
    preferred_domains?: string[];
    excluded_domains?: string[];
    geographic_scope?: string | null;
    language?: string | null;
    notes?: string | null;
  }) => request<UserMonitoringConfig>("PUT", `/user-opportunities/${id}/monitoring`, payload),
  monitoringPause: (id: string) =>
    request<UserMonitoringConfig>("POST", `/user-opportunities/${id}/monitoring/pause`),
  monitoringResume: (id: string) =>
    request<UserMonitoringConfig>("POST", `/user-opportunities/${id}/monitoring/resume`),
  monitoringDelete: (id: string) =>
    request<{ deleted: boolean }>("DELETE", `/user-opportunities/${id}/monitoring`),
  // Phase R4a — one MANUAL monitoring run (no scheduler exists). The server
  // answers honestly: complete/partial with real events, or failed with the
  // reason recorded on the config.
  monitoringRun: (id: string) =>
    request<UserMonitoringRunResult>("POST", `/user-opportunities/${id}/monitoring/run`),
  monitoringEvents: (id: string) =>
    request<{ events: UserMonitoringEvent[] }>("GET", `/user-opportunities/${id}/monitoring/events`),
};
