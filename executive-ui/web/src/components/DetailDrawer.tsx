// A small, generic detail drawer for record types that aren't opportunities
// (evidence, assumptions, monitoring updates). Deliberately separate from
// Drawer.tsx (the existing opportunity drawer) so that component is never
// touched — this one only ever reads from data already loaded in `overview`,
// never fabricates a field, and always has a safe "not available" state.
import { useEffect } from "react";
import { useApp } from "../store";
import { confidenceLabel } from "../lib/format";
import { humanize } from "../lib/labels";
import type { FeedItem } from "../types";
import Icon from "./Icon";

// A feed item's `detail` field is a comma-joined list of KB record ids
// (see executive-ui/adapter/collect.py). Reuse whatever id is already there —
// never invent a relation that isn't in the data.
function relatedTarget(f: FeedItem): { type: "opportunity" | "evidence"; id: string } | null {
  const ids = (f.detail || "").split(",").map((s) => s.trim()).filter(Boolean);
  const opp = ids.find((id) => /^OPP-\d+/i.test(id));
  if (opp) return { type: "opportunity", id: opp };
  const ev = ids.find((id) => /^EV-/i.test(id));
  if (ev) return { type: "evidence", id: ev };
  return null;
}

function Unavailable({ label }: { label: string }) {
  return (
    <div className="empty-state" style={{ padding: "32px 22px" }}>
      <Icon name="alert" className="icon" />
      <div className="empty-state-title">Not available</div>
      {label}
    </div>
  );
}

export default function DetailDrawer() {
  const { detailTarget, closeDetail, overview, openDrawer, openDetail } = useApp();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeDetail();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeDetail]);

  const show = !!detailTarget;

  let title = "";
  let body: React.ReactNode = null;

  if (detailTarget?.type === "evidence") {
    const e = overview?.evidence.find((x) => x.ev_id === detailTarget.id);
    if (!e) {
      title = "Evidence";
      body = <Unavailable label="This evidence record is not on file or could not be loaded." />;
    } else {
      title = e.title !== "—" ? e.title : "Customer-evidence record";
      body = (
        <div className="drawer-body">
          <p className="source-tag" style={{ display: "block", marginBottom: 14 }}>{e.ev_id}</p>
          <dl className="detail-fields">
            <div><dt>Source type</dt><dd>{humanize(e.source_type) || "—"}</dd></div>
            <div><dt>Evidence class</dt><dd>{humanize(e.evidence_class) || "—"}</dd></div>
            <div><dt>Strength</dt><dd>{String(e.strength)}{e.weak && <span className="chip"> lead, not a finding</span>}</dd></div>
            <div><dt>Confidence</dt><dd>{confidenceLabel(e.confidence)}</dd></div>
            <div><dt>Status</dt><dd>{humanize(e.status) || "—"}</dd></div>
            <div><dt>Segment</dt><dd>{humanize(e.segment) !== "—" ? humanize(e.segment) : "Not recorded"}</dd></div>
            <div><dt>Role</dt><dd>{e.role || "—"}</dd></div>
          </dl>
          {!e.resolved && <p style={{ color: "var(--warning)" }}>Referenced but not yet on file.</p>}
        </div>
      );
    }
  } else if (detailTarget?.type === "assumption") {
    const [oppId, factorKey] = detailTarget.id.split("::");
    const a = overview?.assumptions.find((x) => x.opportunity_id === oppId && x.factor_key === factorKey);
    if (!a) {
      title = "Assumption";
      body = <Unavailable label="This assumption record is not on file or could not be loaded." />;
    } else {
      title = "Assumption";
      body = (
        <div className="drawer-body">
          <p style={{ marginTop: 0 }}>{humanize(a.text)}</p>
          <dl className="detail-fields">
            <div><dt>Dimension</dt><dd>{humanize(a.factor_key)}</dd></div>
            <div><dt>Status</dt><dd>{humanize(a.status) || "—"}</dd></div>
            <div><dt>Sensitivity</dt><dd>{humanize(a.sensitivity) || "—"}</dd></div>
            <div><dt>Validation method</dt><dd>{humanize(a.validation_method) || "—"}</dd></div>
            <div><dt>Owner</dt><dd>{a.owner || "—"}</dd></div>
            <div><dt>Decision importance</dt><dd>{humanize(a.decision_importance) || "—"}</dd></div>
            <div><dt>Source</dt><dd>{humanize(a.source) || "—"}</dd></div>
          </dl>
        </div>
      );
    }
  } else if (detailTarget?.type === "monitoring_update") {
    const f = overview?.feed.find((x) => x.id === detailTarget.id);
    if (!f) {
      title = "Update";
      body = <Unavailable label="This update is not available — it may have rolled off the feed." />;
    } else {
      title = "Update";
      const names = Object.fromEntries(
        [...(overview?.opportunities ?? []), ...(overview?.archived ?? [])].map((o) => [o.id, o.name]),
      );
      const related = relatedTarget(f);
      body = (
        <div className="drawer-body">
          <p style={{ marginTop: 0, fontWeight: 600 }}>{humanize(f.title, names)}</p>
          <dl className="detail-fields">
            <div><dt>Detected</dt><dd>{f.detected_at || "—"}</dd></div>
            <div><dt>Type</dt><dd style={{ textTransform: "capitalize" }}>{f.kind.replace(/-/g, " ")}</dd></div>
            {f.detail && f.detail !== "—" && <div><dt>Reference</dt><dd>{humanize(f.detail, names)}</dd></div>}
          </dl>
          {f.before_after ? (
            <div className="mon-field-value" style={{ marginTop: 6 }}>
              <b>What changed:</b> {f.before_after.before} → {f.before_after.after}
            </div>
          ) : (
            <p className="source-tag" style={{ display: "block", marginTop: 6 }}>
              New monitoring information was received. Open the related record below for details.
            </p>
          )}
          {related && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              style={{ marginTop: 16 }}
              onClick={() => (related.type === "opportunity" ? openDrawer(related.id) : openDetail("evidence", related.id))}
            >
              Open related {related.type === "opportunity" ? "opportunity" : "evidence"}
            </button>
          )}
        </div>
      );
    }
  }

  return (
    <>
      <div className={`drawer-backdrop${show ? " show" : ""}${show ? "" : " hidden"}`} onClick={closeDetail} />
      <aside
        className={`drawer${show ? " show" : ""}${show ? "" : " hidden"}`}
        role="dialog"
        aria-modal="true"
        aria-label={title || "Detail"}
      >
        {show && (
          <>
            <div className="drawer-header">
              <div className="drawer-header-title">{title}</div>
              <button className="drawer-close" onClick={closeDetail} aria-label="Close detail">
                <Icon name="x" />
              </button>
            </div>
            {body}
          </>
        )}
      </aside>
    </>
  );
}
