// Deterministic calculators (Phase C1) — pick a calculator, fill its declared
// inputs (each optionally labelled Fact/Estimate/Assumption with a note), and
// see the FULLY SHOWN working the server computed. The client never does the
// arithmetic; a calculation over assumed inputs is labelled illustrative, never
// a validated figure. Results can be saved and attached to an opportunity.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  calculatorsApi,
  type CalcEnvelope,
  type CalcInputValue,
  type CalculatorSpec,
  type SavedCalculation,
} from "../lib/calculatorsApi";
import Icon from "./Icon";

const LABELS: { value: string; text: string }[] = [
  { value: "A", text: "Assumption" },
  { value: "E", text: "Estimate" },
  { value: "F", text: "Fact" },
];

type FieldState = { value: string; label: string; note: string };

function ShownWorking({ env }: { env: CalcEnvelope }) {
  const outputs = Object.entries(env.outputs);
  return (
    <div className="calc-result" data-testid="calc-result">
      <h3>{env.title}</h3>

      <div className="calc-outputs">
        {outputs.map(([key, out]) => (
          <div key={key} className="calc-output">
            <span className="calc-output-label">{key}</span>
            <span className="calc-output-value">
              {out.value === null ? out.display : out.display}
              {out.unit ? ` ${out.unit}` : ""}
            </span>
            {out.value === null && out.reason && (
              <span className="calc-output-reason">{out.reason}</span>
            )}
          </div>
        ))}
      </div>

      <h4>Working</h4>
      <div className="calc-steps-wrap">
        <table className="calc-steps">
          <thead>
            <tr><th>Step</th><th>Formula</th><th>Substituted</th><th>Result</th></tr>
          </thead>
          <tbody>
            {env.steps.map((s, i) => (
              <tr key={i}>
                <td>{s.output}</td>
                <td>{s.expression}</td>
                <td>{s.substituted}</td>
                <td>{s.result_display}{s.unit ? ` ${s.unit}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h4>Inputs</h4>
      <ul className="calc-input-basis">
        {Object.entries(env.normalized_inputs).map(([name, n]) => (
          <li key={name}>
            <b>{name}</b> = {n.value.toLocaleString()}{" "}
            <span className={`calc-basis calc-basis-${n.label}`}>
              {LABELS.find((l) => l.value === n.label)?.text ?? n.label}
            </span>
            {n.note && <span className="calc-note"> — {n.note}</span>}
          </li>
        ))}
      </ul>

      {env.warnings.length > 0 && (
        <div className="calc-warnings">
          {env.warnings.map((w, i) => (
            <div key={i} className="banner-note"><Icon name="alert" /> {w}</div>
          ))}
        </div>
      )}
      {env.disclaimers.map((d, i) => (
        <p key={i} className="calc-disclaimer" data-testid="calc-disclaimer">{d}</p>
      ))}
    </div>
  );
}

export default function CalculatorsPanel() {
  const [catalog, setCatalog] = useState<CalculatorSpec[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [fields, setFields] = useState<Record<string, FieldState>>({});
  const [envelope, setEnvelope] = useState<CalcEnvelope | null>(null);
  const [computeError, setComputeError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveLabel, setSaveLabel] = useState("");
  const [saveOpp, setSaveOpp] = useState("");
  const [saved, setSaved] = useState<SavedCalculation[]>([]);
  const [saveNote, setSaveNote] = useState<string | null>(null);

  const selected = useMemo(
    () => catalog?.find((c) => c.id === selectedId) ?? null,
    [catalog, selectedId],
  );

  const loadSaved = useCallback(async () => {
    const res = await calculatorsApi.listSaved();
    if (res.ok) setSaved(res.data.saved_calculations);
  }, []);

  useEffect(() => {
    void (async () => {
      const res = await calculatorsApi.catalog();
      if (res.ok) {
        setCatalog(res.data.calculators);
        if (res.data.calculators.length) setSelectedId(res.data.calculators[0].id);
      } else {
        setError(res.error);
      }
    })();
    void loadSaved();
  }, [loadSaved]);

  // reset the form when the calculator changes
  useEffect(() => {
    if (!selected) return;
    const next: Record<string, FieldState> = {};
    for (const spec of selected.inputs) next[spec.name] = { value: "", label: "A", note: "" };
    setFields(next);
    setEnvelope(null);
    setComputeError(null);
    setSaveNote(null);
  }, [selected]);

  const buildInputs = (): Record<string, CalcInputValue> | null => {
    if (!selected) return null;
    const inputs: Record<string, CalcInputValue> = {};
    for (const spec of selected.inputs) {
      const f = fields[spec.name];
      if (!f || f.value.trim() === "") {
        if (spec.required) {
          setComputeError(`Enter a value for ${spec.name} (${spec.unit}).`);
          return null;
        }
        continue;
      }
      const num = Number(f.value);
      if (!Number.isFinite(num)) {
        setComputeError(`${spec.name} must be a number.`);
        return null;
      }
      inputs[spec.name] = f.note.trim() || f.label !== "A"
        ? { value: num, label: f.label, note: f.note.trim() }
        : num;
    }
    return inputs;
  };

  const compute = async () => {
    const inputs = buildInputs();
    if (!inputs || !selected) return;
    setBusy(true);
    setComputeError(null);
    setSaveNote(null);
    const res = await calculatorsApi.compute(selected.id, inputs);
    setBusy(false);
    if (res.ok) setEnvelope(res.data.calculation);
    else { setEnvelope(null); setComputeError(res.error); }
  };

  const save = async () => {
    const inputs = buildInputs();
    if (!inputs || !selected) return;
    setBusy(true);
    const res = await calculatorsApi.save(selected.id, inputs, {
      label: saveLabel.trim() || undefined,
      opportunity_ref: saveOpp.trim() || undefined,
    });
    setBusy(false);
    if (res.ok) {
      setSaveNote(`Saved ${res.data.saved_calculation.id}.`);
      setSaveLabel("");
      void loadSaved();
    } else {
      setSaveNote(`Could not save: ${res.error}`);
    }
  };

  const remove = async (id: string) => {
    const res = await calculatorsApi.deleteSaved(id);
    if (res.ok) void loadSaved();
  };

  if (error) return (
    <div className="tab-panel">
      <h2>Calculators</h2>
      <div className="banner-note"><Icon name="alert" /> {error}</div>
    </div>
  );

  return (
    <div className="tab-panel">
      <h2>Deterministic calculators</h2>
      <p className="research-review-hint">
        Every number is computed server-side with the full formula shown — the same
        inputs always produce the same outputs. A calculation over assumed inputs is
        illustrative, not a validated figure; nothing here is written to the knowledge base.
      </p>

      {catalog === null ? (
        <p className="empty-note">Loading calculators…</p>
      ) : (
        <>
          <label className="calc-field">
            <span>Calculator</span>
            <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}
              data-testid="calc-select">
              {catalog.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
          </label>

          {selected && (
            <>
              <p className="calc-desc">{selected.description}</p>
              {selected.notes.map((n, i) => (
                <p key={i} className="calc-note-line">· {n}</p>
              ))}

              <div className="calc-inputs">
                {selected.inputs.map((spec) => (
                  <div key={spec.name} className="calc-input-row">
                    <label className="calc-field">
                      <span>{spec.name} <em>({spec.unit})</em>{spec.required ? "" : " · optional"}</span>
                      <input type="number" inputMode="decimal"
                        value={fields[spec.name]?.value ?? ""}
                        placeholder={spec.description}
                        onChange={(e) => setFields((f) => ({
                          ...f, [spec.name]: { ...f[spec.name], value: e.target.value },
                        }))} />
                    </label>
                    <select aria-label={`basis for ${spec.name}`}
                      value={fields[spec.name]?.label ?? "A"}
                      onChange={(e) => setFields((f) => ({
                        ...f, [spec.name]: { ...f[spec.name], label: e.target.value },
                      }))}>
                      {LABELS.map((l) => <option key={l.value} value={l.value}>{l.text}</option>)}
                    </select>
                    <input type="text" className="calc-note-input" placeholder="source / note (optional)"
                      value={fields[spec.name]?.note ?? ""}
                      onChange={(e) => setFields((f) => ({
                        ...f, [spec.name]: { ...f[spec.name], note: e.target.value },
                      }))} />
                  </div>
                ))}
              </div>

              <div className="calc-actions">
                <button className="send-btn" disabled={busy} onClick={compute} data-testid="calc-compute">
                  {busy ? "Computing…" : "Compute"}
                </button>
              </div>
              {computeError && <div className="banner-note"><Icon name="alert" /> {computeError}</div>}
            </>
          )}

          {envelope && (
            <>
              <ShownWorking env={envelope} />
              <div className="calc-save">
                <input type="text" placeholder="label (optional)" value={saveLabel}
                  onChange={(e) => setSaveLabel(e.target.value)} />
                <input type="text" placeholder="attach to OPP-nnn / UOPP-… (optional)" value={saveOpp}
                  onChange={(e) => setSaveOpp(e.target.value)} />
                <button className="btn-secondary" disabled={busy} onClick={save} data-testid="calc-save">
                  Save calculation
                </button>
                {saveNote && <span className="research-review-hint">{saveNote}</span>}
              </div>
            </>
          )}
        </>
      )}

      <h3>Saved calculations</h3>
      {saved.length === 0 ? (
        <p className="empty-note">No saved calculations yet.</p>
      ) : (
        saved.map((s) => (
          <div key={s.id} className="calc-saved-row" data-testid="calc-saved-row">
            <span className="calc-saved-title">{s.label || s.title || s.calculator}</span>
            <span className="research-profile-chip">{s.calculator}</span>
            {s.opportunity_ref && <span className="research-profile-chip">{s.opportunity_ref}</span>}
            <span className="research-source-meta">{s.created_at.slice(0, 10)}</span>
            <button className="btn-secondary" onClick={() => void remove(s.id)}
              aria-label={`delete ${s.id}`}>Delete</button>
          </div>
        ))
      )}
    </div>
  );
}
