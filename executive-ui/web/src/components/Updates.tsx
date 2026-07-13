import { useApp } from "../store";
import Icon, { type IconName } from "./Icon";

function iconForKind(kind: string): IconName {
  if (kind === "alert") return "alert";
  if (kind === "prediction-resolved") return "check-circle";
  if (kind === "summary") return "file";
  return "activity";
}

export default function Updates() {
  const { overview } = useApp();
  const feed = overview?.feed ?? [];

  return (
    <section className="view" id="view-updates">
      <div className="panel-wrap" style={{ paddingTop: 44 }}>
        <div className="panel-title-row">
          <div>
            <div className="panel-title">Updates</div>
            <div className="panel-sub">Signals and resolved predictions across the portfolio — {feed.length} items</div>
          </div>
        </div>

        {feed.length === 0 ? (
          <div className="empty-state">
            <Icon name="activity" className="icon" />
            <div className="empty-state-title">No updates yet</div>
            Monitoring signals and resolved predictions will appear here.
          </div>
        ) : (
          <div className="list-card">
            {feed.map((f) => (
              <div className="list-row" key={f.id}>
                <div
                  className="list-row-icon"
                  style={f.tier === "critical" ? { background: "var(--critical-soft)", color: "var(--critical)" }
                    : f.tier === "important" ? { background: "var(--warning-soft)", color: "var(--warning)" } : undefined}
                >
                  <Icon name={iconForKind(f.kind)} size={16} />
                </div>
                <div className="list-row-main">
                  <div className="list-row-title">
                    {f.title}
                    {f.detail && f.detail !== "—" && <span className="chip">{f.detail}</span>}
                  </div>
                  {f.before_after && (
                    <div className="list-row-sub">{f.before_after.before} → {f.before_after.after}</div>
                  )}
                </div>
                <div className="list-row-meta">{f.detected_at}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
