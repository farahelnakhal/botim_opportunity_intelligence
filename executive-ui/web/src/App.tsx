import { useApp } from "./store";
import { isLive } from "./lib/api";
import Sidebar from "./components/Sidebar";
import Home from "./components/Home";
import Updates from "./components/Updates";
import ProjectWorkspace from "./components/ProjectWorkspace";
import Drawer from "./components/Drawer";
import DetailDrawer from "./components/DetailDrawer";
import Icon from "./components/Icon";
import { KnowledgePanel, MonitoringPanel, ReportsPanel, SettingsPanel } from "./components/panels";

export default function App() {
  const { view, loading, error, setSidebarOpen } = useApp();

  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        <div className="mobile-bar">
          <button className="hamburger" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            <svg className="icon" viewBox="0 0 24 24"><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></svg>
          </button>
          <div className="brand-name" style={{ fontSize: 14 }}>BOTIM Opportunity Intelligence</div>
        </div>

        {loading ? (
          <div className="empty-state" style={{ paddingTop: 120 }}>
            <div className="step-spin" style={{ margin: "0 auto 12px" }} />
            Loading engine data…
          </div>
        ) : error ? (
          <div className="view">
            <div className="panel-wrap">
              <div className="error-banner">Could not load engine data: {error}</div>
            </div>
          </div>
        ) : (
          <>
            {view === "home" && <Home />}
            {view === "updates" && <Updates />}
            {view === "project" && <ProjectWorkspace />}
            {/* Global, portfolio-wide destinations — deliberately independent of
                whatever project/chat is currently open (see store.tsx go*). */}
            {view === "monitoring" && <section className="view" id="view-monitoring"><MonitoringPanel /></section>}
            {view === "knowledge" && <section className="view" id="view-knowledge"><KnowledgePanel /></section>}
            {view === "reports" && <section className="view" id="view-reports"><ReportsPanel /></section>}
            {view === "settings" && <section className="view" id="view-settings"><SettingsPanel /></section>}
          </>
        )}

        {isLive() === false && (
          <div style={{ position: "fixed", bottom: 12, right: 14, zIndex: 30 }}>
            <span className="chip" title="The Python API was unreachable; showing a bundled snapshot of real engine output.">
              <Icon name="alert" size={12} /> offline snapshot
            </span>
          </div>
        )}
      </main>
      <Drawer />
      <DetailDrawer />
    </div>
  );
}
