# BOTIM Opportunity Intelligence

An internal AI research and product-discovery agent for BOTIM/AstraTech: it discovers evidence of SME merchant pain in the UAE, converts that evidence into scored and stress-tested payment/lending product opportunities, models the commercial economics honestly, and produces meeting-ready recommendations — while remaining willing to reject weak ideas, including its own.

The agent is defined in **`MASTER_PROMPT.md`** and composed of two modules over one shared knowledge base:

| | Customer & Market Intelligence | Product & Opportunity Intelligence |
|---|---|---|
| Prompt | `customer-intelligence/SYSTEM_PROMPT.md` | `opportunity-intelligence/SYSTEM_PROMPT.md` |
| Produces | Evidence records (EV-…), segments (SEG-…), competitor profiles, inflection points (IP-…), weekly updates with handoffs | Backlog (OPP-…), scorecards, commercial/subsidy models, stress tests, experiments (VE-…), recommendations, decision journal |
| Tools | `customer-intelligence/tools/` (conformance checker) | `opportunity-intelligence/tools/` (computation engine, 10+ CLI commands) |

Evidence flows A→B by ID; evidence *requests* flow B→A through the backlog's REQ queue. Ownership and collaboration rules: `WORKSTREAMS.md`.

## Quickstart

```bash
# The integration gate — run before every push; must pass clean
python3 shared/integration_check.py

# Explore the current state
python3 opportunity-intelligence/tools/run.py evidence      # parsed evidence records
python3 opportunity-intelligence/tools/run.py check         # knowledge-base sweep
python3 opportunity-intelligence/tools/run.py sync          # evidence → scorecard suggestions
python3 opportunity-intelligence/tools/run.py calibration   # decision-journal Brier report
python3 customer-intelligence/tools/conformance_check.py .  # evidence-format conformance
```

Pure Python 3 standard library throughout — nothing to install.

## Repository map

```
MASTER_PROMPT.md            The combined agent: routing, shared loop, non-negotiables
WORKSTREAMS.md              Ownership, cross-module contract, git rules
shared/                     Integration gate + cross-module tests
customer-intelligence/      Workstream A module (prompts, frameworks, templates, tools)
opportunity-intelligence/   Workstream B module (prompts, frameworks, templates, reasoning layer, engine)
knowledge-base/             The cumulative shared memory
├── customer-evidence/      A: scored EV records, source log, weekly updates
├── segments/  competitors/  inflection-points/        A: reference entities
├── product-ideas/          B: BACKLOG.md, opportunity profiles, recommendations, decision journal
├── commercial-models/      B: model inputs (JSON) + engine-computed reports + BENCHMARKS.md
├── opportunity-scores/     B: 17-dimension scorecards (JSON, engine-validated)
└── validation/             B: experiment specs + pre-committed result files
```

## Operating principles (the short version)

1. Evidence before advocacy — assumptions are marked `(A)`, cited facts carry EV ids, and classifications are capped by assumption load.
2. Numbers come from the engine — commercial figures are computed from committed inputs JSON, never hand-authored.
3. Correct payment terminology — merchants pay MDR; issuers earn interchange or a programme share, never "the full MDR".
4. Kill thresholds are pre-committed — experiments and predictions are logged before outcomes are knowable.
5. The knowledge base is cumulative — update, link, and re-score; never restart.
