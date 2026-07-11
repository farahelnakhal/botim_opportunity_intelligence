# Test Case 1 — Revenue-Linked Revolving Credit (worked illustration)

**What this file is:** a walkthrough of how the module evaluates an idea end-to-end, using OPP-001 as the example. **The load-bearing artefacts live in the knowledge base, not here** — this file shows the *method*; edit the canonical files, never this one, to change the analysis.

| Step | Canonical artefact |
|---|---|
| Opportunity profile + value proposition + stress test + 7-week MVP | `knowledge-base/product-ideas/opp-001-revenue-linked-credit.md` |
| 17-dimension scorecard (engine-validated) | `knowledge-base/opportunity-scores/opp-001-scorecard.json` |
| Commercial model inputs (F/E/A-labelled) | `knowledge-base/commercial-models/opp-001-inputs.json` |
| Computed three-case model | `knowledge-base/commercial-models/opp-001-computed.md` |
| Model narrative (what the numbers mean) | `knowledge-base/commercial-models/opp-001-revenue-linked-credit.md` |
| Validation experiment (pre-committed thresholds) | `knowledge-base/validation/VE-001-revenue-routing-commitment.md` + `VE-001-result.json` |
| Meeting-ready recommendation | `knowledge-base/product-ideas/opp-001-revenue-linked-credit-recommendation-2026-07-10.md` |

## What the walkthrough demonstrates

1. **Assumption discipline:** with no customer evidence, 15 of 17 scores carry `(A)` — the engine caps classification at "Promising but unvalidated" regardless of the composite (3.5). Run it: `python3 opportunity-intelligence/tools/run.py score knowledge-base/opportunity-scores/opp-001-scorecard.json`.
2. **Economics before enthusiasm:** the computed model shows base +137/merchant/month but break-even ≈1,100 merchants vs a base-case 500 — a tension the recommendation states rather than hides.
3. **Kill-first stress testing:** the strongest case against (merchants won't move receiving rails) became VE-001's hypothesis, with pass/fail thresholds committed before any field work.
4. **The full command sequence:** `score` → `model` → `sensitivity` → `simulate` → `stress` → (field work) → `verdict` → backlog action.

Classification: **Promising but unvalidated** — gated on VE-001.
