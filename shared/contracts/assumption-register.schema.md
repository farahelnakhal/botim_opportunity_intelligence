# assumption-register.schema — v1.0

**Producer:** `impact.cli assumptions --opportunity <OPP> --format json` · **Kind:** derived (regenerable read model).

**Two distinct files — do not confuse:**
- **Authoritative mutation store:** `knowledge-base/impact/assumptions/<opp>.json` — changed ONLY by approved impacts (`impact/apply.py`). Source of truth for status + supporting/contradicting evidence.
- **Generated read model (this contract):** `knowledge-base/impact/assumption-registers/<opp>.json` — derived, regenerated from authoritative sources, **not independently editable, never a second source of truth.**

Top-level: `meta` (common block), `opportunity_id`, `name`, `score` (same as brief `score`), `counts` `{total_assumptions, unresolved, no_supporting_evidence, contradicted}`, `assumptions[]`, `evidence_problems[]`.

Each `assumptions[]` item:

| Field | Req? | Nullable | Type / enum |
|---|---|---|---|
| `assumption_id` | required | no | `ASM-<OPP>-<factor>` |
| `opportunity_id` | required | no | string |
| `statement` | required | no | string |
| `category` | required | no | enum: customer, pain, behaviour, switching, willingness_to_pay, product, commercial, credit, regulatory, operational, technical |
| `status` | required | no | enum: untested, partially_supported, supported, contradicted |
| `source` | required | no | enum: scorecard factor, product hypothesis, commercial model, risk analysis, manual entry |
| `factor` | optional | yes | scorecard factor key (null for manual assumptions) |
| `supporting_ev` | required | no | string[] (EV ids) |
| `supporting_ev_provenance` | optional | no | `{ev_id: "impact"|"scorecard_basis"}` |
| `contradicting_ev` | required | no | string[] (never removes supporting) |
| `evidence_confidence` | required | no | `{rule, cited_ev_confidences{}, derived: high|medium|low|null}` |
| `decision_importance` | required | no | enum: critical, high, medium, low |
| `score_impact` | required | no | object; `decision_sensitivity` is **null** unless safely derivable, with `score_impact_explanation` |
| `sensitivity` | optional | yes | string |
| `next_validation_method` | optional | yes | string |
| `validation_owner` | optional | yes | string |
| `target_date` | optional | yes | date string |
| `last_updated` | optional | yes | ISO8601 (from score history) |
| `change_history` | required | no | array (derived from append-only score history) |
| `related_ve` | required | no | string[] (VE ids) |
| `rejection_condition` | optional | yes | string |

`status` is emitted in **underscore** form (`partially_supported`); the authoritative store uses the legacy space form and is normalized at this boundary.

**Rules reflected here:** a scorecard factor with `assumption:true` always appears; medium evidence yields at most `partially_supported` (never auto `supported`); weak/vendor/funding evidence changes nothing; `evidence_problems[]` reports unresolved EV references rather than dropping them silently.
