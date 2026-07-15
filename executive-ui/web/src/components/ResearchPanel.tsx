// Research workspace (Phase R3) — runs list, run detail (queries, sources
// with freshness + safe links, candidate claims), human review, and manual
// claim entry. Everything shown comes from the research API verbatim; empty,
// partial, and failed states are rendered honestly (no fabricated activity).
import { useCallback, useEffect, useState } from "react";
import { researchApi } from "../lib/researchApi";
import { safeExternalUrl } from "../lib/safeUrl";
import Icon from "./Icon";
import type { ResearchCandidate, ResearchRun, ResearchRunSummary, ResearchSource } from "../types";

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending — not executed yet",
  running: "Running",
  complete: "Complete",
  partial: "Partial — some steps failed",
  failed: "Failed",
};

function StatusBadge({ status }: { status: string }) {
  return <span className={`research-status research-status-${status}`}>{STATUS_LABEL[status] ?? status}</span>;
}

function SourceRow({ s, selectable, selected, onToggle }: {
  s: ResearchSource; selectable: boolean; selected: boolean; onToggle: () => void;
}) {
  const url = safeExternalUrl(s.canonical_url);
  return (
    <div className={`research-source${s.duplicate_of ? " duplicate" : ""}`}>
      {selectable && (
        <input type="checkbox" checked={selected} onChange={onToggle}
          aria-label={`cite ${s.id}`} disabled={!!s.duplicate_of} />
      )}
      <div className="research-source-main">
        <div className="research-source-title">
          {s.title || s.domain}
          {s.freshness_status && s.freshness_status !== "unknown" && (
            <span className={`freshness-badge freshness-${s.freshness_status}`}
              title={s.freshness_reason}>{s.freshness_status}</span>
          )}
          {s.freshness_status === "unknown" && (
            <span className="freshness-badge freshness-unknown" title={s.freshness_reason}>
              no publication date
            </span>
          )}
          {s.duplicate_of && <span className="research-dup" title={`duplicate of ${s.duplicate_of}`}>duplicate</span>}
        </div>
        <div className="research-source-meta">
          {s.publisher && <span>{s.publisher} · </span>}
          {s.published_at && <span>published {s.published_at.slice(0, 10)} · </span>}
          <span>{s.domain}</span>
          {url ? (
            <>
              {" · "}
              <a href={url} target="_blank" rel="noopener noreferrer">open source</a>
            </>
          ) : (
            <span> · no safe external link</span>
          )}
        </div>
        {s.excerpt && <div className="research-source-excerpt">{s.excerpt.slice(0, 280)}{s.excerpt.length > 280 ? "…" : ""}</div>}
      </div>
    </div>
  );
}

function CandidateRow({ c, onReviewed }: { c: ResearchCandidate; onReviewed: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const review = async (action: "approve" | "reject") => {
    setBusy(true);
    setError(null);
    const res = await researchApi.reviewCandidate(c.id, action);
    setBusy(false);
    if (!res.ok) setError(res.error);
    else onReviewed();
  };
  return (
    <div className={`research-candidate status-${c.status}`}>
      <div className="research-candidate-claim">{c.claim}</div>
      <div className="research-source-meta">
        cites {c.source_ids.length} source{c.source_ids.length === 1 ? "" : "s"} · status: {c.status.replace("_", " ")}
        {c.review_note && <> · note: {c.review_note}</>}
      </div>
      {c.contradicts && (
        <div className="research-contradicts"><Icon name="alert" size={12} /> Recorded contradiction: {c.contradicts}</div>
      )}
      {c.status === "pending_review" && (
        <div className="research-review-actions">
          <button className="btn-secondary" disabled={busy} onClick={() => review("approve")}>Approve</button>
          <button className="btn-secondary" disabled={busy} onClick={() => review("reject")}>Reject</button>
          <span className="research-review-hint">
            Approval marks this usable as clearly-labelled external research — it never becomes repository evidence.
          </span>
        </div>
      )}
      {error && <div className="banner-note"><Icon name="alert" /> {error}</div>}
    </div>
  );
}

function RunDetail({ runId, onBack }: { runId: string; onBack: () => void }) {
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [claim, setClaim] = useState("");
  const [claimError, setClaimError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const res = await researchApi.getRun(runId);
    if (res.ok) { setRun(res.data); setError(null); }
    else setError(res.error);
  }, [runId]);

  useEffect(() => { void reload(); }, [reload]);

  const execute = async () => {
    setExecuting(true);
    const res = await researchApi.executeRun(runId);
    setExecuting(false);
    if (res.ok) setRun(res.data);
    else setError(res.error);
  };

  const submitClaim = async () => {
    if (!claim.trim() || selected.length === 0) return;
    const res = await researchApi.addCandidate(runId, { claim: claim.trim(), source_ids: selected });
    if (!res.ok) { setClaimError(res.error); return; }
    setClaim("");
    setSelected([]);
    setClaimError(null);
    void reload();
  };

  if (error) return (
    <div className="tab-panel">
      <button className="btn-secondary" onClick={onBack}>← All runs</button>
      <div className="banner-note" style={{ marginTop: 12 }}><Icon name="alert" /> {error}</div>
    </div>
  );
  if (!run) return <div className="tab-panel">Loading research run…</div>;

  const sources = run.sources ?? [];
  const candidates = run.candidate_evidence ?? [];
  return (
    <div className="tab-panel research-run-detail">
      <button className="btn-secondary" onClick={onBack}>← All runs</button>
      <h2>{run.title}</h2>
      <div className="research-run-meta">
        <StatusBadge status={run.status} />
        {run.profile && <span className="research-profile-chip">{run.profile}</span>}
        {run.opportunity_ref && <span className="research-profile-chip">{run.opportunity_ref}</span>}
        <span>{run.counts?.queries ?? 0} queries · {run.counts?.sources ?? 0} sources · {run.counts?.candidates ?? 0} candidates</span>
      </div>
      {run.error && <div className="banner-note"><Icon name="alert" /> {run.error}</div>}
      {run.status === "pending" && (
        <button className="send-btn research-execute" disabled={executing} onClick={execute}>
          {executing ? "Executing…" : "Execute run"}
        </button>
      )}

      <h3>Queries</h3>
      {(run.queries ?? []).length === 0 && <p className="empty-note">No queries planned.</p>}
      {(run.queries ?? []).map((q) => (
        <div key={q.id} className={`research-query status-${q.status}`}>
          <span className="research-query-text">{q.query_text}</span>
          <span className="research-source-meta">
            {q.objective && <>{q.objective} · </>}{q.status}
            {q.result_count !== null && <> · {q.result_count} results</>}
            {q.error && <> · {q.error}</>}
          </span>
        </div>
      ))}

      <h3>Sources</h3>
      {sources.length === 0 && <p className="empty-note">No sources recorded{run.status === "pending" ? " — the run has not been executed yet" : ""}.</p>}
      {sources.map((s) => (
        <SourceRow key={s.id} s={s}
          selectable={run.status !== "failed"}
          selected={selected.includes(s.id)}
          onToggle={() => setSelected((cur) =>
            cur.includes(s.id) ? cur.filter((x) => x !== s.id) : [...cur, s.id])} />
      ))}

      {run.status !== "failed" && sources.length > 0 && (
        <div className="research-claim-form">
          <h3>Record a candidate claim</h3>
          <p className="research-review-hint">
            Write a claim supported by the sources you tick above. It starts as
            pending review; a claim with no ticked source cannot be recorded.
          </p>
          <textarea rows={2} value={claim} placeholder="e.g. The UAE has roughly N SMEs according to …"
            onChange={(e) => setClaim(e.target.value)} />
          <button className="btn-secondary" disabled={!claim.trim() || selected.length === 0}
            onClick={submitClaim}>
            Add candidate claim ({selected.length} source{selected.length === 1 ? "" : "s"})
          </button>
          {claimError && <div className="banner-note"><Icon name="alert" /> {claimError}</div>}
        </div>
      )}

      <h3>Candidate claims</h3>
      {candidates.length === 0 && <p className="empty-note">No candidate claims recorded yet.</p>}
      {candidates.map((c) => <CandidateRow key={c.id} c={c} onReviewed={() => void reload()} />)}
    </div>
  );
}

const PROFILES = [
  { value: "", label: "No profile — I'll write queries later" },
  { value: "generic", label: "Generic opportunity research" },
  { value: "sme-financial-product", label: "SME financial-product opportunity" },
];

function CreateRunForm({ onCreated }: { onCreated: (run: ResearchRun) => void }) {
  const [title, setTitle] = useState("");
  const [profile, setProfile] = useState("sme-financial-product");
  const [market, setMarket] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!title.trim()) return;
    setBusy(true);
    const res = await researchApi.createRun({
      title: title.trim(),
      ...(profile ? { profile, context: market.trim() ? { market: market.trim() } : undefined } : {}),
    });
    setBusy(false);
    if (!res.ok) { setError(res.error); return; }
    setError(null);
    setTitle("");
    onCreated(res.data);
  };

  return (
    <div className="research-create-form">
      <h3>New research run</h3>
      <input type="text" value={title} placeholder="Run title, e.g. UAE SME card market sizing"
        onChange={(e) => setTitle(e.target.value)} aria-label="Run title" />
      <select value={profile} onChange={(e) => setProfile(e.target.value)} aria-label="Research profile">
        {PROFILES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
      </select>
      <input type="text" value={market} placeholder="Market (optional, default UAE)"
        onChange={(e) => setMarket(e.target.value)} aria-label="Market" />
      <button className="btn-secondary" disabled={!title.trim() || busy} onClick={submit}>
        Create run
      </button>
      {error && <div className="banner-note"><Icon name="alert" /> {error}</div>}
    </div>
  );
}

export default function ResearchPanel() {
  const [runs, setRuns] = useState<ResearchRunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openRunId, setOpenRunId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const res = await researchApi.listRuns();
    if (res.ok) { setRuns(res.data.runs); setError(null); }
    else { setRuns(null); setError(res.error); }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  if (openRunId) {
    return <RunDetail runId={openRunId} onBack={() => { setOpenRunId(null); void reload(); }} />;
  }

  return (
    <div className="tab-panel">
      <h2>External research</h2>
      <p className="research-review-hint">
        Runs execute bounded web research and record sources verbatim. Claims you
        record from sources are candidates pending human review — approval makes
        them citable as clearly-labelled external research, never repository evidence.
      </p>
      {error && <div className="banner-note"><Icon name="alert" /> {error}</div>}
      <CreateRunForm onCreated={(run) => { setOpenRunId(run.id); }} />
      <h3>Runs</h3>
      {runs === null && !error && <p className="empty-note">Loading…</p>}
      {runs !== null && runs.length === 0 && (
        <p className="empty-note">No research runs yet — create the first one above.</p>
      )}
      {(runs ?? []).map((r) => (
        <button key={r.id} type="button" className="research-run-row" onClick={() => setOpenRunId(r.id)}>
          <span className="research-run-title">{r.title}</span>
          <StatusBadge status={r.status} />
          {r.opportunity_ref && <span className="research-profile-chip">{r.opportunity_ref}</span>}
          <span className="research-source-meta">{r.created_at.slice(0, 10)}</span>
        </button>
      ))}
    </div>
  );
}
