# Customer & Market Intelligence Module (Workstream A)

This module is the customer-and-market research arm of the BOTIM Opportunity Intelligence agent. It discovers, records, scores, and maintains evidence about SME merchant pain, customer segments, competitors, and market inflection points in the UAE (and later the GCC), so that Workstream B can turn that evidence into product opportunities.

The module is **user-centric**: real merchant behaviour outweighs stated interest, market-size headlines, and analyst assumptions. The knowledge base is **cumulative** — research runs update what changed instead of restarting from scratch.

## What lives where

```
customer-intelligence/
├── README.md                       ← this file
├── SYSTEM_PROMPT.md                ← the module's operating prompt
├── guides/
│   ├── source-discovery.md         ← how to find evidence sources autonomously
│   └── research-quality.md         ← fact vs inference, contradiction checks, confidence
├── frameworks/
│   ├── evidence-scoring.md         ← 10-axis 1–5 scoring for every pain point
│   └── pain-point-taxonomy.md      ← canonical pain categories
├── templates/
│   ├── customer-evidence.md        ← ⚠ format is a parsing contract with Workstream B
│   ├── customer-segment.md
│   ├── competitor-profile.md
│   ├── inflection-point.md
│   ├── weekly-market-update.md
│   ├── source-log.md
│   └── customer-interview.md       ← interview → evidence pipeline (with confidence caps)
├── commands/
│   └── example-commands.md         ← five worked example invocations
├── test-cases/
│   └── test-cases.md               ← three realistic test scenarios
└── tools/
    ├── conformance_check.py        ← read-only knowledge-base validator (stdlib only)
    └── tests/test_conformance.py

knowledge-base/                     (Workstream A owns only these four)
├── customer-evidence/              ← scored evidence records + weekly updates
├── competitors/                    ← one profile per competitor + watchlist
├── segments/                       ← one profile per customer segment
└── inflection-points/              ← one record per market change
```

## Core workflows

1. **Competitor research** — build or refresh a competitor profile.
2. **Voice-of-customer research** — mine reviews, forums, and communities for merchant wording.
3. **Merchant pain-point research** — deep-dive one pain across segments and sources.
4. **Customer-segment discovery** — split "SMEs" into precise, behaviour-defined segments.
5. **Inflection-point discovery** — detect market changes that alter opportunity timing.
6. **Weekly market updates** — a delta report: what changed since last week.
7. **Product-change tracking** — competitor launches, pricing changes, withdrawals.
8. **Source discovery** — expand the source list, log every source used.
9. **Customer interview synthesis** — convert interview notes into scored evidence records.
10. **Evidence contradiction checks** — actively search for evidence against a conclusion.

Each workflow reads existing knowledge-base records first, then adds or updates records using the templates, then updates the relevant source log.

## ID conventions

| Record type | ID format | Example |
|---|---|---|
| Evidence record | `EV-<year>-W<iso-week>-<seq>` | `EV-2026-W28-003` |
| Segment | `SEG-<kebab-slug>` | `SEG-uae-importers-upfront-pay` |
| Competitor | `<kebab-name>.md` | `mamo.md` |
| Inflection point | `IP-<year>-<seq>` | `IP-2026-004` |
| Source | `SRC-<seq>` (in the source log) | `SRC-041` |

Workstream B may cite evidence by ID (e.g. an opportunity score referencing `EV-2026-W28-003`). IDs are never reused or renumbered.

**ID-collision rule (concurrent runs).** This repo is worked on by two people and multiple agent runs. Before minting any new ID:

1. `git pull` the latest branch state.
2. Search the knowledge base for the highest existing ID of that type (e.g. `grep -ro "EV-2026-W[0-9]*-[0-9]*" knowledge-base/customer-evidence/`).
3. Select the next unused ID **immediately before writing** the record — not at the start of a long research run.
4. Re-run the search just before committing; if a collision appeared (someone else pushed), renumber your new records (never the pre-existing ones) and re-check.

The same rule applies to `SRC-`, `IP-`, and any sequential ID. `customer-intelligence/tools/conformance_check.py` fails on duplicate IDs as a backstop.

## Boundaries

Per the workstream rules in the root `README.md`, this module never modifies:

- `opportunity-intelligence/` or `knowledge-base/product-ideas/`, `knowledge-base/commercial-models/`, `knowledge-base/validation/`, `knowledge-base/opportunity-scores/` (Workstream B)
- Shared files (`README.md`, `MASTER_PROMPT.md`, root `templates/`, `context/`, `shared/`)

Cross-module suggestions are recorded in weekly updates under "Handoffs to Workstream B", not implemented directly.

## Conformance

Evidence records are machine-consumed by Workstream B, so the record format is a compatibility contract (see the note at the top of `templates/customer-evidence.md`). Before committing knowledge-base changes:

```
python3 customer-intelligence/tools/conformance_check.py .          # validate live KB (exit 0 = pass)
python3 -m unittest discover customer-intelligence/tools/tests -v   # run the checker's test suite
```

The checker is read-only and validates: unique EV IDs, High/Medium/Low confidence values, valid status tokens, all ten score axes, required fields, and that EV/SRC/SEG/IP references in structured fields resolve (example IDs in prose/documentation are deliberately ignored).
