# Product & Opportunity Intelligence Module (Workstream B)

The module of the BOTIM Opportunity Intelligence agent that turns customer evidence into scored, stress-tested, commercially modelled SME payment and lending opportunities — and meeting-ready recommendations. It is explicitly willing to reject weak ideas, including the current favourite.

Ownership and collaboration rules: see `WORKSTREAMS.md` at repo root; the combined agent is defined in `MASTER_PROMPT.md`. This module owns `opportunity-intelligence/` and `knowledge-base/{product-ideas, commercial-models, validation, opportunity-scores}/` only.

## What this module does / does not do

**Does:** product hypotheses from evidence · segment value propositions · opportunity scoring (17 dimensions) · stress tests with Strong/Promising/Weak/Reject classification · commercial models with downside/base/upside · MDR/interchange subsidy math · BOTIM-advantage analysis · seven-week MVPs · validation experiments · backlog · meeting-ready outputs.

**Does not:** primary customer-data collection. It consumes structured findings from the Customer & Market Intelligence module (Workstream A). Missing evidence is marked `(A)` and requested via the backlog's evidence-request queue — never fabricated.

## Module map

```
opportunity-intelligence/
├── SYSTEM_PROMPT.md                    Module system prompt (rules, workflow, terminology)
├── frameworks/
│   ├── opportunity-scoring.md          17-dimension 1–5 scoring model + companion fields
│   └── product-stress-test.md          Kill-the-idea framework + classification rubric
├── reasoning/
│   ├── README.md                       Reasoning layer: calibration, adversarial checks, base rates
│   ├── reasoning-protocol.md           6-step pass run at every decision point
│   └── reference-classes.md            Base rates consulted before classification (outside view)
├── templates/
│   ├── opportunity-profile.md          Consolidated evaluation form (all framework fields)
│   ├── commercial-model.md             Full unit-economics template (ranges, 3 cases, break-even)
│   ├── mdr-interchange-subsidy-model.md  Net interchange math; max free days/cashback/subsidy
│   ├── value-proposition.md            Organic-switching-first VP template + data loop
│   ├── seven-week-mvp.md               Week-by-week MVP with kill thresholds
│   ├── validation-experiment.md        Falsifiable experiments, pre-committed thresholds
│   ├── opportunity-backlog.md          Living backlog + archive + evidence-request queue
│   └── meeting-ready-output.md         One-page decision view + appendices
├── commands/EXAMPLE_COMMANDS.md        Five example commands to drive the module
└── test-cases/                         Worked examples (incl. one deliberate Reject)
    ├── 01-revenue-linked-revolving-credit.md
    ├── 02-supplier-payment-card.md
    └── 03-generic-cashback-business-wallet.md

knowledge-base/            (this module's four owned folders — see each folder's README)
├── product-ideas/         Opportunity profiles, BACKLOG.md, issued recommendations
├── commercial-models/     Completed commercial + subsidy models
├── validation/            Experiment specs and results
└── opportunity-scores/    Completed scorecards
```

## Standard workflow

Evidence in → opportunity framework → scorecard → stress test → commercial model + subsidy model → (if promising) value proposition, MVP, experiments → backlog update → meeting-ready output on request. Details in `SYSTEM_PROMPT.md`.

## Non-negotiables

1. All 17 scores shown, never only a composite.
2. Ranges (downside/base/upside), AED, F/E/A labels on every model input.
3. Correct terminology: accepting merchant pays MDR; BOTIM earns issuer interchange or a programme share, never full MDR.
4. A value proposition must survive with all promotions removed (organic switching test).
5. Experiments have pre-committed success AND failure thresholds and non-leading questions.
6. Classifications apply to propositions, not the company launch decision.
7. Assumption-heavy scorecards (>6 of 17 `(A)`) cap out at "Promising but unvalidated".

## Cross-module requests

The **single source of truth for evidence requests is the REQ queue in `knowledge-base/product-ideas/BACKLOG.md`** (REQ-001 answered — Workstream A's `EV-YYYY-Wnn-nnn` scheme is adopted and parsed by `tools/`; REQ-002 partially answered; REQ-003..007 tracked there with statuses). Do not maintain request lists anywhere else, including here.
