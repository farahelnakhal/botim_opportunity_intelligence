# Reasoning Pass (per important/critical event)

The module never merely forwards updates. Before an alert is emitted, answer seven questions — each with an **artefact-level consequence**, reusing existing machinery. Answers are recorded in the event's summary; "why did/didn't I get alerted" must always be answerable from the record.

| # | Question | Consequence (mechanical) |
|---|---|---|
| 1 | Does this materially change our understanding? | Reflected in novelty/impact scores; if no → tier ≤ informative, no summary needed |
| 2 | Does this invalidate previous assumptions? | List the specific (A)-labelled model inputs, scorecard bases, or IP falsifiers touched — **by id**. Vague "this challenges our thesis" is not an answer |
| 3 | Does this create a new opportunity? | Propose a backlog candidate row (Unscored) + file an evidence candidate for Workstream A; never score it yourself |
| 4 | Does this increase competitive risk? | Map to a named stress scenario (`funded_competitor_capture`, `rate_compression`, …) or propose a new custom scenario for the affected OPP's scenarios file |
| 5 | Should product hypotheses be rescored? | Emit rescore flags `{opp, dimensions, reason, event_id}` — surfaced to Workstream B exactly like sync-bridge suggestions: report-only, human applies |
| 6 | Should validation experiments change? | Flag the affected VE for **redesign as a new experiment** if compromised. Never edit thresholds — pre-commitment is inviolable |
| 7 | Should executives be informed immediately? | Only via tier = critical, which requires the confidence gate. There is no side channel |

## Honesty rules

- Every claim in a summary carries a source (EV/IP/SRC id or adapter provenance with access label and fetch date).
- Confidence uses Workstream A's vocabulary (High/Medium/Low + why); a summary may not be more confident than its weakest load-bearing source.
- If an alert cites unpromoted evidence candidates, it says so explicitly ("unverified — candidate pending Workstream A review").
- Conflicting sources → one event, confidence capped at 2, routed to verification, never alerted as fact.
