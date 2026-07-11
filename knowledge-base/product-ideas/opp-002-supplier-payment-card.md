# OPP-002 — Supplier-Payment Commercial Card with Free-Credit Days

Opportunity profile. Classification: **Promising but unvalidated (borderline Weak)** — gated on VE-002. Linked artefacts: subsidy model (`../commercial-models/opp-002-subsidy-inputs.json`, run with `run.py subsidy`), experiment (`../validation/VE-002-supplier-payment-mapping.md`), pre-committed result file (`../validation/VE-002-result.json`). Worked illustration: `opportunity-intelligence/test-cases/02-…`. Full commercial model and scorecard: **deliberately not built until VE-002 reports** — supplier acceptance is empirical, not modellable.

## Proposition

A BOTIM commercial Visa card (AstraTech credit behind it) that merchants use to **pay suppliers**. N interest-free days funded partly by issuer interchange on supplier spend; AstraTech earns financing revenue on balances revolved beyond the free period.

- **Segment (A):** trading/retail SMEs buying AED 30k–150k/month of stock from card-payable (or onboardable) suppliers.
- **Organic switching reason:** free-credit days on spend that already exists + credit access without bank paperwork.
- **Terminology check:** the supplier (accepting merchant) pays MDR to its acquirer; BOTIM earns issuer interchange / programme share only — the subsidy engine has no MDR input by construction.

## What the engine says (subsidy model, all (A))

Net payment margin 25/60/90 bps across cases. The ceiling if the whole budget funds free days: ~11/27/41 days. A **20-free-day package survives base and upside but is a loss-leader in downside**; a 45-day offer is a loss-leader everywhere except upside and must be flagged as such or funded from proven lending margin.

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
