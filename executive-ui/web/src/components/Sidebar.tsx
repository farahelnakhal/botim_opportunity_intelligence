import { useState } from "react";
import { useApp, type View } from "../store";
import Icon, { type IconName } from "./Icon";

// Global, portfolio-wide destinations — independent of whatever chat/project
// is currently open. Each maps straight to a top-level `View`, not a project tab.
const WORKSPACE_NAV: { key: string; label: string; icon: IconName; view: View }[] = [
  { key: "updates", label: "Updates", icon: "activity", view: "updates" },
  { key: "monitoring", label: "Monitoring", icon: "bell", view: "monitoring" },
  { key: "reports", label: "Reports & Briefs", icon: "file", view: "reports" },
  { key: "library", label: "Knowledge Base", icon: "book", view: "knowledge" },
  { key: "settings", label: "Settings", icon: "settings", view: "settings" },
];

export default function Sidebar() {
  const {
    projects, generated, userProjects, appMode, view, activeProjectId, theme, toggleTheme,
    sidebarOpen, goHome, goUpdates, goMonitoring, goKnowledge, goReports, goSettings, openProject,
  } = useApp();
  const [showDemo, setShowDemo] = useState(true);

  const GLOBAL_NAV_ACTIONS: Record<View, (() => void) | undefined> = {
    home: undefined,
    project: undefined,
    report: undefined, // Phase 4 — opened via openReport/URL, never from the nav
    updates: goUpdates,
    monitoring: goMonitoring,
    knowledge: goKnowledge,
    reports: goReports,
    settings: goSettings,
  };

  const navItem = (p: { id: string; name: string }, icon: IconName, title?: string) => (
    <button
      key={p.id}
      className={`nav-item${view === "project" && activeProjectId === p.id ? " active" : ""}`}
      onClick={() => openProject(p.id)}
      title={title ?? p.name}
    >
      <Icon name={icon} />
      {p.name}
    </button>
  );

  return (
    <aside className={`sidebar${sidebarOpen ? " open" : ""}`} id="sidebar">
      <div className="brand">
        <div className="brand-mark">B</div>
        <div>
          <div className="brand-name">BOTIM</div>
          <div className="brand-sub">Opportunity Intelligence</div>
        </div>
      </div>
      {/* Phase 5 — a visible badge whenever the backend serves demo data */}
      {appMode === "demo" && (
        <div className="demo-data-badge" data-testid="demo-data-badge">
          <Icon name="alert" size={12} /> Demo data
        </div>
      )}

      <button className="new-project-btn" onClick={goHome}>
        <Icon name="plus" size={16} /> New analysis
      </button>

      {/* Phase 6 — persisted user opportunities (real records, every mode) */}
      {userProjects.length > 0 && (
        <>
          <div className="nav-section-label">Your opportunities</div>
          <div className="nav-list">
            {userProjects.map((p) => navItem(p, "folder", `${p.name} — ${p.classification_label}`))}
          </div>
        </>
      )}

      {/* Unsaved analyses (browser-local until "Save opportunity") */}
      {generated.length > 0 && (
        <>
          <div className="nav-section-label">Unsaved analyses</div>
          <div className="nav-list">
            {generated.map((p) => navItem(p, "star", `${p.name} — unsaved analysis`))}
          </div>
        </>
      )}

      {/* Phase 5 — the committed corpus appears only when the backend serves
          it (demo/test mode) and is labelled, collapsible, never mixed in */}
      {projects.length > 0 && (
        <>
          <button
            type="button"
            className="nav-section-label nav-section-toggle"
            onClick={() => setShowDemo((v) => !v)}
            aria-expanded={showDemo}
          >
            Demo opportunities {showDemo ? "▾" : "▸"}
          </button>
          {showDemo && (
            <div className="nav-list" data-testid="demo-opportunities">
              {projects.map((p) => navItem(p, "folder", `${p.name} — demo data`))}
            </div>
          )}
        </>
      )}

      {userProjects.length === 0 && generated.length === 0 && projects.length === 0 && (
        <div className="sidebar-empty-note" data-testid="sidebar-empty-invite">
          No opportunities yet. Start with <b>New analysis</b> to define your first one.
        </div>
      )}

      <div className="nav-section-label">Workspace</div>
      <div className="nav-list">
        {WORKSPACE_NAV.map((n) => (
          <button
            key={n.key}
            className={`nav-item${view === n.view ? " active" : ""}`}
            onClick={GLOBAL_NAV_ACTIONS[n.view]}
          >
            <Icon name={n.icon} />
            {n.label}
          </button>
        ))}
      </div>

      <div className="sidebar-spacer" />

      <div className="sidebar-bottom">
        <div className="theme-toggle">
          <span>Dark mode</span>
          <button className={`switch${theme === "dark" ? " on" : ""}`} onClick={toggleTheme} aria-label="Toggle dark mode" />
        </div>
        {/* Phase 5 — no invented logged-in identity. Demo mode keeps the
            labelled demo persona; every other mode shows a neutral row. */}
        <div className="profile-row">
          <div className="avatar">{appMode === "demo" ? "SA" : "•"}</div>
          <div className="profile-meta">
            {appMode === "demo" ? (
              <>
                <div className="profile-name">Strategy Lead</div>
                <div className="profile-role">Demo persona</div>
              </>
            ) : (
              <>
                <div className="profile-name">This workspace</div>
                <div className="profile-role">No account signed in</div>
              </>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
