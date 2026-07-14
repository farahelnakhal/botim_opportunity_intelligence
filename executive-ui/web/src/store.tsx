import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import { copilotApi } from "./lib/copilotApi";
import type { ChatBlock, Citation, CopilotChatResult, Opportunity, OverviewPayload } from "./types";

export type View = "home" | "updates" | "project" | "monitoring" | "knowledge" | "reports" | "settings";
export type Tab =
  | "chat" | "knowledge" | "interviews" | "reports" | "monitoring" | "files" | "sources" | "settings";

// Generic detail-drawer target — a lighter-weight sibling to the opportunity
// drawer (drawerOppId) for record types that aren't opportunities. Kept
// separate so the existing opportunity drawer is never touched.
export type DetailTargetType = "evidence" | "assumption" | "monitoring_update" | "merchant_finding";
export interface DetailTarget {
  type: DetailTargetType;
  id: string;
  // merchant_finding detail is rendered entirely from the citation object
  // itself (Phase 2H) — no extra backend lookup needed or available.
  payload?: Citation;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  blocks?: ChatBlock[];
  stages?: string[];
  streaming?: boolean;
  // Populated for copilot-backend-answered assistant turns (Phase 2C/2K).
  citations?: Citation[];
  copilotAssumptions?: string[];
  unknowns?: string[];
  copilotWarnings?: string[];
  recommendedNextActions?: string[];
  copilotUnavailable?: boolean;
}

export interface AppState {
  theme: "light" | "dark";
  toggleTheme: () => void;

  loading: boolean;
  error: string | null;
  overview: OverviewPayload | null;
  projects: Opportunity[]; // committed KB opportunities
  generated: Opportunity[]; // on-demand AI analyses created this session

  view: View;
  activeProjectId: string | null;
  activeTab: Tab;
  sidebarOpen: boolean;

  conversations: Record<string, Message[]>;

  drawerOppId: string | null;
  detailTarget: DetailTarget | null;

  goHome: () => void;
  goUpdates: () => void;
  goMonitoring: () => void;
  goKnowledge: () => void;
  goReports: () => void;
  goSettings: () => void;
  openProject: (id: string, tab?: Tab) => void;
  setTab: (tab: Tab) => void;
  setSidebarOpen: (open: boolean) => void;
  openDrawer: (id: string) => void;
  closeDrawer: () => void;
  openDetail: (type: DetailTargetType, id: string, payload?: Citation) => void;
  closeDetail: () => void;
  send: (message: string, projectId?: string) => Promise<void>;
  analyzeNew: (prompt: string) => Promise<void>; // start a fresh analysis of ANY opportunity
  clearConversation: (projectId: string) => Promise<void>; // Phase 2I — end the copilot conversation for this chat
}

const Ctx = createContext<AppState | null>(null);

let seq = 0;
const nextId = () => `m${++seq}`;

// --- lightweight persistence so conversations & analyses survive a reload ---
const LS = {
  conv: "botim.conversations", gen: "botim.generated", theme: "botim.theme",
  copilotConv: "botim.copilotConversationIds",
};
function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / disabled storage — non-fatal */
  }
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">(() => load<"light" | "dark">(LS.theme, "light"));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [view, setView] = useState<View>("home");
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState<Record<string, Message[]>>(() => load(LS.conv, {}));
  const [drawerOppId, setDrawerOppId] = useState<string | null>(null);
  const [detailTarget, setDetailTarget] = useState<DetailTarget | null>(null);
  const [generated, setGenerated] = useState<Opportunity[]>(() => load<Opportunity[]>(LS.gen, []));
  // Phase 2I — the copilot conversation id backing each chat (project id ->
  // conv_… ). A brand-new chat has none yet; the first send() creates one.
  // Switching projects never reuses another project's conversation id.
  const [copilotConversationIds, setCopilotConversationIds] =
    useState<Record<string, string>>(() => load(LS.copilotConv, {}));

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
    save(LS.theme, theme);
  }, [theme]);

  useEffect(() => save(LS.conv, conversations), [conversations]);
  useEffect(() => save(LS.gen, generated), [generated]);
  useEffect(() => save(LS.copilotConv, copilotConversationIds), [copilotConversationIds]);

  useEffect(() => {
    let cancel = false;
    api
      .overview()
      .then((ov) => {
        if (cancel) return;
        setOverview(ov);
        setLoading(false);
      })
      .catch((e) => {
        if (cancel) return;
        setError(String(e));
        setLoading(false);
      });
    return () => {
      cancel = true;
    };
  }, []);

  const projects = useMemo(
    () => (overview ? [...overview.opportunities, ...overview.archived] : []),
    [overview],
  );

  const toggleTheme = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);
  const goHome = useCallback(() => {
    setView("home");
    setSidebarOpen(false);
  }, []);
  const goUpdates = useCallback(() => {
    setView("updates");
    setSidebarOpen(false);
  }, []);
  // Global, portfolio-wide destinations. These deliberately do NOT touch
  // activeProjectId/activeTab, so the current chat/project is preserved and
  // restored exactly as it was when the user navigates back to it.
  const goMonitoring = useCallback(() => {
    setView("monitoring");
    setSidebarOpen(false);
  }, []);
  const goKnowledge = useCallback(() => {
    setView("knowledge");
    setSidebarOpen(false);
  }, []);
  const goReports = useCallback(() => {
    setView("reports");
    setSidebarOpen(false);
  }, []);
  const goSettings = useCallback(() => {
    setView("settings");
    setSidebarOpen(false);
  }, []);
  const openProject = useCallback((id: string, tab: Tab = "chat") => {
    setActiveProjectId(id);
    setActiveTab(tab);
    setView("project");
    setSidebarOpen(false);
  }, []);
  const setTab = useCallback((tab: Tab) => setActiveTab(tab), []);
  const openDrawer = useCallback((id: string) => setDrawerOppId(id), []);
  const closeDrawer = useCallback(() => setDrawerOppId(null), []);
  const openDetail = useCallback(
    (type: DetailTargetType, id: string, payload?: Citation) => setDetailTarget({ type, id, payload }),
    [],
  );
  const closeDetail = useCallback(() => setDetailTarget(null), []);

  // Shared: append the user turn + a pending assistant turn, reveal progress
  // stages one at a time, then land the final copilot-backend response.
  // Phase 2 adapter (2C): one clear place that turns a CopilotChatResult into
  // the Message shape Chat.tsx renders — never spread across components.
  const deliverCopilot = useCallback(async (pid: string, userText: string, result: CopilotChatResult) => {
    const userMsg: Message = { id: nextId(), role: "user", text: userText };
    const stages = result.unavailable
      ? ["Contacting the grounded copilot", "Unavailable"]
      : ["Understanding the question", "Retrieving grounded repository context", "Preparing the answer", "Finished"];
    const pendingId = nextId();
    const pending: Message = { id: pendingId, role: "assistant", text: "", streaming: true, stages: [] };
    setConversations((c) => ({ ...c, [pid]: [...(c[pid] ?? []), userMsg, pending] }));
    for (let i = 1; i <= stages.length; i++) {
      await new Promise((r) => setTimeout(r, 180));
      setConversations((c) => ({
        ...c,
        [pid]: (c[pid] ?? []).map((m) => (m.id === pendingId ? { ...m, stages: stages.slice(0, i) } : m)),
      }));
    }
    // Phase 2L/2J — never silently substitute a router/generate.py answer when
    // copilot-backend is unreachable; say so honestly instead.
    const text = result.unavailable
      ? "Grounded analysis is temporarily unavailable right now (the copilot backend could not be reached). "
        + "No repository-grounded answer was generated for this message — please try again shortly."
      : result.answerMarkdown;
    setConversations((c) => ({
      ...c,
      [pid]: (c[pid] ?? []).map((m) => (m.id === pendingId ? {
        ...m, text, stages, streaming: false,
        citations: result.citations,
        copilotAssumptions: result.assumptions,
        unknowns: result.unknowns,
        copilotWarnings: result.warnings,
        recommendedNextActions: result.recommendedNextActions,
        copilotUnavailable: result.unavailable,
      } : m)),
    }));
  }, []);

  const send = useCallback(
    async (message: string, projectId?: string) => {
      const pid = projectId ?? activeProjectId ?? overview?.opportunities[0]?.id ?? "portfolio";
      if (!activeProjectId) setActiveProjectId(pid);
      setView("project");
      setActiveTab("chat");
      const existingConvId = copilotConversationIds[pid] ?? null;
      // A committed KB opportunity is passed as selected context so follow-ups
      // resolve correctly even without an explicit OPP- id in the message text
      // (Phase 2D/2G) — a copilot-originated topic (or the shared "portfolio"
      // chat) carries no such context, letting the first message start fresh.
      const isCommittedOpportunity = !!overview
        && (overview.opportunities.some((o) => o.id === pid) || overview.archived.some((o) => o.id === pid));
      const context = isCommittedOpportunity ? { opportunity_id: pid } : undefined;
      const result = await copilotApi.chat(message, existingConvId, context);
      if (!existingConvId && !result.unavailable && result.conversationId) {
        setCopilotConversationIds((m) => ({ ...m, [pid]: result.conversationId }));
      }
      await deliverCopilot(pid, message, result);
    },
    [activeProjectId, overview, copilotConversationIds, deliverCopilot],
  );

  const analyzeNew = useCallback(
    async (prompt: string) => {
      // Always a brand-new copilot conversation (Phase 2I: "new chat gets a
      // new conversation_id" / "does not inherit prior product context").
      const result = await copilotApi.chat(prompt, null, {});
      const pid = result.conversationId || `local-${nextId()}`;
      const title = prompt.trim().replace(/\.$/, "").slice(0, 80) || "New analysis";
      // No score is ever fabricated for a new idea — copilot-backend never
      // computes one (Phase 2E: no valid scorecard inputs exist yet). This
      // stub only carries enough shape to reuse the existing project-workspace
      // UI (sidebar entry, header, drawer) unchanged; the real content is the
      // grounded conversation itself (citations/assumptions/unknowns/actions).
      const stub: Opportunity = {
        id: pid, name: title.charAt(0).toUpperCase() + title.slice(1),
        raw_score: null, raw_max: 85, composite: null,
        classification: "unscored", classification_label: "Unscored",
        confidence: "—", assumption_count: 0, factors: [], critical_flags: [],
        segment: "—", jtbd: "—", hypothesis: "—",
        strongest_evidence: [], contradictory_evidence: "—", rejection_conditions: "—",
        validation_plan: "—", score_history: [],
        latest_change: "Started via the grounded product-discovery copilot", latest_alert: "—",
        next_action: result.recommendedNextActions[0] || "—",
        profile_path: "(generated — not committed to the knowledge base)",
        is_archived: false, impact_history: [], brief_envelope: null,
        generated: true, engine: "copilot",
      };
      setGenerated((g) => (g.some((x) => x.id === pid) ? g : [stub, ...g]));
      if (!result.unavailable && result.conversationId) {
        setCopilotConversationIds((m) => ({ ...m, [pid]: result.conversationId }));
      }
      setActiveProjectId(pid);
      setActiveTab("chat");
      setView("project");
      setSidebarOpen(false);
      await deliverCopilot(pid, prompt, result);
    },
    [deliverCopilot],
  );

  const clearConversation = useCallback(
    async (projectId: string) => {
      const cid = copilotConversationIds[projectId];
      if (cid) await copilotApi.deleteConversation(cid);
      setCopilotConversationIds((m) => {
        const next = { ...m };
        delete next[projectId];
        return next;
      });
      setConversations((c) => {
        const next = { ...c };
        delete next[projectId];
        return next;
      });
    },
    [copilotConversationIds],
  );

  const value: AppState = {
    theme, toggleTheme,
    loading, error, overview, projects, generated,
    view, activeProjectId, activeTab, sidebarOpen,
    conversations, drawerOppId, detailTarget,
    goHome, goUpdates, goMonitoring, goKnowledge, goReports, goSettings,
    openProject, setTab, setSidebarOpen, openDrawer, closeDrawer, openDetail, closeDetail,
    send, analyzeNew, clearConversation,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used within AppProvider");
  return v;
}
