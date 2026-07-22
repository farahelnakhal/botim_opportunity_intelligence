# Verified-source market sizing (Phase C2) — schema v1

Persistence + composition contract for candidate TAM/SAM/SOM sizings built from
a research run's verified, tier-ranked figures. Implementation:

- `shared/research/figures.py` — extract + verbatim-verify numeric figures
  (see `research.schema.md`, `RFIG-`).
- `shared/research/corroboration.py` — the pure corroboration engine.
- `shared/market_sizing/store.py` — the `MSZ-` candidate store (runtime SQLite
  at `MARKET_SIZING_DB_PATH`, default `runtime/market-sizing.db`, gitignored).
- `executive-ui/api/market_sizing_builder.py` — the composition orchestration
  (figures → corroboration → the C1 `market_sizing` calculator).

Changes to this contract are **additive only**.

**Nothing here is authoritative knowledge.** A sizing is a *candidate*: a human
approves or rejects it exactly once, and approval **never** writes a committed
score or `knowledge-base/` — that stays the `impact` CLI (`--approver`). No
number is ever computed or estimated by a model; every figure traces to a
cited source.

## ID namespace

| Prefix | Object | Shape |
|---|---|---|
| `MSZ-` | candidate market sizing | `MSZ-<12 hex>` |

Cannot collide with committed KB ids (`EV-`, `OPP-nnn`, …), the runtime
`UOPP-`/`MCFG-`/`CALC-` namespaces, or the research `RRUN-`/`RSRC-`/`RFIG-`… ids.

## Candidate lifecycle

```
pending_review -> approved | rejected     (exactly once; 409 if already terminal)
```

Terminal states are immutable. Approval records `reviewed_at`, `reviewer`,
`review_note` — and nothing else: no score, no KB write, no EV id.

## Object

`id` (`MSZ-`), `opportunity_id` (`OPP-nnn` — the committed opportunity the
sizing attaches to), `status` (`pending_review|approved|rejected`), `calculator`
(the C1 calculator id used, e.g. `market_sizing`), `run_id` (the source
`RRUN-`), `confidence` (`verified|low_confidence`), `sizing` (the envelope
below), `reviewed_at?`, `reviewer?`, `review_note?`, `owner_user_id?` (R8b
ownership — legacy NULL rows stay shared; a foreign row answers an
indistinguishable 404), `created_at`.

### `sizing` envelope

`method` (`top_down|bottom_up`), `calculator`, `envelope` (the **C1 typed-step
envelope** — sourced inputs carry a populated `source_id` and their F/A label,
so TAM/SAM/SOM trace back to sources through the calculator's own provenance),
`inputs_meta` (per-input corroboration verdict / assumption detail), `run_id`,
`overall_confidence`, `confidence_basis` (a human-readable sentence).

## Corroboration & the evidence-label invariant

A **sourced** input is `verified` only when **≥2 independent T1/T2 sources agree
within the tolerance band** (default 10% relative; `C2_CORROBORATION_TOLERANCE`
overrides). *Independent* = distinct registrable domain (a primary + an
aggregator repeating it is one voice — this is why Statista, tiered T3 as an
aggregator, can never be the second corroborator). Otherwise the input is
`low_confidence` (single-source, lower-tier only, disagreeing, or unit
mismatch). The overall sizing is `verified` iff every sourced input is verified.

**Evidence label (invariant, decision-log C2 · H3):** inside the C1 calculator's
own typed-step labels, a corroborated sourced input carries **F** (Fact), a
low-confidence sourced input carries **A** (Assumption), and analyst fractions
(`serviceable_fraction`, `obtainable_share`) always carry **A**. So a
low-confidence figure and a corroborated one are **never identical** — not
merely on a UI badge, but in the calculator's label propagation itself. This is
distinct from the review-status axis (`pending_review`/`approved`); the two are
never collapsed. The UI reinforces this: verified vs low-confidence render as
distinctly-worded, distinctly-classed badges, never the same chip.

## Honesty rules

- A sourced input with **no figures** refuses the build (422, the missing
  quantity named) — a market-size input is never invented.
- No model computes, estimates, rounds, or expands any number; figures are
  verbatim-verified before they enter (see `research.schema.md`).
- `low_confidence` is stored and shown, never dropped and never silently
  upgraded to `verified`.

## HTTP (both `/api/` and `/executive-api/` aliases)

| Route | Behavior |
|---|---|
| `POST /opportunities/{OPP-nnn}/market-sizing` | compose + persist a candidate. Body `{run_id, method, inputs}` where each sourced input is `{quantity}` and each assumption is `{value, note?}`. Deterministic; **no model runs**. Mode-gated (demo corpus), quota-guarded, run owner-guarded. Missing figure → 422; bad input → 400. Returns 201 with the candidate |
| `POST /market-sizing/{MSZ-id}/review` | `{action: "approve"\|"reject", note?}` — exactly once; 409 if already reviewed; owner-guarded 404 |
| `GET /market-sizing[?opportunity_id=OPP-nnn]` | `{market_sizings: [sizing…]}` — owner-scoped; honest empty list |
| `GET /market-sizing/{MSZ-id}` | the candidate; 404 if absent/foreign; 400 on malformed id |

No PUT/DELETE routes exist. Errors are structured `{error: message}` with no
stack traces.
