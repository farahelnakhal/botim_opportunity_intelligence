# Commercial Model — OPP-001 Revenue-Linked Revolving Credit on BOTIM Business Wallet

Per `opportunity-intelligence/templates/commercial-model.md`. All figures AED, month-12 steady state, per-merchant monthly unless noted. **Every input below is (A) — assumption — pending VE-001 results and REQ-002 evidence.** This model exists to find the numbers that matter, not to prove viability.

## 1. Volume drivers

| Input | Downside | Base | Upside | F/E/A | Source |
|---|---|---|---|---|---|
| Active merchants (month 12) | 150 | 500 | 1,500 | A | BOTIM merchant funnel unproven; needs BOTIM channel data |
| Monthly revenue per merchant | 80,000 | 120,000 | 160,000 | A | Segment band AED 50k–300k, weighted low |
| Share of revenue routed through BOTIM wallet | 15% | 30% | 50% | A | Tied to VE-001 routing-commitment threshold (30%) |
| Routed flow per merchant | 12,000 | 36,000 | 80,000 | E | Product of the above |
| Online/offline mix of routed flow | 20/80 | 30/70 | 40/60 | A | QR/pay-by-link vs in-person QR; affects processing cost only in this product (no card interchange in v1) |

## 2. Credit drivers

| Input | Downside | Base | Upside | F/E/A | Notes |
|---|---|---|---|---|---|
| Credit limit (multiple of monthly routed flow) | 0.5× | 0.75× | 1.0× | A | Grows with observed flow; capped early for cold-start risk |
| Utilisation of limit | 50% | 65% | 70% | A | Revolvers dominate in working-capital products |
| Average drawn balance | 3,000 | 17,500 | 56,000 | E | limit × utilisation |
| Financing rate (annualised, flat-equivalent) | 16% | 20% | 24% | A | AstraTech SME pricing to confirm — market range for unsecured SME revolving |
| Average credit duration | 45 days | 60 days | 75 days | A | Revenue-linked repayment shortens duration when flow is healthy |

## 3. Revenue lines (per merchant / month)

| Line | Downside | Base | Upside | Notes |
|---|---|---|---|---|
| Financing revenue (drawn × rate / 12) | 40 | 292 | 1,120 | Core line |
| Payment revenue (routed flow × net take) | 12 | 108 | 400 | Net take 10 / 30 / 50 bps (A) on wallet P2M receipts — this is a BOTIM wallet fee, not card interchange; no MDR/interchange claim in v1 |
| Subscription revenue | 0 | 0 | 25 | Free in MVP; upside assumes paid tier later |
| Transfer / FX / supplier commissions | 0 | 10 | 40 | Negligible until supplier-payment features exist (see OPP-002/006) |
| **Total revenue** | **52** | **410** | **1,585** | |

## 4. Cost lines (per merchant / month)

| Line | Downside | Base | Upside | Notes |
|---|---|---|---|---|
| Cost of capital (drawn × funding rate / 12) | 25 | 117 | 327 | Funding rate 10% / 8% / 7% (A) — AstraTech treasury to confirm |
| Expected credit loss (drawn × ECL / 12) | 30 | 87 | 187 | ECL 12% / 6% / 4% annualised (A) — downside reflects adverse selection + cold start; the single most dangerous assumption |
| Fraud loss | 8 | 10 | 15 | Cash-in recycling controls assumed partially effective |
| Processing cost (wallet txns) | 10 | 22 | 40 | Per-txn rails cost on routed flow |
| Scheme fees | 0 | 0 | 0 | No card in v1 |
| Rewards / cashback | 0 | 0 | 0 | None — organic proposition by design |
| Servicing (support, collections, ops) | 30 | 25 | 20 | Collections-heavy in downside |
| CAC amortised over 12 months | 8 | 12 | 20 | CAC 100 / 150 / 250 (A); assumes mostly organic BOTIM channel — if paid channels needed, multiply ×3–5 |
| **Total cost** | **111** | **273** | **609** | |

## 5. Outputs

| Output | Downside | Base | Upside |
|---|---|---|---|
| Contribution margin (AED / merchant / month) | **−59** | **+137** | **+976** |
| Contribution margin (% of revenue) | −113% | 33% | 62% |
| Programme fixed costs / month (A) | 250,000 | 150,000 | 120,000 |
| **Break-even (merchants at that case's unit economics)** | never (negative unit economics) | ≈1,100 | ≈125 |
| Months to break-even at base ramp | — | ~18–24 (needs merchant-growth curve beyond month 12) | ~9 |
| Max affordable free-credit period funded by payment margin alone | ~3 days | ~24 days | >60 days |
| Max affordable cashback (payment margin fully allocated) | 0.1% of routed flow | 0.3% | 0.5% |
| Max affordable fee subsidy (from total contribution) | 0 | ~137/merchant/month | ~976/merchant/month |

Free-credit-days math (base): payment margin 108/month ÷ (drawn 17,500 × 8% ÷ 365 ≈ 3.8/day) ≈ 28 days, rounded down to ~24 after fraud/processing already netted. In this product free days are mostly a **lending-margin** decision, not an interchange play — the interchange-funded version is OPP-002's model.

## 6. Assumption register (ranked by sensitivity)

| # | Assumption | Value used (base) | If 50% worse | Firmed up by |
|---|---|---|---|---|
| 1 | ECL rate | 6% annualised | Contribution +137 → +50; downside case worsens to −89 | Cold-start pilot with capped limits; AstraTech book benchmarks |
| 2 | Share of revenue routed | 30% | Halves payment revenue AND cuts limit growth → drawn balance falls ~50%; contribution → ~+45 | **VE-001** (directly) |
| 3 | Utilisation / drawn balance | 65% of 0.75× flow | Financing revenue −50%; contribution → ~−9 | Concierge MVP drawdown data |
| 4 | Financing rate achievable | 20% | Contribution → +64 | AstraTech pricing + competitor scan (REQ to Workstream A: competitor pricing evidence) |
| 5 | Organic CAC via BOTIM channel | 150 one-off | Minor at organic levels; fatal if paid CAC ×5 needed | BOTIM funnel test in MVP weeks 1–3 |

## 7. Verdict

- Base case clears unit economics (+137/merchant/month, 33%) but **fixed costs push break-even to ≈1,100 merchants — above the base month-12 merchant count.** The model only closes with either upside merchant growth, higher routed share, or lower fixed cost.
- Downside is unambiguously loss-making: adverse-selection-driven ECL (12%) plus low routing (15%) cannot be priced away at 16–24% APR.
- **The one number to validate first: routed share of revenue** — it drives payment revenue, limit growth, drawn balance, AND credit-risk visibility simultaneously. That is exactly what VE-001 tests. Second: ECL, which only a capped-limit pilot can measure.

*Changelog: 2026-07-10 — v1 built entirely on assumptions; revisit after VE-001 and REQ-002.*
