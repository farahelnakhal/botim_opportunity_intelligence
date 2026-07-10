# OPP-009 — F&B Weekend-Cycle Credit (Sector-Specific Ultra-Short Revolving)

**Classification: Weak (as a standalone product) — fold into OPP-001 as a segment configuration.**

Dry-run evaluation: this file is the module's acceptance test on a fresh idea, produced end-to-end with the frameworks and engine (`opp-009-scorecard.json`, `opp-009-inputs.json`, `opp-009-computed.md`). All customer numbers are `(A)`.

## Proposition

Ultra-short revolving credit for small F&B merchants matched to the weekly cash cycle: draw Thursday for weekend stock, weekend receipts arrive into the BOTIM wallet, repayment sweeps Monday. 4–7 day cycles, per-cycle fees (~0.5%/cycle ≈ 26% annualised), limits sized to one weekend's stock.

- **Segment (A):** F&B, 1–2 outlets, AED 60k–130k monthly revenue, UAE.
- **Organic switching reason:** credit timed exactly to the sector's cash rhythm; repayment invisible.

## What the engine says

- **Scorecard:** composite 3.5, 15/17 `(A)` → capped at "promising" regardless of merit. No critical-dimension flags; credit-risk visibility is the standout strength (4 — a 5-day feedback loop surfaces defaults within a week).
- **Commercial model (base):** contribution **+70** AED/merchant/month at a healthy 38.8% margin — but absolute revenue is small (avg drawn balance only ~3.8k), so **break-even needs ≈1,987 merchants against a base-case count of 300**. Downside is loss-making (−49).
- **Monte Carlo (10k draws):** P50 contribution 64, P5–P95 of 6–148, P(loss) 3.2% — riskier than OPP-001's 0.9% because the margin cushion is thinner.
- **Scenarios:** perfect_storm and credit_and_run kill it. Notably, **adverse_selection survives here (+37)** — small balances and the fast cycle cap the damage — but **routing_decay nearly kills it (+3)**: the entire design hangs on weekend receipts being routed.
- **Sensitivity:** top risks are merchant revenue, routed share, and payment take — i.e. the same routing question as OPP-001, concentrated on weekends.

## Stress test (decisive sections)

- **Strongest case FOR:** the tightest possible underwriting loop in the whole idea family — weekly repayment evidence, small bounded exposures, sector-native product language ("weekend stock money").
- **Strongest case AGAINST:** it is not a product; it is **OPP-001 with different parameters** (smaller limit multiple, shorter duration, F&B targeting). As a standalone it duplicates OPP-001's entire infrastructure — onboarding, wallet rails, lending licence, collections — to earn roughly **half the contribution per merchant (+70 vs +136)** while needing ~2x the merchants to cover its own fixed costs. Nothing in it is defensible independently (defensibility scored 2).
- **Adverse selection / fraud / credit risk:** materially better than OPP-001 (fast feedback, small tickets) — this is the idea's genuine insight, and it transfers to OPP-001 as a policy: *shorter first cycles and weekend-linked sweeps for F&B cohorts*.
- **Why competitors haven't built it:** merchant cash advance products exist globally on acquirer rails; the weekly-cycle framing needs receipt visibility, which is (b) capability — but the capability belongs to whoever runs the wallet, i.e. OPP-001.
- **Disproof:** if VE-001 shows F&B merchants won't route weekend receipts, this dies with OPP-001; there is no independent survival path — which is itself the argument against standalone status.

## Verdict

**Weak as a standalone.** The classification is about product boundaries, not the idea's quality: the valuable parts (cycle-matched limits, fast-feedback underwriting, Monday sweeps) should be carried into OPP-001's concierge pilot as the F&B segment configuration, at near-zero extra cost. Revisit standalone status only if OPP-001's pilot shows F&B cohorts behaving so differently that they warrant separate economics.

- **Evidence confidence:** Low (15/17 assumption-based).
- **Main invalidation risk:** weekend receipts don't route (shared with OPP-001, tested by VE-001).
- **Dependency:** VE-001 outcome; REQ-002 evidence.
- **Next action:** fold cycle-matched limit/sweep parameters into OPP-001's MVP design; no separate experiment warranted.

*Changelog: 2026-07-10 — v1, dry-run evaluation; classified Weak-standalone / fold-into-OPP-001.*
