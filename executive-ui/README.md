# Executive UI — BOTIM Product Discovery Copilot

A read-only, executive-facing view over the three workstreams' committed outputs. It answers: what opportunities are we investigating, which segment, what evidence supports each, what assumptions remain, what changed, why a score changed, what to do next — and, prominently, **whether anything has been validated or selected (it has not).**

## Run it

```bash
python3 executive-ui/build.py            # render static HTML into executive-ui/dist/
python3 executive-ui/build.py --serve    # build, then serve dist/ at http://localhost:8000
```

Pure Python 3 standard library — no Node, no npm, no build toolchain. Output (`dist/`) is gitignored; only source is committed.

## Architecture (read-only, single source of truth)

```
repository outputs ──► adapter/collect.py ──► UIModel ──► render/*.py ──► static HTML + app.css/app.js
   (scorecards,          (reuses B's scoring,     (dataclasses)   (server-rendered,
    evidence, backlog,    evidence, backlog,                       stdlib string
    journal, monitoring)  journal + C's monitoring                templating)
                          engines — NO recompute)
```

- **No second scoring engine.** The adapter calls `opportunity_engine.scoring.evaluate` etc.; the UI never recalculates scores or reinterprets confidence.
- **Never writes to the knowledge base.** Reads only; the sole output is `dist/`.
- **No invented data.** Missing fields render as "—"; empty inputs render honest empty states.

## Screens

Overview · Opportunity Detail (all 17 factors, never hidden) · Evidence Traceability (weak evidence visually separated as "leads, not findings") · Assumptions & Gaps (client-side filtering) · Intelligence Feed · Rescore Review (read-only) · Executive Brief (consumes recommendation docs).

## Honest scope notes (features the brief assumed that don't exist yet)

- **No impact-proposal / approval / rollback workflow exists** in the system. Screens 5–6 are read-only and show the closest real analogue (monitoring alerts / report-only rescore suggestions); **no fake approval controls** are rendered.
- **No executive-brief generator exists** — the Brief screen consumes committed recommendation docs where present (currently OPP-001) and shows honest empty states elsewhere.
- **Assumption status/sensitivity/owner and per-factor score history are not structured fields** — derived where possible, shown as "—" otherwise.

## Tests

```bash
python3 -m unittest discover -s executive-ui/tests
```

Adapter correctness, render/empty-state tests, weak-vs-strong evidence display, score before/after, the "no affirmative validated/selected claim" guard (distinguishes negations), OPP-013 + another opportunity, and the EV-TEST-001 synthetic scenario in an isolated sandbox that leaves live data untouched. Wired into `shared/integration_check.py`.
