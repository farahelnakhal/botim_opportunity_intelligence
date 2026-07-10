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

# Check EV-id citations before putting them in a scorecard; exit code 2 on missing/malformed
python3 opportunity-intelligence/tools/run.py cite EV-2026-W28-001,EV-2026-W28-002

# CI-style sweep of the whole knowledge base: every model computes, every scorecard
# passes caps, every VE spec has quantified pre-committed thresholds, the backlog is
# internally consistent and its VE/REQ references resolve. Exit code 1 on any failure.
python3 opportunity-intelligence/tools/run.py check
```

Run `check` before every commit that touches `knowledge-base/` — it is the module's regression test.

Add `--write <path>` to `model`/`subsidy`/`score` to save the report as markdown. The tool refuses to write into Workstream A or shared paths.

## Inputs

Machine-readable inputs live next to their markdown models in this module's knowledge-base folders:

- `knowledge-base/commercial-models/<opp>-inputs.json` — commercial model
- `knowledge-base/commercial-models/<opp>-subsidy-inputs.json` — subsidy model
- `knowledge-base/opportunity-scores/<opp>-scorecard.json` — scorecard

Every numeric input may be `{"value": n, "label": "F|E|A", "note": "..."}`; bare numbers default to label **A** (assumption). All three cases (downside/base/upside) are mandatory — the engine refuses single-case models.

## Discipline enforced in code, not just prose

- **No full-MDR error:** the subsidy model has no MDR input — it starts from issuer interchange / programme share bps, so the error cannot be expressed.
- **One subsidy budget:** free days + cashback + fee subsidies are charged against the same budget (stacking check); 2% cashback against 60 bps margin fails, as OPP-003 did.
- **All 17 scores or nothing:** scorecards missing dimensions are rejected; half-points are rejected.
- **Assumption cap:** >6 of 17 assumption-based scores blocks a `strong` classification (exit code 2).
- **Critical floors:** low pain severity / switching intent / credit-risk visibility / MVP feasibility raise flags for stress-test scrutiny.
- **Evidence honesty:** citations are checked against real records; records with evidence strength ≤2 or status `needs-more-evidence` are flagged as leads, not findings.
- **No unfalsifiable experiments:** VE specs missing any mandatory field, or with hypotheses/thresholds that contain no number, fail `check` (`experiments.py`).
- **Backlog integrity:** duplicate OPP ids, `reject` rows outside the archive, live rows without a next action, and dangling VE-/REQ- references all fail `check` (`backlog.py`).

## Workstream A integration

`opportunity_engine/evidence.py` parses `knowledge-base/customer-evidence/records/YYYY-Wnn.md` files in Workstream A's `customer-evidence.md` template format (`EV-YYYY-Wnn-nnn` ids, 10-axis dotted score blocks). Read-only by design; this answers REQ-001 from our side — we consume their scheme as published.

## Tests

```bash
python3 -m unittest discover -s opportunity-intelligence/tools/tests -v
```

36 tests pin the engine to the published OPP-001/OPP-002 numbers and run the process validators against the repo's real knowledge-base files, so code, markdown, and process artefacts can't silently drift.
