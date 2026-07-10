# Product-Opportunity Backlog

Living document per `opportunity-intelligence/templates/opportunity-backlog.md`. Rows are never deleted — rejected/parked ideas move to the Archive with a reopen trigger.

Profiles for OPP-001..003 currently live in `opportunity-intelligence/test-cases/` (they were built as worked examples); they migrate to this folder as evidence lands and scores are refreshed.

## Backlog

| ID | Proposition | Segment | Classification | Composite (indicative) | Evidence confidence | Top invalidation risk | Next action | Owner | Last updated |
|---|---|---|---|---|---|---|---|---|---|
| OPP-001 | Revenue-linked revolving credit on BOTIM business wallet (AstraTech line, limits grow with routed revenue) | F&B/retail, 1–3 outlets, UAE | Promising but unvalidated | 3.5 | Low | Merchants won't move receiving rails; credit drawn without routing | VE-001 | Workstream B | 2026-07-10 |
| OPP-002 | Supplier-payment commercial card with free-credit days funded by net interchange | Trading/retail SMEs, AED 30k–150k/mo supplier spend | Promising but unvalidated (borderline Weak) | — (scored qualitatively; scorecard pending VE-002) | Low | Supplier card acceptance <20% → no eligible volume | VE-002 | Workstream B | 2026-07-10 |
| OPP-004 | Business IBAN + basic account for under-banked micro-merchants (fragment spun out of OPP-003) | Micro-merchants without business bank accounts | Unscored | — | Low | Pain may be licensing-driven, not solvable by BOTIM | REQ-004 (evidence request) | Workstream B | 2026-07-10 |
| OPP-005 | VAT / payroll / supplier sub-wallets for financial visibility | Digitised SMEs already receiving payments digitally | Unscored | — | Low | Visibility alone may not clear the organic-switching bar | Score after REQ-002 evidence lands | Workstream B | 2026-07-10 |
| OPP-006 | Inventory financing wallet (credit released against stock purchases via approved suppliers) | Retail/trading SMEs with recurring stock cycles | Unscored | — | Low | Collusive merchant–supplier invoicing; ops complexity | Score after VE-002 (shares supplier-side unknowns) | Workstream B | 2026-07-10 |
| OPP-007 | Cash-to-digital conversion play (cash-heavy merchants onboarded via cash-in network + wallet) | Cash-heavy micro/small merchants | Unscored | — | Low | Cash-in infrastructure cost; behaviour change is hardest here | Score after REQ-005 segment definitions | Workstream B | 2026-07-10 |
| OPP-008 | Free SME account with paid lending (account free; monetise via AstraTech credit only) | Broad SME | Unscored | — | Low | Free account alone fails organic-switching test without a credit hook | Score after OPP-001 validation (overlapping hypothesis) | Workstream B | 2026-07-10 |

## Evidence-request queue (to Customer & Market Intelligence — recorded here, never written into their folders)

| Req ID | For proposition | Evidence needed | Why it matters | Status |
|---|---|---|---|---|
| REQ-001 | All | Stable evidence-ID scheme (e.g. EV-###) in `knowledge-base/customer-evidence/` | Scorecards must cite evidence by ID | Open |
| REQ-002 | OPP-001, OPP-005, OPP-008 | Working-capital pain: severity, frequency, current workaround and its cost (F&B/retail, 1–3 outlets, UAE) | 15 of 17 OPP-001 scores are assumption-based | Open |
| REQ-003 | OPP-002, OPP-006 | How target merchants pay suppliers today: instrument, terms, card acceptance, surcharging | Decisive unknown for the supplier-card model | Open |
| REQ-004 | OPP-004 | IBAN/business-account access pain for micro-merchants (rejection reasons, workarounds, costs) | Determines whether OPP-004 is a real proposition | Open |
| REQ-005 | All | Segment definitions in `knowledge-base/segments/` referenceable by name | Consistent segment naming across modules | Open |
| REQ-006 | All | Inflection-point catalogue (bank rejection, expansion, VAT deadlines, big orders) | Experiment recruitment targeting | Open |

## Archive

| ID | Proposition | Rejected/parked on | Decisive reason | Reopen trigger |
|---|---|---|---|---|
| OPP-003 | Generic 2%-cashback business wallet + prepaid card | 2026-07-10 | Fails organic-switching test; 200 bps cashback vs 25–90 bps net payment margin loses money in all three cases (arithmetic, not assumption) | Board-approved loss-leader strategy with defined payback via a validated credit product — i.e. a different proposition |

## Changelog

- 2026-07-10 — Backlog instantiated. OPP-001/002 logged from worked test cases; OPP-003 archived as Reject; OPP-004..008 seeded unscored from project-context idea list. Evidence-request queue opened (REQ-001..006).
- 2026-07-10 — OPP-001 full commercial model built (`knowledge-base/commercial-models/opp-001-revenue-linked-credit.md`): base case +137 AED/merchant/month contribution but break-even ≈1,100 merchants vs base 500; downside loss-making. Classification unchanged; VE-001 remains the gate.
- 2026-07-10 — OPP-001 opportunity profile created (`opp-001-revenue-linked-credit.md`): value proposition (organic switching = credit access unavailable elsewhere + activity-linked limits) and 7-week concierge MVP with kill thresholds. OPP-001 package complete pending field validation; VE-001 gates the MVP.
