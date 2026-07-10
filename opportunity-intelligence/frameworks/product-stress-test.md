# Product Stress-Test Framework

Run this on every proposition **after** scoring and **before** any commercial modelling is presented as a recommendation. The purpose is to try to kill the idea. An idea that survives an honest attempt to kill it is worth modelling; an idea that is only ever argued *for* is not.

## 1. The two strongest cases

- **Strongest case FOR:** the best honest argument, grounded in evidence IDs where possible.
- **Strongest case AGAINST:** written as if by a sceptical investor. Must be a real argument, not a strawman.

## 2. Market reality check

- **Similar products:** who has built this or something close (UAE, GCC, global)? What happened to them?
- **Why hasn't it been built here?** Choose and justify one or more:
  - (a) Nobody had the distribution/data — genuine gap.
  - (b) Regulation/licensing makes it hard — is BOTIM/AstraTech actually better placed?
  - (c) The economics don't work — show why ours would differ.
  - (d) The demand isn't real — the most dangerous answer; requires direct validation.
- **Copyability:** who could copy it (banks, telco wallets, POS acquirers, BNPL players), how fast, and what stops them?

## 3. Risk interrogation

- **Adverse selection:** which merchants will be *most* attracted? If the answer is "those rejected by banks and other lenders," explain what offsets that.
- **Fraud risk:** first-party fraud (fake merchants, bust-out, cash-recycling to inflate limits), collusion (merchant–supplier fake invoices), identity fraud at onboarding.
- **Credit risk:** what does BOTIM/AstraTech actually see before lending? What happens to visibility if the merchant routes revenue away after drawing credit?
- **Operational dependencies:** licences, scheme membership, BIN sponsor, issuer-processor, acquiring partner, KYB provider, IBAN provider, collections capability — and which are outside our control.

## 4. Behaviour-change tests (the hard part)

- **Routing test:** will merchants route *enough* payment activity through BOTIM for the data/economics to work? What share of their flow, and why would they?
- **Benefit-size test:** is the benefit large enough to change behaviour, or merely nice? Quantify it in AED/month for the target merchant and compare to their switching effort.
- **Organic-switching test:** strip away launch promotions and cashback. What remains that makes a merchant move? If nothing remains, the proposition fails this test.

## 5. Disproof plan

- **What evidence would disprove it:** list 2–4 concrete findings that would kill the idea (e.g. "merchants pay suppliers by bank transfer on 60-day terms and suppliers refuse cards").
- **What must be validated directly:** the claims that cannot be settled from desk research, each mapped to an experiment in `templates/validation-experiment.md`.

## 6. Classification

Classify the **proposition** (not the company launch decision) as exactly one of:

| Classification | Criteria |
|---|---|
| **Strong opportunity** | Survives the case-against; critical scores ≥3 with Medium+ evidence confidence; economics plausible in base case; clear organic switching reason; validation path exists |
| **Promising but unvalidated** | Survives on logic but key scores are assumption-based, or the organic switching reason is plausible but untested |
| **Weak** | Fails one behaviour-change test, or economics only work in the upside case, or the pain is real but the workaround is good enough |
| **Reject** | Fails the organic-switching test outright, or adverse selection/fraud is structural, or the disproving evidence already exists |

Every classification must state: the single decisive factor, evidence confidence, and the recommended next action (experiment, evidence request to Workstream A, or archive).

Store completed stress tests in `knowledge-base/product-ideas/<idea-slug>.md` alongside the opportunity profile.
