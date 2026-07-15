// A small, generic detail drawer for record types that aren't opportunities
// (evidence, assumptions, monitoring updates). Deliberately separate from
// Drawer.tsx (the existing opportunity drawer) so that component is never
// touched — this one only ever reads from data already loaded in `overview`,
// never fabricates a field, and always has a safe "not available" state.
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../store";
import { confidenceLabel, humanFactorKey } from "../lib/format";
import { humanize, humanizeRef, nameMap } from "../lib/labels";
import type { FeedItem, JournalPayload, MonitoringPayload } from "../types";
import Icon from "./Icon";
import Markdown from "./Markdown";
import { ExternalSourceLink, FreshnessBadge } from "./Provenance";

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

  // Phase 4 — full monitoring events + per-event summary markdown are loaded
  // lazily the first time a monitoring detail is opened; predictions likewise
  // for the prediction detail. Failures degrade to the safe fallback bodies
  // below — never a crash, never invented data.
  const [mon, setMon] = useState<MonitoringPayload | null>(null);
  const [summaries, setSummaries] = useState<Record<string, { markdown: string; truncated: boolean } | null>>({});
  const [journal, setJournal] = useState<JournalPayload | null>(null);
  const monId = detailTarget?.type === "monitoring_update" ? detailTarget.id : null;
  const predId = detailTarget?.type === "prediction" ? detailTarget.id : null;
  useEffect(() => {
    if (monId && mon === null) {
      api.monitoring().then(setMon)
        .catch(() => setMon({ events: [], alerts: [], summaries: [], summary_state: null }));
    }
  }, [monId, mon]);
  useEffect(() => {
    if (monId && /^EVT-\d{4}-W\d{2}-\d{3}$/.test(monId) && !(monId in summaries)) {
      api.monitoringSummary(monId).then((md) => setSummaries((s) => ({ ...s, [monId]: md })));
    }
  }, [monId, summaries]);
  useEffect(() => {
    if (predId && journal === null) {
      api.journal().then(setJournal)
        .catch(() => setJournal({ predictions: [], calibration: null }));
    }
  }, [predId, journal]);

  const show = !!detailTarget;

  let title = "";
  let body: React.ReactNode = null;

  if (detailTarget?.type === "evidence") {
    const e = overview?.evidence.find((x) => x.ev_id === detailTarget.id);
    const names = nameMap([...(overview?.opportunities ?? []), ...(overview?.archived ?? [])]);
    if (!e) {
      title = "Evidence";
      body = <Unavailable label="This evidence record is not on file or could not be loaded." />;
    } else {
      title = e.title !== "—" ? e.title : "Customer-evidence record";
      const contradiction = e.contradictory_evidence && e.contradictory_evidence !== "—"
        ? e.contradictory_evidence : null;
      body = (
        <div className="drawer-body">
          <p className="source-tag" style={{ display: "block", marginBottom: 10 }}>{e.ev_id}</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
            <FreshnessBadge status={e.freshness_status} />
            {e.weak && <span className="chip">lead, not a finding</span>}
          </div>
          {e.freshness_reason && (
            <p className="source-tag" style={{ display: "block", marginBottom: 12 }} data-testid="freshness-reason">
              {e.freshness_reason}
            </p>
          )}
          <dl className="detail-fields">
            <div><dt>Strength</dt><dd>{String(e.strength)}</dd></div>
            <div><dt>Confidence</dt><dd>{confidenceLabel(e.confidence)}</dd></div>
            <div><dt>Status</dt><dd>{humanize(e.status) || "—"}</dd></div>
            <div><dt>Contradictory evidence</dt><dd>{contradiction ?? "None recorded"}</dd></div>
            <div><dt>Segment</dt><dd>{humanize(e.segment) !== "—" ? humanize(e.segment) : "Not recorded"}</dd></div>
            <div><dt>Role</dt><dd>{e.role || "—"}</dd></div>
            <div><dt>Source</dt><dd>{e.source_title ?? "Internal record"}</dd></div>
            <div><dt>Publisher</dt><dd>{e.publisher ?? "—"}</dd></div>
            <div><dt>Date of evidence</dt><dd>{e.publication_date ?? e.date_of_evidence ?? "Not recorded"}</dd></div>
            <div><dt>Retrieved</dt><dd>{e.retrieved_at ?? "Not recorded"}</dd></div>
            <div><dt>Last verified</dt><dd>{e.last_verified_at ?? "Not recorded"}</dd></div>
            <div><dt>Access</dt><dd>{humanize(e.access_label ?? e.source_type) || "—"}</dd></div>
          </dl>
          {e.excerpt && (
            <blockquote className="excerpt-quote" data-testid="evidence-excerpt">{e.excerpt}</blockquote>
          )}
          {(e.linked_opportunity_ids?.length ?? 0) > 0 && (
            <>
              <div className="mon-field-label" style={{ marginTop: 10 }}>Linked opportunities</div>
              <div className="linked-chip-row">
                {e.linked_opportunity_ids!.map((oid) => (
                  <button key={oid} type="button" className="linked-chip"
                    onClick={() => openDrawer(oid)}
                    aria-label={`Open linked opportunity: ${names[oid] || oid}`}>
                    {names[oid] || oid}
                  </button>
                ))}
              </div>
            </>
          )}
          {(e.linked_assumption_ids?.length ?? 0) > 0 && (
            <>
              <div className="mon-field-label" style={{ marginTop: 10 }}>Linked assumptions</div>
              <div className="linked-chip-row">
                {e.linked_assumption_ids!.map((aid) => {
                  const [oppId, factorKey] = aid.split("::");
                  return (
                    <button key={aid} type="button" className="linked-chip"
                      onClick={() => openDetail("assumption", aid)}
                      aria-label={`Open linked assumption: ${humanFactorKey(factorKey || "")} (${names[oppId] || oppId})`}>
                      {humanFactorKey(factorKey || "")} · {names[oppId] || oppId}
                    </button>
                  );
                })}
              </div>
            </>
          )}
          <ExternalSourceLink url={e.source_url} label={e.source_title} />
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
  } else if (detailTarget?.type === "merchant_finding") {
    // Rendered entirely from the citation itself (Phase 2H) — copilot-backend
    // already embeds everything a safe detail view may show in `metadata`;
    // there is no separate lookup, and no participant/identity/transcript
    // field is ever present in this object in the first place.
    const c = detailTarget.payload;
    const meta = (c?.metadata ?? {}) as Record<string, unknown>;
    if (!c) {
      title = "Merchant finding";
      body = <Unavailable label="This Merchant Voice finding is not available." />;
    } else {
      title = "Merchant Voice finding";
      body = (
        <div className="drawer-body">
          <p className="source-tag" style={{ display: "block", marginBottom: 14 }}>{c.id}</p>
          <p style={{ marginTop: 0 }}>{humanize(c.title)}</p>
          <dl className="detail-fields">
            <div><dt>Campaign</dt><dd>{String(meta.campaign_id ?? "—")}</dd></div>
            <div><dt>Method</dt><dd>{humanize(String(meta.method ?? "")) || "—"}</dd></div>
            <div><dt>Segment</dt><dd>{meta.segment_id ? String(meta.segment_id) : "Not segment-specific"}</dd></div>
            <div><dt>Strength band</dt><dd>{humanize(String(meta.strength_band ?? "")) || "—"}</dd></div>
            <div><dt>Support count</dt><dd>{String(meta.support_count ?? "—")}</dd></div>
            <div><dt>Contradiction count</dt><dd>{String(meta.contradiction_count ?? "—")}</dd></div>
            <div><dt>Denominator</dt><dd>{meta.denominator_definition ? `${meta.denominator} — ${meta.denominator_definition}` : String(meta.denominator ?? "—")}</dd></div>
          </dl>
          <p className="source-tag" style={{ display: "block", marginTop: 6 }}>
            A Merchant Voice research signal — not authoritative Part A evidence, and never proof that
            pain, frequency, or willingness to pay have been established.
          </p>
        </div>
      );
    }
  } else if (detailTarget?.type === "monitoring_update") {
    const names = nameMap([...(overview?.opportunities ?? []), ...(overview?.archived ?? [])]);
    const event = mon?.events.find((x) => x.id === detailTarget.id);
    const f = overview?.feed.find((x) => x.id === detailTarget.id);
    if (event) {
      title = "Monitoring event";
      const isInternal = event.adapter === "kb-watcher";
      const details = (event.details ?? {}) as Record<string, unknown>;
      const facts = event.facts;
      const summary = summaries[event.id];
      const summaryLoading = !(event.id in summaries);
      const detailRows = Object.entries(details).filter(([, v]) => v !== null && v !== "");
      const sourceTitle = (details.source_title ?? details.source) as string | undefined;
      const sourceUrl = (details.source_url ?? details.url) as string | undefined;
      const fetchedAt = (details.fetched_at ?? details.fetched) as string | undefined;
      const related = [event.thread_id, event.dedup_of].filter(Boolean) as string[];
      body = (
        <div className="drawer-body">
          <p style={{ marginTop: 0, fontWeight: 600 }}>{humanize(event.title, names)}</p>
          <p className="source-tag" style={{ display: "block", marginBottom: 8 }}>{event.id}</p>
          {isInternal && (
            <div className="no-source-note" data-testid="internal-kb-note" style={{ marginBottom: 12 }}>
              <b>Internal knowledge-base change</b> — this event was detected by the repository
              watcher; no external source URL applies.
            </div>
          )}
          <dl className="detail-fields">
            <div><dt>Status</dt><dd style={{ textTransform: "capitalize" }}>{event.status || "—"}</dd></div>
            <div><dt>Detected</dt><dd>{event.detected_at || "—"}</dd></div>
            <div><dt>Tier</dt><dd style={{ textTransform: "capitalize" }}>{event.tier || "—"}</dd></div>
            <div><dt>Event type</dt><dd style={{ textTransform: "capitalize" }}>{String(event.signal_type || "—").replace(/_/g, " ")}</dd></div>
            <div><dt>Detected by</dt><dd>{isInternal ? "Internal knowledge-base watcher" : event.adapter || "—"}</dd></div>
            <div><dt>Affected entity</dt><dd>{humanizeRef(event.entity, names)}</dd></div>
            {sourceTitle && <div><dt>Source</dt><dd>{String(sourceTitle)}</dd></div>}
            {fetchedAt && <div><dt>Fetched</dt><dd>{String(fetchedAt)}</dd></div>}
          </dl>
          {detailRows.length > 0 && (
            <>
              <div className="mon-field-label" style={{ marginTop: 8 }}>What changed</div>
              <dl className="detail-fields" data-testid="event-details" style={{ marginTop: 6 }}>
                {detailRows.map(([k, v]) => (
                  <div key={k}>
                    <dt style={{ textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</dt>
                    <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}
          {facts != null && (Array.isArray(facts) ? facts.length > 0 : Object.keys(facts).length > 0) && (
            <>
              <div className="mon-field-label" style={{ marginTop: 8 }}>Facts</div>
              <dl className="detail-fields" data-testid="event-facts" style={{ marginTop: 6 }}>
                {(Array.isArray(facts)
                  ? facts.map((v, i) => [String(i + 1), v] as [string, unknown])
                  : Object.entries(facts)
                ).map(([k, v]) => (
                  <div key={k}>
                    <dt style={{ textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</dt>
                    <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}
          <div className="mon-field-label" style={{ marginTop: 8 }}>Significance scores</div>
          <div className="linked-chip-row" data-testid="event-scores">
            {Object.entries(event.scores ?? {}).map(([k, v]) => (
              <span className="chip" key={k}>{k} {String(v)}/5</span>
            ))}
          </div>
          {(event.kb_links?.length ?? 0) > 0 && (
            <>
              <div className="mon-field-label" style={{ marginTop: 10 }}>Affected records</div>
              <div className="linked-chip-row">
                {event.kb_links!.map((ref) => {
                  if (/^OPP-\d{3}$/.test(ref)) {
                    return (
                      <button key={ref} type="button" className="linked-chip" onClick={() => openDrawer(ref)}
                        aria-label={`Open affected opportunity: ${names[ref] || ref}`}>
                        {names[ref] || ref}
                      </button>
                    );
                  }
                  if (/^EV-\d{4}-W\d{2}-\d{3}$/.test(ref)) {
                    return (
                      <button key={ref} type="button" className="linked-chip" onClick={() => openDetail("evidence", ref)}
                        aria-label={`Open affected evidence: ${ref}`}>
                        Evidence record ({ref})
                      </button>
                    );
                  }
                  return <span key={ref} className="chip">{humanizeRef(ref, names)}</span>;
                })}
              </div>
            </>
          )}
          {related.length > 0 && (
            <>
              <div className="mon-field-label" style={{ marginTop: 10 }}>Related monitoring events</div>
              <div className="linked-chip-row">
                {related.map((rid) => (
                  <button key={rid} type="button" className="linked-chip"
                    onClick={() => openDetail("monitoring_update", rid)}
                    aria-label={`Open related monitoring event ${rid}`}>
                    {rid}
                  </button>
                ))}
              </div>
            </>
          )}
          {isInternal ? null : sourceUrl !== undefined && (
            <ExternalSourceLink url={String(sourceUrl)} label={sourceTitle ? String(sourceTitle) : null} />
          )}
          <div className="mon-field-label" style={{ marginTop: 14 }}>Detailed summary</div>
          {summaryLoading ? (
            <p className="source-tag" style={{ display: "block" }}>Loading summary…</p>
          ) : summary ? (
            <div data-testid="event-summary">
              <Markdown text={summary.markdown} />
              {summary.truncated && (
                <p className="source-tag" style={{ display: "block" }}>Summary truncated for display.</p>
              )}
            </div>
          ) : (
            <p className="source-tag" style={{ display: "block" }} data-testid="no-event-summary">
              No detailed summary is on file for this event.
            </p>
          )}
        </div>
      );
    } else if (monId && mon === null) {
      title = "Monitoring event";
      body = <div className="drawer-body"><div className="skeleton" style={{ height: 120 }} /></div>;
    } else if (!f) {
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
  } else if (detailTarget?.type === "prediction") {
    // Phase 4 — full prediction detail from the decision journal. Optional
    // fields (rationale, links, outcome) render honestly when absent.
    const names = nameMap([...(overview?.opportunities ?? []), ...(overview?.archived ?? [])]);
    const p = journal?.predictions.find((x) => x.id === detailTarget.id);
    if (journal === null) {
      title = "Prediction";
      body = <div className="drawer-body"><div className="skeleton" style={{ height: 120 }} /></div>;
    } else if (!p) {
      title = "Prediction";
      body = <Unavailable label="This prediction is not in the decision journal or could not be loaded." />;
    } else {
      title = "Prediction";
      const resolved = p.outcome !== null;
      const statusLabel = resolved ? (p.outcome ? "Came true" : "Did not happen") : "Open";
      body = (
        <div className="drawer-body">
          <p style={{ marginTop: 0, fontWeight: 600 }} data-testid="prediction-statement">{humanize(p.statement, names)}</p>
          <p className="source-tag" style={{ display: "block", marginBottom: 10 }}>{p.id}</p>
          <div style={{ marginBottom: 10 }}>
            <span className={`pill-status ${resolved ? "complete" : "designed"}`}>{statusLabel}</span>
          </div>
          <dl className="detail-fields">
            <div><dt>Stated confidence</dt><dd>{Math.round(p.p * 100)}%</dd></div>
            <div><dt>Logged</dt><dd>{p.made || "—"}</dd></div>
            <div><dt>Resolve by</dt><dd>{p.resolve_by || "—"}</dd></div>
            {resolved && <div><dt>Resolved on</dt><dd>{p.resolved_on || "—"}</dd></div>}
            {p.brier != null && <div><dt>Brier score</dt><dd>{p.brier}</dd></div>}
          </dl>
          <div className="mon-field-label">Rationale</div>
          {p.rationale ? (
            <p style={{ marginTop: 6 }} data-testid="prediction-rationale">{humanize(p.rationale, names)}</p>
          ) : (
            <p className="source-tag" style={{ display: "block", marginTop: 6 }} data-testid="no-rationale">
              No rationale was recorded for this prediction.
            </p>
          )}
          {resolved && p.resolution_note && (
            <>
              <div className="mon-field-label" style={{ marginTop: 10 }}>Resolution note</div>
              <p style={{ marginTop: 6 }} data-testid="prediction-resolution">{humanize(p.resolution_note, names)}</p>
            </>
          )}
          {(p.links?.length ?? 0) > 0 ? (
            <>
              <div className="mon-field-label" style={{ marginTop: 10 }}>Linked records</div>
              <div className="linked-chip-row">
                {p.links.map((ref) => {
                  if (/^OPP-\d{3}$/.test(ref)) {
                    return (
                      <button key={ref} type="button" className="linked-chip" onClick={() => openDrawer(ref)}
                        aria-label={`Open linked opportunity: ${names[ref] || ref}`}>
                        {names[ref] || ref}
                      </button>
                    );
                  }
                  if (/^EV-\d{4}-W\d{2}-\d{3}$/.test(ref)) {
                    return (
                      <button key={ref} type="button" className="linked-chip" onClick={() => openDetail("evidence", ref)}
                        aria-label={`Open linked evidence: ${ref}`}>
                        Evidence record ({ref})
                      </button>
                    );
                  }
                  return (
                    <span key={ref} className="chip" title={ref}>
                      {humanizeRef(ref, names)} ({ref})
                    </span>
                  );
                })}
              </div>
            </>
          ) : (
            <p className="source-tag" style={{ display: "block", marginTop: 10 }}>
              No linked records were recorded.
            </p>
          )}
          {p.excluded_from_calibration && (
            <p className="source-tag" style={{ display: "block", marginTop: 10 }}>
              Excluded from calibration (resolved the day it was made).
            </p>
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
