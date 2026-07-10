# Test Case 2 — Supplier-Payment Commercial Card with Free-Credit Days

**Purpose of this file:** worked example testing the MDR/interchange subsidy model and the "card economics fund free credit" hypothesis. All merchant-behaviour numbers are assumptions `(A)`.

## Proposition

A BOTIM commercial Visa card (issued with AstraTech credit behind it) that merchants use to **pay suppliers**. Merchants get N interest-free days funded partly by interchange on their supplier spend; AstraTech earns financing revenue on balances revolved beyond the free period.

- **Segment (A):** trading/retail SMEs buying AED 30k–150k/month of stock from suppliers who accept cards or can be onboarded to.
- **Organic switching reason:** free-credit days on spend they already make + credit access without bank paperwork.

## Subsidy model (per `templates/mdr-interchange-subsidy-model.md`)

Terminology check: the **supplier** (accepting merchant) pays MDR to its acquirer; BOTIM earns issuer interchange / programme share only.

| Line (bps of spend) | Downside | Base | Upside |
|---|---|---|---|
| Gross commercial interchange (A) | 90 | 130 | 170 |
| − Programme splits (BIN sponsor, processor) (A) | −40 | −40 | −45 |
| − Scheme fees (A) | −10 | −12 | −15 |
| − Processing (A) | −10 | −10 | −10 |
| − Fraud (A) | −5 | −8 | −10 |
| **Net payment margin** | **25** | **60** | **90** |

Max free-credit days fully funded by payment margin, at 8% (A) funding:

- Downside: 0.0025 × 365 / 0.08 ≈ **11 days**
- Base: 0.0060 × 365 / 0.08 ≈ **27 days**
- Upside: 0.0090 × 365 / 0.08 ≈ **41 days**

…before ECL, servicing, and any cashback. With ECL 2% annualised on drawn balances (A) and servicing, the base case supports roughly **15–20 free days**, not 30–45. A "45 days free" offer is a loss-leader in every case except upside — must be flagged as such with a payback story, or funded from lending margin on revolvers.

## Stress test (summary)

- **FOR:** spend already exists; the card monetises it and the free days are a genuine, quantifiable benefit; underwriting sees supplier-spend patterns.
- **AGAINST:** **supplier acceptance is the wall.** UAE wholesale suppliers on bank transfer + 30/60-day terms have little reason to eat 1.5–2.5% MDR. If suppliers surcharge or refuse, eligible volume collapses. This is answer (c)+(d) to "why hasn't it been built": acceptance economics on the supply side.
- **Adverse selection:** merchants who revolve immediately (can't repay in free period) are the most attracted; interchange doesn't cover their risk.
- **Fraud:** collusive merchant–supplier fake invoicing to cash out credit lines.
- **Disproof:** if <20% of target merchants' supplier base accepts (or would accept) cards without surcharge, the model has no volume.

## Classification: **Promising but unvalidated** (borderline Weak)

- **Evidence confidence:** Low. The decisive unknown is supplier acceptance, which is empirical, not modellable.
- **Main invalidation risk:** supplier card acceptance below threshold → eligible volume too small for any subsidy.
- **Dependency:** Customer & Market Intelligence — evidence on how target merchants actually pay suppliers today (instrument, terms, surcharging) before further modelling.
- **Recommended next action:** VE-002 — supplier-payment mapping via 12 merchant interviews + 10 supplier calls; failure threshold: <20% card-acceptance willingness → reclassify Weak.
