# OPP-003 — Generic Cashback Business Wallet (ARCHIVED: Reject)

Rejected proposition, kept so the decision isn't re-litigated from scratch. Archived in `BACKLOG.md` with a reopen trigger. Worked illustration: `opportunity-intelligence/test-cases/03-…`.

## Proposition (as evaluated)

BOTIM business wallet + prepaid Visa card offering 2% cashback on all business spend, free transfers, and a business IBAN — acquisition driven by the cashback offer.

## Why it was rejected (decisive factors)

1. **Fails the organic-switching test outright.** Strip the cashback and what remains is "another wallet with an IBAN" — free transfers and generic convenience are non-qualifying switching reasons by framework rule.
2. **The economics are arithmetic, not assumption.** 200 bps of cashback against 25–90 bps of net payment margin (see `../commercial-models/opp-002-subsidy-inputs.json` margins) loses 110–175 bps on every dirham **in all three cases including upside**, with no lending margin attached to offset it. The subsidy engine's stacking check fails it mechanically — this exact case is a permanent regression test (`test_cashback_stacking_is_charged_to_same_budget`).
3. **Adverse selection + copyability:** cashback-maximisers churn when the promotion ends; any bank or wallet can outbid a cashback number; no data or distribution moat in the offer itself.

- **Evidence confidence:** High *for the rejection* — arithmetic.
- **Reopen trigger:** a board-approved loss-leader strategy with a defined payback via a validated credit product — i.e. a different proposition.
- **What survives:** the business-IBAN-for-underbanked-micro-merchants fragment lives on as **OPP-004** (needs REQ-004 evidence).

*Note: this classification applies to the proposition only, not any wider launch decision.*
*Changelog: 2026-07-10 — profile migrated from test-cases/ (audit remediation).*
