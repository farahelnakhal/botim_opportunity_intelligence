import { useApp } from "../store";
import { humanize, nameMap } from "../lib/labels";
import Icon, { type IconName } from "./Icon";

function iconForKind(kind: string): IconName {
  if (kind === "alert") return "alert";
  if (kind === "prediction-resolved") return "check-circle";
  if (kind === "summary") return "file";
  return "activity";
}

export default function Updates() {
  const { overview, openDetail } = useApp();
  const feed = overview?.feed ?? [];
  const names = nameMap([...(overview?.opportunities ?? []), ...(overview?.archived ?? [])]);

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
              <button
                type="button"
                className="list-row clickable"
                key={f.id}
                onClick={() =>
                  // Phase 4 — a resolved prediction opens the prediction
                  // detail; every other feed item opens the monitoring detail.
                  openDetail(f.kind === "prediction-resolved" ? "prediction" : "monitoring_update", f.id)
                }
                aria-label={`Open update detail: ${humanize(f.title, names)}`}
              >
                <div
                  className="list-row-icon"
                  style={f.tier === "critical" ? { background: "var(--critical-soft)", color: "var(--critical)" }
                    : f.tier === "important" ? { background: "var(--warning-soft)", color: "var(--warning)" } : undefined}
                >
                  <Icon name={iconForKind(f.kind)} size={16} />
                </div>
                <div className="list-row-main">
                  <div className="list-row-title">
                    {humanize(f.title, names)}
                    {f.detail && f.detail !== "—" && <span className="chip">{humanize(f.detail, names)}</span>}
                  </div>
                  {f.before_after ? (
                    <div className="list-row-sub">{f.before_after.before} → {f.before_after.after}</div>
                  ) : (
                    <div className="list-row-sub">New monitoring information was received. Open for details.</div>
                  )}
                </div>
                <div className="list-row-meta">{f.detected_at}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
