import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import type { ChatBlock, Opportunity, OverviewPayload } from "./types";

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
  projects: Opportunity[]; // real opportunities presented as "projects"

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
}

const Ctx = createContext<AppState | null>(null);

let seq = 0;
const nextId = () => `m${++seq}`;

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [view, setView] = useState<View>("home");
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState<Record<string, Message[]>>({});
  const [drawerOppId, setDrawerOppId] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.body.setAttribute("data-theme", theme);
  }, [theme]);

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

  const send = useCallback(
    async (message: string, projectId?: string) => {
      const pid = projectId ?? activeProjectId ?? overview?.opportunities[0]?.id ?? "portfolio";
      if (!activeProjectId) setActiveProjectId(pid);
      setView("project");
      setActiveTab("chat");

      const userMsg: Message = { id: nextId(), role: "user", text: message };
      const pendingId = nextId();
      const pending: Message = { id: pendingId, role: "assistant", text: "", streaming: true, stages: [] };
      setConversations((c) => ({ ...c, [pid]: [...(c[pid] ?? []), userMsg, pending] }));

      const resp = await api.chat(message);

      // reveal progress stages one at a time for the long-running-task feel
      for (let i = 1; i <= resp.stages.length; i++) {
        await new Promise((r) => setTimeout(r, 260));
        setConversations((c) => ({
          ...c,
          [pid]: (c[pid] ?? []).map((m) =>
            m.id === pendingId ? { ...m, stages: resp.stages.slice(0, i) } : m,
          ),
        }));
      }
      await new Promise((r) => setTimeout(r, 200));
      setConversations((c) => ({
        ...c,
        [pid]: (c[pid] ?? []).map((m) =>
          m.id === pendingId
            ? { ...m, text: resp.text, blocks: resp.blocks, stages: resp.stages, streaming: false }
            : m,
        ),
      }));
    },
    [activeProjectId, overview],
  );

  const value: AppState = {
    theme, toggleTheme,
    loading, error, overview, projects,
    view, activeProjectId, activeTab, sidebarOpen,
    conversations, drawerOppId,
    goHome, goUpdates, openProject, setTab, setSidebarOpen, openDrawer, closeDrawer, send,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used within AppProvider");
  return v;
}
