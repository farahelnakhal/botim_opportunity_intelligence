# OPP-013 — Import Payment + Working-Capital Account

**Classification: Promising but unvalidated (borderline Weak — see critical flag).** Evidence confidence **Medium** (9/17 dimensions evidenced; 8 (A) → engine-capped at promising regardless). Full-scale combined-agent test: every stage below ran through both modules' tooling on 2026-07-11. Linked: scorecard `../opportunity-scores/opp-013-scorecard.json` · model `../commercial-models/opp-013-{inputs.json,computed.md}` · custom scenarios `opp-013-scenarios.json` · experiment `../validation/VE-004-importer-cycle-financing.md`.

## Proposition

One account for small UAE importers: **pay overseas suppliers by T/T through BOTIM at transparent all-in FX pricing, and finance the pay-upfront/collect-30-90-days-later gap with AstraTech credit repaid from the sales cycle.** Financing is conditional on routing supplier payments through the account — routing *is* the underwriting data. Target: importers below/outside the AED 1M+ eligibility floor that funded fintechs (CredibleX, Comfi) serve.

- **Segment:** `SEG-uae-importers-upfront-pay` (Workstream A; **Low confidence — their stated upgrade condition is exactly what VE-004 collects**).
- **Evidence base:** EV-2026-W28-013 (AED ~105–130/transfer + 1.5–2.8% FX spread, provider-hopping), EV-014 (T/T is the rail — cards capped out of the core job at $12–15k/3%), EV-015 (financing mechanism validated by LATR at 8–15% p.a.; **UAE small-importer demand explicitly unverified**), EV-017/019 (competitor execution/compliance weakness), IP-2026-002 (funded competitors deploying now).

## Reasoning protocol

1. **Outside view:** RC-4 (revenue-linked pricing 10–50%+ accepted) supports 18% pricing; RC-9 (77% unsecured rejection) supports the below-the-floor thesis; RC-2's routing caution applies less here — *paying* through a new rail is an easier behaviour change than *receiving* (payer controls the flow), which is why base routed share (60%) exceeds OPP-001's (30%). Divergence argued, not assumed.
2. **Pre-mortem:** *"Failed because our own transfer rails weren't ready — EV-018's 12-day delays happened to a financed supplier payment, the shipment was lost, and the story spread through the exact trade communities we recruited from."* Second story: transit/invoice fraud — financing payments for goods that never ship. Both are named scenarios in `opp-013-scenarios.json`.
3. **Disconfirmation:** cheap rails already exist (Wio AED 35–40, Wise from 0.31%, exchange houses) — Workstream A's own contradictory-evidence row says fee pain is provider-specific: **"capture, not category creation."** Therefore the transfer wedge alone fails the organic-switching test (switching_intent scored 2 → critical flag); the credit must carry the proposition. Also: EV-015 found *zero* independent borrower reviews of the funded competitors — category demand is still partly vendor narrative.
4. **Prediction:** PRED-007 — VE-004 passes both thresholds, p=0.40 (segment confidence Low pulls down; funded-competitor existence pulls up).
5. **Sensitivity conditioning:** viable *if* merchants route ≥ ~45% of supplier volume and net FX take holds ≥ ~50 bps — routed_share and payment_take_bps are tornado ranks 2–3 behind volume. Base break-even (364 merchants) sits almost exactly at base active count (350): the base case is knife-edge by construction, honesty over optimism.
6. **This changes if:** VE-004 interviews refute the payment-timing pattern (segment thesis dies); or BOTIM's transfer rails can't hit business-grade execution SLAs (EV-018 unresolved = hard gate); or CredibleX/Comfi publish real traction below the AED 1M floor (whitespace closes).

## Engine results (all commands run 2026-07-11, committed artefacts)

| Layer | Result |
|---|---|
| Scorecard | Composite 3.2 · 8/17 (A) → capped at promising · **critical flag: switching_intent ≤ 2** |
| Model (base) | **+468/merchant/month** (52% margin) · break-even **364 vs 350 base merchants** · downside −40 · upside +2,852 · credit turns 5.6×/yr |
| Monte Carlo (20k draws) | P50 +461 · P5 +183 · **P(loss) 0.0%** (independence caveat as always) |
| Built-in scenarios | 7/8 survive · **credit_and_run kills (−26)** · perfect_storm barely survives (+40) |
| Custom scenarios | 5/5 survive · worst: **own_rail_failure +115** (the EV-018 scenario) · fx_margin_compression +180 |
| Sync bridge | **No divergence** — demand scores were written to the cited evidence's own axis values |
| Citations | 4 cited, all resolve; EV-018 correctly auto-flagged weak (lead, not finding) |

## Honest read

The economics are the strongest per-merchant in the backlog *if* the routing assumption holds, and the segment-fit logic (below-the-floor importers, payer-controlled routing) is coherent. But three things keep this at borderline: evidence says fee-switching intent is weak (flag fired), the segment itself is Low confidence, and two funded competitors are deploying into the adjacent space right now. The single cheapest de-risk is VE-004 — which also happens to be the exact instrument Workstream A needs to upgrade their segment confidence: one experiment, both modules paid.

**Dependencies:** VE-004 field work; EV-018 rail-quality resolution (internal, hard gate before any pilot); REQ-007 (first-person importer accounts — shared with A's verification queue).
**Next action:** run VE-004; nothing else until it reports.

*Changelog: 2026-07-11 — created as the combined agent's full-scale test; all engine layers run and committed.*
