import { useApp, type Tab } from "../store";
import { statusFromClassification, tagLabel } from "../lib/format";
import Icon from "./Icon";
import Chat from "./Chat";
import {
  FilesPanel, InterviewsPanel, KnowledgePanel, MonitoringPanel, ReportsPanel, SettingsPanel, SourcesPanel,
} from "./panels";

const TABS: { key: Tab; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "knowledge", label: "Knowledge" },
  { key: "interviews", label: "Experiments" },
  { key: "reports", label: "Reports" },
  { key: "monitoring", label: "Monitoring" },
  { key: "files", label: "Files" },
  { key: "sources", label: "Sources" },
  { key: "settings", label: "Settings" },
];

export default function ProjectWorkspace() {
  const { projects, activeProjectId, activeTab, setTab } = useApp();
  const opp = projects.find((p) => p.id === activeProjectId) ?? projects[0];
  if (!opp) return null;

  const status = statusFromClassification(opp.classification);
  const statusLabel = status === "active" ? "Active" : status === "reject" ? "Archived" : "In review";

  return (
    <section className="view" id="view-project">
      <div className="project-header">
        <div className="ph-left">
          <div className="ph-title">{opp.name}</div>
          <div className={`status-pill ${status}`}>
            <span className={`status-dot ${status === "reject" ? "paused" : status}`} />
            {statusLabel}
          </div>
          <div className="market-badge" title="Classification">
            <span>{opp.id}</span><span>·</span><span>{tagLabel(opp.classification)}</span>
          </div>
        </div>
        <div className="ph-right">
          <button className="btn"><Icon name="share" size={14} /> Share</button>
        </div>
      </div>

      <nav className="project-tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`ptab${activeTab === t.key ? " active" : ""}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>

      {activeTab === "chat" && <Chat projectId={opp.id} />}
      {activeTab === "knowledge" && <div className="tab-panel"><KnowledgePanel /></div>}
      {activeTab === "interviews" && <div className="tab-panel"><InterviewsPanel /></div>}
      {activeTab === "reports" && <div className="tab-panel"><ReportsPanel /></div>}
      {activeTab === "monitoring" && <div className="tab-panel"><MonitoringPanel /></div>}
      {activeTab === "files" && <div className="tab-panel"><FilesPanel /></div>}
      {activeTab === "sources" && <div className="tab-panel"><SourcesPanel opp={opp} /></div>}
      {activeTab === "settings" && <div className="tab-panel"><SettingsPanel opp={opp} /></div>}
    </section>
  );
}
