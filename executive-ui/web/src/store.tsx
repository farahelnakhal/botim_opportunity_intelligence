import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import type { ChatBlock, ChatResponse, Opportunity, OverviewPayload } from "./types";

export type View = "home" | "updates" | "project";
export type Tab =
  | "chat" | "knowledge" | "interviews" | "reports" | "monitoring" | "files" | "sources" | "settings";

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  blocks?: ChatBlock[];
  stages?: string[];
  streaming?: boolean;
}

interface AppState {
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

  goHome: () => void;
  goUpdates: () => void;
  openProject: (id: string, tab?: Tab) => void;
  setTab: (tab: Tab) => void;
  setSidebarOpen: (open: boolean) => void;
  openDrawer: (id: string) => void;
  closeDrawer: () => void;
  send: (message: string, projectId?: string) => Promise<void>;
  analyzeNew: (prompt: string) => Promise<void>; // start a fresh analysis of ANY opportunity
}

const Ctx = createContext<AppState | null>(null);

let seq = 0;
const nextId = () => `m${++seq}`;

// --- lightweight persistence so conversations & analyses survive a reload ---
const LS = { conv: "botim.conversations", gen: "botim.generated", theme: "botim.theme" };
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
  const [generated, setGenerated] = useState<Opportunity[]>(() => load<Opportunity[]>(LS.gen, []));

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
    save(LS.theme, theme);
  }, [theme]);

  useEffect(() => save(LS.conv, conversations), [conversations]);
  useEffect(() => save(LS.gen, generated), [generated]);

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
  const openProject = useCallback((id: string, tab: Tab = "chat") => {
    setActiveProjectId(id);
    setActiveTab(tab);
    setView("project");
    setSidebarOpen(false);
  }, []);
  const setTab = useCallback((tab: Tab) => setActiveTab(tab), []);
  const openDrawer = useCallback((id: string) => setDrawerOppId(id), []);
  const closeDrawer = useCallback(() => setDrawerOppId(null), []);

  // Shared: append the user turn + a pending assistant turn, reveal progress
  // stages one at a time, then land the final response.
  const deliver = useCallback(async (pid: string, userText: string, resp: ChatResponse) => {
    const userMsg: Message = { id: nextId(), role: "user", text: userText };
    const pendingId = nextId();
    const pending: Message = { id: pendingId, role: "assistant", text: "", streaming: true, stages: [] };
    setConversations((c) => ({ ...c, [pid]: [...(c[pid] ?? []), userMsg, pending] }));
    for (let i = 1; i <= resp.stages.length; i++) {
      await new Promise((r) => setTimeout(r, 240));
      setConversations((c) => ({
        ...c,
        [pid]: (c[pid] ?? []).map((m) => (m.id === pendingId ? { ...m, stages: resp.stages.slice(0, i) } : m)),
      }));
    }
    await new Promise((r) => setTimeout(r, 200));
    setConversations((c) => ({
      ...c,
      [pid]: (c[pid] ?? []).map((m) =>
        m.id === pendingId ? { ...m, text: resp.text, blocks: resp.blocks, stages: resp.stages, streaming: false } : m),
    }));
  }, []);

  const isGenerated = useCallback((id: string | null) => !!id && generated.some((g) => g.id === id), [generated]);

  const send = useCallback(
    async (message: string, projectId?: string) => {
      const pid = projectId ?? activeProjectId ?? overview?.opportunities[0]?.id ?? "portfolio";
      if (!activeProjectId) setActiveProjectId(pid);
      setView("project");
      setActiveTab("chat");
      // Follow-ups inside a generated analysis keep analysing that topic in context;
      // follow-ups inside a committed opportunity use the read-only router.
      if (isGenerated(pid)) {
        const topic = generated.find((g) => g.id === pid)?.name ?? "";
        const history = (conversations[pid] ?? [])
          .filter((m) => m.text)
          .map((m) => ({ role: m.role, content: m.text }));
        const resp = await api.analyze(`${topic}. Follow-up: ${message}`, history);
        if (resp.generated_opportunity) {
          const updated = { ...resp.generated_opportunity, id: pid, name: topic };
          setGenerated((g) => g.map((x) => (x.id === pid ? updated : x)));
          resp.blocks = resp.blocks.map((b) => (b.type === "opportunity" || b.type === "scorecard") ? { ...b, opportunity: updated } : b);
        }
        await deliver(pid, message, resp);
        return;
      }
      await deliver(pid, message, await api.chat(message));
    },
    [activeProjectId, overview, generated, isGenerated, deliver, conversations],
  );

  const analyzeNew = useCallback(
    async (prompt: string) => {
      const resp = await api.analyze(prompt);
      const opp = resp.generated_opportunity;
      const pid = opp?.id ?? `GEN-${Date.now()}`;
      if (opp) setGenerated((g) => (g.some((x) => x.id === opp.id) ? g : [opp, ...g]));
      setActiveProjectId(pid);
      setActiveTab("chat");
      setView("project");
      setSidebarOpen(false);
      await deliver(pid, prompt, resp);
    },
    [deliver],
  );

  const value: AppState = {
    theme, toggleTheme,
    loading, error, overview, projects, generated,
    view, activeProjectId, activeTab, sidebarOpen,
    conversations, drawerOppId,
    goHome, goUpdates, openProject, setTab, setSidebarOpen, openDrawer, closeDrawer, send, analyzeNew,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used within AppProvider");
  return v;
}
