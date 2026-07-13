import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../store";
import { confidenceLabel, tagLabel } from "../lib/format";
import type { Brief, Experiment, JournalPayload, MonitoringPayload, Opportunity } from "../types";
import Icon from "./Icon";
import Collapsible from "./Collapsible";
import { CalibrationCard, DecisionJournalEntry } from "./cards";

/* ---------------- Knowledge ---------------- */
export function KnowledgePanel() {
  const { overview } = useApp();
  const [q, setQ] = useState("");
  if (!overview) return null;
  const ev = overview.evidence.filter((e) =>
    (e.ev_id + e.title + e.segment).toLowerCase().includes(q.toLowerCase()));
  const strong = overview.evidence.filter((e) => !e.weak).length;
  const health = overview.evidence.length ? Math.round((strong / overview.evidence.length) * 100) : 0;

  const stats: [number, string][] = [
    [overview.evidence.length, "Evidence records"],
    [strong, "Score-driving (strong)"],
    [overview.evidence.length - strong, "Leads (weak)"],
    [overview.assumptions.length, "Tracked assumptions"],
    [overview.opportunities.length, "Live opportunities"],
    [overview.archived.length, "Archived"],
  ];

  return (
    <div className="panel-wrap">
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Knowledge</div>
          <div className="panel-sub">Every evidence record behind the scores — read-only</div>
        </div>
      </div>
      <div className="search-box">
        <Icon name="search" />
        <input placeholder="Search evidence by id, title, or segment…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="stat-grid">
        {stats.map(([n, l]) => (
          <div className="stat-card" key={l}>
            <div className="stat-icon-row"><Icon name="file" /></div>
            <div className="stat-num">{n}</div>
            <div className="stat-label">{l}</div>
          </div>
        ))}
      </div>
      <div className="health-card">
        <div className="health-top">
          <div style={{ fontSize: 13.5, fontWeight: 650 }}>Evidence strength</div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{health}%</div>
        </div>
        <div className="health-bar"><div className="health-bar-fill" style={{ width: `${health}%` }} /></div>
        <div className="health-note">
          {strong} of {overview.evidence.length} records are strong enough to drive a score; the rest are leads, not findings.
        </div>
      </div>
      <div className="section-label">Evidence records</div>
      <div className="list-card">
        {ev.map((e) => (
          <div className="list-row" key={e.ev_id}>
            <div className="list-row-icon" style={e.weak ? { background: "var(--warning-soft)", color: "var(--warning)" } : undefined}>
              <Icon name="file" size={16} />
            </div>
            <div className="list-row-main">
              <div className="list-row-title">{e.ev_id}{e.weak && <span className="chip">lead</span>}</div>
              <div className="list-row-sub">{e.title !== "—" ? e.title : "(no title recorded)"}</div>
            </div>
            <div className="list-row-meta">strength {String(e.strength)} · {confidenceLabel(e.confidence)}</div>
          </div>
        ))}
        {ev.length === 0 && <div className="list-row"><div className="list-row-sub">No matching evidence.</div></div>}
      </div>
    </div>
  );
}

/* ---------------- Interviews / experiments ---------------- */
export function InterviewsPanel() {
  const [exps, setExps] = useState<Experiment[] | null>(null);
  useEffect(() => { api.experiments().then(setExps); }, []);
  if (!exps) return <PanelSkeleton />;
  return (
    <div className="panel-wrap">
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Validation experiments</div>
          <div className="panel-sub">Each experiment has a pre-committed success and kill threshold, set before the run</div>
        </div>
      </div>
      {exps.length === 0 ? <EmptyPanel icon="check-circle" title="No experiments" note="No VE specs are committed yet." /> : (
        <div className="list-card" style={{ padding: 0 }}>
          {exps.map((e) => {
            const status = (e.result?.status || e.status || "designed").toLowerCase();
            const done = status.includes("complete") || status.includes("pass") || status.includes("fail");
            return (
              <div className="file-row" key={e.id}>
                <div className="file-thumb"><Icon name="check-circle" size={18} /></div>
                <div className="file-main">
                  <div className="file-name">{e.id} — {e.title}</div>
                  <div className="file-summary">{e.hypothesis}</div>
                  <div className="file-tags">
                    <span className="chip">Success: {truncate(e.success_threshold)}</span>
                    <span className="chip">Kill: {truncate(e.kill_threshold)}</span>
                  </div>
                </div>
                <div className="file-meta-col"><span className={`pill-status ${done ? "complete" : "designed"}`}>{status}</span></div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---------------- Reports / briefs + decision journal ---------------- */
export function ReportsPanel() {
  const { overview } = useApp();
  const [journal, setJournal] = useState<JournalPayload | null>(null);
  useEffect(() => { api.journal().then(setJournal); }, []);
  const briefs: Brief[] = (overview?.briefs ?? []).filter((b) => b.exists);

  return (
    <div className="panel-wrap">
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Reports & briefs</div>
          <div className="panel-sub">Executive-ready outputs — generated from engine truth, never asserting a build decision</div>
        </div>
      </div>

      {briefs.length === 0 ? (
        <EmptyPanel icon="file" title="No committed briefs yet" note="Recommendation documents will appear here once written through the impact workflow." />
      ) : (
        <div className="report-grid">
          {briefs.map((b) => (
            <div className="report-card" key={b.opportunity_id}>
              <div className="report-top">
                <div className="report-title">{b.opportunity_id} — recommendation</div>
                <span className="pill-status ready">Committed</span>
              </div>
              <div className="report-meta">{b.path}</div>
              <div className="report-preview">{firstPara(b.body)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="section-label">Decision journal & calibration</div>
      {journal ? (
        <>
          <CalibrationCard data={journal.calibration} />
          {journal.predictions.map((p) => <DecisionJournalEntry key={p.id} data={p} />)}
        </>
      ) : <PanelSkeleton />}
    </div>
  );
}

/* ---------------- Monitoring ---------------- */
export function MonitoringPanel() {
  const [mon, setMon] = useState<MonitoringPayload | null>(null);
  useEffect(() => { api.monitoring().then(setMon); }, []);
  if (!mon) return <PanelSkeleton />;

  const groups: { tier: string; label: string }[] = [
    { tier: "critical", label: "Critical" },
    { tier: "important", label: "Important" },
    { tier: "info", label: "Informational" },
  ];
  const byTier = (t: string) => mon.events.filter((e) => {
    const tier = (e.tier || "info").toLowerCase();
    if (t === "info") return tier !== "critical" && tier !== "important";
    return tier === t;
  });

  return (
    <div className="panel-wrap">
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Monitoring</div>
          <div className="panel-sub">Meaningful changes only — {mon.events.length} signals, {mon.alerts.length} alerts</div>
        </div>
      </div>
      {mon.events.length === 0 && <EmptyPanel icon="bell" title="No monitoring events" note="The monitoring engine has produced no signals for this period." />}
      {groups.map((g) => {
        const items = byTier(g.tier);
        if (!items.length) return null;
        return (
          <div key={g.tier}>
            <div className="mon-group-label"><span className={`mon-dot ${g.tier}`} />{g.label}</div>
            {items.map((e) => (
              <div className={`mon-card ${g.tier}`} key={e.id}>
                <div className="mon-card-title">{e.title}</div>
                <div className="mon-fields">
                  <div><div className="mon-field-label">Detected</div><div className="mon-field-value">{e.detected_at}</div></div>
                  <div><div className="mon-field-label">Signal</div><div className="mon-field-value">{e.signal_type || e.adapter || "—"}</div></div>
                  {e.kb_links?.length ? <div><div className="mon-field-label">Affected</div><div className="mon-field-value">{e.kb_links.join(", ")}</div></div> : null}
                  {e.entity && <div><div className="mon-field-label">Source</div><div className="mon-field-value">{e.entity}</div></div>}
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/* ---------------- Files (upload demo, local only) ---------------- */
export function FilesPanel() {
  const [drag, setDrag] = useState(false);
  const [files, setFiles] = useState<{ name: string; size: number }[]>([]);
  const onDrop = (list: FileList | null) => {
    if (!list) return;
    setFiles((f) => [...f, ...Array.from(list).map((x) => ({ name: x.name, size: x.size }))]);
  };
  return (
    <div className="panel-wrap">
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Files</div>
          <div className="panel-sub">Attach source documents for this opportunity (stored locally in this session)</div>
        </div>
      </div>
      <label
        className={`dropzone${drag ? " drag" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); onDrop(e.dataTransfer.files); }}
      >
        <Icon name="upload" />
        Drag files here, or <b>browse</b> to attach PDFs, Word, PowerPoint, Excel, CSV, images, or text
        <input type="file" multiple hidden onChange={(e) => onDrop(e.target.files)} />
      </label>
      {files.length > 0 && (
        <div className="list-card">
          {files.map((f, i) => (
            <div className="file-row" key={i}>
              <div className="file-thumb"><Icon name="file" size={18} /></div>
              <div className="file-main">
                <div className="file-name">{f.name}</div>
                <div className="file-summary">{(f.size / 1024).toFixed(1)} KB · attached locally (not uploaded to the engine)</div>
              </div>
              <div className="file-meta-col"><span className="pill-status processing">Local</span></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Sources (evidence provenance) ---------------- */
export function SourcesPanel({ opp }: { opp: Opportunity }) {
  const { overview } = useApp();
  const refs = useMemo(() => {
    const ids = new Set(opp.factors.flatMap((f) => f.evidence_ids));
    return (overview?.evidence ?? []).filter((e) => ids.has(e.ev_id));
  }, [opp, overview]);

  return (
    <div className="panel-wrap">
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Sources</div>
          <div className="panel-sub">Every citation behind {opp.id}'s scorecard, linked to the evidence store</div>
        </div>
      </div>
      {refs.length === 0 ? (
        <EmptyPanel icon="book" title="No cited sources" note="This scorecard cites no evidence records." />
      ) : (
        <div className="list-card">
          {refs.map((e) => (
            <div className="file-row" key={e.ev_id}>
              <div className="file-thumb"><Icon name={e.resolved ? "file" : "alert"} size={18} /></div>
              <div className="file-main">
                <div className="file-name">{e.ev_id}</div>
                <div className="file-summary">{e.title !== "—" ? e.title : "(no title recorded)"}</div>
                <div className="file-tags"><span className="chip">{e.role}</span>{e.weak && <span className="chip">lead</span>}</div>
              </div>
              <div className="file-meta-col">
                <span className={`pill-status ${e.resolved ? "processed" : "processing"}`}>{e.resolved ? "resolved" : "unresolved"}</span>
                <span style={{ fontSize: 11.5, color: "var(--text-tertiary)" }}>strength {String(e.strength)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Settings ---------------- */
export function SettingsPanel({ opp }: { opp: Opportunity }) {
  return (
    <div className="panel-wrap" style={{ maxWidth: 680 }}>
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Settings</div>
          <div className="panel-sub">Configuration for {opp.id} — {opp.name}</div>
        </div>
      </div>
      <div className="settings-section">
        <div className="settings-section-title">General</div>
        <div className="field-row"><div className="field-label">Opportunity</div><input className="field-input" value={opp.name} readOnly /></div>
        <div className="field-row"><div className="field-label">Classification</div><input className="field-input" value={tagLabel(opp.classification)} readOnly /></div>
        <div className="field-row" style={{ marginBottom: 0 }}><div className="field-label">Segment</div><input className="field-input" value={opp.segment} readOnly /></div>
      </div>
      <div className="settings-section">
        <div className="settings-section-title">Governance</div>
        <div className="toggle-row">
          <div>
            <div className="toggle-row-text">Read-only presentation</div>
            <div className="toggle-row-sub">Scores are computed by the engine. The UI never recomputes or overrides them.</div>
          </div>
          <button className="switch on" aria-label="read-only" />
        </div>
        <div className="toggle-row" style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 4 }}>
          <div>
            <div className="toggle-row-text">Approval workflow</div>
            <div className="toggle-row-sub">Score changes are approved via the impact CLI: <code>apply-impact --approver</code>. No approval button exists here by design.</div>
          </div>
        </div>
      </div>
      <div className="settings-section">
        <div className="settings-section-title">Provenance</div>
        <div className="field-row" style={{ marginBottom: 0 }}>
          <div className="field-label">Profile document</div>
          <input className="field-input" value={opp.profile_path} readOnly />
        </div>
      </div>
    </div>
  );
}

/* ---------------- shared bits ---------------- */
export function PanelSkeleton() {
  return (
    <div className="panel-wrap">
      <div className="skeleton" style={{ height: 28, width: 220, marginBottom: 20 }} />
      <div className="stat-grid">
        {[0, 1, 2].map((i) => <div className="skeleton" key={i} style={{ height: 84 }} />)}
      </div>
      <div className="skeleton" style={{ height: 120, marginTop: 16 }} />
    </div>
  );
}

function EmptyPanel({ icon, title, note }: { icon: Parameters<typeof Icon>[0]["name"]; title: string; note: string }) {
  return (
    <div className="empty-state">
      <Icon name={icon} className="icon" />
      <div className="empty-state-title">{title}</div>
      {note}
    </div>
  );
}

function truncate(s: string, n = 60): string {
  return s && s.length > n ? s.slice(0, n) + "…" : s || "—";
}
function firstPara(md: string): string {
  const lines = (md || "").split("\n").map((l) => l.trim()).filter(Boolean).filter((l) => !l.startsWith("#"));
  return truncate(lines[0] || "", 180);
}

// Collapsible re-export so the workspace can lazy-render richer detail if needed
export { Collapsible };
