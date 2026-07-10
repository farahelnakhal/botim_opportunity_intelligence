# Example Commands — Product & Opportunity Intelligence

Five representative commands showing how to drive this module. Each states what the module will do and which files it reads/writes.

---

## 1. Evaluate a new product idea end-to-end

```
Evaluate this idea: a revolving SME credit facility from AstraTech, loaded onto a
BOTIM business wallet, with limits that grow with payment activity routed through
BOTIM. Target: F&B merchants with 1–3 outlets in Dubai/Sharjah.
Run the full workflow: opportunity framework → scoring → stress test →
commercial model → classification. Use evidence from knowledge-base/customer-evidence/
where it exists; mark everything else as assumption and log evidence requests.
```

Reads: `knowledge-base/customer-evidence/`, `segments/`, `competitors/` (read-only). Writes: `knowledge-base/product-ideas/`, `opportunity-scores/`, `commercial-models/`, updates `BACKLOG.md`.

## 2. Model the free-credit-days subsidy

```
Using templates/mdr-interchange-subsidy-model.md, estimate the maximum affordable
free-credit period for a supplier-payment card, assuming commercial-card interchange
in the UAE, a 60/40 offline/online mix, and BOTIM earning a programme share (not full
MDR). Show downside/base/upside and state which assumption breaks the model first.
```

Writes: `knowledge-base/commercial-models/<slug>-subsidy.md`.

## 3. Stress-test the current favourite

```
Run frameworks/product-stress-test.md against the business-IBAN + prepaid Visa
card idea. Write the strongest case against it as if you were a sceptical investor.
Do not soften the conclusion — if it's Weak or Reject, say so and give the decisive
factor.
```

Writes: stress-test section in `knowledge-base/product-ideas/<slug>.md`, updates `BACKLOG.md`.

## 4. Design a validation experiment

```
The riskiest assumption for OPP-003 is that merchants will route ≥50% of supplier
spend through a BOTIM card to keep their credit limit growing. Design the cheapest
experiment that can falsify this, using templates/validation-experiment.md, with
pre-committed success and failure thresholds and non-leading interview questions.
```

Writes: `knowledge-base/validation/VE-###-<slug>.md`, updates `BACKLOG.md` next-action.

## 5. Produce the meeting pack

```
Using templates/meeting-ready-output.md, produce a meeting-ready recommendation for
the top proposition in the backlog. One decision page, appendices from the existing
scorecard, stress test, and commercial model. Flag every number that rests on an
assumption rather than evidence, and end with a single concrete ask.
```

Reads: all module knowledge-base folders. Writes: `knowledge-base/product-ideas/<slug>-recommendation-YYYY-MM-DD.md`.
