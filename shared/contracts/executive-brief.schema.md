# executive-brief.schema — v1.0

**Producer:** `impact.cli brief --opportunity <OPP> --format json` · **Kind:** derived (regenerable) · **Authoritative source:** the opportunity scorecard (`knowledge-base/opportunity-scores/<opp>-scorecard.json`) + engine `opportunity_engine.scoring`. This brief never recomputes scores.

Top-level object:

| Field | Req? | Nullable | Type / enum | Notes |
|---|---|---|---|---|
| `meta` | required | no | object | common `meta` block (see README) |
| `opportunity` | required | no | object | `{opportunity_id, name, customer{segment_id?,segment_title?,segment_confidence?,job_to_be_done?}}` |
| `score` | required | no | object | engine values, verbatim (below) |
| `confidence` | required | no | object | multiple confidences exposed separately (below) |
| `assumptions` | required | no | object | `{total, unresolved, no_supporting_evidence, contradicted, items[]}` |
| `evidence` | required | no | object | `{supporting_primary[], supporting_leads[], contradicting[], detail{}}` |
| `recent_changes` | required | no | array | may be empty |
| `recommended_action` | required | no | object | `{ve: string|null, text}` |
| `decision_requested` | required | no | object | `{text, no_build_decision: string|null}` |

`score` — mirrors the engine exactly:
`raw_score` "X/85" (required), `raw` int, `raw_max` 85, `composite_score` float (engine composite, unchanged name), `assumption_count` int, `assumption_cap` int (6), `capped` bool, `classification` enum `strong|promising|weak|reject|null`, `critical_flags` string[].

`confidence` — never collapsed into one value:
`segment` `{segment_id, value, source}` · `opportunity_assessment` `{value, source}` · `evidence_distribution` `{high,medium,low,unknown,source}` · `note`. Any `value` may be null when the underlying source doesn't state it.

`evidence`:
- `supporting_primary` — behavioural, non-weak EV ids (weak/lead evidence is excluded here).
- `supporting_leads` — weak/lead EV ids (e.g. `needs-more-evidence` or strength ≤ 2); shown as context, never primary support.
- `contradicting` — EV ids; supporting evidence is preserved even when contradiction exists.
- `detail` — `{ev_id: {confidence, title}}`.

Enums: classification `strong|promising|weak|reject`; confidence values `high|medium|low|null`.

**Wording guarantees (enforced by the producer):** never asserts "validated"/"selected"/"launch approved" etc.; includes `decision_requested.no_build_decision = "No product or build decision has been made."` whenever `classification` is `promising` (or null) — i.e. promising-but-unvalidated.

**Parity:** the Markdown brief (`--format md`) is rendered from the same view object; substantive fields (score, classification, unresolved count, recommended action, decision requested, supporting/contradicting evidence ids) are identical to this JSON.
