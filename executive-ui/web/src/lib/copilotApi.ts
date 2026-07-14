// Client for copilot-backend's conversation contract
// (shared/contracts/conversation-api.schema.md). This is the ONLY client that
// talks to copilot-backend — conversational requests (chat, follow-ups,
// new-product analysis, Merchant Voice questions) belong here, never in
// lib/api.ts (which stays the read-only executive-ui/api dashboard client).
//
// On any failure (network error, non-2xx, malformed body) this returns an
// honest `unavailable: true` result — it never falls back to generate.py,
// the deterministic router, or seed data, and never fabricates an answer.

import type { Citation, CopilotChatResult, CopilotConfidence } from "../types";

const BASE = import.meta.env.VITE_COPILOT_API_BASE_URL || "/copilot-api";
const CHAT_TIMEOUT_MS = 45000;

export interface CopilotContext {
  opportunity_id?: string;
  segment_id?: string;
}

function unavailableResult(conversationId: string, reason: string): CopilotChatResult {
  return {
    conversationId,
    messageId: null,
    answerMarkdown: "",
    answerType: "unavailable",
    confidence: null,
    citations: [],
    assumptions: [],
    unknowns: [],
    recommendedNextActions: [],
    warnings: [],
    unavailable: true,
    unavailableReason: reason,
  };
}

function isCitation(x: unknown): x is Citation {
  return !!x && typeof x === "object" && typeof (x as Citation).id === "string";
}

function toResult(data: Record<string, unknown>): CopilotChatResult {
  const citations = Array.isArray(data.citations) ? data.citations.filter(isCitation) : [];
  const conf = data.confidence as CopilotConfidence | undefined;
  return {
    conversationId: String(data.conversation_id ?? ""),
    messageId: (data.message_id as string) ?? null,
    answerMarkdown: String(data.answer_markdown ?? ""),
    answerType: String(data.answer_type ?? "analysis"),
    confidence: conf ? { level: conf.level, basis: conf.basis } : null,
    citations,
    assumptions: Array.isArray(data.assumptions) ? (data.assumptions as string[]) : [],
    unknowns: Array.isArray(data.unknowns) ? (data.unknowns as string[]) : [],
    recommendedNextActions: Array.isArray(data.recommended_next_actions)
      ? (data.recommended_next_actions as string[])
      : [],
    warnings: Array.isArray(data.warnings) ? (data.warnings as string[]) : [],
    unavailable: false,
  };
}

async function post(path: string, body: unknown, timeoutMs: number) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    let data: Record<string, unknown> | null = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok || !data) {
      const err = (data?.error as { message?: string } | undefined) ?? undefined;
      return { ok: false as const, reason: err?.message || `HTTP ${res.status}` };
    }
    if ("error" in data) {
      const err = data.error as { message?: string };
      return { ok: false as const, reason: err?.message || "copilot returned an error" };
    }
    return { ok: true as const, data };
  } catch (e) {
    return { ok: false as const, reason: e instanceof Error ? e.message : String(e) };
  } finally {
    clearTimeout(timer);
  }
}

export const copilotApi = {
  async chat(
    message: string,
    conversationId: string | null,
    context?: CopilotContext,
  ): Promise<CopilotChatResult> {
    const r = await post(
      "/chat",
      { conversation_id: conversationId, message, context: context ?? {} },
      CHAT_TIMEOUT_MS,
    );
    if (!r.ok) return unavailableResult(conversationId ?? "", r.reason);
    return toResult(r.data);
  },

  async deleteConversation(conversationId: string): Promise<boolean> {
    try {
      const res = await fetch(`${BASE}/conversations/${encodeURIComponent(conversationId)}`, {
        method: "DELETE",
      });
      return res.ok;
    } catch {
      return false;
    }
  },
};
