# Opportunity Intelligence Engine (tools)

Computation layer for this module's frameworks. Pure Python 3 standard library — no installs needed. The markdown frameworks define the method; this code executes it repeatably, so re-running a model after new evidence is one command, not a hand-rebuild.

## Commands (run from repo root)

```bash
# Three-case commercial model (contribution, break-even, subsidy ceilings)
python3 opportunity-intelligence/tools/run.py model knowledge-base/commercial-models/opp-001-inputs.json

# Interchange subsidy model for card products (max free days / cashback / fee subsidy)
python3 opportunity-intelligence/tools/run.py subsidy knowledge-base/commercial-models/opp-002-subsidy-inputs.json

# Validate a 17-dimension scorecard (caps, floors, composite); exit code 2 on violations
python3 opportunity-intelligence/tools/run.py score knowledge-base/opportunity-scores/opp-001-scorecard.json

# List Workstream A evidence records (read-only)
python3 opportunity-intelligence/tools/run.py evidence

# Evidence→scorecard sync: compare cited records' axis scores against scorecard
# dimensions via the agreed mapping; suggests re-scores / (A)-flips. Report-only.
python3 opportunity-intelligence/tools/run.py sync

# Check EV-id citations before putting them in a scorecard; exit code 2 on missing/malformed
python3 opportunity-intelligence/tools/run.py cite EV-2026-W28-001,EV-2026-W28-002

# Tornado sensitivity: perturb every input ±50% (harmful direction kept), rank by
# contribution damage — the assumption register's "if 50% worse" column, computed
python3 opportunity-intelligence/tools/run.py sensitivity knowledge-base/commercial-models/opp-001-inputs.json --case base --degrade 0.5

# Evaluate experiment results against their PRE-COMMITTED thresholds (verdict:
# pass / fail / inconclusive / pending; kill thresholds kill even mid-run)
python3 opportunity-intelligence/tools/run.py verdict knowledge-base/validation/VE-001-result.json

# Monte Carlo: 5,000+ draws from triangular distributions spanning the three cases;
# contribution/break-even distributions, P(loss). Deterministic (seeded).
python3 opportunity-intelligence/tools/run.py simulate knowledge-base/commercial-models/opp-001-inputs.json --n 10000

# Named adverse scenarios (credit_and_run, adverse_selection, rate_compression,
# perfect_storm, ...): correlated shocks that independent sampling can't produce.
# Custom scenario files via --scenarios.
python3 opportunity-intelligence/tools/run.py stress knowledge-base/commercial-models/opp-001-inputs.json

# Two-way stress grid: contribution across two inputs' ranges; the negative-cell
# boundary is the viability frontier
python3 opportunity-intelligence/tools/run.py grid knowledge-base/commercial-models/opp-001-inputs.json --x routed_share --y ecl_rate_annual

# CI-style sweep of the whole knowledge base: every model computes, every scorecard
# passes caps, every VE spec has quantified pre-committed thresholds, every result
# file evaluates, the backlog is internally consistent and its VE/REQ references
# resolve. Exit code 1 on any failure.
python3 opportunity-intelligence/tools/run.py check
```

When VE field work completes: fill the `observed` values in
`knowledge-base/validation/VE-nnn-result.json` (thresholds were pre-committed there
before the run — do not edit them), run `verdict`, and apply the pre-committed
`on_pass`/`on_fail`/`on_inconclusive` action to the backlog.

Run `check` before every commit that touches `knowledge-base/` — it is the module's regression test.

**Canonical-numbers rule:** every numeric table in a knowledge-base document must be an engine-written report (`--write`) from a committed inputs JSON. Narrative markdown interprets the numbers; it never hand-authors them. (Audit remediation 2026-07-10: OPP-001's hand-written tables were retired in favour of `opp-001-computed.md`.)

Add `--write <path>` to `model`/`subsidy`/`score` to save the report as markdown. The tool refuses to write into Workstream A or shared paths.

## Inputs

Machine-readable inputs live next to their markdown models in this module's knowledge-base folders:

- `knowledge-base/commercial-models/<opp>-inputs.json` — commercial model
- `knowledge-base/commercial-models/<opp>-subsidy-inputs.json` — subsidy model
- `knowledge-base/opportunity-scores/<opp>-scorecard.json` — scorecard

Every numeric input may be `{"value": n, "label": "F|E|A", "note": "..."}`; bare numbers default to label **A** (assumption). All three cases (downside/base/upside) are mandatory — the engine refuses single-case models.

**Optional card/acquiring inputs** (backwards-compatible; omit for wallet products): `acquiring_revenue_monthly`; the online/offline blend trio `offline_share` + `payment_take_bps_offline` + `payment_take_bps_online` (all-or-nothing, and `payment_take_bps` must then be 0 — the engine rejects double counting); `avg_credit_duration_days` (reporting-only: derives monthly originations and credit turns; the balance model embeds duration in utilisation). Monte Carlo samples optional inputs but rejects them if present in only some cases; sensitivity perturbs them (except the reporting-only duration); scenarios may shock them only in models that use them.

## Discipline enforced in code, not just prose

- **No full-MDR error:** the subsidy model has no MDR input — it starts from issuer interchange / programme share bps, so the error cannot be expressed.
- **One subsidy budget:** free days + cashback + fee subsidies are charged against the same budget (stacking check); 2% cashback against 60 bps margin fails, as OPP-003 did.
- **All 17 scores or nothing:** scorecards missing dimensions are rejected; half-points are rejected.
- **Assumption cap:** >6 of 17 assumption-based scores blocks a `strong` classification (exit code 2).
- **Critical floors:** low pain severity / switching intent / credit-risk visibility / MVP feasibility raise flags for stress-test scrutiny.
- **Evidence honesty:** citations are checked against real records; records with evidence strength ≤2 or status `needs-more-evidence` are flagged as leads, not findings.
- **No unfalsifiable experiments:** VE specs missing any mandatory field, or with hypotheses/thresholds that contain no number, fail `check` (`experiments.py`).
- **Backlog integrity:** duplicate OPP ids, `reject` rows outside the archive, live rows without a next action, and dangling VE-/REQ- references all fail `check` (`backlog.py`).
- **No post-hoc verdicts:** experiment outcomes are computed from thresholds committed before the run (`results.py`); a breached kill threshold fails the experiment even while other metrics are pending.
- **Mechanical sensitivity:** the harmful direction of each input is discovered by perturbation, not hand-labelled (`sensitivity.py`) — for OPP-001 it ranks `financing_rate_annual`, `monthly_revenue_per_merchant`, and `routed_share` as the top risks.
- **Stated simulation limits:** Monte Carlo (`montecarlo.py`) samples inputs independently and says so in every report; correlated adversity is covered explicitly by the named scenarios (`stress.py`), where for OPP-001 `credit_and_run`, `adverse_selection`, and `perfect_storm` all kill unit economics.
- **Reproducibility:** simulations are seeded and deterministic; the same command always yields the same report.

## Workstream A integration

`opportunity_engine/evidence.py` parses `knowledge-base/customer-evidence/records/YYYY-Wnn.md` files in Workstream A's `customer-evidence.md` template format (`EV-YYYY-Wnn-nnn` ids, 10-axis dotted score blocks). Read-only by design; this answers REQ-001 from our side — we consume their scheme as published.

## Tests

```bash
python3 -m unittest discover -s opportunity-intelligence/tools/tests -v
```

89 tests pin the engine to the published OPP-001/OPP-002 numbers, run the process validators against the repo's real knowledge-base files, and fuzz the core engine with 300+ randomized input sets asserting accounting identities (contribution = revenue − cost, break-even defined iff economics positive, net ≤ gross free days) and monotonicity properties (raising a cost never raises contribution; raising a revenue line never lowers it). Code, markdown, and process artefacts can't silently drift.
