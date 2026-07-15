import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import { copilotApi } from "./lib/copilotApi";
import { fromCopilotResult } from "./components/AssistantAnswer";
import type { ChatBlock, Citation, CopilotChatResult, Opportunity, OverviewPayload } from "./types";

export type View =
  | "home" | "updates" | "project" | "monitoring" | "knowledge" | "reports" | "settings" | "report";

// Phase 4 — the web-report route. The report view is the only URL-addressed
// view (/report/OPP-nnn) so a brief can be refreshed, bookmarked, and opened
// directly; everything else stays state-based exactly as before.
const REPORT_PATH_RE = /^\/report\/(OPP-\d{3})$/;
export function matchReportPath(pathname: string): string | null {
  const m = REPORT_PATH_RE.exec(pathname);
  return m ? m[1] : null;
}
export type Tab =
  | "chat" | "knowledge" | "interviews" | "reports" | "monitoring" | "files" | "sources" | "settings";

// Generic detail-drawer target — a lighter-weight sibling to the opportunity
// drawer (drawerOppId) for record types that aren't opportunities. Kept
// separate so the existing opportunity drawer is never touched.
export type DetailTargetType =
  | "evidence" | "assumption" | "monitoring_update" | "merchant_finding" | "prediction";
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
  // Phase 3 — "deterministic_demo" | "live_model"; absent/unknown renders no badge.
  runtimeMode?: "deterministic_demo" | "live_model";
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
  reportOppId: string | null;
  openReport: (id: string) => void;

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
  // Phase 3 — returns the raw result so the caller (Home.tsx) can tell
  // whether a genuine new-product analysis was started (a stub/project was
  // created and this resolves after navigating there) or not (nothing was
  // created/navigated; the caller renders the reply itself, e.g. inline).
  analyzeNew: (prompt: string) => Promise<CopilotChatResult>;
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
  // Phase 4 — direct navigation / refresh on /report/OPP-nnn lands straight
  // in the report view; any other path starts at home as before.
  const [reportOppId, setReportOppId] = useState<string | null>(
    () => matchReportPath(window.location.pathname),
  );
  const [view, setView] = useState<View>(
    () => (matchReportPath(window.location.pathname) ? "report" : "home"),
  );
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
  // Phase 4 — open the web report for one opportunity, with a real URL so
  // refresh/back/bookmark work. Invalid ids are ignored (never navigated).
  const openReport = useCallback((id: string) => {
    if (!/^OPP-\d{3}$/.test(id)) return;
    if (window.location.pathname !== `/report/${id}`) {
      window.history.pushState({ report: id }, "", `/report/${id}`);
    }
    setReportOppId(id);
    setView("report");
    setSidebarOpen(false);
  }, []);
  // Back/forward: re-derive the view from the URL. Leaving a report entry
  // returns to the Reports & Briefs list (the report's launch surface).
  useEffect(() => {
    const onPop = () => {
      const id = matchReportPath(window.location.pathname);
      if (id) {
        setReportOppId(id);
        setView("report");
      } else {
        setView((v) => (v === "report" ? "reports" : v));
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  // Navigating anywhere else clears a stale /report/... URL.
  useEffect(() => {
    if (view !== "report" && matchReportPath(window.location.pathname)) {
      window.history.replaceState({}, "", "/");
    }
  }, [view]);
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
    // copilot-backend is unreachable; say so honestly instead. Shared adapter
    // (AssistantAnswer.fromCopilotResult) so the wording/mapping can't drift
    // between the chat list and Home's inline quick-replies.
    const adapted = fromCopilotResult(result);
    setConversations((c) => ({
      ...c,
      [pid]: (c[pid] ?? []).map((m) => (m.id === pendingId ? {
        ...m, stages, streaming: false,
        text: adapted.text,
        citations: adapted.citations,
        copilotAssumptions: adapted.copilotAssumptions,
        unknowns: adapted.unknowns,
        copilotWarnings: adapted.copilotWarnings,
        recommendedNextActions: adapted.recommendedNextActions,
        copilotUnavailable: adapted.copilotUnavailable,
        runtimeMode: adapted.runtimeMode,
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
      // Phase 3 — store the (possibly new) conversation id whenever we didn't
      // have one yet, OR the stale one just got recovered — in every other
      // case (an ordinary follow-up) the mapping is left untouched, and no
      // other project's mapping is ever touched.
      if ((!existingConvId || result.staleConversationRecovered) && !result.unavailable && result.conversationId) {
        setCopilotConversationIds((m) => ({ ...m, [pid]: result.conversationId }));
      }
      await deliverCopilot(pid, message, result);
    },
    [activeProjectId, overview, copilotConversationIds, deliverCopilot],
  );

  const analyzeNew = useCallback(
    async (prompt: string): Promise<CopilotChatResult> => {
      // Always a brand-new copilot conversation (Phase 2I: "new chat gets a
      // new conversation_id" / "does not inherit prior product context").
      const result = await copilotApi.chat(prompt, null, {});

      // Phase 3 — a local project/opportunity stub is created ONLY when the
      // backend itself confirms this was a genuine new-product analysis.
      // Entering through the "New analysis" UI is not sufficient by itself —
      // a greeting, a monitoring question, etc. must not spawn a junk
      // sidebar entry. The caller (Home.tsx) renders the reply itself
      // (inline, no navigation) whenever this returns without having done so.
      if (result.answerType !== "new_opportunity_analysis") {
        return result;
      }

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
      return result;
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
    view, activeProjectId, activeTab, sidebarOpen, reportOppId, openReport,
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
