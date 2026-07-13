# evidence-gaps.schema — v1.0

**Producer:** `impact.cli gaps --portfolio --format json` · **Kind:** derived (regenerable). **Authoritative source:** the assumption read models across all scorecards.

Top-level: `meta` (common block), `ranking_method`, `gaps[]`, `high_priority_questions[]`, `assumptions_no_supporting_evidence[]`, `assumptions_contradicted[]`, `ve_assumption_map{}`.

`ranking_method` (required, no): `{type: "heuristic (not statistically objective)", weights{}, bands{}}`. **The priority is an explicitly heuristic ranking — not a statistically objective score.**

Each `gaps[]` item:

| Field | Req? | Nullable | Type / enum |
|---|---|---|---|
| `priority_rank` | required | no | int (1 = highest) |
| `priority_score` | required | no | int |
| `priority_band` | required | no | enum: critical, high, medium, low |
| `opportunity_id` | required | no | string |
| `assumption_id` | required | no | string |
| `factor` | optional | yes | string |
| `category` | required | no | category enum |
| `statement` | required | no | string |
| `status` | required | no | status enum (untested/partially_supported/contradicted — supported items are not gaps) |
| `decision_importance` | required | no | importance enum |
| `reasons` | required | no | string[] (human-readable, shown) |
| `inputs_used` | required | no | object (the exact values fed to the score) |
| `missing_inputs` | required | no | string[] (e.g. "no cited supporting evidence") |
| `related_ve` | required | no | string[] |
| `question` | required | no | string (the unanswered question) |

`high_priority_questions[]`: `{priority_rank, priority_band, opportunity_id, question, reasons}`.
`assumptions_no_supporting_evidence[]`: `{opportunity_id, assumption_id, category, status}`.
`assumptions_contradicted[]`: `{opportunity_id, assumption_id, supporting_ev[], contradicting_ev[]}` (both sides shown).
`ve_assumption_map`: `{opportunity_id: {ve_id: [assumption_id, …]}}`.

Portfolio generation tolerates an opportunity with no authoritative assumption register (it falls back to the scorecard's assumption factors).
