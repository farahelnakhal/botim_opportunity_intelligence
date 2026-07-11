# OPP-010 — Settlement Assurance + Hold Underwriting

**Classification: Promising but unvalidated** (7/17 scores still assumption-based — capped; but this is the module's first majority-evidenced proposition: evidence confidence **Medium**). Source: Workstream A W28 handoffs #1 and #2 (`knowledge-base/customer-evidence/weekly-updates/2026-W28.md` §9). Linked: scorecard `../opportunity-scores/opp-010-scorecard.json` · model `../commercial-models/opp-010-{inputs.json,computed.md}` · experiment `../validation/VE-003-hold-underwriting-demand.md`.

## Proposition

BOTIM acceptance (acquiring) with **guaranteed settlement timelines**, where risk reviews become **priced advances instead of frozen funds**: when a transaction pattern triggers review, AstraTech underwrites the chargeback exposure and releases the money for a fee, rather than holding it for weeks–months as UAE PSPs demonstrably do. Paid same-day settlement as a premium tier.

- **Segment:** `SEG-uae-online-sme-psp-merchants` (Workstream A definition) — plus marketplace sellers later (OPP-012).
- **Decision-maker:** owner (micro/small online merchants).
- **JTBD (evidenced):** "get the money my customers already paid me, when I was told I'd get it."

## Demand — evidence-backed for the first time

- **Pain severity 5, financial impact 5:** EV-2026-W28-004 (all funds held 540 days, Sanadak/DFSA escalation), EV-005 (AED 65k, 2 weeks; 4-month loops), EV-003 (2–7 day promises running to months), EV-007 ($3.5k permanently withheld).
- **Pain frequency 4:** 8 of 12 W28 records are hold/freeze/settlement pain across 7+ providers — structural, not one bad PSP.
- **Willingness to pay 5 (priced, observed):** merchants already pay **+0.5–0.75% for same-day settlement** (mamo.md) — WTP for settlement speed is a market fact, not a survey answer.
- **Switching intent 4:** EV-011 (explicit switch after dismissive incumbents); hold events are self-generating inflection points.
- **Organic switching reason:** *money arrives when promised, and a hold becomes a priced option instead of a black box.* Survives with all promotions removed.

## Why BOTIM/AstraTech — the handoff's thesis

PSPs hold funds because chargeback risk is a **credit risk they cannot price** — they have no lending capability, so their only tool is freezing. AstraTech can underwrite it; BOTIM as acquirer sees the chargeback data that prices it. The combination is the moat (defensibility 3 (A): other lender-acquirer combos could copy; IP-2026-001 — Wio's 2026 payments launch — bounds the window).

## Reasoning protocol (steps 1–6)

1. **Outside view:** RC-2 warns new-rail routing is hard (10–30%) — but acceptance switching is *winner-take-most*: a merchant who moves their gateway moves ~all its volume, unlike wallet routing. RC-7/RC-8 inform VE-003 thresholds. Base-case routed share 70% is *above* RC-2's class because the reference class is the wrong shape for acceptance switching — this divergence is argued, not assumed silently.
2. **Pre-mortem:** *"Failed because we became the PSP we replaced: our own risk/compliance forced holds we'd promised not to impose, and the guarantee was exposed as marketing."* Second failure story: adverse selection — the merchants most eager to switch are the ones other PSPs held *for good reason*. Both map to scenarios (`adverse_selection`; guarantee-integrity needs a new custom scenario when the model matures).
3. **Disconfirmation searched:** EV-002 partially self-contradicts (vanished settlements eventually paid — incident, not theft); holds may be concentrated in high-risk MCCs that we'd also hold. **Not yet searched:** base rates of legitimate-vs-abusive holds; UAE acquiring rules on settlement guarantees. Cheapest refutation: 10 interviews with held merchants — if most operate in genuinely high-risk categories, the wedge shrinks to a niche.
4. **Prediction logged:** PRED-006 (see decision journal).
5. **Sensitivity conditioning:** viable *if* per-merchant volume ≥ ~AED 60k/month and net acquiring take ≥ ~25 bps online — the two top tornado inputs. Downside case is break-even-ish (+3), not loss-making.
6. **This changes if:** interviews show held merchants are predominantly high-risk-category (we'd hold them too); or UAE regulation prohibits settlement-time guarantees by non-banks; or net acquiring economics after interchange/scheme come in below ~20 bps.

## Engine results (all commands run 2026-07-11)

- **Model (base):** +342/merchant/month at 70% margin; break-even 526 merchants vs base 400; downside +3 (break-even effectively never); upside +1,545.
- **Scenarios: survives all 8** — including perfect_storm (+112) and credit_and_run (+104) — because acquiring margin is independent of the lending book. Weakest to routing_decay (+159).
- **Monte Carlo:** P50 +382, P5 +198, **P(loss) 0.0%** across 5k draws. Caveat honestly: economics inputs are still (A); robustness is conditional on the acquiring-margin assumption.

## Execution reality check

- **mvp_feasibility_7wk = 2:** a full acquiring stack (scheme membership, BIN sponsor, settlement rails) does NOT fit 7 weeks. The 7-week variant is **concierge advance-against-existing-PSP-receivables**: merchant keeps their PSP; AstraTech advances held/receivable funds at a priced fee — tests the demand and the risk pricing without building acquiring. Full acceptance product is the expansion path, not the MVP.
- **Fixed costs (A) 180k/month** reflect the acquiring stack — the biggest structural bet.

## Status

- **Main invalidation risk:** held merchants are high-risk categories we would also hold — the wedge is real but small.
- **Dependency:** VE-003 field work; REQ evidence on segment sizing (payment_volume is the largest evidenced-demand gap); regulatory review of settlement-guarantee permissibility.
- **Next action:** VE-003 (interviews + waitlist among hold-affected merchants), in parallel with the regulatory question.

*Changelog: 2026-07-11 — created from Workstream A W28 handoffs; first majority-evidenced scorecard (10/17 dimensions cited).*
