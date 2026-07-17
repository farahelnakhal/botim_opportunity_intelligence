import { useApp, type Tab } from "../store";
import { statusFromClassification, tagLabel } from "../lib/format";
import { copyText, downloadText, opportunityFilename, opportunityMarkdown } from "../lib/actions";
import ActionButton from "./ActionButton";
import Chat from "./Chat";
import {
  FilesPanel, InterviewsPanel, KnowledgePanel, MonitoringPanel, ReportsPanel, SettingsPanel, SourcesPanel,
} from "./panels";
import { UserMonitoringPanel, UserOpportunityDetails } from "./UserOpportunityPanel";
import UserDocumentsPanel from "./UserDocumentsPanel";
import WorkspacePanel from "./WorkspacePanel";

const TABS: { key: Tab; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "knowledge", label: "Knowledge" },
  { key: "interviews", label: "Interviews" },
  { key: "reports", label: "Reports & Briefs" },
  { key: "monitoring", label: "Monitoring" },
  { key: "files", label: "Files" },
  { key: "sources", label: "Sources" },
  { key: "settings", label: "Settings" },
];

// Phase 6 — a persisted user opportunity gets a focused workspace: its chat,
// an editable Details panel, and its monitoring configuration. The
// demo-corpus tabs (scorecard sources, interviews, …) would fabricate
// context a user draft does not have, so they are not shown for it.
const USER_TABS: { key: Tab; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "analysis", label: "Analysis" }, // Phase R5 PR4-UI — the preliminary workspace
  { key: "knowledge", label: "Details" },
  { key: "files", label: "Files" },       // Phase R7 — uploaded documents
  { key: "monitoring", label: "Monitoring" },
];

export default function ProjectWorkspace() {
  const { projects, generated, userProjects, userOpps, activeProjectId, activeTab, setTab,
          saveOpportunity, openReport } = useApp();
  const opp = [...generated, ...userProjects, ...projects].find((p) => p.id === activeProjectId)
    ?? userProjects[0] ?? projects[0];
  if (!opp) return null;

  const isUser = opp.source === "user";
  const userRecord = isUser ? userOpps.find((u) => u.id === opp.id) : undefined;
  const isUnsaved = !!opp.unsaved;

  const status = statusFromClassification(opp.classification);
  const statusLabel = isUser
    ? (userRecord?.status === "archived" ? "Archived" : userRecord?.status === "draft" ? "Draft" : "Saved")
    : isUnsaved ? "Unsaved"
    : status === "active" ? "Active" : status === "reject" ? "Archived" : "In review";

  const tabs = isUser ? USER_TABS : TABS;
  const effectiveTab = tabs.some((t) => t.key === activeTab) ? activeTab : "chat";

  return (
    <section className="view" id="view-project">
      <div className="project-header">
        <div className="ph-left">
          <div className="ph-title">{opp.name}</div>
          <div className={`status-pill ${status}`}>
            <span className={`status-dot ${status === "reject" ? "paused" : status}`} />
            {statusLabel}
          </div>
          <div className="market-badge" title="Market"><span>🇦🇪</span><span>UAE</span></div>
          {isUser
            ? <div className="ph-updated">Your opportunity · unvalidated</div>
            : opp.generated
              ? <div className="ph-updated">Unsaved analysis · not persisted</div>
              : <div className="ph-updated">{tagLabel(opp.classification)} · demo data</div>}
        </div>
        <div className="ph-right">
          {isUnsaved && (
            <ActionButton
              className="btn btn-primary" icon="check-circle" label="Save opportunity" doneLabel="Saved"
              title="Persist this analysis as your opportunity (survives refresh and restarts)"
              onAct={async () => {
                const created = await saveOpportunity(opp.id);
                if (!created) throw new Error("save failed");
              }}
            />
          )}
          {isUser && (
            <ActionButton className="btn" icon="external" label="Open report" doneLabel="Opened"
              onAct={() => openReport(opp.id)} />
          )}
          <ActionButton
            className="btn btn-sm" icon="external" label="Export" doneLabel="Saved"
            title="Download this analysis as a Markdown file"
            onAct={() => downloadText(opportunityFilename(opp), opportunityMarkdown(opp))}
          />
          <ActionButton
            className="btn" icon="share" label="Share" doneLabel="Copied"
            title="Copy a shareable text summary to the clipboard"
            onAct={() => copyText(opportunityMarkdown(opp))}
          />
        </div>
      </div>

      <nav className="project-tabs">
        {tabs.map((t) => (
          <button key={t.key} className={`ptab${effectiveTab === t.key ? " active" : ""}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>

      {effectiveTab === "chat" && <Chat projectId={opp.id} />}
      {isUser ? (
        <>
          {effectiveTab === "analysis" && <div className="tab-panel"><WorkspacePanel oppId={opp.id} /></div>}
          {effectiveTab === "knowledge" && <div className="tab-panel"><UserOpportunityDetails oppId={opp.id} /></div>}
          {effectiveTab === "files" && <div className="tab-panel"><UserDocumentsPanel oppId={opp.id} /></div>}
          {effectiveTab === "monitoring" && <div className="tab-panel"><UserMonitoringPanel oppId={opp.id} /></div>}
        </>
      ) : (
        <>
          {effectiveTab === "knowledge" && <div className="tab-panel"><KnowledgePanel /></div>}
          {effectiveTab === "interviews" && <div className="tab-panel"><InterviewsPanel opp={opp} /></div>}
          {effectiveTab === "reports" && <div className="tab-panel"><ReportsPanel /></div>}
          {effectiveTab === "monitoring" && <div className="tab-panel"><MonitoringPanel /></div>}
          {effectiveTab === "files" && <div className="tab-panel"><FilesPanel /></div>}
          {effectiveTab === "sources" && <div className="tab-panel"><SourcesPanel opp={opp} /></div>}
          {effectiveTab === "settings" && <div className="tab-panel"><SettingsPanel opp={opp} /></div>}
        </>
      )}
    </section>
  );
}
