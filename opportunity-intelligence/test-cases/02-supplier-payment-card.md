# Test Case 2 — Supplier-Payment Card (worked illustration)

**What this file is:** a walkthrough of the MDR/interchange subsidy method, using OPP-002. **Canonical artefacts live in the knowledge base** — edit those, not this file.

| Step | Canonical artefact |
|---|---|
| Opportunity profile + stress test | `knowledge-base/product-ideas/opp-002-supplier-payment-card.md` |
| Subsidy model inputs | `knowledge-base/commercial-models/opp-002-subsidy-inputs.json` |
| Validation experiment | `knowledge-base/validation/VE-002-supplier-payment-mapping.md` + `VE-002-result.json` |

## What the walkthrough demonstrates

1. **Correct card terminology by construction:** the supplier (accepting merchant) pays MDR to its acquirer; BOTIM models only issuer interchange / programme share. The subsidy engine has **no MDR input**, so the full-MDR error cannot be expressed. Run it: `python3 opportunity-intelligence/tools/run.py subsidy knowledge-base/commercial-models/opp-002-subsidy-inputs.json`.
2. **Subsidy ceilings from net margin:** 25/60/90 bps net margin across cases supports at most ~11/27/41 fully-funded free-credit days; the offered 20-day package fails the downside case and must be flagged as a loss-leader there.
3. **Model only what's modellable:** the decisive unknown (supplier card acceptance) is empirical — so the full commercial model is deliberately deferred until VE-002 reports, and the failure threshold (<20% surcharge-free acceptance → reclassify Weak) was committed in advance.

Classification: **Promising but unvalidated (borderline Weak)** — gated on VE-002.
