# Significance Scoring & Tiering

Every event is scored 1–5 on five axes; the tier is then **computed, never chosen**. Implemented in `tools/monitoring_engine/significance.py`; `monitor.py check` recomputes every stored tier and fails on mismatch.

## Axes (anchors)

| Axis | 1 | 3 | 5 |
|---|---|---|---|
| **impact** | no plausible effect on any backlog OPP or segment | touches one OPP's assumptions or one segment | invalidates a load-bearing assumption, opens/closes a wedge, or moves a live decision |
| **urgency** | no decay in value of knowing | acting this month matters | acting this week/day matters |
| **confidence** | single weak/unverified source | one strong or several weak aligned sources | official/primary source or multiple independent confirmations |
| **relevance** | outside UAE SME payments/lending scope | adjacent | squarely on a monitored entity/segment/OPP |
| **novelty** | already known (KB or prior event) | new detail on a known theme | genuinely new fact changing the picture |

## Tier rule (mechanical, in evaluation order)

1. `confidence < 3` → at most **informative** (unverified bombshells go to the verification queue, not to executives).
2. `impact ≥ 4 AND urgency ≥ 4 AND confidence ≥ 3` → **critical**.
3. `impact ≥ 3 AND confidence ≥ 3 AND novelty ≥ 3` → **important**.
4. `relevance ≥ 3` → **informative**.
5. else → **insignificant** (stored for the dashboard archive; never notified).

## Default scores by internal signal type

KB-watcher events get defaults (overridable with justification in the event's `score_note`):

| Signal | impact | urgency | confidence | relevance | novelty | Typical tier |
|---|---|---|---|---|---|---|
| ve_verdict_conclusive (pass/fail) | 5 | 4 | 5 | 5 | 5 | critical |
| ve_observations_progress | 2 | 2 | 5 | 4 | 3 | informative |
| opportunity_reclassified | 4 | 3 | 5 | 5 | 4 | important |
| new_opportunity | 3 | 3 | 4 | 5 | 4 | important |
| new_evidence_record | 2 | 2 | 3 | 4 | 3 | informative |
| evidence_score_change (any axis Δ≥1) | 3 | 2 | 3 | 4 | 3 | important |
| evidence_status_change | 2 | 2 | 4 | 4 | 3 | informative |
| segment_confidence_change | 3 | 2 | 4 | 5 | 4 | important |
| new_segment / new_inflection_point | 3 | 3 | 3 | 5 | 4 | important |
| ip_status_change (confirmed/invalidated) | 4 | 4 | 4 | 5 | 4 | critical |
| prediction_resolved | 3 | 2 | 5 | 4 | 4 | important |
| new_experiment | 2 | 2 | 5 | 4 | 3 | informative |

External-adapter events (P1) have per-adapter defaults; regulator sources start at confidence 5, social at 2.

## Fatigue budget

Per user, per day, per channel: max `fatigue_budget` instant alerts (default 3). Overflow is demoted to the next digest with `demoted_by_budget: true`. `critical` events may exceed the budget but never the confidence gate. Same-thread repeats collapse into one evolving alert.
