# research-request.schema — v1.0

**Producer:** `impact.cli research-request --assumption <ASM-ID>` · **Kind:** derived proposal.

A generated request is a **proposal**; it does **not** enter Part A's production backlog. It becomes actionable only after explicit human review/approval. Default `status` is `draft`. (Distinct from Part B's `REQ-00n` backlog ids, which are owned by `knowledge-base/product-ideas/BACKLOG.md` and are not modified by this generator.)

| Field | Req? | Nullable | Type / enum |
|---|---|---|---|
| `meta` | required | no | common `meta` block |
| `request_id` | required | no | `REQ-<OPP>-<factor>` |
| `status` | required | no | enum: draft, approved, completed, rejected (default `draft`) |
| `opportunity_id` | required | no | string |
| `assumption_id` | required | no | string |
| `question` | required | no | string |
| `why_it_matters` | required | no | string |
| `current_evidence` | required | no | `{status, supporting_ev[], contradicting_ev[], evidence_confidence: high|medium|low|null}` |
| `required_evidence` | required | no | string |
| `preferred_sources` | required | no | string[] |
| `success_threshold` | optional | yes | string (from linked VE success metrics) |
| `rejection_threshold` | optional | yes | string (from linked VE failure metrics) |
| `deadline_or_review_point` | optional | yes | string |
| `note` | required | no | string |

Persistence: written only under `knowledge-base/impact/research-requests/<request_id>.json` and only with `--write`/`--output`; never into Part A or Part B owned files.
