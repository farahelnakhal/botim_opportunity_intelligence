# Deterministic calculators (Phase C1) — schema v1

Contract for the deterministic-calculator surface. Implementation:
`shared/calculators/` (`base.py` — the typed-step engine + F/E/A provenance;
`calculators.py` — the registry; `render.py` — shown-working markdown;
`store.py` — the `CALC-` runtime store at `CALCULATORS_DB_PATH`, default
`runtime/calculators.db`, gitignored). Exposed by the executive API
(`/calculators/*`) and the copilot (`run_calculator` / `list_calculators`
tools). Changes to this contract are **additive only**.

Everything a calculator produces is a **pure function of its inputs**: the same
inputs always yield the same outputs. A calculation over assumed/estimated
inputs is **illustrative / preliminary — never a validated figure**. No
calculator writes `knowledge-base/`; the LLM never performs the arithmetic (it
only narrates the computed numbers). It is the prerequisite for **C2**
(verified-source TAM/SAM/SOM), which will bind each input to an `RSRC-` source
via the reserved `source_id` field.

## ID namespace

| Prefix | Object | Shape |
|---|---|---|
| `CALC-` | a saved calculation | `CALC-<12 hex>` |

Cannot collide with any other namespace (`OPP-`, `UOPP-`, `RRUN-`, `RQRY-`,
`RSRC-`, `RCAND-`, `RREV-`, `AWV-`, `WSUB-`, `MCFG-`, `MEVT-`, `DOC-`, `USER-`).

## Provenance labels (F/E/A)

Every input carries a label — `F` (fact), `E` (estimate), `A` (assumption);
a bare number defaults to `A`. Labels **propagate worst-of** through each step,
so a result is only as strong as its weakest input, and the "illustrative"
disclaimer is derived automatically (any `A`/`E` → illustrative). An input may
be a bare number or `{value, label, note, source_id?}`; `source_id` is
**reserved for C2** (accepted, unused in C1).

## Result envelope (the pure `compute` output; also the persisted shape)

| Field | Type | Notes |
|---|---|---|
| `calculator_id` | string | registry id |
| `calculator_version` | int | stamps the formula that produced the result (re-derivability) |
| `title` | string | human title |
| `normalized_inputs` | `{name: {value, label, note, source_id}}` | every input, normalized |
| `steps` | step[] | the typed dataflow (below) |
| `outputs` | `{key: output}` | final named results (below) |
| `warnings` | string[] | plausibility / honesty warnings (e.g. not-gross-MDR) |
| `result_label` | `F\|E\|A` | worst-of over the outputs |
| `disclaimers` | string[] | illustrative / not-a-bank stamps, derived from the label + calculator |

### Step (machine-checkable, not display-only)

| Field | Type | Notes |
|---|---|---|
| `output` | string | the quantity this step produces |
| `op` | `add\|sub\|mul\|div\|pow` | the operation |
| `operands` | `[{ref, value, label, const?}]` | ordered; `ref` is an input/step name or a constant |
| `result` | number | engine-computed (raw, full precision) |
| `result_display` | string | presentation only — **never fed back into computation** |
| `label` | `F\|E\|A` | worst-of the operands |
| `unit` | string | declared output unit |
| `expression` | string | the formula, rendered from the spec |
| `substituted` | string | the formula with operand values plugged in |

A self-consistency check re-evaluates `op(operands)` for every step and confirms
it equals `result` (and that each declared output traces to a produced
quantity) on every compute — a rendering/typo bug is a `500`, never a wrong
number shown.

### Output

| Field | Type | Notes |
|---|---|---|
| `value` | number \| null | null for an honest "never"/"undefined" |
| `label` | `F\|E\|A` | |
| `unit` | string \| null | |
| `kind` | string | `currency\|count\|percent\|ratio\|months\|never\|undefined\|…` |
| `display` | string | formatted value, or the literal `never`/`undefined` |
| `reason` | string | present only for a null value — why it is undefined/never |

## Calculators (schema v1)

`market_sizing` (top-down TAM/SAM/SOM) · `market_sizing_bottomup` ·
`growth_projection` (forward CAGR) · `implied_cagr` · `adoption_forecast` ·
`unit_contribution` · `breakeven` · `payback_period` · `payments_take`. Each
declares an ordered input list (`name`, `unit`, `kind`, `required`,
`description`, `min`, `max`); `GET /calculators` returns the live catalog. A
`fraction` input must be 0..1 (rejected with a "not a percent" hint if >1);
a non-positive denominator yields an honest "never"/"undefined", never 0.
`payments_take` requires a **net** take (bps) and always warns that BOTIM never
earns the full (gross) MDR, flagging issuer-implying magnitudes — BOTIM is not
assumed to be a bank/issuer/lender.

## Saved calculation (`CALC-` store)

A saved row stores the full envelope plus `calculator_version` and
`normalized_inputs`, so any saved result is re-derivable/verifiable against the
formula that produced it. Additional fields: `id` (`CALC-`), `calculator`,
`title`, `label`, `opportunity_ref` (`OPP-`/`UOPP-` link, optional),
`owner_user_id` (owner-scoped; legacy NULL-owner rows shared; a foreign row is
an indistinguishable 404 — same rule as the research/user stores), `created_at`.

## HTTP (executive API; `/api/` and `/executive-api/` aliases)

| Route | Behavior |
|---|---|
| `GET /calculators` | catalog: each calculator + its input specs (read-only) |
| `POST /calculators/{name}/compute` | **stateless** — body `{inputs}` → the full envelope; nothing saved |
| `POST /calculators/{name}` | compute **and save** → `{saved_calculation}` (body `{inputs, label?, opportunity_ref?}`); owner-scoped; `calculator_save` quota |
| `GET /calculators/results[?opportunity_ref=]` | list saved calculations (owner-scoped) |
| `GET /calculators/results/{CALC-id}` | one saved calculation (owner-scoped; foreign → 404) |
| `DELETE /calculators/results/{CALC-id}` | real delete (owner-guarded) |

Errors are structured `{error: message}` with no SQL/paths/keys; a bad id shape
is `400`, a missing/foreign record `404`, a bad input `400`.

## Copilot integration (additive to conversation-api.schema.md)

- `list_calculators()` — the catalog + required inputs; the model calls it to
  learn what `run_calculator` needs and **asks the user for missing inputs
  rather than inventing them**.
- `run_calculator(calculator_id, inputs)` — computes and returns the envelope +
  rendered shown-working. Read-only (never saves); the formula is fixed (no
  expression is ever evaluated from user text).
- Grounding presents the shown working as facts (formula, substituted values,
  result), routes assumption-labelled inputs into `assumptions`, warns
  illustrative, sets confidence `low`, and applies the no-decision banner.
- A **numeric-fidelity guard** (wordguard) rejects any large figure in the
  model's prose that is not in the grounded facts, falling back to the exact
  computed working — the model may only narrate the calculator's numbers.
