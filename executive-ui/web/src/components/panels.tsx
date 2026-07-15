import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../store";
import { confidenceLabel, humanFactorKey, tagLabel } from "../lib/format";
import { humanize, nameMap } from "../lib/labels";
import { copyText, downloadText } from "../lib/actions";
import type { Brief, Experiment, JournalPayload, MonitoringPayload, Opportunity } from "../types";
import Icon from "./Icon";
import ActionButton from "./ActionButton";
import Collapsible from "./Collapsible";
import { CalibrationCard, DecisionJournalEntry } from "./cards";

/* ---------------- Knowledge ---------------- */
export function KnowledgePanel() {
  const { overview, openDetail } = useApp();
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
          <button
            type="button"
            className="list-row clickable"
            key={e.ev_id}
            onClick={() => openDetail("evidence", e.ev_id)}
            aria-label={`Open evidence detail: ${e.title !== "—" ? e.title : e.ev_id}`}
          >
            <div className="list-row-icon" style={e.weak ? { background: "var(--warning-soft)", color: "var(--warning)" } : undefined}>
              <Icon name="file" size={16} />
            </div>
            <div className="list-row-main">
              <div className="list-row-title">{e.title !== "—" ? e.title : "Customer-evidence record"}{e.weak && <span className="chip">lead</span>}</div>
              <div className="list-row-sub">{humanize(e.segment) !== "—" ? humanize(e.segment) : "Segment not recorded"}</div>
            </div>
            <div className="list-row-meta">strength {String(e.strength)} · {confidenceLabel(e.confidence)}</div>
          </button>
        ))}
        {ev.length === 0 && <div className="list-row"><div className="list-row-sub">No matching evidence.</div></div>}
      </div>
    </div>
  );
}

/* ---------------- Interviews / experiments ---------------- */
// Turn a scoring dimension into a non-leading customer-interview question.
const QUESTION_TEMPLATES: Record<string, string> = {
  pain_severity: "Tell me about the last time this problem cost you — what happened?",
  pain_frequency: "How often does this situation come up in a typical month?",
  financial_impact: "Roughly what does this problem cost you when it happens?",
  workaround_cost: "How do you handle it today, and what does that workaround cost you?",
  switching_intent: "What would have to be true for you to switch to a new way of doing this?",
  willingness_to_pay: "If something solved this reliably, what would a fair monthly price feel like?",
  digital_readiness: "Which tools or apps do you already use to run this part of your business?",
  payment_volume: "Roughly what monthly payment volume flows through your business?",
  credit_need: "When cash is tight, how do you currently bridge the gap?",
  botim_distribution_advantage: "How do you currently discover and sign up for services like this?",
  transaction_data_advantage: "Would you be comfortable sharing transaction history to get a better offer?",
  payment_revenue_potential: "What do you pay today to accept or move payments?",
  lending_revenue_potential: "Have you borrowed for working capital before — on what terms?",
  credit_risk_visibility: "What causes a bad month for your cash flow?",
  competitive_defensibility: "Who else offers something like this to you today?",
  ease_of_validation: "Would you be willing to try an early version and give feedback?",
  mvp_feasibility_7wk: "What is the one feature that would make this a must-have on day one?",
};

function suggestedSurvey(opp: Opportunity, offset = 0) {
  const ranked = opp.factors
    .filter((f) => f.assumption)
    .sort((a, b) => a.score - b.score);
  if (ranked.length === 0) return [];
  // Rotate through the weak dimensions so "New survey" yields a fresh set.
  const start = offset % ranked.length;
  const rotated = [...ranked.slice(start), ...ranked.slice(0, start)].slice(0, 5);
  return rotated.map((f) => ({ key: f.key, q: QUESTION_TEMPLATES[f.key] || `Tell me about ${f.key.replace(/_/g, " ")}.` }));
}

export function InterviewsPanel({ opp }: { opp: Opportunity }) {
  const [exps, setExps] = useState<Experiment[] | null>(null);
  const [offset, setOffset] = useState(0); // "New survey" rotates through weakest assumptions
  useEffect(() => { api.experiments().then(setExps); }, []);
  const survey = suggestedSurvey(opp, offset);

  const surveyText = () =>
    `Customer-validation survey — ${opp.name}\n\n` +
    survey.map((s, i) => `${i + 1}. ${s.q}  [${humanFactorKey(s.key)}]`).join("\n") +
    `\n\nNo product or build decision has been made.\n`;

  return (
    <div className="panel-wrap">
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Interviews</div>
          <div className="panel-sub">Survey customers to validate the assumptions behind this opportunity</div>
        </div>
        <ActionButton
          className="btn btn-primary" icon="plus" label="New survey" doneLabel="Regenerated"
          title="Regenerate from the next set of weak assumptions"
          onAct={() => setOffset((o) => o + 5)}
        />
      </div>

      {survey.length > 0 && (
        <div className="suggested-survey">
          <div className="suggested-survey-eyebrow"><Icon name="star" size={14} /> Suggested · closes the weakest assumptions on this opportunity</div>
          <div className="suggested-survey-title">Customer-validation survey</div>
          <div className="suggested-survey-desc">
            Generated from the lowest-scoring, evidence-free dimensions — the questions most likely to change the
            recommendation. Non-leading, ordered so pain comes before concept.
          </div>
          <div className="survey-q-list">
            {survey.map((s, i) => (
              <div className="survey-q-row" key={s.key}>
                <span className="survey-q-num">{String(i + 1).padStart(2, "0")}</span>
                <span className="survey-q-text">{s.q}</span>
                <span className="survey-q-type">{humanFactorKey(s.key)}</span>
              </div>
            ))}
          </div>
          <div className="suggested-survey-foot">
            <div className="suggested-survey-reach">These questions close the biggest evidence gaps before any build commitment.</div>
            <div style={{ display: "flex", gap: 8 }}>
              <ActionButton className="btn" label="Copy questions" doneLabel="Copied"
                onAct={() => copyText(surveyText())} />
              <ActionButton className="btn btn-primary" icon="external" label="Download survey" doneLabel="Saved"
                onAct={() => downloadText(`survey-${opp.id}.md`, surveyText())} />
            </div>
          </div>
        </div>
      )}

      <div className="section-label" style={{ marginTop: 0 }}>Validation experiments</div>
      <div className="panel-sub" style={{ marginBottom: 12 }}>Each experiment has a pre-committed success and kill threshold, set before the run.</div>
      {!exps ? <PanelSkeleton /> : exps.length === 0 ? <EmptyPanel icon="check-circle" title="No experiments yet" note="Committed experiments will appear here." /> : (
        <div className="list-card" style={{ padding: 0 }}>
          {exps.map((e) => {
            const status = (e.result?.status || e.status || "designed").toLowerCase();
            const done = status.includes("complete") || status.includes("pass") || status.includes("fail");
            return (
              <div className="file-row" key={e.id}>
                <div className="file-thumb"><Icon name="check-circle" size={18} /></div>
                <div className="file-main">
                  <div className="file-name">{e.title}</div>
                  <div className="file-summary">{humanize(e.hypothesis)}</div>
                  <div className="file-tags">
                    <span className="chip">Success: {truncate(humanize(e.success_threshold))}</span>
                    <span className="chip">Kill: {truncate(humanize(e.kill_threshold))}</span>
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
  const { overview, openReport } = useApp();
  const [journal, setJournal] = useState<JournalPayload | null>(null);
  useEffect(() => { api.journal().then(setJournal); }, []);
  const briefs: Brief[] = (overview?.briefs ?? []).filter((b) => b.exists);
  const names = nameMap([...(overview?.opportunities ?? []), ...(overview?.archived ?? [])]);

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
                {/* Phase 4 — the title is a semantic button opening the web
                    report route (/report/OPP-nnn); Export stays separate. */}
                <button
                  type="button"
                  className="report-title report-title-link"
                  onClick={() => openReport(b.opportunity_id)}
                  aria-label={`Open web report: ${names[b.opportunity_id] || b.opportunity_id} — recommendation`}
                >
                  {names[b.opportunity_id] || "Opportunity"} — recommendation
                </button>
                <span className="pill-status ready">Committed</span>
              </div>
              <div className="report-meta">Executive recommendation brief</div>
              <div className="report-preview">{humanize(firstPara(b.body))}</div>
              <div className="report-actions">
                <ActionButton className="btn btn-sm" icon="external" label="Export" doneLabel="Saved"
                  onAct={() => downloadText(`${b.opportunity_id.toLowerCase()}-recommendation.md`, b.body)} />
                <ActionButton className="btn btn-sm" label="Copy" doneLabel="Copied"
                  onAct={() => copyText(b.body)} />
              </div>
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
// Phase 4 — current-state summary card. Every number comes from the backend's
// summary_state (committed artefacts only); a null count renders as "—",
// never as an invented value.
function MonitoringSummaryCard({ state }: { state: NonNullable<MonitoringPayload["summary_state"]> }) {
  const n = (v: number | null) => (v == null ? "—" : String(v));
  const stats: [string, string][] = [
    [n(state.event_count), "Events this period"],
    [n(state.open_alert_count), "Open alerts"],
    [n(state.unresolved_warning_count), "Unresolved warnings"],
    [n(state.monitored_entity_count), "Monitored entities"],
  ];
  const statusLabel: Record<string, string> = {
    "active": "Monitoring active",
    "no-recent-updates": "No recent updates",
    "no-events": "No events yet",
    "never-run": "Never run",
    "unavailable": "Monitoring unavailable",
  };
  return (
    <div className="health-card" data-testid="monitoring-summary" style={{ marginBottom: 18 }}>
      <div className="health-top">
        <div style={{ fontSize: 13.5, fontWeight: 650 }}>
          {statusLabel[state.status] ?? state.status}
          {state.internal_only && <span className="chip" style={{ marginLeft: 8 }}>internal knowledge-base changes only</span>}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
          {state.latest_event_at ? `Latest event ${state.latest_event_at}` : "No events"}
          {state.last_checked ? ` · last checked ${state.last_checked}` : " · no run timestamp recorded"}
        </div>
      </div>
      <div className="stat-grid" style={{ marginTop: 12 }}>
        {stats.map(([v, l]) => (
          <div className="stat-card" key={l}>
            <div className="stat-num">{v}</div>
            <div className="stat-label">{l}</div>
          </div>
        ))}
      </div>
      <div className="health-note">{state.status_note}</div>
    </div>
  );
}

export function MonitoringPanel() {
  const { overview, openDetail } = useApp();
  const names = nameMap([...(overview?.opportunities ?? []), ...(overview?.archived ?? [])]);
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
      {mon.summary_state && <MonitoringSummaryCard state={mon.summary_state} />}

      {/* Phase 7 — user monitoring configurations, clearly distinguished
          from the internal-KB/demo event stream below */}
      {(mon.user_monitoring?.configs.length ?? 0) > 0 && (
        <div data-testid="user-monitoring-section">
          <div className="section-label">Your monitoring configurations</div>
          <div className="list-card" style={{ marginBottom: 18 }}>
            {mon.user_monitoring!.configs.map((c) => {
              const label = c.status === "never_run" ? "Configured — awaiting monitoring run"
                : c.status === "paused" ? "Paused"
                : c.status === "error" ? `Error: ${c.last_error ?? "unknown"}`
                : c.status === "active" ? "Active" : c.status;
              return (
                <div className="list-row" key={c.opportunity_id}>
                  <div className="list-row-icon"><Icon name="bell" size={16} /></div>
                  <div className="list-row-main">
                    <div className="list-row-title">{c.opportunity_title ?? c.opportunity_id}</div>
                    <div className="list-row-sub">
                      {label} · cadence {c.cadence ?? "manual"} · last run {c.last_run_at ?? "unavailable"}
                    </div>
                  </div>
                  <div className="list-row-meta">
                    <span className={`pill-status ${c.enabled ? "designed" : "processing"}`}>
                      {c.enabled ? "configured" : "paused"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="source-tag" style={{ display: "block", marginBottom: 16 }}>
            {mon.user_monitoring!.note}
          </p>
        </div>
      )}

      {mon.events.length === 0 && <EmptyPanel icon="bell" title="No monitoring events" note="No monitoring events exist yet — none are fabricated." />}
      {mon.events.length > 0 && <div className="section-label">Knowledge-base &amp; demo monitoring events</div>}
      {groups.map((g) => {
        const items = byTier(g.tier);
        if (!items.length) return null;
        return (
          <div key={g.tier}>
            <div className="mon-group-label"><span className={`mon-dot ${g.tier}`} />{g.label}</div>
            {items.map((e) => (
              <button
                type="button"
                className={`mon-card ${g.tier} clickable`}
                key={e.id}
                onClick={() => openDetail("monitoring_update", e.id)}
                aria-label={`Open monitoring detail: ${humanize(e.title, names)}`}
              >
                <div className="mon-card-title">{humanize(e.title, names)}</div>
                <div className="mon-fields">
                  <div><div className="mon-field-label">Detected</div><div className="mon-field-value">{e.detected_at}</div></div>
                  <div><div className="mon-field-label">Signal</div><div className="mon-field-value" style={{ textTransform: "capitalize" }}>{String(e.signal_type || e.adapter || "—").replace(/_/g, " ")}</div></div>
                  {e.kb_links?.length ? <div><div className="mon-field-label">Affected</div><div className="mon-field-value">{humanize(e.kb_links.join(", "), names)}</div></div> : null}
                </div>
              </button>
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
  const { overview, openDetail } = useApp();
  const refs = useMemo(() => {
    const ids = new Set(opp.factors.flatMap((f) => f.evidence_ids));
    return (overview?.evidence ?? []).filter((e) => ids.has(e.ev_id));
  }, [opp, overview]);

  return (
    <div className="panel-wrap">
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Sources</div>
          <div className="panel-sub">Every source behind this analysis, linked to the evidence on file</div>
        </div>
      </div>
      {refs.length === 0 ? (
        <EmptyPanel icon="book" title="No cited sources" note="This scorecard cites no evidence records." />
      ) : (
        <div className="list-card">
          {refs.map((e) => (
            <button
              type="button"
              className="file-row clickable"
              key={e.ev_id}
              onClick={() => openDetail("evidence", e.ev_id)}
              aria-label={`Open source detail: ${e.title !== "—" ? e.title : e.ev_id}`}
            >
              <div className="file-thumb"><Icon name={e.resolved ? "file" : "alert"} size={18} /></div>
              <div className="file-main">
                <div className="file-name">{e.title !== "—" ? e.title : "Customer-evidence record"}</div>
                <div className="file-summary">{humanize(e.segment) !== "—" ? humanize(e.segment) : "Segment not recorded"}</div>
                <div className="file-tags"><span className="chip">{e.role}</span>{e.weak && <span className="chip">lead</span>}</div>
              </div>
              <div className="file-meta-col">
                <span className={`pill-status ${e.resolved ? "processed" : "processing"}`}>{e.resolved ? "resolved" : "unresolved"}</span>
                <span style={{ fontSize: 11.5, color: "var(--text-tertiary)" }}>strength {String(e.strength)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Settings ---------------- */
const MARKETS: Record<string, { flag: string; name: string; regulator: string; currency: string }> = {
  AE: { flag: "🇦🇪", name: "United Arab Emirates", regulator: "Central Bank of the UAE (CBUAE)", currency: "AED — UAE Dirham" },
  SA: { flag: "🇸🇦", name: "Saudi Arabia", regulator: "Saudi Central Bank (SAMA)", currency: "SAR — Saudi Riyal" },
  EG: { flag: "🇪🇬", name: "Egypt", regulator: "Central Bank of Egypt (CBE)", currency: "EGP — Egyptian Pound" },
  PK: { flag: "🇵🇰", name: "Pakistan", regulator: "State Bank of Pakistan (SBP)", currency: "PKR — Pakistani Rupee" },
  JO: { flag: "🇯🇴", name: "Jordan", regulator: "Central Bank of Jordan (CBJ)", currency: "JOD — Jordanian Dinar" },
};

export function SettingsPanel({ opp }: { opp?: Opportunity }) {
  const { appMode } = useApp();
  // Phase 5 — email ingestion/recipients are demo-only theatre: in any
  // non-demo mode no fake addresses are invented and the sections below are
  // replaced by an honest "not available" note.
  const demoEmailFeatures = appMode === "demo";
  const [country, setCountry] = useState("AE");
  const [notify, setNotify] = useState(true);
  const [autoProcess, setAutoProcess] = useState(true);
  const [recipients, setRecipients] = useState<string[]>(
    demoEmailFeatures ? ["strategy@botim.ai", "research@botim.ai"] : []);
  const [newEmail, setNewEmail] = useState("");
  const m = MARKETS[country];
  const inbox = opp
    ? `${opp.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 28)}@botim.ai`
    : "workspace@botim.ai";

  const addRecipient = () => {
    const e = newEmail.trim();
    if (e && !recipients.includes(e)) setRecipients((r) => [...r, e]);
    setNewEmail("");
  };

  return (
    <div className="panel-wrap" style={{ maxWidth: 680 }}>
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Settings</div>
          <div className="panel-sub">{opp ? `Configuration for ${opp.name}` : "Workspace-wide configuration — not tied to any single chat or opportunity"}</div>
        </div>
      </div>

      {opp ? (
        <div className="settings-section">
          <div className="settings-section-title">General</div>
          <div className="field-row"><div className="field-label">Opportunity</div><input className="field-input" defaultValue={opp.name} /></div>
          <div className="field-row"><div className="field-label">Classification</div><input className="field-input" value={tagLabel(opp.classification)} readOnly /></div>
          <div className="field-row" style={{ marginBottom: 0 }}><div className="field-label">Segment</div><input className="field-input" value={humanize(opp.segment)} readOnly /></div>
        </div>
      ) : (
        <div className="empty-state" style={{ padding: "18px 0 28px" }}>
          Select an opportunity from the sidebar to configure opportunity-specific settings. The sections below apply workspace-wide.
        </div>
      )}

      <div className="settings-section">
        <div className="settings-section-title">Market</div>
        <div className="field-row">
          <div className="field-label">Country</div>
          <select className="field-input" value={country} onChange={(e) => setCountry(e.target.value)}>
            {Object.entries(MARKETS).map(([code, mk]) => (
              <option key={code} value={code}>{mk.flag} {mk.name}</option>
            ))}
          </select>
          <div className="toggle-row-sub">Sets the regulator, currency, and comparable market data this analysis references.</div>
        </div>
        <div className="field-row"><div className="field-label">Regulator</div><input className="field-input" value={m.regulator} readOnly /></div>
        <div className="field-row" style={{ marginBottom: 0 }}><div className="field-label">Currency</div><input className="field-input" value={m.currency} readOnly /></div>
      </div>

      {demoEmailFeatures ? (
        <>
          <div className="settings-section">
            <div className="settings-section-title">Email ingestion <span className="chip">demo</span></div>
            <div className="field-row">
              <div className="field-label">Incoming email address</div>
              <div className="email-box">
                <span>{inbox}</span>
                <ActionButton className="btn btn-sm" label="Copy" doneLabel="Copied" onAct={() => copyText(inbox)} />
              </div>
              <div className="toggle-row-sub">Forward reports or evidence here — attachments are summarised and filed automatically.</div>
            </div>
            <div className="toggle-row">
              <div>
                <div className="toggle-row-text">Auto-process incoming attachments</div>
                <div className="toggle-row-sub">Extract, summarise, and file on arrival</div>
              </div>
              <button className={`switch${autoProcess ? " on" : ""}`} onClick={() => setAutoProcess((v) => !v)} />
            </div>
          </div>

          <div className="settings-section">
            <div className="settings-section-title">Notification recipients <span className="chip">demo</span></div>
            <div className="toggle-row" style={{ marginBottom: 12 }}>
              <div>
                <div className="toggle-row-text">Email members on critical alerts</div>
                <div className="toggle-row-sub">Send the people below an email when a critical signal fires</div>
              </div>
              <button className={`switch${notify ? " on" : ""}`} onClick={() => setNotify((v) => !v)} />
            </div>
            <div className="list-card" style={{ marginBottom: 12 }}>
              {recipients.map((r) => (
                <div className="list-row" key={r}>
                  <div className="list-row-icon"><Icon name="users" size={16} /></div>
                  <div className="list-row-main"><div className="list-row-title">{r}</div></div>
                  <button className="btn btn-sm" onClick={() => setRecipients((list) => list.filter((x) => x !== r))}>Remove</button>
                </div>
              ))}
              {recipients.length === 0 && <div className="list-row"><div className="list-row-sub">No recipients yet.</div></div>}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="field-input" style={{ flex: 1 }} placeholder="name@company.com" value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") addRecipient(); }}
              />
              <button className="btn btn-primary" onClick={addRecipient}>Add</button>
            </div>
          </div>
        </>
      ) : (
        <div className="settings-section" data-testid="email-unavailable">
          <div className="settings-section-title">Email &amp; notifications</div>
          <div className="toggle-row-sub" style={{ lineHeight: 1.5 }}>
            Email ingestion and alert recipients are not available yet — no email is sent or
            received by this workspace, so no addresses are configured here.
          </div>
        </div>
      )}

      <div className="settings-section">
        <div className="settings-section-title">Governance</div>
        <div className="toggle-row">
          <div>
            <div className="toggle-row-text">Read-only scoring</div>
            <div className="toggle-row-sub">Scores are computed by the analysis engine. This interface never recomputes or overrides them.</div>
          </div>
          <button className="switch on" aria-label="read-only" disabled />
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
