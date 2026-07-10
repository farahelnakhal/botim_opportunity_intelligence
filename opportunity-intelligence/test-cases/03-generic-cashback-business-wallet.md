# Test Case 3 — Generic Cashback Business Wallet ("Wallet + 2% Cashback")

**Purpose of this file:** worked example proving the module will reject weak propositions. This idea is deliberately close to a plausible-sounding launch plan.

## Proposition

A BOTIM business wallet with a prepaid Visa card offering 2% cashback on all business spend, free transfers, and a business IBAN — customer acquisition driven by the cashback offer.

## Why it looks attractive

Simple to explain, fast to launch, cashback demonstrably acquires users, and it seeds the merchant base for later credit products.

## Stress test (decisive sections)

- **Organic-switching test — FAILED.** Strip the cashback: what remains is "another wallet with an IBAN". Free transfers and generic convenience are explicitly non-qualifying switching reasons. The IBAN alone may matter to under-banked micro-merchants, but that is a *different, narrower* proposition than this one.
- **Economics — FAILED.** 2% cashback (200 bps) against a net payment margin of 25–90 bps (see Test Case 2 table) loses 110–175 bps on every dirham of spend, with no lending margin attached to offset it. The subsidy-stacking cross-check in `mdr-interchange-subsidy-model.md` fails in **all three cases including upside**.
- **Adverse selection:** cashback-maximisers concentrate spend while it lasts and churn when it ends; the "seeded base" is the least loyal cohort available.
- **Fraud:** cashback arbitrage via self-dealing (merchant pays own/friendly terminal, harvests 2%, reverses).
- **Copyability:** total — any bank or wallet can outbid a cashback number; there is no data or distribution moat in the offer itself.
- **Why hasn't it been built:** it has, repeatedly, in many markets; cashback-led wallets without an attached lending or software margin shrink when promotions end. Answer (c): the economics don't work.

## Scorecard floors triggered

Payment revenue potential 1, Competitive defensibility 1, and the proposition fails the organic-switching test outright — per the stress-test rubric this forces **Reject** regardless of the composite.

## Classification: **REJECT**

- **Decisive factor:** no organic switching reason survives removal of the subsidy, and the subsidy itself is unaffordable at any case in the interchange model.
- **Evidence confidence:** High *for the rejection* — the economics are arithmetic, not assumption.
- **Reopen trigger (archived in backlog, not deleted):** a strategic decision to buy market share at a stated, board-approved loss with a defined payback via a validated credit product — i.e. a different proposition.
- **What survives:** the business-IBAN-for-underbanked-micro-merchants fragment may be worth evaluating as its own proposition (new backlog entry, needs Workstream A evidence on IBAN-access pain).

*Note: this classification applies to the proposition only, not to any wider launch decision.*
