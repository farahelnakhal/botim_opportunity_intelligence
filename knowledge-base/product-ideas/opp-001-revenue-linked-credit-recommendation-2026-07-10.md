# Meeting-Ready Recommendation — OPP-001 Revenue-Linked Revolving Credit

Issued 2026-07-10 per `opportunity-intelligence/templates/meeting-ready-output.md`. **Assumption-stage document:** evidence confidence is Low, so under this module's own rules the recommendation is capped at "run the experiment" — it is not a build recommendation.

---

## Page 1 — Decision view

### Recommendation
Approve validation experiment **VE-001** (3 weeks, ~15 interviews + 50 waitlist offers) now, with the 7-week concierge pilot pre-approved **conditionally** — it starts only if VE-001 passes its pre-committed threshold.

### The opportunity
- **Proposition:** an AstraTech working-capital line inside the BOTIM business wallet whose limit grows automatically with revenue the merchant routes in; repayment is a small share of incoming payments.
- **Segment:** F&B/retail owner-operators, 1–3 outlets, AED 50k–300k monthly revenue, UAE *(assumed — REQ-002 open)*.
- **Classification:** **Promising but unvalidated** — 15 of 17 scorecard dimensions are assumption-based, which caps the classification regardless of the composite (3.5 indicative).
- **Organic switching reason:** credit access unavailable elsewhere, with limits visibly linked to actual activity. Routing revenue *is* the credit application. No cashback or promotion anywhere in the design.
- **BOTIM advantage:** distribution to merchants already on BOTIM + real-time revenue visibility once flows route in. **AstraTech advantage:** lending licence, underwriting and collections capability — the loop needs both.

### The numbers (base case, downside in brackets; all inputs (A))
- Contribution margin: **+137 AED/merchant/month, 33%** (−59, loss-making)
- Break-even: **≈1,100 merchants** at base unit economics (never, in downside) — above the base month-12 count of 500; the model closes only with upside growth, higher routed share, or lower fixed cost
- Max free-credit days fundable from payment margin alone: ~24 (~3) — free days here are a lending-margin decision, not an interchange play
- VE-001 cost: staff time + incentives, ~3 weeks. Pilot cost if triggered: capped at 30 starter limits of AED 5k–15k (max exposure ≈ AED 450k) plus concierge ops

### What we are confident about vs not
| Confident (evidence/arithmetic) | Not confident (assumption) |
|---|---|
| The economics arithmetic itself; free-credit ceiling; that a 2%-cashback variant is unaffordable (OPP-003 rejected) | Pain severity/frequency for this segment in UAE; willingness to route ≥30% of revenue; ECL (6% base, 12% downside); achievable financing rate; organic CAC via BOTIM channel |

### Main invalidation risk
Merchants take the credit but won't move their *receiving* rails — routing decays or never starts (credit-and-run). This is the hardest behaviour change in payments, and it kills the data loop, the payment revenue, and the underwriting advantage simultaneously. Likelihood: genuinely unknown — which is exactly why VE-001 exists.

### The ask
1. Approve **VE-001** (3 weeks): pass = ≥40% of qualified merchants complete a waitlist that states the ≥30% routing condition; fail = ≤15% → OPP-001 is reclassified Weak and we stop.
2. Pre-approve the **7-week concierge pilot** conditional on VE-001 passing (scope, kill thresholds, and ≈AED 450k max credit exposure per the MVP plan).
3. Nudge Workstream A on **REQ-001/REQ-002** (evidence-ID scheme; working-capital pain evidence) so the scorecard can be re-based on evidence.

---

## Appendices (by reference — single source of truth)

- **A. Scorecard (all 17 scores):** `opportunity-intelligence/test-cases/01-revenue-linked-revolving-credit.md`
- **B. Stress test & classification rationale:** same file — strongest case against is the routing chicken-and-egg; adverse selection offset by small growing limits; cash-recycling fraud flagged
- **C. Commercial model (3 cases, break-even, sensitivity-ranked assumptions):** `knowledge-base/commercial-models/opp-001-revenue-linked-credit.md`
- **D. Value proposition & loop:** `knowledge-base/product-ideas/opp-001-revenue-linked-credit.md`
- **E. Validation plan (thresholds pre-committed):** `knowledge-base/validation/VE-001-revenue-routing-commitment.md`
- **F. Seven-week MVP (week-by-week, kill thresholds):** profile file, MVP section
- **G. Evidence register:** no evidence IDs consumed yet — none exist; open requests REQ-001..006 in `BACKLOG.md`

---

*Presentation rules honoured: ranges not point estimates; AED; Low evidence confidence → ask limited to running the experiment; classification applies to the proposition, not the company launch decision.*
