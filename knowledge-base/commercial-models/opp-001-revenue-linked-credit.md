# Commercial Model — OPP-001 Revenue-Linked Revolving Credit (narrative)

**Numbers live in the engine, not here.** Canonical sources:

- Inputs (all F/E/A-labelled): `opp-001-inputs.json`
- Computed three-case model: `opp-001-computed.md` — regenerate after any input change with
  `python3 opportunity-intelligence/tools/run.py model knowledge-base/commercial-models/opp-001-inputs.json --write knowledge-base/commercial-models/opp-001-computed.md`
- Sensitivity ranking: `run.py sensitivity …` · Distributions: `run.py simulate …` · Adverse scenarios: `run.py stress …`

This file carries only the analysis the engine cannot do: what the numbers mean and which assumptions matter.

## Reading the model

- Base case clears unit economics (~+137/merchant/month, ~33% margin) but programme fixed costs put **break-even near 1,100 merchants — above the base-case month-12 count of 500**. The model closes only with upside growth, higher routed share, or lower fixed cost.
- Downside is unambiguously loss-making: adverse-selection ECL plus low routing cannot be priced away at 16–24% APR-equivalent.
- Free-credit days in this product are a **lending-margin decision, not an interchange play** — the wallet's payment take is small; the interchange-funded version is OPP-002's model.

## Assumption register (qualitative; sensitivity command gives the numbers)

| # | Assumption | Why it matters | Firmed up by |
|---|---|---|---|
| 1 | Achievable financing rate (~20% base) | #1 tornado risk: halving it flips contribution negative | AstraTech pricing + competitor scan (REQ to Workstream A) |
| 2 | Share of revenue routed (30% base) | Drives payment revenue, limit growth, drawn balance AND risk visibility at once | **VE-001** (directly) |
| 3 | Merchant revenue band | Scales everything; pure guess pending internal data | BOTIM merchant data |
| 4 | ECL (6% base / 12% downside) | Only a capped-limit pilot can measure it; scenario `adverse_selection` kills at 2.5× | Concierge pilot |
| 5 | Organic CAC via BOTIM channel | Minor if organic; fatal at paid-channel ×4 (scenario `cac_blowout` survives but strains) | MVP weeks 1–3 funnel test |

## Verdict

The one number to validate first is **routed share of revenue** — exactly what VE-001 tests. Second is achievable pricing (desk research, this week-able). Third is ECL, which only the pilot can measure.

*Changelog: 2026-07-10 — v1 hand-built tables. 2026-07-10 — audit remediation: numeric tables retired in favour of engine-computed report; this file is narrative-only.*
