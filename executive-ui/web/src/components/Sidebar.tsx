import { useApp } from "../store";
import Icon, { type IconName } from "./Icon";

const WORKSPACE_NAV: { key: string; label: string; icon: IconName; tab?: string }[] = [
  { key: "updates", label: "Updates", icon: "activity" },
  { key: "monitoring", label: "Monitoring", icon: "bell", tab: "monitoring" },
  { key: "reports", label: "Reports", icon: "file", tab: "reports" },
  { key: "library", label: "Knowledge Base", icon: "book", tab: "knowledge" },
  { key: "settings", label: "Settings", icon: "settings", tab: "settings" },
];

export default function Sidebar() {
  const {
    projects, generated, view, activeProjectId, theme, toggleTheme, sidebarOpen,
    goHome, goUpdates, openProject,
  } = useApp();

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
            className={`nav-item${view === "updates" && n.key === "updates" ? " active" : ""}`}
            onClick={() => {
              if (n.key === "updates") goUpdates();
              else openProject(activeProjectId ?? projects[0]?.id ?? "", n.tab as any);
            }}
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
