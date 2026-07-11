# Opportunity Scoring Framework

Score every product proposition on all 17 dimensions below, 1–5 each. **Always show all individual scores.** Composite scores are a summary aid only — a proposition can be killed by a single low score on a critical dimension regardless of its average.

## How to score

- Score from evidence in `knowledge-base/customer-evidence/` and related folders wherever possible.
- Where evidence is missing, score anyway but mark the score `(A)` for assumption-based and log the evidence request.
- Half-points are not allowed; force a choice.

## Dimensions and anchors

### Demand side

| # | Dimension | 1 | 3 | 5 |
|---|-----------|---|---|---|
| 1 | Pain severity | Minor annoyance | Costs real time/money monthly | Threatens cash flow or survival |
| 2 | Pain frequency | A few times a year | Monthly | Daily or per-transaction |
| 3 | Financial impact | <0.5% of revenue | 1–3% of revenue | >5% of revenue or blocks growth |
| 4 | Workaround cost | Cheap, easy workaround exists | Workaround costs meaningful time/fees | No workaround, or workaround is very costly (e.g. informal lending at high rates) |
| 5 | Switching intent | Satisfied with current provider | Open to switching at an inflection point | Actively seeking alternatives now |
| 6 | Willingness to pay | Expects it free | Would pay a modest fee if value is clear | Already pays more for a worse alternative |
| 7 | Digital readiness | Cash-based, avoids apps | Uses some digital banking/payments | Fully digital operations, expects app-first |

### Volume and credit

| # | Dimension | 1 | 3 | 5 |
|---|-----------|---|---|---|
| 8 | Payment volume | Low/irregular monthly spend | Moderate, seasonal | High, recurring monthly spend (e.g. supplier purchasing) |
| 9 | Credit need | Rarely needs credit | Occasional working-capital gaps | Chronic, recurring working-capital need |

### BOTIM/AstraTech fit

| # | Dimension | 1 | 3 | 5 |
|---|-----------|---|---|---|
| 10 | BOTIM distribution advantage | Segment not on BOTIM; expensive to reach | Partial overlap with BOTIM users/merchants | Segment already active on BOTIM; near-zero CAC |
| 11 | Transaction-data advantage | BOTIM would see no useful flow data | Sees part of the flow | Sees enough flow to underwrite and grow limits |

### Revenue

| # | Dimension | 1 | 3 | 5 |
|---|-----------|---|---|---|
| 12 | Payment revenue potential | Negligible interchange/fees | Covers processing costs | Material contribution margin from payment economics |
| 13 | Lending revenue potential | Thin margin after risk | Viable at scale | Strong risk-adjusted lending margin |

### Risk and execution

| # | Dimension | 1 | 3 | 5 |
|---|-----------|---|---|---|
| 14 | Credit-risk visibility | Underwriting blind; self-reported data only | Partial visibility (statements, some flows) | Real-time visibility of revenue through the platform |
| 15 | Competitive defensibility | Any bank/fintech can copy in months | Some data/distribution moat | Compounding data + distribution loop hard to replicate |
| 16 | Ease of validation | Needs a licensed live product to test | Testable with pilots/prototypes | Testable in weeks with interviews/fake doors/data analysis |
| 17 | Seven-week MVP feasibility | Requires licences/integrations far beyond 7 weeks | Feasible with manual/concierge workarounds | Cleanly buildable in 7 weeks |

## Required companion fields (never omit)

For every scored proposition also record:

- **Evidence confidence:** High / Medium / Low, with the count and type of supporting evidence items (link to `knowledge-base/customer-evidence/` entries).
- **Main assumptions:** the 3–5 assumptions the scores most depend on, each marked `(A)`.
- **Main invalidation risk:** the single finding that would most damage the case.
- **Dependency on another module:** what is needed from Customer & Market Intelligence (or elsewhere) before scores can be trusted.
- **Recommended next action:** one concrete step (usually a validation experiment from `templates/validation-experiment.md`).

## Reading the scores

- **Critical-dimension floors:** if Pain severity ≤2, Switching intent ≤2, Credit-risk visibility ≤2 (for lending products), or 7-week MVP feasibility = 1, flag the proposition for stress-test scrutiny regardless of average.
- **Assumption load:** if more than 6 of 17 scores are `(A)`, classification cannot exceed "Promising but unvalidated".
- Composite (optional, shown last): simple mean, displayed to one decimal, labelled "indicative only".

## Canonical labels (prose ↔ engine)

To avoid vocabulary drift between documents and the engine (`tools/opportunity_engine/scoring.py`):

| Prose (documents, backlog) | Engine enum (JSON, exit codes) |
|---|---|
| Strong opportunity | `strong` |
| Promising but unvalidated (qualifiers allowed, e.g. "borderline Weak") | `promising` |
| Weak (qualifiers allowed, e.g. "standalone") | `weak` |
| Reject (archive only — never a live backlog row) | `reject` |

Evidence confidence: Title case in prose ("Low"), lowercase in JSON (`"low"`). The backlog checker matches classification by substring: a live-row label must contain at least one enum word and must not be reject-only; when a qualifier mentions a second enum word ("Promising but unvalidated (borderline Weak)"), the first word stated is the classification.

## Output format

Store completed scorecards in `knowledge-base/opportunity-scores/<idea-slug>.md` using this table:

```
| Dimension | Score | Basis (evidence / assumption) |
|---|---|---|
| Pain severity | 4 | EV-012, EV-019 |
| Pain frequency | 5 (A) | Assumed daily supplier purchasing — needs evidence |
| ... | ... | ... |
```
