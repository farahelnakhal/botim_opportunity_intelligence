# Test Case 1 — Revenue-Linked Revolving Credit on the BOTIM Wallet

**Purpose of this file:** realistic worked example to test that the module's frameworks produce honest, evidence-disciplined output. All customer numbers below are assumptions `(A)` — no evidence exists yet in `knowledge-base/customer-evidence/`.

## Proposition

AstraTech provides a revolving working-capital line to SME merchants inside a BOTIM business wallet. The limit starts small and grows automatically with revenue the merchant receives into the wallet. Repayment is deducted as a fixed percentage of incoming payments (revenue-linked repayment).

- **Segment (A):** F&B and retail merchants, 1–3 outlets, AED 50k–300k monthly revenue, UAE.
- **Decision-maker (A):** owner-operator.
- **JTBD (A):** "Cover stock purchases and payroll in the gap between paying suppliers and getting paid."

## Scorecard (per `frameworks/opportunity-scoring.md`)

| # | Dimension | Score | Basis |
|---|---|---|---|
| 1 | Pain severity | 4 (A) | Working-capital gaps are the classic SME pain; needs UAE evidence |
| 2 | Pain frequency | 4 (A) | Monthly supplier/payroll cycles |
| 3 | Financial impact | 4 (A) | Informal credit / missed stock costs assumed >3% of revenue |
| 4 | Workaround cost | 4 (A) | Assumed workarounds: personal credit cards, supplier terms, informal lenders |
| 5 | Switching intent | 3 (A) | Only at inflection points (bank rejection, expansion) |
| 6 | Willingness to pay | 4 (A) | Pays more today for worse (informal rates); unverified |
| 7 | Digital readiness | 3 (A) | Mixed; cash-heavy F&B tail |
| 8 | Payment volume | 3 (A) | Depends on wallet acceptance — the big unknown |
| 9 | Credit need | 5 (A) | Chronic working-capital need assumed for segment |
| 10 | BOTIM distribution advantage | 4 (A) | Assumed high BOTIM penetration among owners; needs data |
| 11 | Transaction-data advantage | 3 (A) | Only if revenue actually flows into the wallet first |
| 12 | Payment revenue potential | 2 (A) | Wallet-in flows earn little; no card spend in this version |
| 13 | Lending revenue potential | 4 (A) | Core AstraTech economics |
| 14 | Credit-risk visibility | 3 (A) | Good only AFTER merchants route revenue in; cold-start blind |
| 15 | Competitive defensibility | 3 (A) | Loop is defensible once running; cold start copyable |
| 16 | Ease of validation | 4 | Interviews + waitlist + routing pilot all feasible |
| 17 | Seven-week MVP feasibility | 3 | Concierge lending on AstraTech licence feasible; auto-limits are not |

Composite (indicative only): 3.5. **Assumption load: 15/17 (A) → classification capped at "Promising but unvalidated".**

## Stress test (summary)

- **Strongest case FOR:** activates the full loop — payments generate data, data grows limits, credit pulls more payments in; repayment is invisible to the merchant.
- **Strongest case AGAINST:** chicken-and-egg. Revenue-linked everything requires the merchant to move their *receiving* rails to BOTIM first, which is the hardest behaviour change in payments. Merchants may take the credit and route revenue elsewhere afterwards.
- **Adverse selection:** bank-rejected merchants will be first in line. Offset: limits start small and only grow with observed flow.
- **Fraud:** cash-in recycling to inflate "revenue" and limits — needs velocity/counterparty checks.
- **Why hasn't it been built here:** local wallets lack a licensed SME lender attached (answer (a)/(b)); but demand realism (d) is untested.
- **Disproof:** if merchants at inflection points won't commit to routing ≥30% of revenue for 90 days in exchange for a growing limit, the loop dies.

## Classification: **Promising but unvalidated**

- **Evidence confidence:** Low.
- **Main invalidation risk:** merchants won't move receiving rails; credit gets drawn without routing.
- **Dependency:** Customer & Market Intelligence — evidence on working-capital pain severity, current workaround costs, wallet-acceptance readiness in F&B/retail.
- **Recommended next action:** VE-001 — 15 merchant interviews on last working-capital gap + fake-door waitlist with routing commitment question (per `templates/validation-experiment.md`).
