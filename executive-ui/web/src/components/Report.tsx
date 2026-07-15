// Phase 4 — the web report for one opportunity (/report/OPP-nnn).
//
// Executive-readable rendering of the SAME brief read model the API serves
// (GET /executive-api/brief/{id}) — no second brief model, no recomputation.
// Every listed record is clickable through the existing drawers: evidence,
// assumptions, monitoring events, predictions, and approved Merchant Voice
// findings. Source URLs render only through the safe external-link widget.
// Absent data renders as an honest empty state; unknown ids get a safe
// not-found page. Works in light/dark mode and on mobile (single column).
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../store";
import { confidenceLabel, humanFactorKey, tagClass, tagLabel } from "../lib/format";
import { humanize, humanizeRef, nameMap } from "../lib/labels";
import type { BriefPayload, Citation, UserBriefPayload } from "../types";
import Icon from "./Icon";
import Markdown from "./Markdown";
import { ExternalSourceLink, FreshnessBadge } from "./Provenance";

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="report-section">
      <div className="section-label">{label}</div>
      {children}
    </section>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <p className="source-tag" style={{ display: "block" }}>{text}</p>;
}

// The merchant-finding drawer renders from a Citation-shaped payload
// (Phase 2H); build one from the brief's already-safe finding fields.
function findingToCitation(f: Record<string, unknown>): Citation {
  const type = String(f.finding_type ?? "");
  const band = String(f.strength_band ?? "");
  const role = type === "contradiction" ? "contradictory"
    : type === "concept_reaction" ? "concept_reaction"
    : band === "insufficient" || band === "single_signal" ? "weak_lead" : "primary";
  return {
    id: String(f.finding_id ?? ""),
    type: "merchant_finding",
    title: String(f.approved_statement ?? ""),
    role,
    target: { type: "internal_route", value: `/merchant-findings/${String(f.finding_id ?? "")}` },
    metadata: {
      campaign_id: f.campaign_id, method: f.method, segment_id: f.segment_id,
      strength_band: f.strength_band, support_count: f.support_count,
      contradiction_count: f.contradiction_count, denominator: f.denominator,
      denominator_definition: f.denominator_definition,
    },
  };
}

// Phase 6 — the web report for a persisted user opportunity. Honest partial
// rendering: sections without data say "Not yet defined"; nothing is scored
// or fabricated; monitoring state comes from the stored configuration.
function UserReport({ brief }: { brief: UserBriefPayload }) {
  const text = (v: string | null) =>
    v ? <p>{v}</p> : <EmptyNote text="Not yet defined." />;
  const list = (items: string[], empty: string) =>
    items.length === 0 ? <EmptyNote text={empty} /> : (
      <ul className="evidence-list">
        {items.map((x, i) => <li key={i}><span className="dot" /><span>{x}</span></li>)}
      </ul>
    );
  const mon = brief.monitoring;
  const monLabel = mon.status === "not_configured" ? "Monitoring is not configured for this opportunity."
    : mon.status === "never_run" ? "Configured — awaiting monitoring run (no runner is connected yet)."
    : mon.status === "paused" ? "Monitoring configuration is paused."
    : mon.status === "error" ? `Monitoring error: ${mon.last_error ?? "unknown"}`
    : "Monitoring is active.";
  return (
    <section className="view" id="view-report">
      <div className="panel-wrap report-page">
        <div className="panel-title-row" style={{ alignItems: "flex-start" }}>
          <div>
            <h1 className="panel-title" style={{ marginBottom: 6 }} data-testid="report-title">
              {brief.title}
            </h1>
            <div className="panel-sub">
              {brief.opportunity_id} · generated {brief.generated_at} · v{brief.version}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <span className="tag neutral">{brief.classification_label}</span>
              {brief.is_archived && <span className="tag reject">Archived</span>}
              <span className="tag neutral">Your opportunity</span>
            </div>
          </div>
        </div>
        <div className="banner-note"><Icon name="alert" /><span>{brief.decision_banner}</span></div>

        <Section label="Product definition">{text(brief.product_definition)}</Section>
        <Section label="Problem statement">{text(brief.problem_statement)}</Section>
        <Section label="Target segment">{text(brief.target_segment)}</Section>
        <Section label="Customer description">{text(brief.customer_description)}</Section>
        <Section label="Value proposition">{text(brief.value_proposition)}</Section>
        <Section label={`Assumptions (${brief.assumptions.length})`}>
          {list(brief.assumptions, "No assumptions recorded yet.")}
        </Section>
        <Section label="Risks">{list(brief.risks, "No risks recorded yet.")}</Section>
        <Section label="Unknowns">{list(brief.unknowns, "No unknowns recorded yet.")}</Section>
        <Section label="Recommended next actions">
          {list(brief.next_actions, "No next actions recorded yet.")}
        </Section>
        <Section label="Monitoring">
          <p data-testid="user-report-monitoring">{monLabel}</p>
          {mon.status !== "not_configured" && (
            <p className="source-tag" style={{ display: "block" }}>
              Cadence (intended): {mon.cadence} · last run {mon.last_run_at ?? "unavailable — never run"}
            </p>
          )}
        </Section>
        <Section label="Evidence & scoring">
          <EmptyNote text="No engine score and no evidence citations exist for a user draft — validation has not happened yet, and nothing is fabricated." />
        </Section>
        <Section label="Provenance">
          <p className="source-tag" style={{ display: "block" }}>
            Created {brief.created_at}
            {brief.created_from_analysis ? " from a grounded copilot analysis" : ""} · last updated {brief.updated_at}
          </p>
        </Section>
      </div>
    </section>
  );
}

export default function Report() {
  const { reportOppId, overview, openDetail, goReports } = useApp();
  const [brief, setBrief] = useState<BriefPayload | UserBriefPayload | null | undefined>(undefined); // undefined = loading
  const names = nameMap([...(overview?.opportunities ?? []), ...(overview?.archived ?? [])]);

  useEffect(() => {
    let cancel = false;
    setBrief(undefined);
    if (!reportOppId) {
      setBrief(null);
      return;
    }
    api.brief(reportOppId).then((b) => {
      if (!cancel) setBrief(b);
    });
    return () => {
      cancel = true;
    };
  }, [reportOppId]);

  if (brief === undefined) {
    return (
      <section className="view" id="view-report">
        <div className="panel-wrap report-page">
          <div className="skeleton" style={{ height: 32, width: 340, marginBottom: 16 }} />
          <div className="skeleton" style={{ height: 120, marginBottom: 12 }} />
          <div className="skeleton" style={{ height: 220 }} />
        </div>
      </section>
    );
  }

  if (brief === null) {
    return (
      <section className="view" id="view-report">
        <div className="panel-wrap report-page">
          <div className="empty-state" style={{ paddingTop: 60 }} data-testid="report-not-found">
            <Icon name="alert" className="icon" />
            <div className="empty-state-title">Report not found</div>
            No brief exists for this address. The opportunity id may be wrong, or the API may be
            unavailable.
            <div style={{ marginTop: 16 }}>
              <button type="button" className="btn btn-primary" onClick={goReports}>
                Back to Reports &amp; Briefs
              </button>
            </div>
          </div>
        </div>
      </section>
    );
  }

  if (brief.record_type === "user_opportunity") {
    return <UserReport brief={brief} />;
  }

  const s = brief.score_summary;
  const envelope = brief.brief_envelope ?? {};
  const decisionRequested = (envelope.decision_requested ?? {}) as Record<string, unknown>;
  const recommendedAction = (envelope.recommended_action ?? {}) as Record<string, unknown>;
  const contradictions = brief.evidence.filter((e) => e.role === "contradictory");
  const mv = brief.merchant_voice;

  return (
    <section className="view" id="view-report">
      <div className="panel-wrap report-page">
        <div className="panel-title-row" style={{ alignItems: "flex-start" }}>
          <div>
            <h1 className="panel-title" style={{ marginBottom: 6 }} data-testid="report-title">
              {brief.title}
            </h1>
            <div className="panel-sub">
              {brief.opportunity_id} · generated {brief.generated_at}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              <span className={`tag ${tagClass(brief.classification)}`}>{tagLabel(brief.classification)}</span>
              <span className="tag neutral">Confidence: {confidenceLabel(brief.confidence)}</span>
              {brief.is_archived && <span className="tag reject">Archived</span>}
            </div>
          </div>
        </div>

        <div className="banner-note"><Icon name="alert" /><span>{brief.decision_banner}</span></div>

        <Section label="Score summary">
          <div className="stat-grid">
            <div className="stat-card"><div className="stat-num">{s.raw_score ?? "—"}</div><div className="stat-label">Raw score / {s.raw_max}</div></div>
            <div className="stat-card"><div className="stat-num">{s.composite ?? "—"}</div><div className="stat-label">Composite (reference)</div></div>
            <div className="stat-card"><div className="stat-num">{s.assumption_count}</div><div className="stat-label">Assumption-based factors</div></div>
          </div>
          {s.critical_flags.length > 0 && (
            <p style={{ color: "var(--warning)", fontSize: 13 }}>⚠ Critical flags: {s.critical_flags.join("; ")}</p>
          )}
        </Section>

        <Section label="Executive summary">
          {(recommendedAction.text || decisionRequested.text) ? (
            <>
              {typeof recommendedAction.text === "string" && <p><b>Recommended action:</b> {recommendedAction.text}</p>}
              {typeof decisionRequested.text === "string" && <p><b>Decision requested:</b> {decisionRequested.text}</p>}
            </>
          ) : (
            <EmptyNote text="No executive brief envelope is available for this opportunity." />
          )}
        </Section>

        <Section label="Product definition & problem framing">
          <p><b>Proposition:</b> {humanize(brief.hypothesis, names) || "—"}</p>
          <p><b>Target segment:</b> {humanize(brief.segment) || "—"}</p>
          <p><b>Job-to-be-done:</b> {humanize(brief.jtbd) || "—"}</p>
        </Section>

        <Section label={`Key evidence (${brief.evidence.length})`}>
          {brief.evidence.length === 0 ? (
            <EmptyNote text="This scorecard cites no evidence records — every factor is assumption-based." />
          ) : (
            <div className="list-card">
              {brief.evidence.map((e) => (
                <button type="button" className="list-row clickable" key={e.ev_id}
                  onClick={() => openDetail("evidence", e.ev_id)}
                  aria-label={`Open evidence detail: ${e.title !== "—" ? e.title : e.ev_id}`}>
                  <div className="list-row-icon"><Icon name="file" size={16} /></div>
                  <div className="list-row-main">
                    <div className="list-row-title">{e.title !== "—" ? e.title : "Customer-evidence record"}</div>
                    <div className="list-row-sub">
                      {e.source_title ?? "Internal record"} · strength {String(e.strength)}
                    </div>
                  </div>
                  <div className="list-row-meta"><FreshnessBadge status={e.freshness_status} /></div>
                </button>
              ))}
            </div>
          )}
        </Section>

        <Section label="Contradictions">
          {contradictions.length === 0 && (!brief.contradictory_evidence || brief.contradictory_evidence === "—") ? (
            <EmptyNote text="No contradictory evidence is recorded. Supporting evidence is preserved regardless." />
          ) : (
            <>
              {brief.contradictory_evidence && brief.contradictory_evidence !== "—" && (
                <p>{humanize(brief.contradictory_evidence, names)}</p>
              )}
              {contradictions.map((e) => (
                <button type="button" className="linked-chip" key={e.ev_id}
                  onClick={() => openDetail("evidence", e.ev_id)}
                  aria-label={`Open contradictory evidence: ${e.ev_id}`}>
                  {e.title !== "—" ? e.title : e.ev_id}
                </button>
              ))}
            </>
          )}
        </Section>

        <Section label={`Assumptions (${brief.assumptions.length})`}>
          {brief.assumptions.length === 0 ? (
            <EmptyNote text="No tracked assumptions." />
          ) : (
            <div className="linked-chip-row">
              {brief.assumptions.map((a) => (
                <button type="button" className="linked-chip" key={`${a.opportunity_id}::${a.factor_key}`}
                  onClick={() => openDetail("assumption", `${a.opportunity_id}::${a.factor_key}`)}
                  aria-label={`Open assumption detail: ${humanFactorKey(a.factor_key)}`}>
                  {humanFactorKey(a.factor_key)} · {a.status}
                </button>
              ))}
            </div>
          )}
        </Section>

        <Section label="Monitoring">
          {brief.monitoring.state && (
            <p style={{ fontSize: 13 }}>
              <b>Status:</b> {brief.monitoring.state.status} — {brief.monitoring.state.status_note}
            </p>
          )}
          {brief.monitoring.events.length === 0 ? (
            <EmptyNote text="No monitoring events reference this opportunity." />
          ) : (
            <div className="linked-chip-row">
              {brief.monitoring.events.map((e) => (
                <button type="button" className="linked-chip" key={e.id}
                  onClick={() => openDetail("monitoring_update", e.id)}
                  aria-label={`Open monitoring event: ${humanize(e.title, names)}`}>
                  {humanize(e.title, names)} · {e.detected_at}
                </button>
              ))}
            </div>
          )}
        </Section>

        <Section label={`Predictions (${brief.predictions.length})`}>
          {brief.predictions.length === 0 ? (
            <EmptyNote text="No logged predictions reference this opportunity." />
          ) : (
            <div className="list-card">
              {brief.predictions.map((p) => (
                <button type="button" className="list-row clickable" key={p.id}
                  onClick={() => openDetail("prediction", p.id)}
                  aria-label={`Open prediction detail: ${humanize(p.statement, names)}`}>
                  <div className="list-row-icon"><Icon name="check-circle" size={16} /></div>
                  <div className="list-row-main">
                    <div className="list-row-title">{humanize(p.statement, names)}</div>
                    <div className="list-row-sub">p={Math.round(p.p * 100)}% · due {p.resolve_by}</div>
                  </div>
                  <div className="list-row-meta">
                    <span className={`pill-status ${p.outcome !== null ? "complete" : "designed"}`}>
                      {p.outcome !== null ? (p.outcome ? "came true" : "did not happen") : "open"}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Section>

        <Section label="Merchant Voice findings (approved)">
          {!mv.available || mv.findings.length === 0 ? (
            <EmptyNote text={mv.note || "No approved Merchant Voice findings are available."} />
          ) : (
            <>
              <div className="linked-chip-row">
                {mv.findings.map((f) => {
                  const c = findingToCitation(f);
                  return (
                    <button type="button" className="linked-chip" key={c.id}
                      onClick={() => openDetail("merchant_finding", c.id, c)}
                      aria-label={`Open merchant finding: ${c.title}`}>
                      {c.title}
                    </button>
                  );
                })}
              </div>
              <EmptyNote text={mv.note} />
            </>
          )}
        </Section>

        <Section label="Risks">
          {brief.risks.length === 0 ? (
            <EmptyNote text="No risks are recorded in the impact brief for this opportunity." />
          ) : (
            <ul className="evidence-list">{brief.risks.map((r, i) => <li key={i}><span className="dot weak" /><span>{humanize(r, names)}</span></li>)}</ul>
          )}
        </Section>

        <Section label="Unknowns / open questions">
          {brief.unknowns.length === 0 ? (
            <EmptyNote text="No open evidence gaps are recorded for this opportunity." />
          ) : (
            <ul className="evidence-list">{brief.unknowns.map((u, i) => <li key={i}><span className="dot weak" /><span>{humanize(u, names)}</span></li>)}</ul>
          )}
        </Section>

        <Section label="Recommended next actions">
          {brief.recommended_next_actions.length === 0 ? (
            <EmptyNote text="No recommended next action is recorded." />
          ) : (
            <ul className="evidence-list">{brief.recommended_next_actions.map((a, i) => <li key={i}><span className="dot" /><span>{humanize(a, names)}</span></li>)}</ul>
          )}
        </Section>

        {brief.brief_markdown && (
          <Section label="Committed recommendation brief">
            <div className="card" style={{ cursor: "default" }} data-testid="report-brief-markdown">
              <Markdown text={brief.brief_markdown} />
            </div>
          </Section>
        )}

        <Section label="Sources appendix">
          {brief.sources.length === 0 ? (
            <EmptyNote text="No external sources are recorded behind this opportunity's cited evidence." />
          ) : (
            <div className="list-card" data-testid="report-sources">
              {brief.sources.map((src, i) => (
                <div className="list-row" key={i}>
                  <div className="list-row-icon"><Icon name="book" size={16} /></div>
                  <div className="list-row-main">
                    <div className="list-row-title">{src.source_title ?? "Internal record"}</div>
                    <div className="list-row-sub">
                      {src.publisher ? `${src.publisher} · ` : ""}
                      {src.retrieved_at ? `retrieved ${src.retrieved_at} · ` : ""}
                      {humanizeRef(src.evidence_ids[0] ?? "", names)}
                      {src.evidence_ids.length > 1 ? ` +${src.evidence_ids.length - 1} more` : ""}
                    </div>
                    <ExternalSourceLink url={src.source_url} label={src.source_title} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </section>
  );
}
