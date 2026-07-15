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
    projects, generated, view, activeProjectId, theme, toggleTheme, sidebarOpen,
    goHome, goUpdates, goMonitoring, goKnowledge, goReports, goSettings, openProject,
  } = useApp();

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

  return (
    <aside className={`sidebar${sidebarOpen ? " open" : ""}`} id="sidebar">
      <div className="brand">
        <div className="brand-mark">B</div>
        <div>
          <div className="brand-name">BOTIM</div>
          <div className="brand-sub">Opportunity Intelligence</div>
        </div>
      </div>

      <button className="new-project-btn" onClick={goHome}>
        <Icon name="plus" size={16} /> New analysis
      </button>

      {generated.length > 0 && (
        <>
          <div className="nav-section-label">Your analyses</div>
          <div className="nav-list">
            {generated.map((p) => (
              <button
                key={p.id}
                className={`nav-item${view === "project" && activeProjectId === p.id ? " active" : ""}`}
                onClick={() => openProject(p.id)}
                title={`${p.name} — AI-generated, unvalidated`}
              >
                <Icon name="star" />
                {p.name}
              </button>
            ))}
          </div>
        </>
      )}

      <div className="nav-section-label">Opportunities</div>
      <div className="nav-list">
        {projects.map((p) => (
          <button
            key={p.id}
            className={`nav-item${view === "project" && activeProjectId === p.id ? " active" : ""}`}
            onClick={() => openProject(p.id)}
            title={p.name}
          >
            <Icon name="folder" />
            {p.name}
          </button>
        ))}
      </div>

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
        <div className="profile-row">
          <div className="avatar">SA</div>
          <div className="profile-meta">
            <div className="profile-name">Strategy Lead</div>
            <div className="profile-role">BOTIM Product Discovery</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
