# Product-Opportunity Backlog

Living document per `opportunity-intelligence/templates/opportunity-backlog.md`. Rows are never deleted — rejected/parked ideas move to the Archive with a reopen trigger.

Every proposition's canonical profile lives in this folder (`opp-nnn-*.md`); the files in `opportunity-intelligence/test-cases/` are worked illustrations that point here.

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
| OPP-009 | F&B weekend-cycle credit (ultra-short revolving matched to weekly cash cycle) | F&B, 1–2 outlets | Weak (standalone) — fold into OPP-001 as segment config | 3.5 | Low | Weekend receipts don't route (shared with OPP-001) | Fold cycle-matched limits/sweeps into OPP-001 MVP design; no separate experiment | Workstream B | 2026-07-10 |
| OPP-010 | Settlement assurance + hold underwriting (acceptance with priced holds; from Workstream A handoff #1/#2) | SEG-uae-online-sme-psp-merchants | Promising but unvalidated | 3.9 | Medium (10/17 dims evidenced) | Held merchants are high-risk categories we'd also hold | VE-003 + regulatory review of settlement guarantees | Workstream B | 2026-07-11 |
| OPP-011 | Standalone paid instant-settlement advance (merchant keeps PSP; we advance receivables) | Online SMEs on any PSP | Unscored (candidate; from handoff #2 — largely OPP-010's concierge MVP as a product) | — | Medium (mamo.md priced WTP) | May be a feature of OPP-010, not a product (OPP-009 lesson) | Score after VE-003; assess as OPP-010 MVP first | Workstream B | 2026-07-11 |
| OPP-012 | Marketplace-seller disbursement advances (Amazon.ae et al) | SEG-uae-marketplace-sellers | Unscored (candidate; from handoff #3) | — | Low-Medium (EV-2026-W28-008, 2024-dated) | Platform-risk: marketplaces can change disbursement policy or self-serve financing | Needs refreshed EV-008 evidence (Workstream A verification queue) before scoring | Workstream B | 2026-07-11 |

## Evidence-request queue (to Customer & Market Intelligence — recorded here, never written into their folders)

| Req ID | For proposition | Evidence needed | Why it matters | Status |
|---|---|---|---|---|
| REQ-001 | All | Stable evidence-ID scheme (e.g. EV-###) in `knowledge-base/customer-evidence/` | Scorecards must cite evidence by ID | **Answered** — Workstream A published `EV-YYYY-Wnn-nnn` (weekly record files); our engine parses it (`opportunity-intelligence/tools/`) |
| REQ-002 | OPP-001, OPP-005, OPP-008 | Working-capital pain: severity, frequency, current workaround and its cost (F&B/retail, 1–3 outlets, UAE) | 15 of 17 OPP-001 scores are assumption-based | Partially answered — W28 records cover PSP-hold/banking-access pain (consumed by OPP-010); F&B/retail working-capital voice still open (their next-week focus includes it) |
| REQ-003 | OPP-002, OPP-006 | How target merchants pay suppliers today: instrument, terms, card acceptance, surcharging | Decisive unknown for the supplier-card model | Open |
| REQ-004 | OPP-004 | IBAN/business-account access pain for micro-merchants (rejection reasons, workarounds, costs) | Determines whether OPP-004 is a real proposition | Open |
| REQ-005 | All | Segment definitions in `knowledge-base/segments/` referenceable by name | Consistent segment naming across modules | Open |
| REQ-006 | All | Inflection-point catalogue (bank rejection, expansion, VAT deadlines, big orders) | Experiment recruitment targeting | Open |

## Archive

| ID | Proposition | Rejected/parked on | Decisive reason | Reopen trigger |
|---|---|---|---|---|
| OPP-003 | Generic 2%-cashback business wallet + prepaid card | 2026-07-10 | Fails organic-switching test; 200 bps cashback vs 25–90 bps net payment margin loses money in all three cases (arithmetic, not assumption) | Board-approved loss-leader strategy with defined payback via a validated credit product — i.e. a different proposition |

## Changelog

- 2026-07-11 — Desk-research calibration pass (`commercial-models/BENCHMARKS.md`): official Visa UAE interchange sourced — OPP-002 gross interchange re-based 90/130/170 (A) → 130/180/200 (E); net margin now 65/110/120 bps and the 20-free-day package affordable in ALL cases (was downside loss-leader). RC-3/4/8 sourced, RC-9/10 added. PRED-004 resolved TRUE (revenue-linked pricing ≥18% well inside market norms). OPP-002 remains gated on VE-002 — acceptance, not economics, is now clearly the only open question.
- 2026-07-11 — Workstream A W28 handoffs ingested: OPP-010 created and fully evaluated (first majority-evidenced scorecard, 3.9, survives all 8 stress scenarios; VE-003 designed with pre-committed thresholds; PRED-006 logged); OPP-011/OPP-012 logged as unscored candidates; handoff #4 (IP-2026-001 Wio timing) noted in OPP-010 defensibility. REQ-002 marked partially answered.

- 2026-07-10 — Backlog instantiated. OPP-001/002 logged from worked test cases; OPP-003 archived as Reject; OPP-004..008 seeded unscored from project-context idea list. Evidence-request queue opened (REQ-001..006).
- 2026-07-10 — OPP-001 full commercial model built (`knowledge-base/commercial-models/opp-001-revenue-linked-credit.md`): base case +137 AED/merchant/month contribution but break-even ≈1,100 merchants vs base 500; downside loss-making. Classification unchanged; VE-001 remains the gate.
- 2026-07-10 — OPP-001 opportunity profile created (`opp-001-revenue-linked-credit.md`): value proposition (organic switching = credit access unavailable elsewhere + activity-linked limits) and 7-week concierge MVP with kill thresholds. OPP-001 package complete pending field validation; VE-001 gates the MVP.
- 2026-07-10 — Meeting-ready recommendation issued for OPP-001 (`opp-001-revenue-linked-credit-recommendation-2026-07-10.md`). Ask: approve VE-001 now; concierge pilot pre-approved conditional on VE-001 pass; nudge REQ-001/REQ-002. Assumption-stage — not a build recommendation.
- 2026-07-10 — Computation engine shipped (`opportunity-intelligence/tools/`, 21 tests): commercial + subsidy models, scorecard validation with caps/floors, and a read-only parser for Workstream A's now-published `EV-YYYY-Wnn-nnn` evidence format. REQ-001 marked Answered. Machine-readable inputs added for OPP-001 model/scorecard and OPP-002 subsidy package.
- 2026-07-10 — Audit remediation: canonical-numbers rule adopted (engine-written reports only; OPP-001 hand-written tables retired for `opp-001-computed.md`); OPP-001/002/003 profiles migrated from test-cases/ into this folder (`opp-002-supplier-payment-card.md`, `opp-003-generic-cashback-wallet.md` created); consolidated `templates/opportunity-profile.md` added; classification-label mapping documented in the scoring framework.
- 2026-07-10 — OPP-009 (F&B weekend-cycle credit) evaluated end-to-end as the module's dry-run acceptance test. Engine verdict: +70/merchant/month base but break-even ≈1,987 vs 300 merchants; classified Weak-standalone, valuable parameters folded into OPP-001. Full trail: `opp-009-fnb-weekend-cycle-credit.md`, `opportunity-scores/opp-009-scorecard.json`, `commercial-models/opp-009-{inputs.json,computed.md}`.
