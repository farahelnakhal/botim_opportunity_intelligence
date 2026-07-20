// Deterministic-calculators client (Phase C1) — talks to executive-ui/api's
// /calculators/* routes (shared/contracts/calculators.schema.md). Honest
// failure shape everywhere: {ok:false, error}. The server computes every
// number and returns fully shown working; the client never does arithmetic.

const BASE = import.meta.env.VITE_EXECUTIVE_API_BASE_URL || "/executive-api";

export type CalcResult<T> = { ok: true; data: T } | { ok: false; error: string };

export type CalcInputSpec = {
  name: string;
  unit: string;
  kind: string;
  required: boolean;
  description: string;
  min: number | null;
  max: number | null;
};

export type CalculatorSpec = {
  id: string;
  title: string;
  description: string;
  version: number;
  notes: string[];
  inputs: CalcInputSpec[];
};

export type CalcOperand = { ref: string; value: number; label: string; const?: boolean };
export type CalcStep = {
  output: string;
  op: string;
  operands: CalcOperand[];
  result: number;
  result_display: string;
  label: string;
  unit: string;
  kind: string;
  expression: string;
  substituted: string;
  note?: string;
};
export type CalcOutput = {
  value: number | null;
  label: string;
  unit: string | null;
  kind: string;
  display: string;
  note?: string;
  reason?: string;
};
export type CalcNormalizedInput = {
  value: number;
  label: string;
  note: string;
  source_id: string | null;
};
export type CalcEnvelope = {
  calculator_id: string;
  calculator_version: number;
  title: string;
  normalized_inputs: Record<string, CalcNormalizedInput>;
  steps: CalcStep[];
  outputs: Record<string, CalcOutput>;
  warnings: string[];
  result_label: string;
  disclaimers: string[];
};

export type SavedCalculation = {
  id: string;
  calculator: string;
  calculator_version: number;
  title: string | null;
  label: string | null;
  opportunity_ref: string | null;
  owner_user_id: string | null;
  envelope: CalcEnvelope;
  created_at: string;
};

// a raw input the UI sends: a bare number or {value,label,note}
export type CalcInputValue = number | { value: number; label?: string; note?: string };

async function request<T>(path: string, init?: RequestInit): Promise<CalcResult<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...init,
    });
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      return { ok: false, error: "malformed response from the calculators API" };
    }
    if (!res.ok) {
      const msg = (body as { error?: string })?.error || `HTTP ${res.status}`;
      return { ok: false, error: msg };
    }
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, error: "the calculators API is unreachable" };
  }
}

export const calculatorsApi = {
  catalog() {
    return request<{ calculators: CalculatorSpec[] }>("/calculators");
  },

  compute(name: string, inputs: Record<string, CalcInputValue>) {
    return request<{ calculation: CalcEnvelope }>(
      `/calculators/${encodeURIComponent(name)}/compute`,
      { method: "POST", body: JSON.stringify({ inputs }) },
    );
  },

  save(
    name: string,
    inputs: Record<string, CalcInputValue>,
    extra?: { label?: string; opportunity_ref?: string },
  ) {
    return request<{ saved_calculation: SavedCalculation }>(
      `/calculators/${encodeURIComponent(name)}`,
      { method: "POST", body: JSON.stringify({ inputs, ...extra }) },
    );
  },

  listSaved(opportunityRef?: string) {
    const qs = opportunityRef ? `?opportunity_ref=${encodeURIComponent(opportunityRef)}` : "";
    return request<{ saved_calculations: SavedCalculation[] }>(`/calculators/results${qs}`);
  },

  deleteSaved(id: string) {
    return request<{ deleted: string }>(`/calculators/results/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  },
};
