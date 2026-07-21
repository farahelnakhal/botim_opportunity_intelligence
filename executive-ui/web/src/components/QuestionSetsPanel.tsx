// Question-sets review workspace (Phase R10, PR10c). Lists draft merchant
// research-question sets generated from an opportunity's evidence-gap profile,
// lets a human review them (approve — optionally editing question text —
// reject, or delete), and renders the Merchant Voice hand-off for an approved
// set. Everything shown comes from the API verbatim; empty/unavailable states
// are honest. HARD BOUNDARY: nothing here writes Merchant Voice or contacts a
// merchant — a reviewed set is created as an MV guide MANUALLY by a person.
import { useCallback, useEffect, useState } from "react";
import { questionSetsApi } from "../lib/questionSetsApi";
import Icon from "./Icon";
import type { QuestionSet, QuestionDraft, QuestionSetHandoff } from "../types";

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft — awaiting review",
  approved: "Approved — ready for manual hand-off",
  rejected: "Rejected",
};

// Merchant Voice question taxonomy (mirrors merchant-voice/app/models.py). A UI
// affordance only — the review route re-validates every edit against MV's own
// validator, so this list can never let an out-of-taxonomy value through.
const PURPOSES = ["problem", "behaviour", "workaround", "frequency", "severity",
  "willingness_to_pay", "switching_barrier", "trust", "concept_reaction",
  "rejection_condition", "follow_up"];
const TYPES = ["open_text", "single_choice", "multi_choice", "scale", "yes_no"];

function QuestionEditor({ q, editable, onChange }: {
  q: QuestionDraft; editable: boolean; onChange: (patch: Partial<QuestionDraft>) => void;
}) {
  return (
    <div className="qset-question">
      {editable ? (
        <textarea className="qset-question-text" value={q.text}
          aria-label="question text" rows={2} onChange={(e) => onChange({ text: e.target.value })} />
      ) : (
        <div className="qset-question-text-static">{q.text}</div>
      )}
      <div className="research-source-meta qset-question-meta">
        {editable ? (
          <>
            <select className="qset-edit-select" aria-label="question purpose"
              value={q.purpose ?? ""} onChange={(e) => onChange({ purpose: e.target.value })}>
              {PURPOSES.map((p) => <option key={p} value={p}>purpose: {p}</option>)}
            </select>
            <select className="qset-edit-select" aria-label="question type"
              value={q.question_type ?? "open_text"} onChange={(e) => onChange({ question_type: e.target.value })}>
              {TYPES.map((t) => <option key={t} value={t}>type: {t}</option>)}
            </select>
          </>
        ) : (
          <>
            {q.purpose && <span className="qset-chip">purpose: {q.purpose}</span>}
            {q.question_type && <span className="qset-chip">type: {q.question_type}</span>}
          </>
        )}
        {q.linked_assumption && (
          <span className="qset-chip" title="the evidence gap this question tests">
            tests: {q.linked_assumption}
          </span>
        )}
        {(q.signals ?? []).map((s) => <span key={s} className="qset-signal">{s}</span>)}
      </div>
    </div>
  );
}

function SetCard({ set, onChanged }: { set: QuestionSet; onChanged: () => void }) {
  const [edited, setEdited] = useState<QuestionDraft[]>(set.questions);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [handoff, setHandoff] = useState<QuestionSetHandoff | null>(null);
  const [copied, setCopied] = useState(false);
  const isDraft = set.status === "draft";

  const dirty = edited.some((q, i) =>
    q.text !== set.questions[i]?.text
    || q.purpose !== set.questions[i]?.purpose
    || q.question_type !== set.questions[i]?.question_type);

  const review = async (action: "approve" | "reject") => {
    setBusy(true); setError(null);
    const res = await questionSetsApi.review(set.id, action,
      action === "approve" && dirty ? { questions: edited, note: note || undefined }
        : { note: note || undefined });
    setBusy(false);
    if (!res.ok) { setError(res.error); return; }
    onChanged();
  };

  const remove = async () => {
    setBusy(true); setError(null);
    const res = await questionSetsApi.remove(set.id);
    setBusy(false);
    if (!res.ok) { setError(res.error); return; }
    onChanged();
  };

  const loadHandoff = async () => {
    setError(null);
    const res = await questionSetsApi.handoff(set.id);
    if (!res.ok) { setError(res.error); return; }
    setHandoff(res.data.handoff);
  };

  const copyHandoff = async () => {
    if (!handoff) return;
    try {
      await navigator.clipboard.writeText(handoff.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("could not copy to clipboard");
    }
  };

  return (
    <div className={`qset-card status-${set.status}`} data-testid="qset-card">
      <div className="qset-card-head">
        <span className="qset-opp">{set.opportunity_id}</span>
        <span className={`research-status research-status-${set.status}`}>
          {STATUS_LABEL[set.status] ?? set.status}
        </span>
        <span className="qset-id">{set.id}</span>
      </div>
      <div className="research-source-meta">
        {set.questions.length} question{set.questions.length === 1 ? "" : "s"}
        {set.rejected_count > 0 && <> · {set.rejected_count} rejected in drafting</>}
        {set.provenance?.model && <> · model: {set.provenance.model}</>}
      </div>
      {set.note && <div className="banner-note"><Icon name="alert" size={12} /> {set.note}</div>}

      {edited.map((q, i) => (
        <QuestionEditor key={q.question_id ?? i} q={q} editable={isDraft}
          onChange={(patch) => setEdited(edited.map((x, j) => (j === i ? { ...x, ...patch } : x)))} />
      ))}

      {isDraft && set.questions.length > 0 && (
        <div className="qset-review">
          <input className="qset-note" placeholder="review note (optional)"
            value={note} aria-label="review note" onChange={(e) => setNote(e.target.value)} />
          <button className="btn-secondary" disabled={busy} onClick={() => review("approve")}>
            {dirty ? "Approve edited" : "Approve"}
          </button>
          <button className="btn-secondary" disabled={busy} onClick={() => review("reject")}>Reject</button>
          <span className="research-review-hint">
            Approval only unlocks a manual hand-off — it never creates a Merchant Voice
            guide, changes a score, or contacts a merchant.
          </span>
        </div>
      )}

      {set.status === "approved" && (
        <div className="qset-handoff">
          {!handoff ? (
            <button className="btn-secondary" onClick={loadHandoff}>Merchant Voice hand-off</button>
          ) : (
            <>
              <div className="research-review-hint">
                <Icon name="alert" size={12} /> Proposal only — paste this into Merchant
                Voice yourself via its own guide review/approval flow. Nothing has been
                sent to Merchant Voice or any merchant.
              </div>
              <pre className="qset-handoff-md" data-testid="qset-handoff-md">{handoff.markdown}</pre>
              <button className="btn-secondary" onClick={copyHandoff}>
                {copied ? "Copied" : "Copy hand-off"}
              </button>
            </>
          )}
        </div>
      )}

      <div className="qset-card-foot">
        <button className="btn-link-danger" disabled={busy} onClick={remove}>Delete</button>
      </div>
      {error && <div className="banner-note"><Icon name="alert" size={12} /> {error}</div>}
    </div>
  );
}

export default function QuestionSetsPanel() {
  const [sets, setSets] = useState<QuestionSet[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const res = await questionSetsApi.list();
    if (res.ok) { setSets(res.data.question_sets); setError(null); }
    else setError(res.error);
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  if (error) return (
    <div className="tab-panel">
      <div className="banner-note"><Icon name="alert" /> {error}</div>
    </div>
  );
  if (!sets) return <div className="tab-panel">Loading question sets…</div>;

  return (
    <div className="tab-panel">
      <h2>Merchant research questions</h2>
      <p className="panel-intro">
        Draft, taxonomy-valid merchant-interview questions generated from each opportunity's
        evidence-gap profile. Review and approve a set to unlock a Merchant Voice hand-off —
        then create the guide in Merchant Voice yourself. These are proposals; nothing here
        updates a score or contacts a merchant.
      </p>
      {sets.length === 0 ? (
        <div className="empty-state">No question sets yet. Generate one from an opportunity's gap profile.</div>
      ) : (
        sets.map((s) => <SetCard key={s.id} set={s} onChanged={reload} />)
      )}
    </div>
  );
}
