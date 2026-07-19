// Phase R5 / PR4-UI — the analysis-workspace panel for a saved user
// opportunity. Shows the latest COMPLETE preliminary analysis version and
// lets the user re-run the chain explicitly ("Refresh analysis"). Honesty
// rules baked into the rendering:
//   - every machine-generated number carries a PRELIMINARY badge; the score
//     is stated as engine-capped, never as a validated result;
//   - pending claims are visually separated from human-approved ones;
//   - gaps (skipped/missing chain steps) are always listed, never hidden;
//   - the running state names the real chain steps but never fakes
//     per-step completion (the build is one server-side call);
//   - a stale workspace shows a banner instead of silently rebuilding —
//     ordinary reads NEVER trigger the chain.
import { useEffect, useState } from "react";
import { workspaceApi } from "../lib/workspaceApi";
import type {
  MonitoringQuota, WorkspaceDiff, WorkspaceSubscription, WorkspaceVersion,
  WorkspaceVersionSummary,
} from "../types";
import Icon from "./Icon";

const CLAIM_PILL: Record<string, string> = {
  approved: "active",
  pending_review: "review",
  rejected: "reject",
};
const CLAIM_LABEL: Record<string, string> = {
  approved: "Approved (human-reviewed)",
  pending_review: "Pending review",
  rejected: "Rejected",
};

const CHAIN_STEPS = [
  "Searching committed knowledge-base evidence",
  "Running bounded external research",
  "Extracting source-verified candidate claims",
  "Computing the preliminary score (real engine, assumption-capped)",
];

function PreliminaryBadge() {
  return <span className="ws-prelim-badge" data-testid="preliminary-badge">PRELIMINARY</span>;
}

// Phase R6 — minimal opt-in / cadence control for scheduled monitoring email.
// The signed-in user opts THEMSELVES in (their own account address); a
// double-opt-in confirmation email must be clicked before any mail is sent.
// The scaled daily quota is shown so a user is never silently cut off.
function MonitoringSection({ oppId }: { oppId: string }) {
  const [sub, setSub] = useState<WorkspaceSubscription | null>(null);
  const [quota, setQuota] = useState<MonitoringQuota | null>(null);
  const [cadence, setCadence] = useState(6);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const res = await workspaceApi.getMonitoring(oppId);
    if (!res.ok) { setUnavailable(true); return; }
    setUnavailable(false);
    setSub(res.data.subscription);
    setQuota(res.data.quota);
    if (res.data.subscription) setCadence(res.data.subscription.cadence_hours);
  };
  useEffect(() => {
    setNote(null); setErr(null); setSub(null); setUnavailable(false);
    load();
  }, [oppId]); // eslint-disable-line react-hooks/exhaustive-deps

  const optIn = async () => {
    setBusy(true); setErr(null); setNote(null);
    const res = await workspaceApi.subscribeMonitoring(oppId, cadence);
    setBusy(false);
    if (!res.ok) { setErr(res.error); return; }
    setNote(res.data.confirmation.note);
    await load();
  };
  const optOut = async () => {
    setBusy(true); setErr(null); setNote(null);
    const res = await workspaceApi.unsubscribeMonitoring(oppId);
    setBusy(false);
    if (!res.ok) { setErr(res.error); return; }
    await load();
  };

  if (unavailable) {
    return (
      <div className="ws-section" data-testid="monitoring-section">
        <h4>Scheduled monitoring</h4>
        <p className="empty-note" data-testid="monitoring-unavailable">
          Scheduled monitoring email requires sign-in to be enabled on this deployment.
        </p>
      </div>
    );
  }

  const me = sub?.recipients?.find((r) => r.enabled);
  const on = !!sub?.enabled;
  const pending = !!me?.pending_confirmation;

  return (
    <div className="ws-section" data-testid="monitoring-section">
      <h4>Scheduled monitoring</h4>
      <p className="empty-note">
        Re-runs this analysis on a schedule and emails you <strong>only</strong> when
        something materially changes — never for an unchanged, partial, or failed run.
        Changed items stay preliminary until you review them.
      </p>
      {err && <div className="error-banner" style={{ marginBottom: 8 }}>{err}</div>}

      <div className="uop-form" style={{ marginBottom: 10 }}>
        <label>Re-run every (hours)</label>
        <input type="number" min={4} max={720} value={cadence} data-testid="monitoring-cadence"
          onChange={(e) => setCadence(Number(e.target.value))} disabled={busy} />
      </div>

      {on && !pending && (
        <p data-testid="monitoring-on">
          On — every {sub!.cadence_hours}h, emailing your account address on a material change.
        </p>
      )}
      {pending && (
        <div className="banner-note" data-testid="monitoring-pending" style={{ marginBottom: 8 }}>
          <Icon name="alert" />
          <span>Check your email to confirm — no monitoring email is sent until you
            click the confirmation link.</span>
        </div>
      )}
      {note && <p className="empty-note" data-testid="monitoring-note">{note}</p>}
      {quota && (
        <p className="empty-note" data-testid="monitoring-quota">
          Scheduled runs today: {quota.used}/{quota.limit} used · {quota.remaining} remaining.
        </p>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" className="btn btn-primary" disabled={busy}
          data-testid="monitoring-optin" onClick={optIn}>
          {busy ? "Saving…" : pending ? "Resend confirmation"
            : on ? "Update cadence" : "Turn on monitoring"}
        </button>
        {(on || pending) && (
          <button type="button" className="btn" disabled={busy}
            data-testid="monitoring-optout" onClick={optOut}>
            Turn off
          </button>
        )}
      </div>
    </div>
  );
}

export default function WorkspacePanel({ oppId }: { oppId: string }) {
  const [workspace, setWorkspace] = useState<WorkspaceVersion | null>(null);
  const [emptyNote, setEmptyNote] = useState<string | null>(null);
  const [versions, setVersions] = useState<WorkspaceVersionSummary[]>([]);
  const [diff, setDiff] = useState<WorkspaceDiff | null>(null);
  const [diffNote, setDiffNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");

  const load = async () => {
    setError(null);
    const res = await workspaceApi.get(oppId);
    if (!res.ok) {
      setError(res.error);
      setLoading(false);
      return;
    }
    setWorkspace(res.data.workspace);
    setEmptyNote(res.data.workspace ? null : (res.data.note ?? null));
    setLoading(false);
    // history + diff are secondary — their absence never breaks the panel
    const [vs, df] = await Promise.all([
      workspaceApi.versions(oppId),
      workspaceApi.diff(oppId),
    ]);
    setVersions(vs.ok ? vs.data.versions : []);
    if (df.ok) {
      setDiff(df.data.diff);
      setDiffNote(df.data.diff ? null : (df.data.note ?? null));
    }
  };
  useEffect(() => {
    setLoading(true);
    setWorkspace(null);
    setVersions([]);
    setDiff(null);
    load();
  }, [oppId]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = async () => {
    setRunning(true);
    setError(null);
    const res = await workspaceApi.refresh(oppId, question.trim() || undefined);
    setRunning(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    setQuestion("");
    await load();
  };

  if (loading) {
    return <div className="panel-wrap"><div className="skeleton" style={{ height: 160 }} /></div>;
  }

  const score = workspace?.preliminary_score ?? null;
  const claims = workspace?.claims ?? [];
  const approved = claims.filter((c) => c.status === "approved");
  const pending = claims.filter((c) => c.status === "pending_review");

  return (
    <div className="panel-wrap" style={{ maxWidth: 720 }}>
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Analysis workspace</div>
          <div className="panel-sub">
            {workspace
              ? `Version ${workspace.version} · ${workspace.trigger} · completed ${workspace.completed_at ?? "—"}`
              : "No analysis has been run for this opportunity yet"}
          </div>
        </div>
        <button type="button" className="btn btn-primary" disabled={running}
          data-testid="refresh-analysis"
          onClick={refresh}
          title="Re-run the full analysis chain (knowledge base → external research → claim extraction → preliminary score)">
          {running ? "Running…" : workspace ? "Refresh analysis" : "Run first analysis"}
        </button>
      </div>

      <div className="uop-status-note">
        Everything below is machine-generated <strong>preliminary</strong> analysis — not
        authoritative evidence. Claims stay pending until a human reviews them (Research
        workspace); the preliminary score is computed and capped by the real scoring engine.
      </div>

      <MonitoringSection oppId={oppId} />

      {error && <div className="error-banner" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="uop-form" style={{ marginBottom: 14 }}>
        <label>Focus question for the next refresh (optional)</label>
        <input type="text" value={question} data-testid="workspace-question"
          placeholder="e.g. Is the settlement delay a frequent, severe pain for this segment?"
          onChange={(e) => setQuestion(e.target.value)} disabled={running} />
      </div>

      {running && (
        <div className="ws-running" data-testid="workspace-running">
          <div className="ws-running-title">
            <span className="spinner" aria-hidden />
            Running the analysis chain server-side — live research can take a minute.
          </div>
          <ul>
            {CHAIN_STEPS.map((s) => <li key={s}>{s}</li>)}
          </ul>
          <p className="empty-note">
            Steps without a configured provider are skipped and reported as gaps — never faked.
          </p>
        </div>
      )}

      {!workspace && !running && (
        <p className="empty-note" data-testid="workspace-empty">
          {emptyNote ?? "No analysis workspace exists yet."}
        </p>
      )}

      {workspace && (
        <>
          {workspace.is_stale && (
            <div className="banner-note" data-testid="workspace-stale" style={{ marginBottom: 12 }}>
              <Icon name="alert" />
              <span>
                This analysis is stale (older than the configured threshold). Refresh it before
                relying on it — it is not rebuilt automatically.
              </span>
            </div>
          )}

          {score && (
            <div className="ws-score" data-testid="workspace-score">
              <div className="ws-score-head">
                <h4>Preliminary score</h4>
                <PreliminaryBadge />
              </div>
              <dl className="detail-fields">
                <div><dt>Composite (indicative)</dt><dd>{score.composite}</dd></div>
                <div><dt>Classification</dt><dd>{score.classification}</dd></div>
                <div>
                  <dt>Assumption load</dt>
                  <dd>
                    {score.assumption_count}/17 assumption-based
                    {score.assumption_capped
                      ? ` — engine-capped at '${score.max_classification}'`
                      : ""}
                  </dd>
                </div>
                <div><dt>Confidence</dt><dd>{score.confidence}</dd></div>
                <div><dt>Computed by</dt><dd>{score.engine}</dd></div>
              </dl>
              {score.basis_note && <p className="empty-note">{score.basis_note}</p>}
            </div>
          )}

          <div className="ws-section">
            <h4>External claims from this analysis <PreliminaryBadge /></h4>
            {claims.length === 0 ? (
              <p className="empty-note" data-testid="workspace-no-claims">
                No candidate claims were extracted in this version — see the gaps below for why.
              </p>
            ) : (
              <>
                {approved.map((c) => (
                  <div className="research-source" key={c.id} data-testid="workspace-claim-approved">
                    <div className="research-source-main">
                      <div className="research-source-title">{c.claim}</div>
                      <div className="research-source-meta">
                        <span className={`status-pill ${CLAIM_PILL[c.status]}`}>{CLAIM_LABEL[c.status]}</span>
                        {" "}· {c.id} · origin {c.origin ?? "human"} · {c.source_ids.length} source(s)
                      </div>
                    </div>
                  </div>
                ))}
                {pending.map((c) => (
                  <div className="research-source" key={c.id} data-testid="workspace-claim-pending">
                    <div className="research-source-main">
                      <div className="research-source-title">{c.claim}</div>
                      <div className="research-source-meta">
                        <span className={`status-pill ${CLAIM_PILL[c.status]}`}>{CLAIM_LABEL[c.status]}</span>
                        {" "}· {c.id} · origin {c.origin ?? "human"} · {c.source_ids.length} source(s)
                      </div>
                    </div>
                  </div>
                ))}
                <p className="empty-note">
                  Review pending claims in the Research workspace — approval there carries into
                  every future version of this analysis.
                </p>
              </>
            )}
          </div>

          <div className="ws-section">
            <h4>Excerpts from your uploaded documents</h4>
            {(workspace.document_evidence ?? []).length === 0 ? (
              <p className="empty-note" data-testid="workspace-no-documents">
                No uploaded document content was used in this version — attach files in
                the Files tab and refresh.
              </p>
            ) : (
              (workspace.document_evidence ?? []).map((d) => (
                <div className="research-source" key={`${d.document_id}-${d.chunk_seq}`}
                  data-testid="workspace-document-excerpt">
                  <div className="research-source-main">
                    <div className="research-source-title">{d.filename}</div>
                    <div className="research-source-meta">
                      user-provided document · {d.document_id} · chunk {d.chunk_seq}
                    </div>
                    <div className="ws-doc-excerpt">“{d.excerpt}”</div>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="ws-section">
            <h4>Related committed evidence</h4>
            {workspace.kb_evidence.length === 0 ? (
              <p className="empty-note" data-testid="workspace-no-kb">
                No committed knowledge-base records matched this opportunity.
              </p>
            ) : (
              workspace.kb_evidence.map((e) => (
                <div className="research-source" key={e.id} data-testid="workspace-kb-record">
                  <div className="research-source-main">
                    <div className="research-source-title">{e.id} — {e.title}</div>
                    <div className="research-source-meta">
                      {e.segment ?? "no segment"} · confidence {e.evidence_confidence ?? "unstated"}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="ws-section">
            <h4>Gaps in this analysis</h4>
            {workspace.gaps.length === 0 ? (
              <p className="empty-note">No gaps were recorded for this version.</p>
            ) : (
              <ul className="ws-gaps" data-testid="workspace-gaps">
                {workspace.gaps.map((g) => (
                  <li key={g}><Icon name="alert" size={12} /> {g}</li>
                ))}
              </ul>
            )}
          </div>

          {diff && (
            <div className="ws-section" data-testid="workspace-diff">
              <h4>Changes since the previous version</h4>
              <dl className="detail-fields">
                <div>
                  <dt>Composite</dt>
                  <dd>
                    {diff.composite_before ?? "—"} → {diff.composite_after ?? "—"}
                    {typeof diff.composite_delta === "number" && diff.composite_delta !== 0
                      ? ` (${diff.composite_delta > 0 ? "+" : ""}${diff.composite_delta})`
                      : " (unchanged)"}
                  </dd>
                </div>
                <div><dt>New claims</dt><dd>{diff.new_claim_ids.length ? diff.new_claim_ids.join(", ") : "none"}</dd></div>
                <div><dt>Removed claims</dt><dd>{diff.removed_claim_ids.length ? diff.removed_claim_ids.join(", ") : "none"}</dd></div>
                <div><dt>Resolved gaps</dt><dd>{diff.resolved_gaps.length ? diff.resolved_gaps.join("; ") : "none"}</dd></div>
                <div><dt>New gaps</dt><dd>{diff.new_gaps.length ? diff.new_gaps.join("; ") : "none"}</dd></div>
              </dl>
            </div>
          )}
          {!diff && diffNote && versions.length > 0 && (
            <div className="ws-section">
              <h4>Changes since the previous version</h4>
              <p className="empty-note" data-testid="workspace-diff-note">{diffNote}</p>
            </div>
          )}

          <div className="ws-section">
            <h4>Version history</h4>
            {versions.map((v) => (
              <div className="research-source" key={v.id} data-testid="workspace-version-row">
                <div className="research-source-main">
                  <div className="research-source-title">
                    v{v.version} · {v.status}{v.error ? ` — ${v.error}` : ""}
                  </div>
                  <div className="research-source-meta">
                    trigger {v.trigger} · created {v.created_at}
                    {v.question ? ` · question: ${v.question.slice(0, 80)}` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {workspace.provenance && (
            <div className="ws-section">
              <h4>Provenance</h4>
              <dl className="detail-fields" data-testid="workspace-provenance">
                {Object.entries(workspace.provenance)
                  .filter(([, v]) => v !== null && v !== undefined && String(v) !== "")
                  .map(([k, v]) => (
                    <div key={k}>
                      <dt>{k.replace(/_/g, " ")}</dt>
                      <dd>{Array.isArray(v) ? v.join("; ") : String(v)}</dd>
                    </div>
                  ))}
              </dl>
            </div>
          )}
        </>
      )}
    </div>
  );
}
