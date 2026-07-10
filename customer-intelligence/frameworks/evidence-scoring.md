# Customer-Evidence Scoring Framework

Every pain point is scored 1–5 on ten axes. **All ten scores are always shown individually** — never collapsed into one hidden composite. A summary average may be shown *alongside* the axes, never instead of them.

## The ten axes

| # | Axis | 1 | 3 | 5 |
|---|---|---|---|---|
| 1 | **Frequency** | Seen once, one merchant | Recurs across a handful of distinct merchants | Recurs constantly across many distinct merchants and sources |
| 2 | **Severity** | Minor annoyance | Disrupts operations regularly | Threatens the business (cash-flow crisis, lost customers, closure risk) |
| 3 | **Financial cost** | Negligible | Noticeable recurring cost (fees, penalties, lost sales) | Large recurring cost relative to margins |
| 4 | **Urgency** | Can wait indefinitely | Merchant wants a fix this year | Merchant needs a fix now; actively hunting |
| 5 | **Dissatisfaction with current solutions** | Broadly satisfied | Mixed; tolerates known flaws | Openly frustrated; complains unprompted |
| 6 | **Workaround cost** | No workaround needed | Workaround exists but costs time/money | Expensive, risky, or compliance-grey workaround (personal cards, informal borrowing) |
| 7 | **Switching intent** | No sign of looking | Asks about alternatives | Has switched, is trialling alternatives, or states a concrete switching plan |
| 8 | **Willingness to pay** | Expects free | Pays indirectly (fees, tools) | Already pays meaningfully for an imperfect solution |
| 9 | **BOTIM relevance** | Outside BOTIM/AstraTech's plausible scope | Adjacent; needs new capability | Squarely addressable via BOTIM reach, payments, wallets, cards, IBANs, or AstraTech lending |
| 10 | **Evidence strength** | Stated interest / single weak source | One strong behavioural source or several weak aligned ones | Multiple independent, recent, behavioural sources |

## Scoring rules

- Score from evidence, not intuition; each score of 4–5 must be justifiable by cited evidence IDs.
- **Frequency counts distinct merchants**, not mentions (duplicates collapse to one).
- **Evidence strength (axis 10) caps the others in interpretation**: a pain scoring 5 on severity but 1 on evidence strength is a *lead*, not a finding. Flag such records `needs-more-evidence`.
- Rescore when material new evidence arrives; keep the previous scores in the record's history line so trends are visible.
- Scores are per **segment**: the same pain may score differently for importers vs. restaurants — record separately.

## Presentation format

```
Scores (1–5):
  Frequency ................ 4
  Severity ................. 3
  Financial cost ........... 4
  Urgency .................. 3
  Dissatisfaction .......... 4
  Workaround cost .......... 5
  Switching intent ......... 2
  Willingness to pay ....... 4
  BOTIM relevance .......... 5
  Evidence strength ........ 3
  (mean 3.7 — shown for convenience only)
```

## What the scores feed

Workstream B consumes these scores (by evidence ID) for opportunity scoring. This module's job ends at honest, evidence-backed axis scores; prioritisation across opportunities is Workstream B's.
