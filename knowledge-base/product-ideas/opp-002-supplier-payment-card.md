# OPP-002 — Supplier-Payment Commercial Card with Free-Credit Days

Opportunity profile. Classification: **Promising but unvalidated (borderline Weak)** — gated on VE-002. Linked artefacts: subsidy model (`../commercial-models/opp-002-subsidy-inputs.json`, run with `run.py subsidy`), experiment (`../validation/VE-002-supplier-payment-mapping.md`), pre-committed result file (`../validation/VE-002-result.json`). Worked illustration: `opportunity-intelligence/test-cases/02-…`. Full commercial model and scorecard: **deliberately not built until VE-002 reports** — supplier acceptance is empirical, not modellable.

## Proposition

A BOTIM commercial Visa card (AstraTech credit behind it) that merchants use to **pay suppliers**. N interest-free days funded partly by issuer interchange on supplier spend; AstraTech earns financing revenue on balances revolved beyond the free period.

- **Segment (A):** trading/retail SMEs buying AED 30k–150k/month of stock from card-payable (or onboardable) suppliers.
- **Organic switching reason:** free-credit days on spend that already exists + credit access without bank paperwork.
- **Terminology check:** the supplier (accepting merchant) pays MDR to its acquirer; BOTIM earns issuer interchange / programme share only — the subsidy engine has no MDR input by construction.

## What the engine says (subsidy model — interchange now sourced (E))

2026-07-11 refinement: gross interchange re-based from 90/130/170 (A) to **130/180/200 (E)** on the official Visa UAE schedule (domestic commercial cards 2.00–2.10% general segments; segment programs/large-ticket lower — `../commercial-models/BENCHMARKS.md`). Net payment margin is now **65/110/120 bps**; the free-day ceiling **~30/50/55 days**, and the 20-free-day package is **affordable in all three cases** (previously a downside loss-leader). Programme splits remain (A) — the next number to firm. UAE's uncapped domestic interchange makes the card-economics-fund-free-credit hypothesis materially stronger than first modelled; supplier acceptance (VE-002) remains the decisive gate.

## Stress test (summary)

- **FOR:** spend already exists; the card monetises it and free days are a genuine, quantifiable benefit; underwriting sees supplier-spend patterns.
- **AGAINST — the decisive unknown:** **supplier acceptance.** UAE wholesale suppliers on bank transfer + 30/60-day terms have little reason to eat 1.5–2.5% MDR. If suppliers surcharge or refuse, eligible volume collapses. This is the "economics + demand" answer to why it hasn't been built.
- **Adverse selection:** immediate revolvers (can't repay inside the free period) are most attracted; interchange doesn't cover their risk.
- **Fraud:** collusive merchant–supplier fake invoicing to cash out credit lines.
- **Disproof (pre-committed in VE-002):** <20% of mapped supplier relationships card-payable without surcharge → reclassify Weak.

## Status

- **Evidence confidence:** Low. **Main invalidation risk:** supplier acceptance below threshold.
- **Dependency:** VE-002 field work; REQ-003 evidence (how merchants pay suppliers today).
- **Next action:** run VE-002; on pass, build full commercial model (needs engine schema widened for acquiring/mix/duration — see audit) and MVP design; results also feed OPP-006.

*Changelog: 2026-07-10 — profile migrated from test-cases/ (audit remediation); content unchanged in substance.*
