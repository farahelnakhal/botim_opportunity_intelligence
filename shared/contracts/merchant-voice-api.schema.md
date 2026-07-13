# merchant-voice-api.schema — v1.0 (Phase 1: campaigns + guides only)

> **PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY. NOT APPROVED FOR REAL MERCHANT DATA. NOT FOR PRODUCTION USE.**
> Authentication is a static token→role map compared with `hmac.compare_digest` — this is **not** production identity/access management (no user directory, no session revocation, no token rotation, no TLS termination). Real merchant data requires a separate privacy/security review and a hardened deployment before use. All examples in this document use synthetic IDs only (`MVC-TEST-…`, `MVG-TEST-…`).

**Producer:** `merchant-voice/` (stdlib Python HTTP JSON API, port 8020) · **Consumer:** the future Merchant Voice researcher UI (Farah; scheduled after the current Product Discovery frontend is stable — no frontend work is included in this delivery).

This document covers **only what Phase 1 implements**: research campaigns and versioned research guides. Participants, responses, ingestion, AI extraction, review, evidence candidates, findings, analysis, Part A proposals, and Copilot integration are **not implemented yet** — see the Future Roadmap section at the end for their planned (not active) shape.

## Authentication

Every endpoint except `GET /health` requires `Authorization: Bearer <token>`. Tokens map to exactly one role via server configuration (`MV_TOKENS`); comparison is timing-safe (`hmac.compare_digest`). The server **refuses to start** if no tokens are configured.

## Roles

`viewer < researcher < reviewer < admin` (each role includes everything below it unless a rule says otherwise).

## Endpoint authorization matrix (Phase 1)

| Endpoint | viewer | researcher | reviewer | admin |
|---|---|---|---|---|
| `GET /health` | ✅ (no auth) | ✅ | ✅ | ✅ |
| `POST /campaigns`, `PATCH /campaigns/{id}` (draft only) | — | ✅ | ✅ | ✅ |
| `GET /campaigns`, `GET /campaigns/{id}` | ✅ | ✅ | ✅ | ✅ |
| `POST /campaigns/{id}/transition` → `approved` | — | — | ✅ | ✅ |
| `POST /campaigns/{id}/transition` → other (active/paused/completed) | — | ✅ | ✅ | ✅ |
| `POST /campaigns/{id}/transition` → `archived` | — | — | — | ✅ |
| `POST /campaigns/{id}/guides`, `GET .../guides`, `GET/PATCH /guides/{id}` (draft) | — (read: ✅) | ✅ | ✅ | ✅ |
| `POST /guides/{id}/approve` | — | — | ✅ | ✅ |
| `POST /guides/{id}/new-version` | — | ✅ | ✅ | ✅ |

**Self-approval:** a guide cannot be approved by the same actor who created it unless `MV_ALLOW_SELF_APPROVAL=1` — every such approval is audited with `self_approval: true`.

## Synthetic-only mode

`MV_SYNTHETIC_ONLY=1` (default). While enabled, every campaign's `data_classification` must be `"synthetic"`; any other value is rejected with `invalid_request`.

## Campaign object

| Field | Req? | Nullable | Type / enum |
|---|---|---|---|
| `campaign_id` | required | no | `MVC-...` |
| `title` | required | no | string |
| `objective` | required | no | string |
| `research_questions` | optional | no (defaults `[]`) | string[] |
| `target_segments` | optional | no | string[] (`SEG-...`) |
| `linked_opportunities` | optional | no | string[] (`OPP-nnn`) |
| `linked_assumptions` | optional | no | string[] (`ASM-OPP-nnn-<factor>`) |
| `method` | required | no | enum: `survey`, `interview`, `concept_test` |
| `workflow_status` | required | no | enum: `draft`, `approved`, `active`, `paused`, `completed`, `archived` |
| `owner` | optional | yes | string |
| `consent_template_id` | optional | yes | string |
| `data_classification` | required | no | enum: `synthetic`, `internal`, `confidential`, `restricted` (non-synthetic values rejected while synthetic-only mode is on) |
| `sampling_notes` | optional | yes | string |
| `start_date` / `end_date` | optional | yes | date string |
| `created_by` / `created_at` / `updated_at` | required | no | string / ISO8601 |

**Lifecycle:** `draft → approved → active ⇄ paused → completed → archived`. `archived` is reachable from any non-archived state and is terminal. Invalid transitions return `invalid_request`.

## Research guide object

| Field | Req? | Nullable | Type |
|---|---|---|---|
| `guide_id` | required | no | `MVG-...` |
| `campaign_id` | required | no | string |
| `version` | required | no | int, starts at 1, increments per campaign |
| `workflow_status` | required | no | enum: `draft`, `approved` |
| `approved_by` / `approved_at` | optional | yes | string / ISO8601 |
| `created_by` / `created_at` | required | no | string / ISO8601 |
| `questions` | required | no | array of question objects |

**Immutability:** once `approved`, a guide version can never be edited (`PATCH` on an approved guide → `invalid_request`). Editing further requires `POST /guides/{id}/new-version`, which creates version N+1 in `draft`.

## Guide question object

| Field | Req? | Nullable | Type / enum |
|---|---|---|---|
| `question_id` | required | no | string (server-assigned if omitted) |
| `text` | required | no | string |
| `purpose` | required | no | enum: `problem`, `behaviour`, `workaround`, `frequency`, `severity`, `willingness_to_pay`, `switching_barrier`, `trust`, `concept_reaction`, `rejection_condition`, `follow_up` |
| `question_type` | optional | no (default `open_text`) | enum: `open_text`, `single_choice`, `multi_choice`, `scale`, `yes_no` |
| `follow_up_prompts` | optional | no | string[] |
| `linked_assumption` | optional | yes | `ASM-OPP-nnn-<factor>` |
| `linked_hypothesis` | optional | yes | string |
| `position` | required | no | int (order within the guide) |

## Error shape

```json
{ "schema_version": "1.0", "error": { "code": "invalid_request", "message": "..." } }
```

`error.code` → HTTP status: `invalid_request` 400 · `unauthorized` 401 · `forbidden` 403 · `not_found` 404 · `conflict` 409 · `internal` 500. Messages never contain stack traces, tokens, or secrets.

## Example requests/responses (synthetic data only)

**Create a campaign**
```
POST /api/merchant-voice/campaigns
Authorization: Bearer <researcher-token>

{ "title": "MVC-TEST-001 supplier-payment pilot",
  "objective": "Understand supplier-payment financing pain among UAE importers",
  "method": "interview",
  "target_segments": ["SEG-uae-importers-upfront-pay"],
  "linked_opportunities": ["OPP-013"],
  "data_classification": "synthetic" }
```
→ `201`, the campaign object with `workflow_status: "draft"`.

**Create a guide**
```
POST /api/merchant-voice/campaigns/MVC-TEST-001/guides
Authorization: Bearer <researcher-token>

{ "questions": [
    { "text": "What is your biggest supplier-payment problem?", "purpose": "problem" },
    { "text": "How often does this happen?", "purpose": "frequency" } ] }
```
→ `201`, the guide object, `version: 1`, `workflow_status: "draft"`.

**Approve the guide**
```
POST /api/merchant-voice/guides/MVG-TEST-001-v1/approve
Authorization: Bearer <reviewer-token>
```
→ `200`, `workflow_status: "approved"`, `approved_by`/`approved_at` set.

## Schema version

`1.0` (Phase 1 subset). This document will grow additively as later phases land; existing Phase 1 fields will not be renamed or removed without a version bump and cross-workstream agreement.

## Streaming

Not applicable — this is a synchronous CRUD API, not a conversational endpoint.

---

## Future roadmap (NOT implemented — documented for context only, not active)

The following objects/endpoints are planned for later phases and **must not be treated as available**: participants (pseudonymous, consent-tracked), merchant responses (manual/CSV/transcript ingestion), raw answers, AI-extracted observations (with human review), evidence candidates, approved merchant findings, campaign-level analysis (n-of-m aggregates, never bare percentages), a Part A evidence *proposal* preview (stored in `mv.db`, never an authoritative write — export to `knowledge-base/customer-evidence/merchant-voice-candidates/` will be gated to synthetic data only, reviewer-approved, with Workstream A sign-off), and read-only Copilot tools over **approved, non-suppressed, permission-safe findings only** (a new `merchant_finding` citation type resolving to anonymized internal routes, never identity/contact/raw-transcript data).
