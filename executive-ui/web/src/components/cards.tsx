import { confidenceLabel, humanFactorKey, money, scorePct, tagClass, tagLabel } from "../lib/format";
import { humanize, humanizeRefs, nameMap } from "../lib/labels";
import type {
  Assumption, CommercialModel, EvidenceRef, Experiment, FeedItem, JournalPayload, Opportunity, Prediction,
} from "../types";
import Collapsible from "./Collapsible";
import Icon from "./Icon";
import ScoreRing from "./ScoreRing";
import { useApp } from "../store";

/* ---------------- Banner (honesty guard) ---------------- */
export function Banner({ text }: { text: string }) {
  return (
    <div className="banner-note">
      <Icon name="alert" />
      <span>{text}</span>
    </div>
  );
}

/* ---------------- Opportunity card ---------------- */
export function OpportunityCard({ opp }: { opp: Opportunity }) {
  const { openDrawer } = useApp();
  const rec = opp.next_action && opp.next_action !== "—" ? opp.next_action : opp.classification_label;
  return (
    <div className="opp-card" onClick={() => openDrawer(opp.id)}>
      <ScoreRing raw={opp.raw_score} max={opp.raw_max} />
      <div className="opp-main">
        <div className="opp-top-row">
          <span className={`tag ${tagClass(opp.classification)}`}>{tagLabel(opp.classification)}</span>
          {opp.generated && <span className="tag neutral">AI-generated · unvalidated</span>}
        </div>
        <div className="opp-title">{opp.name}</div>
        <div className="opp-recommendation">{humanize(rec)}</div>
        <div className="opp-meta-row">
          <span>Confidence <b>{confidenceLabel(opp.confidence)}</b></span>
          <span>Assumptions <b>{opp.assumption_count}</b></span>
          {opp.raw_score != null && <span>Composite <b>{opp.composite}</b></span>}
        </div>
      </div>
      <div className="opp-actions" onClick={(e) => e.stopPropagation()}>
        <button className="btn btn-primary btn-sm" onClick={() => openDrawer(opp.id)}>Open analysis</button>
      </div>
    </div>
  );
}

export function OpportunityMini({ opp }: { opp: Opportunity }) {
  const { openDrawer } = useApp();
  return (
    <div className="opp-mini" onClick={() => openDrawer(opp.id)}>
      <div className="opp-mini-top">
        <span className="opp-mini-score">{opp.raw_score ?? "—"}</span>
      </div>
      <div className="opp-mini-title">{opp.name}</div>
      <span className={`tag ${tagClass(opp.classification)}`}>{tagLabel(opp.classification)}</span>
    </div>
  );
}

/* ---------------- Scorecard (17 dimensions) ---------------- */
export function Scorecard({ opp }: { opp: Opportunity }) {
  if (!opp.factors.length) return null;
  return (
    <Collapsible title={`Scorecard — all ${opp.factors.length} dimensions`} icon="layers" defaultOpen>
      <p style={{ marginTop: 0 }}>
        Composite {opp.composite} is reference only — the {opp.factors.length} factors below are the real picture.
        <span className="source-tag"> (A) = assumption-based</span>
      </p>
      <div className="score-bars">
        {opp.factors.map((f) => (
          <div className="score-bar-row" key={f.key}>
            <div className="score-bar-label">
              {humanFactorKey(f.key)} {f.assumption && <span className="source-tag">(A)</span>}
            </div>
            <div className="score-bar-track">
              <div className={`score-bar-fill${f.assumption ? " assume" : ""}`} style={{ width: `${(f.score / 5) * 100}%` }} />
            </div>
            <div className="score-bar-val">{f.score}/5</div>
          </div>
        ))}
      </div>
      {opp.critical_flags.length > 0 && (
        <p style={{ color: "var(--warning)", marginBottom: 0 }}>
          ⚠ Critical-dimension flags: {opp.critical_flags.join("; ")}
        </p>
      )}
    </Collapsible>
  );
}

/* ---------------- Executive summary ---------------- */
export function ExecutiveSummaryCard({ opp }: { opp: Opportunity }) {
  return (
    <div className="opp-card" style={{ cursor: "default", alignItems: "flex-start" }}>
      <ScoreRing raw={opp.raw_score} max={opp.raw_max} />
      <div className="opp-main">
        <div className="opp-top-row">
          <span className={`tag ${tagClass(opp.classification)}`}>{tagLabel(opp.classification)}</span>
          <span className="tag neutral">Confidence: {confidenceLabel(opp.confidence)}</span>
        </div>
        <div className="opp-title">{opp.name}</div>
        {opp.hypothesis && opp.hypothesis !== "—" && (
          <div className="opp-recommendation">{humanize(opp.hypothesis)}</div>
        )}
        <div className="opp-meta-row">
          <span>Segment <b>{humanize(opp.segment)}</b></span>
          <span>Assumptions <b>{opp.assumption_count}</b></span>
        </div>
        {opp.next_action && opp.next_action !== "—" && (
          <p style={{ fontSize: 13, marginTop: 10, marginBottom: 0, color: "var(--text-secondary)" }}>
            <b>Next validation action:</b> {humanize(opp.next_action)}
          </p>
        )}
      </div>
    </div>
  );
}

/* ---------------- Brief envelope ---------------- */
export function BriefEnvelopeCard({ data }: { data: Record<string, any> }) {
  const dr = data.decision_requested || {};
  const ra = data.recommended_action || {};
  const conf = data.confidence?.opportunity_assessment?.value;
  return (
    <Collapsible title="Executive brief (from the impact workflow)" icon="file" defaultOpen>
      {ra.text && <p><b>Recommended action:</b> {ra.text}</p>}
      <p><b>Decision requested:</b> {dr.text || "—"}</p>
      {conf && <p><b>Confidence:</b> {confidenceLabel(String(conf))} — exposed as a separate signal, not collapsed into the score.</p>}
      <p className="source-tag">{dr.no_build_decision || "No product or build decision has been made."}</p>
    </Collapsible>
  );
}

/* ---------------- Commercial model ---------------- */
export function CommercialModelCard({ data }: { data: CommercialModel }) {
  const order = ["downside", "base", "upside"].filter((k) => data.cases[k]);
  return (
    <div className="card">
      <div className="card-head-title" style={{ marginBottom: 12 }}>
        <Icon name="layers" /> Commercial model — {data.name}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-tertiary)" }}>
              <th style={{ padding: "6px 8px" }}>Metric ({data.currency}/merchant/mo)</th>
              {order.map((k) => (
                <th key={k} style={{ padding: "6px 8px", textTransform: "capitalize", textAlign: "right" }}>{k}</th>
              ))}
            </tr>
          </thead>
          <tbody style={{ fontFamily: "var(--font-data)" }}>
            {[
              ["Total revenue", "total_revenue"],
              ["Total cost", "total_cost"],
              ["Contribution", "contribution"],
            ].map(([label, key]) => (
              <tr key={key} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "7px 8px", fontFamily: "var(--font-ui)", color: "var(--text-secondary)" }}>{label}</td>
                {order.map((k) => (
                  <td key={k} style={{ padding: "7px 8px", textAlign: "right" }}>
                    {money((data.cases[k] as any)[key], data.currency)}
                  </td>
                ))}
              </tr>
            ))}
            <tr style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: "7px 8px", fontFamily: "var(--font-ui)", color: "var(--text-secondary)" }}>Break-even merchants</td>
              {order.map((k) => (
                <td key={k} style={{ padding: "7px 8px", textAlign: "right" }}>
                  {data.cases[k].breakeven_merchants ?? "n/a"}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="source-tag" style={{ marginTop: 12, display: "block", lineHeight: 1.5 }}>{data.note}</p>
    </div>
  );
}

/* ---------------- Experiment ---------------- */
export function ExperimentCard({ data }: { data: Experiment }) {
  const status = (data.result?.status || data.status || "designed").toLowerCase();
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <div className="card-head-title"><Icon name="check-circle" /> {data.title}</div>
        <span className={`pill-status ${status.includes("complete") || status.includes("pass") ? "complete" : "designed"}`}>{status}</span>
      </div>
      <div className="card-body" style={{ paddingTop: 12 }}>
        <p><b>Hypothesis:</b> {humanize(data.hypothesis)}</p>
        <p><b>Success threshold:</b> {humanize(data.success_threshold)}</p>
        <p><b>Kill threshold:</b> {humanize(data.kill_threshold)}</p>
      </div>
    </div>
  );
}

/* ---------------- Monitoring alert ---------------- */
function useNames(): Record<string, string> {
  const { overview } = useApp();
  return nameMap([...(overview?.opportunities ?? []), ...(overview?.archived ?? [])]);
}

export function MonitoringAlertCard({ data }: { data: Record<string, any> }) {
  const names = useNames();
  const tier = (data.tier || "info").toLowerCase();
  const cls = tier === "critical" ? "critical" : tier === "important" ? "important" : "info";
  return (
    <div className={`mon-card ${cls}`}>
      <div className="mon-card-title">{humanize(data.title || data.summary || "", names)}</div>
      <div className="mon-fields">
        <div>
          <div className="mon-field-label">Detected</div>
          <div className="mon-field-value">{data.detected_at || data.created_date || "—"}</div>
        </div>
        <div>
          <div className="mon-field-label">Tier</div>
          <div className="mon-field-value" style={{ textTransform: "capitalize" }}>{tier}</div>
        </div>
        {(data.kb_links || data.opportunity_ids) && (
          <div>
            <div className="mon-field-label">Affected</div>
            <div className="mon-field-value">{humanizeRefs(data.kb_links || data.opportunity_ids, names)}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export function FeedItemCard({ data }: { data: FeedItem }) {
  const names = useNames();
  return (
    <div className={`mon-card ${data.tier === "critical" ? "critical" : data.tier === "important" ? "important" : "info"}`}>
      <div className="mon-card-title">{humanize(data.title, names)}</div>
      <div className="mon-fields">
        <div><div className="mon-field-label">Type</div><div className="mon-field-value" style={{ textTransform: "capitalize" }}>{data.kind.replace(/-/g, " ")}</div></div>
        <div><div className="mon-field-label">Detected</div><div className="mon-field-value">{data.detected_at}</div></div>
        {data.before_after && (
          <div><div className="mon-field-label">Change</div><div className="mon-field-value">{data.before_after.before} → {data.before_after.after}</div></div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Decision journal + calibration ---------------- */
export function CalibrationCard({ data }: { data: JournalPayload["calibration"] }) {
  if (!data) return null;
  return (
    <div className="stat-grid" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
      <div className="stat-card"><div className="stat-num">{data.brier == null ? "—" : data.brier}</div><div className="stat-label">Brier score</div></div>
      <div className="stat-card"><div className="stat-num">{data.n_resolved}</div><div className="stat-label">Resolved</div></div>
      <div className="stat-card"><div className="stat-num">{data.n_open}</div><div className="stat-label">Open</div></div>
      <div className="stat-card"><div className="stat-num">{data.n_overdue}</div><div className="stat-label">Overdue</div></div>
    </div>
  );
}

export function DecisionJournalEntry({ data }: { data: Prediction }) {
  const { openDetail } = useApp();
  const resolved = data.outcome !== null;
  return (
    // Phase 4 — a semantic button opening the full prediction detail
    // (rationale, linked records, outcome) in the DetailDrawer.
    <button
      type="button"
      className="card card-clickable"
      style={{ marginBottom: 10 }}
      onClick={() => openDetail("prediction", data.id)}
      aria-label={`Open prediction detail: ${humanize(data.statement)}`}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "flex-start" }}>
        <div className="card-head-title" style={{ fontWeight: 600 }}>Prediction</div>
        <span className={`pill-status ${resolved ? "complete" : "designed"}`}>
          {resolved ? (data.outcome ? "came true" : "did not happen") : "open"}
        </span>
      </div>
      <div className="card-body" style={{ paddingTop: 10 }}>
        <p style={{ color: "var(--text)" }}>{humanize(data.statement)}</p>
        <p className="source-tag">
          p={Math.round(data.p * 100)}% · logged {data.made} · due {data.resolve_by}
          {data.brier != null && ` · Brier ${data.brier}`}
        </p>
      </div>
    </button>
  );
}

/* ---------------- Research plan (generated opportunities) ---------------- */
export function ResearchPlanCard({ data }: { data: { questions: string[]; gaps: string[] } }) {
  return (
    <>
      {data.gaps?.length > 0 && (
        <Collapsible title="Evidence gaps to close before building" icon="alert" defaultOpen>
          <ul className="evidence-list">
            {data.gaps.map((g, i) => (
              <li key={i}><span className="dot weak" /><span>{g}</span></li>
            ))}
          </ul>
        </Collapsible>
      )}
      {data.questions?.length > 0 && (
        <Collapsible title="Customer-research plan (non-leading interview questions)" icon="users" defaultOpen>
          <div className="survey-q-list">
            {data.questions.map((q, i) => (
              <div className="survey-q-row" key={i}>
                <span className="survey-q-num">{String(i + 1).padStart(2, "0")}</span>
                <span className="survey-q-text">{q}</span>
              </div>
            ))}
          </div>
        </Collapsible>
      )}
    </>
  );
}

/* ---------------- Evidence ---------------- */
export function EvidenceCard({ data }: { data: EvidenceRef }) {
  const { openDetail } = useApp();
  const label = data.title && data.title !== "—" ? data.title : "Customer-evidence record";
  return (
    <Collapsible title={`${label}${data.weak ? " · lead, not a finding" : ""}`} icon="file">
      <p className="source-tag">
        Strength {String(data.strength)} · confidence {confidenceLabel(data.confidence)} · {data.role}
        {data.segment && data.segment !== "—" ? ` · ${humanize(data.segment)}` : ""}
      </p>
      {!data.resolved && <p style={{ color: "var(--warning)" }}>Referenced but not yet on file.</p>}
      <button type="button" className="evidence-list-link" onClick={() => openDetail("evidence", data.ev_id)}>
        View full evidence detail →
      </button>
    </Collapsible>
  );
}

/* ---------------- helpers for detail views ---------------- */
export function scoreBarPct(f: { score: number }): number {
  return scorePct(f.score, 5);
}

export function assumptionLine(a: Assumption): string {
  return `${a.factor_key}: ${a.text}`;
}
