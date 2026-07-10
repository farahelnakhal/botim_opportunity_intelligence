# OPP-001 — Revenue-Linked Revolving Credit on BOTIM Business Wallet

Opportunity profile. Classification: **Promising but unvalidated** (capped by 15/17 assumption-based scores). Linked artefacts: scorecard & stress test (`opportunity-intelligence/test-cases/01-revenue-linked-revolving-credit.md`, migrating here after re-score), commercial model (`../commercial-models/opp-001-revenue-linked-credit.md`), experiment (`../validation/VE-001-revenue-routing-commitment.md`).

---

## Value proposition (per `templates/value-proposition.md`)

### Header
- **Segment (A):** F&B/retail owner-operators, 1–3 outlets, AED 50k–300k monthly revenue, UAE.
- **Decision-maker (A):** the owner personally.
- **JTBD (A):** "Cover stock and payroll in the gap between paying out and getting paid, without begging a bank."

### Pain and status quo — all (A), pending REQ-002
- **Credit pain:** working-capital gaps monthly; banks require statements, collateral, and weeks; SME rejection rates high.
- **Current workaround and cost:** personal credit cards (~36% APR equivalent), supplier credit (lost early-payment discounts), informal lenders (opaque, expensive), or missed stock (lost revenue).
- **Alternatives and where they fail:** bank SME loans (slow, document-heavy, size-minimums), BNPL-for-business (thin coverage), other wallets (no lender attached).
- **Inflection point:** bank rejection, sudden large order, seasonal stock build, new outlet.

### The proposition
*For UAE F&B/retail owner-operators who hit monthly working-capital gaps, the BOTIM business account provides a credit limit that grows automatically with the revenue received into it and repays itself as a small share of incoming payments — unlike bank loans, which require paperwork and collateral, because AstraTech underwrites from revenue BOTIM actually sees.*

- **Organic switching reason:** **credit access unavailable elsewhere + limits linked to actual activity.** The merchant routes revenue to BOTIM because routing *is* the credit application: more routed revenue → higher limit, visible in-app. No promotion needed for this logic to work — but whether it works is exactly what VE-001 tests.
- **Quantified benefit (A):** replacing a 36% APR personal-card workaround with a 20% facility on a base drawn balance of ~17.5k saves ~AED 230/month, plus avoided lost-stock episodes; in-app limit growth is the felt benefit.
- **Payment behaviour required:** receive ≥30% of revenue into the BOTIM wallet (QR / payment links). This is the hard ask and the model's most sensitive assumption.
- **Willingness to pay (A):** pays more today for worse (informal/personal-card credit); facility pricing at 16–24% APR-equivalent is cheaper than every current workaround except supplier terms.

### The loop
Active links if validated: payments → data (routed revenue) → underwriting (limit growth) → credit → more routed payments (to keep the limit) → repayment visibility → better terms. Aspirational links: payments → payment revenue at scale; data → cross-sell (supplier payments, OPP-002/006).

### Honesty checks
- Subsidies removed: the proposition survives on credit access alone — *if* the routing ask is acceptable. No cashback anywhere in the design.
- Benefit vs switching effort: switching effort is real (retraining customers to pay via QR/links). Benefit must therefore be credit the merchant cannot get elsewhere, not marginally cheaper credit.
- Sceptical merchant says: "I'll take the credit and keep taking cash." — which is why limits *start* small and grow only with routed flow, and why VE-001's waitlist states the routing condition up front.

---

## Seven-week MVP (per `templates/seven-week-mvp.md`) — concierge model

**Honest scope note:** automated limit engines, in-wallet credit UX, and IBAN issuance do not fit in 7 weeks. The MVP is a **concierge pilot**: real money, real merchants, manual machinery behind a simple front.

### Scope
- **Target segment:** 20–30 F&B/retail merchants, 1–3 outlets, Dubai/Sharjah — recruited from VE-001 waitlist (already routing-committed).
- **Product concept:** merchant receives payments via BOTIM QR/pay-by-link; AstraTech grants a starter limit (AED 5k–15k, ≤0.5× observed monthly routed flow); limit reviewed weekly by a human against routed-flow data; repayment collected as a fixed % of incoming wallet payments, swept manually if needed.
- **Journey (≤8 steps):** waitlist → KYB call + trade-licence check → QR/link setup → 2 weeks routing observation → starter limit offer → drawdown to wallet → auto-% repayment on incoming payments → weekly limit review with in-app/WhatsApp notification of limit growth.
- **Payment mechanism:** existing BOTIM wallet P2M rails. **Credit mechanism:** AstraTech lends on its own licence; funds disbursed to wallet. **Repayment:** percentage-of-inflow sweep (manual reconciliation acceptable). **Revenue model in MVP:** financing margin only; account free. Willingness-to-pay tested via priced term sheet (no free pilot pricing).
- **Switching trigger targeted:** recent bank rejection or seasonal stock build (from VE-001 screening).

### Feature cut
| Essential | Deferred |
|---|---|
| QR/pay-by-link acceptance; manual KYB; starter limit + weekly human review; %-of-inflow repayment; limit-growth notification | Automated underwriting; business IBAN; cards; supplier payments; sub-wallets; accounting integration; any cashback |

### Week-by-week
| Week | Goal | Output |
|---|---|---|
| 1 | Legal/compliance rails confirmed (AstraTech lending docs adapted, wallet disbursement path, collections process); recruit from VE-001 waitlist | Signed internal runbook; 30 candidates |
| 2 | KYB + onboarding first 10 merchants; QR/link live | 10 merchants routing |
| 3 | Onboard remaining cohort; routing observation | 20–30 merchants routing; baseline flow data |
| 4 | First starter limits offered and drawn | ≥10 facilities live |
| 5 | Repayment sweeps running; first weekly limit reviews | Repayment data; first limit increases granted |
| 6 | Full cohort on weekly review cadence; collect objections/drop-offs | Mid-pilot readout |
| 7 | Pilot readout: routing %, drawdown, repayment, limit-growth response | Go/no-go pack via `meeting-ready-output.md` |

### Dependencies
- **Data:** VE-001 results (gate to start); BOTIM merchant-funnel data for CAC reality-check.
- **Integrations:** none new — existing wallet rails + manual back office.
- **Partners:** AstraTech credit/collections team (confirmed needed, status: to confirm), BOTIM P2M product team access.
- **Regulatory:** lending under AstraTech's existing licence; wallet under existing e-money arrangement; no card, no IBAN → no new licensing in MVP. Compliance sign-off is a week-1 gate.

### Metrics
| Success (targets) | Failure (kill thresholds) |
|---|---|
| ≥20 merchants onboarded; ≥60% sustain ≥30% routing for 4+ weeks; ≥50% of eligible merchants draw; repayment collected ≥95% on schedule; observable routing increase after limit growth | <12 merchants despite 30+ offers; routing decays below 20% within 4 weeks; drawdown but routing stops (credit-and-run behaviour in >25% of borrowers); repayment sweep failures >15% |

### Expansion path (if success metrics hit)
Automate the limit engine, add business IBAN (unlocks OPP-004 fragment), then layer supplier payments (OPP-002/006 rails) on the now-visible flow data — the loop's next links.

---

## Status
- **Evidence confidence:** Low — everything above is assumption-architecture awaiting VE-001 + REQ-002.
- **Main invalidation risk:** merchants won't move receiving rails / credit-and-run behaviour.
- **Dependency:** VE-001 result gates the MVP; REQ-002 evidence re-scores the scorecard.
- **Next action:** run VE-001 (field work, human-owned); on pass, seek MVP approval via meeting-ready output.

*Changelog: 2026-07-10 — v1 profile: value proposition + concierge MVP defined; classification unchanged.*
