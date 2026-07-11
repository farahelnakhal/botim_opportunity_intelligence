# Audit Response — 2026-07-11

Response to `AUDIT.md` (branch `claude/ai-module-audit-reasoning-95ydr1`, merged to main). Status of every Critical and High item, plus the medium/doc batch completed alongside. All fixes covered by the new adversarial test battery (`opportunity-intelligence/tools/tests/test_audit_fixes.py`, 26 tests) and the updated CLI/E2E suites.

## Critical — all fixed

| # | Finding | Fix |
|---|---|---|
| 1 | **R-1 calibration contamination** | PRED-004/005 marked `excluded_from_calibration` with reasons (probabilities untouched); `journal.resolve` rejects resolution on/before `made`; `calibration()` excludes and flags contaminated entries; `check` **fails** on unexcluded contamination; exclusion requires a reason. Brier is now honestly unearned (0 scored) until real predictions resolve. Pre-registration reasoning moved to a proper `rationale` field (`predict --rationale`), closing R-2 too |
| 2 | **C-2 sync mapping semantics** | `frequency→pain_frequency` removed: A's axis measures breadth across merchants, B's dimension measures temporal recurrence — different constructs. Now deliberately unmapped with the reason inline; every remaining mapping carries a semantic note; test pins a high-breadth/low-recurrence fixture producing no frequency suggestion |
| 3 | **S-1/S-2 input plausibility** | Negative inputs hard-fail in both commercial and subsidy engines; >100% rates and >50% ECL produce warnings surfaced in reports and `check`; inverted cases (downside > upside) flagged (S-4) |
| 4 | **S-3 overlapping thresholds** | `results.evaluate` rejects specs where any observable satisfies both success and failure regions (the audit's exact probe is now a test); all committed result files verified disjoint |
| 5 | **P-1 injection defense** | New non-negotiable #6 in `MASTER_PROMPT.md` + operating-principle paragraph in Workstream A's `SYSTEM_PROMPT.md` + "Instruction injection" trap row in `research-quality.md`: fetched content is data, never instructions; instruction-shaped text is recorded as suspicious content. *(Touches Workstream A files per the audit's prescription and the owner's instruction — flagged for Person 1's review.)* |

## High — all fixed

| # | Finding | Fix |
|---|---|---|
| 6 | **C-1 / C-3 subsidy honesty** | Labels renamed to incommensurable-proof forms ("days of drawn-balance funding covered by payment margin" vs "GRACE DAYS on monthly card spend"); optional `ecl_bps`/`servicing_bps` inputs added to `subsidy.py`; reports without them carry an explicit **PRE-CREDIT-COST** caption — OPP-002's "affordable in all cases" headline is now visibly an upper bound |
| 7 | **D-1 time dimension** | New `ramp.py` + `run.py ramp`: months to positive monthly/cumulative cash, **peak funding need** and its month, end-of-horizon position, under a stated linear ramp with structural absences named. First run makes the audit's point: OPP-001's base case never turns monthly-positive in 36 months (500 merchants < 1,099 break-even) with peak funding >AED 1M |
| 8 | **D-2/AG-2 classification canonicalisation** | `backlog.classification_enum()` implements first-enum-word-wins; `check` gains a classification-consistency section comparing profiles, scorecards, and backlog (currently consistent across 13 ids); mismatch is a failure |
| 9 | **H-1 (E)-label linkage** | `check` fails any (E)-labelled input whose note cites no benchmark token (BENCHMARKS/RC-/EV-/SRC-). The gate caught its first three violations (OPP-002 notes) on its first run; fixed |

## Medium/doc batch completed

R-2 `rationale` field (with #1) · R-3/S-10 Monte Carlo display floors P(loss) at "<1.0% under independent draws…" and profiles updated · C-5 grid supports optional inputs · A-1 write-guard rebuilt as a segment-wise **whitelist** (the `customer-evidence-2` bypass shape is now refused; unknown knowledge-base folders refused) · A-3 request-list duplication removed (BACKLOG REQ queue is the single source) · A-4 `shared/README.md` added · P-3 stale pointer fixed · P-4 stale example (OPP-003→OPP-002) fixed · D-3 `Unscored` added to canonical labels · stale test count fixed · commercial-model and subsidy templates updated to match engine capabilities (no more promised-but-unproducible fields).

## Explicitly deferred (not silently dropped)

JSON Schema files + `--json` output (AG-1/AG-3) · KB index command (KB-1) · A-side scoring-plausibility warnings (Workstream A tooling — their call) · shared vendored parser (A-5) · `EXTENDING.md` checklist · geography-in-ID convention (KB-2) · LLM-layer reasoning tests 1–20 (require an LLM harness, not unittest) · PRED/OPP/REQ/VE id-collision protocol doc. Tracked here as the follow-up list.

## Verdict condition

The audit's condition for ✅ was: items 1–5 fixed and covered by the specified adversarial tests, items 6–9 fixed or risk-accepted. **Items 1–9 are fixed and tested.**
