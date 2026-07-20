# Evidence-gap profile (Phase R10, PR10a) — schema v1

A deterministic, read-only **weakest-link profile** for one opportunity.
Producer: `impact/gap_profile.py::build_gap_profile(opp_id, now)` (derived read
model — regenerable, never a second source of truth). Exposed read-only via the
copilot tool `get_evidence_gap_profile(opp_id)` and
`GET /api/opportunities/{OPP-nnn}/gap-profile` (mode-gated like the opportunity
detail route: 404 when the demo corpus is hidden). Changes are **additive only**.

The profile **recomputes no score and writes nothing** — it composes five gap
signals the codebase already computes and reuses the existing documented
heuristic ranker (`impact/gaps.py` weights, plus one shown `+1` for stale
load-bearing evidence). It surfaces *where* an opportunity's evidence is weakest
so a human can target research (the seed for R10's question generation, PR10b);
it never drafts, approves, sends, or attaches anything to a merchant, and never
mutates the committed knowledge base.

## The five signals (each shown per weak link)

| Signal | Meaning | Source |
|---|---|---|
| `no_supporting_evidence` | assumption cites no Part A evidence | `tracker.build` supporting_ev |
| `assumption_capped` | still-assumption dimension under a >6-assumption cap | `scoring.evaluate` assumption flags + `ASSUMPTION_CAP` |
| `contradicted` | assumption status is `contradicted` | authoritative assumption register |
| `stale_load_bearing` | a supporting EV record is stale (>180d) | `shared/freshness.py` |
| `open_gap` | assumption still untested / partially_supported | `tracker.build` status |

## Object

| Field | Type | Notes |
|---|---|---|
| `meta` | object | standard `genmeta` block (kind `evidence-gap-profile`, source files + hashes, `generated_at`, `is_derived: true`, `authoritative: false`) |
| `opportunity_id` | `OPP-nnn` | |
| `name` | string | |
| `evidence_base` | object | summary counts (below) |
| `ranking_method` | object | `type` (heuristic), `weights`, `bands`, `signals` — every weight shown |
| `weak_links` | weak_link[] | ranked, newest-weakest first |

### `evidence_base`

`supporting_ev_records` (distinct EV cited across assumptions), `assumptions_total`,
`assumptions_open`, `assumptions_without_evidence`, `assumptions_contradicted`,
`assumption_count`, `assumption_cap`, `assumption_capped` (bool),
`assumptions_to_lift_cap`, `stale_load_bearing_ev` (EV id[]).

### `weak_link`

| Field | Type | Notes |
|---|---|---|
| `assumption_id` | `ASM-OPP-nnn-<factor>` | the traceable unit; PR10b tags generated questions with this |
| `opportunity_id` / `factor` / `category` | | |
| `statement` | string | the assumption text |
| `status` | `untested\|partially_supported\|contradicted` | never `supported` (supported assumptions are not weak links) |
| `decision_importance` | `critical\|high\|medium\|low` | |
| `signals` | string[] | which of the five fired |
| `supporting_ev` / `contradicting_ev` | `EV-…[]` | |
| `stale_ev` | `[{ev_id, freshness_status, age_days, reference_date}]` | stale load-bearing detail |
| `priority_score` | int | heuristic (weights shown in `ranking_method`) |
| `priority_band` | `critical\|high\|medium\|low` | ≥7 / 5-6 / 3-4 / ≤2 |
| `reasons` | string[] | every input to the score, shown |
| `missing_inputs` | string[] | honest note of what could not be computed |
| `priority_rank` | int | 1-based, after the descending sort |

## Honesty guarantees
- Deterministic: same inputs → byte-identical profile (given the same `now`).
- No fabrication: absent dates → freshness `unknown` (never invented); a missing
  opportunity is a 404 (`FileNotFoundError` at the module boundary), never an
  empty-but-successful profile.
- Read-only: nothing here writes `knowledge-base/`, mints an EV id, drafts a
  merchant question, or changes a score — those remain human `impact` CLI
  (`--approver`) and Merchant Voice actions.
