# Test Case 3 — Generic Cashback Business Wallet (worked illustration of a Reject)

**What this file is:** proof the module rejects weak propositions — deliberately an idea that sounds like a plausible launch plan. **The canonical rejected profile lives in the knowledge base** — this file shows why the machinery said no.

| Step | Canonical artefact |
|---|---|
| Rejected profile + reopen trigger | `knowledge-base/product-ideas/opp-003-generic-cashback-wallet.md` |
| Archive row | `knowledge-base/product-ideas/BACKLOG.md` (Archive section) |

## What the walkthrough demonstrates

1. **The organic-switching test has teeth:** strip the 2% cashback and nothing qualifying remains ("another wallet with an IBAN") — automatic fail, whatever the scores say.
2. **Arithmetic beats argument:** 200 bps cashback against 25–90 bps net payment margin loses money in **all three cases including upside**. The subsidy engine's one-budget stacking check fails it mechanically, and that exact case is a permanent regression test (`test_cashback_stacking_is_charged_to_same_budget` in `tools/tests/test_engine.py`).
3. **Rejection is productive:** the idea's one defensible fragment (business IBAN for under-banked micro-merchants) was spun out as OPP-004 with its own evidence request, and the archive row carries a reopen trigger so the decision is revisitable on stated terms, not by amnesia.

Classification: **REJECT** — evidence confidence High *for the rejection* (it's arithmetic).
