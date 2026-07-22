// Verified-source market sizing (Phase C2), nested in a research run's detail.
// Shows the run's tier-badged verified figures, builds a candidate TAM/SAM/SOM
// from them, and reviews it. The hard honesty constraint of this phase is
// VISUAL: a low-confidence, single-source number must never look identical to a
// corroborated one. So corroboration status and evidence basis are rendered as
// distinctly-classed, distinctly-worded badges — never the same chip — both at
// the per-input level (Fact vs Assumption) and the whole-sizing level
// (Verified vs Low confidence). The client never computes a number.
import { useCallback, useEffect, useState } from "react";
import {
  marketSizingApi,
  type MarketSizing,
  type MszConfidence,
  type ResearchFigure,
} from "../lib/marketSizingApi";
import type { CalcNormalizedInput } from "../lib/calculatorsApi";
import Icon from "./Icon";

const OPP_RE = /^OPP-\d{3}$/;

// Client mirror of the server's METHODS (market_sizing_builder.py) — which
// inputs are source-verified vs analyst assumptions. Additive; the server
// remains the authority and re-validates.
const METHODS: Record<string, { label: string; sourced: string[]; assumption: string[] }> = {
  top_down: {
    label: "Top-down (population × value × shares)",
    sourced: ["population", "annual_value_per_unit"],
    assumption: ["serviceable_fraction", "obtainable_share"],
  },
  bottom_up: {
    label: "Bottom-up (customers × units × price)",
    sourced: ["num_customers", "units_per_customer_per_year", "price_per_unit"],
    assumption: [],
  },
};

const BASIS_TEXT: Record<string, string> = { F: "Fact", E: "Estimate", A: "Assumption" };

// Per-input evidence basis (F/E/A). Distinct class + distinct word per label so
// a Fact input can never be mistaken for an Assumption input in the DOM.
function BasisChip({ label }: { label: string }) {
  return (
    <span className={`calc-basis calc-basis-${label}`} data-testid={`basis-${label}`}>
      {BASIS_TEXT[label] ?? label}
    </span>
  );
}

// Whole-sizing corroboration status. Distinct class + distinct word per state.
function ConfidenceBadge({ confidence }: { confidence: MszConfidence }) {
  const text = confidence === "verified" ? "Verified" : "Low confidence";
  return (
    <span className={`msz-confidence msz-confidence-${confidence}`}
      data-testid={`msz-confidence-${confidence}`}>
      {text}
    </span>
  );
}

function TierChip({ tier }: { tier: string | null }) {
  const t = tier || "T?";
  return <span className={`msz-tier msz-tier-${t}`} data-testid={`tier-${t}`}>{t}</span>;
}

function FigureRow({ f }: { f: ResearchFigure }) {
  return (
    <div className="msz-figure-row" data-testid="msz-figure-row">
      <TierChip tier={f.tier} />
      <span className="msz-figure-quantity">{f.quantity}</span>
      <span className="msz-figure-value">{f.value.toLocaleString()}{f.unit ? ` ${f.unit}` : ""}</span>
      {f.supporting_quote && <span className="research-source-meta">“{f.supporting_quote}”</span>}
    </div>
  );
}

function SizingResult({ sizing, onReviewed }: { sizing: MarketSizing; onReviewed: () => void }) {
  const env = sizing.sizing.envelope;
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const terminal = sizing.status !== "pending_review";

  const review = async (action: "approve" | "reject") => {
    setBusy(true);
    setErr(null);
    const res = await marketSizingApi.reviewSizing(sizing.id, action, note.trim() || undefined);
    setBusy(false);
    if (res.ok) onReviewed();
    else setErr(res.error);
  };

  return (
    <div className="msz-result" data-testid="msz-result">
      <div className="msz-result-head">
        <span className="msz-result-id">{sizing.id}</span>
        <ConfidenceBadge confidence={sizing.confidence} />
        <span className={`msz-status msz-status-${sizing.status}`}>{sizing.status}</span>
      </div>
      <p className="msz-confidence-basis" data-testid="msz-confidence-basis">
        {sizing.sizing.confidence_basis}
      </p>

      <div className="msz-outputs">
        {Object.entries(env.outputs).map(([k, o]) => (
          <div key={k} className="msz-output">
            <span className="msz-output-label">{k.toUpperCase()}</span>
            <span className="msz-output-value">{o.display}{o.unit ? ` ${o.unit}` : ""}</span>
          </div>
        ))}
      </div>

      <h5>Inputs &amp; evidence basis</h5>
      <ul className="msz-input-basis">
        {Object.entries(env.normalized_inputs).map(([name, n]: [string, CalcNormalizedInput]) => (
          <li key={name} data-testid={`msz-input-${name}`}>
            <b>{name}</b> = {n.value.toLocaleString()} <BasisChip label={n.label} />
            {n.source_id && <span className="msz-source-ref" data-testid={`source-${name}`}> ·
              traced to {n.source_id}</span>}
            {n.note && <span className="calc-note"> — {n.note}</span>}
          </li>
        ))}
      </ul>

      {!terminal ? (
        <div className="msz-review">
          <input type="text" placeholder="review note (optional)" value={note}
            onChange={(e) => setNote(e.target.value)} data-testid="msz-review-note" />
          <button className="send-btn" disabled={busy} onClick={() => void review("approve")}
            data-testid="msz-approve">Approve</button>
          <button className="btn-secondary" disabled={busy} onClick={() => void review("reject")}
            data-testid="msz-reject">Reject</button>
          {err && <span className="banner-note"><Icon name="alert" /> {err}</span>}
        </div>
      ) : (
        <p className="research-review-hint">
          Reviewed: {sizing.status}{sizing.reviewer ? ` by ${sizing.reviewer}` : ""}
          {sizing.review_note ? ` — ${sizing.review_note}` : ""}. Approval records a
          candidate only; it never writes a committed score or the knowledge base.
        </p>
      )}
    </div>
  );
}

export default function MarketSizingSection(
  { runId, opportunityRef, hasSources }:
  { runId: string; opportunityRef: string | null; hasSources: boolean },
) {
  const [figures, setFigures] = useState<ResearchFigure[]>([]);
  const [sizings, setSizings] = useState<MarketSizing[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [extractNote, setExtractNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const oppFromRun = opportunityRef && OPP_RE.test(opportunityRef) ? opportunityRef : "";
  const [oppId, setOppId] = useState(oppFromRun);
  const [method, setMethod] = useState("top_down");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [assumptions, setAssumptions] = useState<Record<string, string>>({});
  const [buildError, setBuildError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [f, s] = await Promise.all([
      marketSizingApi.listFigures(runId),
      marketSizingApi.listSizings(oppFromRun || undefined),
    ]);
    if (f.ok) setFigures(f.data.figures); else setError(f.error);
    if (s.ok) setSizings(s.data.market_sizings);
  }, [runId, oppFromRun]);

  useEffect(() => { void reload(); }, [reload]);

  const quantities = Array.from(new Set(figures.map((f) => f.quantity)));

  const extract = async () => {
    setBusy(true);
    setExtractNote(null);
    const res = await marketSizingApi.extractFigures(runId);
    setBusy(false);
    if (res.ok) {
      setExtractNote(`Extracted ${res.data.accepted} verified figure(s) `
        + `(${res.data.proposed} proposed, ${res.data.rejected.length} rejected as unverifiable).`);
      void reload();
    } else {
      setExtractNote(res.error);
    }
  };

  const build = async () => {
    setBuildError(null);
    const spec = METHODS[method];
    if (!OPP_RE.test(oppId)) {
      setBuildError("Enter the committed opportunity id (OPP-nnn) this sizing attaches to.");
      return;
    }
    const inputs: Record<string, { quantity: string } | { value: number; note?: string }> = {};
    for (const name of spec.sourced) {
      const q = mapping[name];
      if (!q) { setBuildError(`Map a verified figure to '${name}' (never invented).`); return; }
      inputs[name] = { quantity: q };
    }
    for (const name of spec.assumption) {
      const raw = assumptions[name];
      const num = Number(raw);
      if (raw === undefined || raw === "" || !Number.isFinite(num)) {
        setBuildError(`Enter the analyst assumption '${name}' (a number in 0..1).`);
        return;
      }
      inputs[name] = { value: num, note: "analyst assumption" };
    }
    setBusy(true);
    const res = await marketSizingApi.buildSizing(oppId, { run_id: runId, method, inputs });
    setBusy(false);
    if (res.ok) { setSizings((cur) => [res.data.market_sizing, ...cur]); }
    else setBuildError(res.error);
  };

  const spec = METHODS[method];

  return (
    <div className="msz-section" data-testid="msz-section">
      <h3>Verified-source market sizing</h3>
      <p className="research-review-hint">
        Figures are extracted from this run's sources and verified verbatim against
        the cited text; each carries its source tier. A sizing is corroborated only
        when ≥2 independent T1/T2 sources agree — otherwise it is low-confidence, and
        never shown as if validated. Results are candidates pending human review;
        approval never writes a committed score or the knowledge base.
      </p>

      {error && <div className="banner-note"><Icon name="alert" /> {error}</div>}

      <h4>Verified figures</h4>
      {figures.length === 0 ? (
        <p className="empty-note">
          No verified figures yet{hasSources ? "" : " — the run has no sources to extract from"}.
        </p>
      ) : (
        figures.map((f) => <FigureRow key={f.id} f={f} />)
      )}
      {hasSources && (
        <div className="msz-extract-actions">
          <button className="btn-secondary" disabled={busy} onClick={() => void extract()}
            data-testid="msz-extract"
            title="Ask the model to propose numeric figures, then keep only those that verify verbatim against a cited source">
            {busy ? "Extracting…" : "Extract figures from sources"}
          </button>
          {extractNote && <span className="research-review-hint" data-testid="msz-extract-note">{extractNote}</span>}
        </div>
      )}

      {figures.length > 0 && (
        <div className="msz-build">
          <h4>Build a candidate sizing</h4>
          <label className="calc-field">
            <span>Method</span>
            <select value={method} data-testid="msz-method"
              onChange={(e) => { setMethod(e.target.value); setMapping({}); setAssumptions({}); }}>
              {Object.entries(METHODS).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
            </select>
          </label>

          {spec.sourced.map((name) => (
            <label key={name} className="calc-field">
              <span>{name} <em>(verified figure)</em></span>
              <select value={mapping[name] ?? ""} data-testid={`msz-map-${name}`}
                onChange={(e) => setMapping((m) => ({ ...m, [name]: e.target.value }))}>
                <option value="">— pick a verified quantity —</option>
                {quantities.map((q) => <option key={q} value={q}>{q}</option>)}
              </select>
            </label>
          ))}
          {spec.assumption.map((name) => (
            <label key={name} className="calc-field">
              <span>{name} <em>(analyst assumption, 0..1)</em></span>
              <input type="number" inputMode="decimal" step="0.01" min="0" max="1"
                value={assumptions[name] ?? ""} data-testid={`msz-assume-${name}`}
                onChange={(e) => setAssumptions((a) => ({ ...a, [name]: e.target.value }))} />
            </label>
          ))}

          {!oppFromRun && (
            <label className="calc-field">
              <span>Attach to opportunity <em>(OPP-nnn)</em></span>
              <input type="text" placeholder="OPP-013" value={oppId} data-testid="msz-opp"
                onChange={(e) => setOppId(e.target.value)} />
            </label>
          )}

          <button className="send-btn" disabled={busy} onClick={() => void build()} data-testid="msz-build">
            {busy ? "Composing…" : "Compose candidate sizing"}
          </button>
          {buildError && <div className="banner-note" data-testid="msz-build-error"><Icon name="alert" /> {buildError}</div>}
        </div>
      )}

      <h4>Candidate sizings</h4>
      {sizings.length === 0 ? (
        <p className="empty-note">No candidate sizings yet.</p>
      ) : (
        sizings.map((s) => <SizingResult key={s.id} sizing={s} onReviewed={() => void reload()} />)
      )}
    </div>
  );
}
