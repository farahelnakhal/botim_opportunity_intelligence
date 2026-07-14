# merchant-voice-api.schema — v1.4 (Phase 1 + 2 + 3 + 4 + 5: campaigns, guides, participants, responses, CSV/transcript ingestion, consent & deletion, AI-assisted extraction, human review, evidence candidates, approved findings, Part A evidence proposals, synthetic-only export, read-only Copilot query layer)

> **PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY. NOT APPROVED FOR REAL MERCHANT DATA. NOT FOR PRODUCTION USE.**
> Authentication is a static token→role map compared with `hmac.compare_digest` — this is **not** production identity/access management (no user directory, no session revocation, no token rotation, no TLS termination). Real merchant data requires a separate privacy/security review and a hardened deployment before use. All examples in this document use synthetic IDs only (`MVC-TEST-…`, `MVG-TEST-…`, `MVP-TEST-…`, `MVR-TEST-…`).

**Producer:** `merchant-voice/` (stdlib Python HTTP JSON API, port 8020) · **Consumer:** the future Merchant Voice researcher UI (Farah; scheduled after the current Product Discovery frontend is stable — no frontend work is included in this delivery) **and** `copilot-backend/` (read-only, via `app/published_query.py` — see the Copilot integration section below).

This document covers **what Phase 1 + 2 + 3 + 4 + 5 implement**: research campaigns, versioned research guides, pseudonymous participants (identity kept in a separate `identity.db`), manual and CSV-bulk response ingestion, text-only transcript ingestion, deterministic redaction, consent/privacy gating, withdrawal/retention/deletion, AI-assisted extraction of structured pending-review observations, the **human-governed review workflow** (observation review/edit/approve/reject/merge, evidence candidates, immutable approved Merchant Voice findings with deterministic strength bands and campaign-level analysis), a **human-reviewed Part A evidence-proposal workflow** (draft → submit → approve → approve-export → synthetic-only export), and a **read-only query layer** the Product Discovery Copilot uses for grounded, cited answers. **An approved Merchant Voice finding — and an approved Part A evidence proposal — are still NOT authoritative Part A evidence.** Nothing in this service mints an EV ID, writes `knowledge-base/customer-evidence/records/`, promotes anything into Part A, or changes a score, assumption, impact proposal, or monitoring record. Phase 6+ is **not implemented yet** — see the Future Roadmap section at the end.

**The provenance chain this service preserves at every step:** raw merchant response → AI-extracted observation (never authoritative) → human-reviewed observation → evidence candidate → approved Merchant Voice finding → Part A evidence **proposal** (Phase 5, still non-authoritative) → exported synthetic demo candidate *(never Part A evidence)* → authoritative Part A evidence *(a separate, human Workstream A action outside this service, still not built as an automated path — Phase 6+)*.

## Authentication

Every endpoint except `GET /health` requires `Authorization: Bearer <token>`. Tokens map to exactly one role via server configuration (`MV_TOKENS`); comparison is timing-safe (`hmac.compare_digest`). The server **refuses to start** if no tokens are configured.

## Roles

`viewer < researcher < reviewer < admin` (each role includes everything below it unless a rule says otherwise).

## Endpoint authorization matrix (Phase 1 + 2 + 3 + 4 + 5)

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
| `POST /participants`, `PATCH /participants/{id}` | — (no access) | ✅ | ✅ | ✅ |
| `GET /campaigns/{id}/participants`, `GET /participants/{id}` | — (no access) | ✅ | ✅ | ✅ |
| `POST /participants/{id}/withdraw-consent` | — (no access) | ✅ | ✅ | ✅ |
| `POST /participants/{id}/request-deletion` | — (no access) | — | — | ✅ |
| `POST /responses`, `GET /responses/{id}`, `GET /campaigns/{id}/responses` | — (no access) | ✅ | ✅ | ✅ |
| `POST /imports/csv/preview`, `POST /imports/csv/commit` | — (no access) | ✅ | ✅ | ✅ |
| `POST /responses/{id}/transcript`, `GET .../transcript-metadata` | — (no access) | ✅ | ✅ | ✅ |
| `POST /maintenance/expire-retention` | — (no access) | — | — | ✅ |
| `POST /maintenance/retry-transcript-deletions` | — (no access) | — | — | ✅ |
| `POST /responses/{id}/extract` | — (no access) | ✅ | ✅ | ✅ |
| `GET /responses/{id}/extraction-runs`, `GET /extraction-runs/{id}` | — (no access) | ✅ | ✅ | ✅ |
| `GET /review/observations`, `GET /responses/{id}/observations`, `GET /observations/{id}` | — (no access) | ✅ | ✅ | ✅ |
| `PATCH /observations/{id}` (pending_review only) | — (no access) | ✅ | ✅ | ✅ |
| `POST /observations/{id}/approve`, `/reject`, `/merge` | — (no access) | — | ✅ | ✅ |
| `POST /evidence-candidates`, `PATCH .../{id}` (draft only), `.../submit` | — (no access) | ✅ | ✅ | ✅ |
| `GET /evidence-candidates`, `GET .../{id}` | — (no access) | ✅ | ✅ | ✅ |
| `POST /evidence-candidates/{id}/approve`, `/reject` | — (no access) | — | ✅ | ✅ |
| `GET /findings`, `GET /findings/{id}` | ✅ (published-only) | ✅ (all statuses) | ✅ (all statuses) | ✅ (all statuses) |
| `POST /findings/{id}/publish`, `/suppress` | — (no access) | — | ✅ | ✅ |
| `GET /campaigns/{id}/analysis` | ✅ (aggregate counts only) | ✅ (+ sample statements) | ✅ (+ sample statements) | ✅ (+ sample statements) |
| `GET /segments/{id}/findings`, `/opportunities/{id}/findings`, `/assumptions/{id}/findings` | ✅ (published-only) | ✅ (published-only) | ✅ (published-only) | ✅ (published-only) |
| `POST /findings/{id}/part-a-proposals` (generate), `PATCH /part-a-proposals/{id}` (draft only), `.../submit` | — (no access) | ✅ | ✅ | ✅ |
| `GET /part-a-proposals`, `GET .../{id}` | — (no access) | ✅ | ✅ | ✅ |
| `POST /part-a-proposals/{id}/approve`, `/reject`, `/approve-export`, `/export` | — (no access) | — | ✅ | ✅ |
| `GET /published/findings`, `/published/campaigns/{id}`, `/published/segments/{id}`, `/published/opportunities/{id}`, `/published/assumptions/{id}` | ✅ | ✅ | ✅ | ✅ |

**No approval endpoint exists in Phase 3** for observations created by extraction — Phase 4 adds the actual approve/reject/merge actions, all reviewer+.

**Self-approval:** a creator (of a guide, an observation, an evidence candidate, or a Part A evidence proposal — including its separate export approval) cannot approve their own object unless `MV_ALLOW_SELF_APPROVAL=1`, and even then only in synthetic-only mode, with a reason required — every such approval is audited with `self_approval: true` and is never hidden from later reviewers.

**Viewer has no access at all** to Phase 2/3 routes, the review queue, observation editing, evidence-candidate routes, or Part A proposal routes — not a filtered view, a hard `403 forbidden`. Viewer's Phase 4/5 access is published findings, aggregate (no-raw-source) campaign analysis, and the read-only `/published/*` surface.

**No role may create authoritative EV evidence, promote a proposal into Part A, or write `knowledge-base/customer-evidence/records/`** — there is no endpoint in this service that does any of these; the only file-writing action anywhere in Phase 5 is the synthetic-only export into `knowledge-base/customer-evidence/merchant-voice-candidates/` (see below).

## Synthetic-only mode

`MV_SYNTHETIC_ONLY=1` (default). While enabled, every campaign's `data_classification` must be `"synthetic"`; any other value is rejected with `invalid_request`. The same rule applies to merchant identities and participants (Phase 2).

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

## Merchant identity (identity.db — never exposed directly)

Merchant identity is the durable, cross-campaign privacy record: `merchant_identity_id`, `protected_external_reference` (an opaque researcher-assigned reference — never a raw phone/email), `consent_status`, `permitted_use`, `quote_permission`, `ai_processing_permission`, `data_classification`, `retention_expires_at`, `deletion_requested_at`, `deleted_at`, `created_at`/`updated_at`. It lives in a **separate database** (`identity.db`) and has **no direct API endpoint** — it is only ever created (optionally) as a side effect of `POST /participants` (via an inline `merchant_identity` object) or referenced by an existing `merchant_identity_id`. No route returns its fields.

## Participant object (mv.db)

| Field | Req? | Nullable | Type / enum |
|---|---|---|---|
| `participant_id` | required | no | `MVP-...` |
| `merchant_identity_id` | required | no | `MID-...` (identity.db reference only — no identity fields are ever joined in) |
| `campaign_id` | required | no | string |
| `segment_id` | optional | yes | `SEG-...` |
| `industry` / `company_size` / `geography` / `respondent_role` | optional | yes | string |
| `consent_status` | required | no | enum: `granted`, `withdrawn`, `expired`, `pending` |
| `permitted_use` | required | no | enum: `internal_research_only`, `internal_research_and_product_development` |
| `quote_permission` / `ai_processing_permission` | optional | no (default `false`) | bool — **may only narrow, never widen,** the linked identity's grant (`invalid_request` otherwise) |
| `data_classification` | required | no | enum, synthetic-only enforced |
| `retention_expires_at` | optional | yes | ISO8601 |
| `workflow_status` | required | no | enum: `invited` → `enrolled` (auto, on first accepted response) → `completed` (manual) |
| `suppression_status` / `suppression_cause` | required/optional | no/yes | enum `none`\|`suppressed`; cause enum `withdrawn`\|`retention_expired`\|`deletion_request` |
| `created_by` / `created_at` / `updated_at` | required | no | string / ISO8601 |

`GET /campaigns/{id}/participants` excludes suppressed participants by default (the "normal query" exclusion); `GET /participants/{id}` still returns a suppressed record for compliance lookups. A suppressed participant cannot be edited (`PATCH` → `invalid_request`).

## Response object (mv.db)

| Field | Type / enum |
|---|---|
| `response_id` | `MVR-...` |
| `campaign_id` / `participant_id` / `guide_id` / `guide_version` | string / string / string / int |
| `method` | enum, must match the campaign's `method` |
| `ingestion_source` | enum: `manual`, `csv_import` |
| `submitted_at` | ISO8601 |
| `processing_status` | enum: `received`, `eligible_for_ai_processing`, `blocked_for_ai`, `suppressed` (see Consent gate below) |
| `duplicate_status` | enum: `unique`, `duplicate` — duplicates are **flagged, never dropped** |
| `consent_snapshot` | object — a copy of the participant's consent fields at submission time |
| `transcript_status` | enum: `none`, `stored`, `pending_deletion`, `deleted`, `deletion_failed` |
| `answers` | array of raw answer objects (below) |

No response ever becomes evidence directly — Part A proposals (Phase 5, not built) are a separate, human-reviewed step.

## Raw answer object

| Field | Type / enum |
|---|---|
| `answer_id` | `MVA-...` |
| `response_id` / `question_id` | string |
| `original_answer` | string, or `null` if the participant is suppressed or the content has been purged — this is a **read-time visibility rule**, not necessarily physical deletion (see Suppression below) |
| `content_visible` | bool — derived at read time; `false` whenever `original_answer` is `null` |
| `language` | one of `en`, `ar`, `ur`, `hi`, `fr` |
| `is_direct_quote` | bool — a quote may only be cited if this AND the participant's `quote_permission` are both true |
| `redaction_status` | enum: `pending`, `complete`, `failed`, `not_required` |
| `sensitive_data_flags` | array of detected categories (`phone`, `email`, `iban`, `account`, `name`, `entity`) plus `manual_review_required` when present |
| `content_purged` | bool |
| `created_at` | ISO8601 |

## Consent / privacy gate (enforced now; nothing calls a provider yet)

Before any future AI extraction (Phase 3) may process a response, ALL of the following must hold — enforced by `app/consent.py`, testable today even though no provider call exists:
consent is `granted` and not suppressed · retention has not expired · `ai_processing_permission` is `true` · every answer's `redaction_status` is `complete` (a `failed` redaction blocks the whole response as `blocked_for_ai` and never exposes the original text in an error).

## Manual response ingestion

`POST /responses` validates: the campaign is `active`; the participant belongs to the campaign and has valid consent; the guide is `approved`; every `question_id` belongs to that guide version; answer language/length; and duplicate detection — key `(participant_id, question_id, normalized_answer_hash)` — before storing. Redaction runs synchronously on every answer at ingestion time.

## CSV bulk import — `POST /imports/csv/preview` then `POST /imports/csv/commit`

- **Preview writes nothing** to participant/response/answer tables (its only write is a single-use, expiring preview-token bookkeeping row).
- Required columns: `participant_ref`, `question_id`, `answer`. Optional: `submitted_at`, `language`, `respondent_role`, `segment_id`, `quote_permission`, `ai_processing_permission`.
- `participant_ref` must match an **existing** `participant_id` in the campaign — CSV import never creates participants or merchant identities.
- Max size 2 MB, UTF-8 only. A leading `=`, `+`, `-`, or `@` in any cell is neutralized (prefixed with `'`) — defense against spreadsheet formula injection.
- The preview token binds file hash + `campaign_id` + `guide_id` + actor + expiry (default 15 minutes, `MV_CSV_PREVIEW_TTL_S`). Commit re-validates everything from scratch, rejects a changed file or a mismatched/expired/already-used token (`409 conflict`), and writes all rows in **one transaction** (partial failure → nothing is written).
- Row-level errors and duplicates are returned in the response, never silently dropped.

## Transcript ingestion — `POST /responses/{id}/transcript`, `GET .../transcript-metadata`

Text only: `.txt` / `.md` / `.vtt`, max 1 MB, UTF-8, extension+declared content-type must match. The stored filename is generated **only** from the already-validated `response_id` (`{response_id}.{extension}`) — any client-supplied filename is never read or retained. The transcript directory is not web-served (this service has no static file handler). The database stores metadata only (extension, content type, language, size, storage status, speaker map) — transcript text is never returned by any endpoint, logged, or placed in an audit event. Re-`POST` replaces the stored transcript and speaker map (researcher-editable).

## Suppression, withdrawal, retention & deletion

`POST /participants/{id}/withdraw-consent` (researcher+), `POST /participants/{id}/request-deletion` (admin only), and the maintenance sweep `POST /maintenance/expire-retention` (admin only) all funnel through one routine (`suppress_participant`):

- **`withdrawn`**: quote permission removed immediately; raw content is **not** deleted from storage but every read path returns it as suppressed (`original_answer: null`, `content_visible: false`) from that point on.
- **`retention_expired` / `deletion_request`**: raw answer content is purged (`original_answer` set to `null`, `content_purged: true`) and any attached transcript is scheduled for deletion.
- Transcript deletion is **not** claimed atomic with the SQLite commit: the DB transaction (suppress + purge + mark `pending_deletion`) commits first; only then is filesystem deletion attempted. A failure leaves the transcript `pending_deletion`/`deletion_failed` (never claims success) for a later `POST /maintenance/retry-transcript-deletions` (admin only) to retry. No transcript content or file path ever appears in an audit event or error message.
- Every one of these operations is audited (actor/action/object/counts only — never raw content).

## Denominator counts (foundation only — no endpoint yet)

`app/counting.py` computes, per campaign: `invited_count`, `enrolled_count`, `submitted_response_count`, `valid_participant_count`, `included_participant_count`, `excluded_or_suppressed_count` — six explicitly-defined counts, deliberately **not** a single ambiguous `sample_size`. Not yet exposed via an endpoint; campaign-level analysis (Phase 4) will consume these.

## Extraction eligibility (the gate before any provider call)

`POST /responses/{id}/extract` calls **one canonical eligibility function** (`app/eligibility.py`) before it may construct a prompt or call the provider. ALL of the following must hold, or the request fails with the matching error code below and no provider call is made:

campaign method is valid · response exists · participant is not suppressed · `consent_status` is `granted` · `ai_processing_permission` is `true` · retention has not expired · response content is not purged · every relevant answer's `redaction_status` is `complete` · `processing_status` is not `blocked_for_ai`/`suppressed` · transcript status is not `pending_deletion`/`deletion_failed`.

## Provider integration

Uses the same canonical `shared.llm.provider` abstraction as `copilot-backend` — no second provider abstraction. The extraction system prompt and tool schema (`app/extraction_prompt.py`) are never returned by any API endpoint. Live provider calls require `ANTHROPIC_API_KEY`; standard/CI tests use `MockProvider` and make no network call. A Merchant-Voice-specific live-smoke gate (`MV_RUN_LIVE_TESTS=1`, in addition to the API key) keeps any live-model test explicitly opt-in.

**Model input** is limited to: the eligible answers' already-redacted text, the guide question each answers, the campaign's `method`, the allowed observation-type/confidence taxonomy, and the campaign's *own* already-linked `target_segments`/`linked_opportunities`/`linked_assumptions` IDs (link suggestions are validated against this campaign-scoped set only — not the whole repository's identifier space, which this service does not parse). **Never sent:** identity.db content, contact information, raw unredacted text, tokens, this service's configuration, or unrelated repository content. Merchant answer text is explicitly framed to the model as untrusted data, not instructions.

## Observation object

| Field | Type / enum |
|---|---|
| `observation_id` | `MVO-...` |
| `response_id` / `campaign_id` / `participant_id` / `source_answer_id` | string |
| `observation_type` | enum: `pain`, `job_to_be_done`, `behaviour`, `workaround`, `frequency`, `severity`, `payment_rail`, `trust_concern`, `willingness_to_pay_signal`, `switching_barrier`, `concept_reaction`, `objection`, `contradiction`, `rejection_condition`, `adoption_condition`, `follow_up_question` |
| `normalized_statement` | string |
| `source_excerpt` | string — always an exact, normalized substring of the source answer text it was extracted from (never fuzzy-matched; a fabricated excerpt is rejected, not persisted) |
| `is_direct_quote` | bool — true only when `normalized_statement` is materially identical to `source_excerpt` **and** the participant's `quote_permission` is true; otherwise forced `false` with `quote_downgraded` in `sensitivity_flags` |
| `extraction_confidence` | enum: `low`, `medium`, `high` |
| `frequency` | enum (`daily`, `weekly`, `monthly`, `every_order`, `most_transactions`, `twice_monthly`, `recurring`, `rarely`, `once`) or `null` — cleared (never inferred) unless the source excerpt contains explicit frequency language |
| `severity` | enum (`low`, `medium`, `high`) or `null` — cleared unless the source excerpt contains explicit severity-supporting language (monetary loss, delay, missed payment, operational blockage, escalation, inability to complete a task) |
| `current_workaround` / `payment_rail` / `follow_up_question` | string or `null` |
| `linked_segments` / `linked_opportunities` / `linked_assumptions` | string[] — filtered down to the campaign's own linked IDs; anything else is **removed** (never replaced with an invented ID) and flagged `invalid_link_removed` |
| `contradiction_target` | `observation_id` or `null` — must reference an observation from the **same response**; otherwise cleared and flagged `contradiction_target_removed` |
| `sensitivity_flags` | string[] — computed by this service only; the model's own self-reported flags are discarded |
| `workflow_status` | enum: `pending_review`, `approved`, `rejected`, `superseded` — see "Observation review" below |
| `suppression_status` | enum: `active`, `suppressed` — independent of `workflow_status`; set by the Phase 2 suppression cascade, never by a review action |
| `reviewer_notes` | string or `null` — free-text, reviewer-editable while `pending_review` |
| `rejection_reason` | one of the rejection reason codes below, or `null` |
| `reviewed_by` / `reviewed_at` | string / ISO8601, or `null` until approved or rejected |
| `self_approval` | bool — true when the approver was also the creator (only possible with `MV_ALLOW_SELF_APPROVAL=1` in synthetic-only mode) |
| `superseded_by_run_id` | `extraction_run_id` or `null` — set when a rerun superseded this (still-`pending_review`) observation |
| `superseded_by_observation_id` | `observation_id` or `null` — set when a reviewer merge superseded this observation into a canonical one |
| `created_by` / `created_at` / `updated_at` | string / ISO8601 |
| `model_provider` / `model_name` / `extraction_run_id` / `source_hash` | string |

**Willingness-to-pay safeguard:** `willingness_to_pay_signal` requires explicit source support (price/fee acceptance, a trade-off, a prior paid workaround, a deposit/commitment, observed purchase behavior, or an explicit refusal at a stated price). Generic interest phrases ("sounds useful", "good idea", "I like it", "maybe", "could be helpful", "I would try it") are downgraded to `concept_reaction` with a flag — never persisted as willingness to pay.

**Single-response guard:** a statement that reads as a cross-merchant generalization ("merchants generally", "most merchants", "X percent of merchants", ...) is **rejected outright**, not persisted — every observation is about the one response it came from; cross-participant patterns are Phase 4's job.

**Concept-test distinction:** for `concept_test` campaigns, a concept reaction never counts as problem validation and "I would try it" never counts as willingness to pay — the same universal WTP safeguard above already enforces this; `campaign_method` is included with every observation response so a consumer can apply this distinction.

## Extraction run object

| Field | Type / enum |
|---|---|
| `extraction_run_id` | `MER-...` |
| `response_id` / `provider` / `model` / `actor_id` | string |
| `started_at` / `completed_at` | ISO8601 (`completed_at` null while `in_progress`) |
| `status` | enum: `in_progress`, `completed`, `failed` |
| `input_source_hash` | string — hash of the response's redacted content at the time of this run |
| `proposed_count` / `accepted_count` / `rejected_count` | int or `null` (until `completed`) |
| `safe_error_code` | one of the error codes below, or `null` |

**Never stored:** the full provider payload, the hidden system prompt, raw unredacted input, or the model's full reasoning.

**Idempotency & rerun:** `POST /responses/{id}/extract` with no body (or `{"rerun": false}`) returns the existing `completed` run for the response's current redacted content (identified by `input_source_hash`) if one exists — it does not silently create duplicate observations. `{"rerun": true}` always creates a new run and marks every prior still-`pending_review` observation for that response `workflow_status: "superseded"` with `superseded_by_run_id` set to the new run — an already-approved/rejected observation is never touched by a rerun. Superseded observations are never overwritten or deleted.

## Observation review (Phase 4)

`GET /review/observations` lists `pending_review` observations (optionally filtered; suppressed ones excluded by default). Each entry includes only redacted content already covered above, plus (via a separate detail call) the guide question text and transcript metadata (never transcript content) — never identity.db fields, contact info, or unredacted transcript text.

**Editable while `pending_review`** (`PATCH /observations/{id}`): `normalized_statement`, `observation_type`, `is_direct_quote`, `linked_segments`, `linked_opportunities`, `linked_assumptions`, `contradiction_target`, `frequency`, `severity`, `current_workaround`, `payment_rail`, `follow_up_question`, `sensitivity_flags`, `reviewer_notes`.

**Immutable always** (`source_immutable` error if touched): `response_id`, `participant_id`, `campaign_id`, `source_answer_id`, `source_excerpt`, `source_hash`, `extraction_run_id`. A reviewer can never make the excerpt say something the source doesn't.

Every edit **re-runs the same deterministic Phase 3 safeguards** (quote/paraphrase, WTP classification, frequency/severity support, aggregate-language prohibition, link validation) against the edited fields — a reviewer cannot introduce an unsupported claim by editing any more than the model could by extracting one. Editing, approving, or rejecting anything other than a `pending_review` observation fails with `invalid_transition` — approved/rejected observations are never silently changed; a correction requires a new observation via merge/supersession instead.

**Approve** (`POST /observations/{id}/approve`, reviewer+): sets `workflow_status: "approved"`. **Reject** (reviewer+) requires one of the rejection reasons below, sets `workflow_status: "rejected"` — rejected observations are preserved (never deleted) but excluded from candidates/findings/analysis. **Merge** (`POST /observations/{id}/merge`, reviewer+, body `{"duplicate_observation_ids": [...]}`): the target observation in the URL is canonical and untouched; every listed duplicate becomes `workflow_status: "superseded"` with `superseded_by_observation_id` set to the canonical — every source observation remains stored (full provenance, including its own quote, is never lost), and a contradiction can never be merged into the statement it contradicts.

**Rejection reason codes:** `unsupported_by_source`, `fabricated_or_inaccurate`, `duplicate`, `wrong_category`, `privacy_or_consent_issue`, `insufficient_context`, `irrelevant`, `other`.

## Evidence candidate object

| Field | Type / enum |
|---|---|
| `candidate_id` | `MEC-...` |
| `campaign_id` | string — **every linked observation must share this campaign** (Phase 4 candidates never span campaigns; this is how "don't silently combine surveys and interviews" holds structurally) |
| `finding_type` | enum — same taxonomy as `observation_type` |
| `statement` | string — the reviewer-composed candidate statement |
| `segment_id` | string or `null` — inferred from supporting observations' participants if not given explicitly; a genuine mismatch is `incompatible_segment` |
| `linked_opportunities` / `linked_assumptions` | string[] |
| `proposed_evidence_role` | enum: `supporting`, `contradicting`, `contextual` |
| `workflow_status` | enum: `draft`, `pending_review`, `approved`, `rejected`, `superseded` |
| `strength_band` | one of the strength bands below, or `null` until computed |
| `limitations` | string[] |
| `denominator_definition` | string or `null` |
| `included_participant_count` / `support_count` / `contradiction_count` | int — **always computed from the linked observations, never accepted from the caller** ("counts don't match" is structurally impossible) |
| `source_version_hash` | string — hash of every linked observation's (id, workflow_status, suppression_status); `submit`/`approve` recompute and refuse (`stale_source_version`) if anything drifted since the candidate was last saved |
| `created_by` / `created_at` / `updated_at` / `reviewed_by` / `reviewed_at` | string / ISO8601 |
| `rejection_reason` | one of the codes above, or `null` |
| `superseded_by_candidate_id` / `supersedes_candidate_id` | `candidate_id` or `null` |
| `self_approval` | bool |

**candidate_observations** join: `{candidate_id, observation_id, role}` where `role` is `supporting`, `contradicting`, or `contextual`. Every linked observation must be `workflow_status: "approved"` and `suppression_status: "active"` at creation and at every later transition, or the request fails (`observation_not_approved` / `source_suppressed`).

**Candidate creation fails if:** no `supporting` observation is linked (`missing_support`); linked observations span more than one segment without a resolvable common value (`incompatible_segment`); a `concept_test` campaign's `finding_type` is outside `concept_reaction`/`objection`/`adoption_condition`/`rejection_condition`/`willingness_to_pay_signal` (`incompatible_method`); a linked observation isn't approved+active (`observation_not_approved` / `source_suppressed`); or a known approved contradictory observation (one whose `contradiction_target` points at an included supporting observation) is omitted without `contradiction_exclusion_reason` (`contradiction_exclusion_requires_reason` — when provided, the exclusion is recorded in `limitations` and audited, never silent).

**Workflow:** `draft` (create/edit freely) → `submit` → `pending_review` → `approve` (reviewer+, creates the finding below) or `reject` (reviewer+, reason required). Approved candidates are immutable; a correction requires a new candidate, optionally with `supersedes_candidate_id` set — approving it automatically supersedes the prior candidate and its finding.

## Merchant finding object

Created **only** as a side effect of approving a candidate — there is no direct "create finding" endpoint, and a finding is still **not authoritative Part A evidence**.

| Field | Type / enum |
|---|---|
| `finding_id` | `MEF-...` |
| `candidate_id` / `campaign_id` | string |
| `approved_statement` | string — copied from the candidate at approval; never edited afterward |
| `segment_id` / `method` | string — `method` is the campaign's method, preserved on every finding |
| `linked_opportunities` / `linked_assumptions` | string[] |
| `strength_band` | see below |
| `limitations` | string[] |
| `numerator` | int — the candidate's `included_participant_count` |
| `denominator` | int — the campaign's own `included_participant_count` (`app/counting.py`) at approval time |
| `denominator_definition` | string, e.g. "included participants in campaign MVC-TEST-001" |
| `support_count` / `contradiction_count` | int |
| `workflow_status` | enum: `approved`, `superseded` |
| `publication_status` | enum: `unpublished`, `published`, `needs_revalidation`, `suppressed` |
| `approved_by` / `approved_at` | string / ISO8601 — historical, never changed by revalidation |
| `source_version_hash` | string |
| `superseded_by_finding_id` | `finding_id` or `null` |
| `published_at` / `published_by` | string / ISO8601, or `null` |

**Full provenance is always traceable:** finding → candidate → candidate_observations → reviewed observations → source answers → response → participant → guide question → campaign. No merchant identity detail is ever copied into a finding.

**Publish** (`POST /findings/{id}/publish`, reviewer+) verifies: `workflow_status == "approved"`; `publication_status` is not `needs_revalidation` or `suppressed`; every linked observation is still `approved`+`active`; every linked *direct-quote* observation's participant still has `quote_permission` (else `quote_permission_denied`). Publishing never writes to Part A — it only makes the finding eligible for the published query layer (and, in Phase 5, Copilot retrieval). **Suppress** (reviewer+) sets `publication_status: "suppressed"` directly.

## Strength bands (deterministic — the model never assigns these)

`single_signal` (one supporting participant) · `emerging_pattern` (≥2 supporting participants, or ≥3 with notable limitations/segment-method inconsistency) · `repeated_pattern` (≥3 independent supporting participants, consistent segment and method, contradictions don't dominate) · `mixed_pattern` (meaningful support and contradiction coexist) · `contradicted` (contradictions equal or outnumber support) · `insufficient` (no usable support). "Market validated" is never used as a label. See `app/strength.py` for the exact, documented rule order.

## Campaign analysis — `GET /campaigns/{id}/analysis`

Uses only reviewed (`approved`), active (non-suppressed) data. Every aggregate carries its own `numerator`, `denominator`, `denominator_definition`, `campaign_id`, `method`, `segment_id`, and `contradiction_count` — **no bare percentage by default**; prefer "3 of 8 included interviewed merchants in MVC-TEST-001." Results are always grouped by `segment_id` (`segments: {segment_id: {...}}`) with an explicit `grouping_note` — segments are never silently pooled, and a campaign's method is fixed by construction (analysis is always scoped to one campaign). Categories: `recurring_pains`, `recurring_behaviors`, `common_workarounds`, `objections`, `switching_barriers`, `wtp_signals`, `contradictions`, `adoption_conditions`, `rejection_conditions`, plus `unanswered_follow_up_questions` and `findings_by_strength_band`. Viewer receives the same shape with `sample_statements` omitted (aggregate counts only, no raw-ish source text); researcher/reviewer/admin receive up to 5 sample `normalized_statement`s per category.

## Withdrawal & revalidation (integrates with the Phase 2 suppression cascade)

When a participant is withdrawn, retention-expired, or deletion-requested (`app/suppression.py`): every observation of theirs becomes `suppression_status: "suppressed"` (workflow_status is untouched — a rejected/approved review decision remains visible for audit); every **approved** evidence candidate referencing one of those observations has its counts recalculated from the current (post-suppression) state; that recalculation cascades into the candidate's finding — `numerator`/`denominator`/`strength_band` are recomputed and `publication_status` becomes `needs_revalidation` (some valid support remains) or `suppressed` (none does). A published finding is *never* left stale: the published query layer (`GET /findings` for viewer, and the segment/opportunity/assumption lookups for everyone) excludes it immediately. `approved_statement`/`approved_by`/`approved_at` are historical facts and are never rewritten by this cascade — this is the one narrow, explicitly-required exception to "approved findings are immutable," and every recalculation is audited with safe before/after counts (never source content).

## Part A evidence proposal object (Phase 5 — non-authoritative)

A **PROPOSAL** is a human-reviewed draft mapping of an approved+published Merchant Voice finding into the shape Workstream A's Part A evidence-candidate intake expects. It is never itself Part A evidence, never mints an EV ID, and approving one never writes `knowledge-base/customer-evidence/records/`.

| Field | Type / enum |
|---|---|
| `proposal_id` | string (`MEP-…`) |
| `finding_id` | string (`MEF-…`) — the source finding |
| `campaign_id` | string |
| `source_finding_version_hash` | string — a fingerprint of the finding's state (workflow/publication status, counts, strength_band) at generation/last-refresh time; recomputed fresh on every submit/approve/export to detect drift even though `merchant_findings.source_version_hash` itself doesn't change on recalculation |
| `payload` | object — see below |
| `rendered_markdown` | string — human-readable preview, always carries the synthetic banner when `payload.classification == "synthetic"` |
| `workflow_status` | `draft` \| `pending_review` \| `approved` \| `rejected` \| `superseded` |
| `publication_status` | `unpublished` \| `export_approved` \| `needs_revalidation` \| `suppressed` \| `exported_synthetic` — **a separate concept from `workflow_status`**, exactly as with observations/candidates/findings |
| `reviewer` / `reviewed_at` | string, or `null` |
| `rejection_reason` | one of the shared rejection-reason codes, or `null` |
| `created_by` / `created_at` / `updated_at` | string |
| `export_status` | `not_exported` \| `exported` \| `export_failed` |
| `export_path` | string, relative to the repo root (e.g. `knowledge-base/customer-evidence/merchant-voice-candidates/MEP-….md`), or `null` |
| `exported_at` | string, or `null` |
| `superseded_by_proposal_id` | string, or `null` |
| `synthetic_only` | boolean — mirrors the source campaign's `data_classification == "synthetic"` at generation time |
| `needs_revalidation_reason` | string, or `null` — set by the invalidation cascade (never hand-written) |

**`payload` (the proposal's evidence-candidate-shaped mapping):** `proposed_title`, `proposed_evidence_statement` (the finding's own `approved_statement` — the safe, reviewer-authored generalization; never a raw quote), `editor_notes` (the only genuinely free-text field, researcher-editable in draft), `source_type` (`"merchant_voice_research"`), `campaign_method`, `segment_id`, `linked_opportunities`, `linked_assumptions`, `suggested_strength` (copied from the finding's `strength_band` — **never silently relabelled as final Part A evidence strength**), `reviewer_required: true`, `strength_decision_note` (always states "Workstream A decides final evidence strength"), `support_count`, `contradiction_count`, `numerator`, `denominator`, `denominator_definition`, `limitations` (includes an entry for every quote withheld on permission grounds), `provenance` (`finding_id` → `candidate_id` → `campaign_id` → `guide_ids` → per-observation `{observation_id, role, observation_type, response_id, participant_id, source_answer_id, question_id, extraction_run_id}` — pseudonymous participant/response ids only, never a merchant name/company/phone/email/identity.db value, never raw transcript content), `quotes` (only observations that are currently `is_direct_quote`, `approved`+`active`, with `quote_permission` true and consent/retention still valid — otherwise the quote is omitted, a limitation is recorded, and the finding's own approved statement stands in as the safe paraphrase), `contradictory_evidence` (contradicting observations, never dropped), `review_history` (the finding's own audit trail: `action`/`actor_role`/`timestamp` only, never reviewer names beyond role or any content), `classification` (`"synthetic"` or `"live"`, from the campaign's `data_classification`), `authoritative_ev_id` (always `null` — there is no field here that could ever hold a minted EV ID).

**Generation** (`POST /findings/{id}/part-a-proposals`, researcher+) requires the finding to be `workflow_status == "approved"`, `publication_status == "published"` (not `needs_revalidation` or `suppressed`), with every linked observation still consent-valid, retention-valid, and permission-safe. Fails `finding_not_publishable` or `finding_needs_revalidation` otherwise.

**Review workflow:** `draft → pending_review → approved → rejected` (mirrors candidates/observations); `PATCH` only touches `payload.proposed_title`/`payload.editor_notes` on a `draft` — every other field is always server-recomputed, never hand-edited. Approving requires `pending_review` and re-checks the finding's live fingerprint against `source_finding_version_hash` (`proposal_stale` if drifted) and that the proposal hasn't already been cascade-flagged (`source_version_changed` if it has). Self-approval follows the shared rule (`MV_ALLOW_SELF_APPROVAL=1`, synthetic-only, reason required, audited `self_approval: true`). **An approved proposal is immutable** — a later source change produces a new proposal (regenerate) or a superseding one, never an edit of the approved one.

**Export approval is a separate action** (`POST .../approve-export`, reviewer+) from content approval — it moves `publication_status` to `export_approved` and is itself subject to the same self-approval rule.

## Synthetic-only export — `POST /part-a-proposals/{id}/export`

Requires **all** of: the source campaign's `data_classification == "synthetic"`; the finding still `approved`+`published`; the proposal `workflow_status == "approved"`; `publication_status == "export_approved"`; the live fingerprint still matches `source_finding_version_hash` (else `proposal_stale`); caller role reviewer or admin. For any **non-synthetic** campaign, export always returns `non_synthetic_export_forbidden` and lists the future prerequisites: privacy approval, redaction verification, quote-permission verification, human reviewer approval, Workstream A approval, approved production deployment.

The export target is **always** `knowledge-base/customer-evidence/merchant-voice-candidates/` — **never** `knowledge-base/customer-evidence/records/` (the authoritative Part A path). The filename is **always server-generated from the proposal ID** (`{proposal_id}.md`) — there is no path/filename parameter anywhere in the export call, so a caller-supplied path is structurally impossible, not merely rejected. The exported file always opens with the banner:

```
SYNTHETIC DATA — DEMO ONLY
NOT AUTHORITATIVE PART A EVIDENCE
REQUIRES WORKSTREAM A REVIEW
```

and never contains a minted EV ID (`authoritative_ev_id` is always rendered as `null`). Export never writes anywhere else, never touches `knowledge-base/customer-evidence/records/`, and never mints an EV ID or promotes the proposal into Part A.

## Strength bands (deterministic — the model never assigns these)

`single_signal` (one supporting participant) · `emerging_pattern` (≥2 supporting participants, or ≥3 with notable limitations/segment-method inconsistency) · `repeated_pattern` (≥3 independent supporting participants, consistent segment and method, contradictions don't dominate) · `mixed_pattern` (meaningful support and contradiction coexist) · `contradicted` (contradictions equal or outnumber support) · `insufficient` (no usable support). "Market validated" is never used as a label. See `app/strength.py` for the exact, documented rule order. A proposal's `suggested_strength` copies this value verbatim but is explicitly labelled non-authoritative (see above) — Workstream A decides final Part A evidence strength.

## Campaign analysis — `GET /campaigns/{id}/analysis`

Uses only reviewed (`approved`), active (non-suppressed) data. Every aggregate carries its own `numerator`, `denominator`, `denominator_definition`, `campaign_id`, `method`, `segment_id`, and `contradiction_count` — **no bare percentage by default**; prefer "3 of 8 included interviewed merchants in MVC-TEST-001." Results are always grouped by `segment_id` (`segments: {segment_id: {...}}`) with an explicit `grouping_note` — segments are never silently pooled, and a campaign's method is fixed by construction (analysis is always scoped to one campaign). Categories: `recurring_pains`, `recurring_behaviors`, `common_workarounds`, `objections`, `switching_barriers`, `wtp_signals`, `contradictions`, `adoption_conditions`, `rejection_conditions`, plus `unanswered_follow_up_questions` and `findings_by_strength_band`. Viewer receives the same shape with `sample_statements` omitted (aggregate counts only, no raw-ish source text); researcher/reviewer/admin receive up to 5 sample `normalized_statement`s per category.

## Read-only "published" query surface — `GET /published/*` (Phase 5, the same seam Copilot calls into)

`GET /published/findings`, `GET /published/campaigns/{id}` (a campaign summary grouped by finding type, with aggregated limitations), `GET /published/segments/{id}`, `GET /published/opportunities/{id}`, `GET /published/assumptions/{id}` — all roles including viewer. Backed by `app/published_query.py`, which **never opens `identity.db`** and returns only approved+published, non-superseded, consent/retention-valid, permission-safe content — never unreviewed/rejected/suppressed observations, `needs_revalidation` findings, draft proposals, or researcher-only review notes. `copilot-backend/app/mv_tools.py` calls this exact module directly (loaded under the alias `mv_app` to avoid a package-name collision with its own `app` package) against a genuinely read-only SQLite connection (`mode=ro`).

## Withdrawal & revalidation (integrates with the Phase 2 suppression cascade)

When a participant is withdrawn, retention-expired, or deletion-requested (`app/suppression.py`): every observation of theirs becomes `suppression_status: "suppressed"` (workflow_status is untouched — a rejected/approved review decision remains visible for audit); every **approved** evidence candidate referencing one of those observations has its counts recalculated from the current (post-suppression) state; that recalculation cascades into the candidate's finding — `numerator`/`denominator`/`strength_band` are recomputed and `publication_status` becomes `needs_revalidation` (some valid support remains) or `suppressed` (none does). A published finding is *never* left stale: the published query layer (`GET /findings` for viewer, the segment/opportunity/assumption lookups, and `GET /published/*` for everyone) excludes it immediately. `approved_statement`/`approved_by`/`approved_at` are historical facts and are never rewritten by this cascade — this is the one narrow, explicitly-required exception to "approved findings are immutable," and every recalculation is audited with safe before/after counts (never source content).

**Phase 5 extends this one step further** (`app/part_a_proposal.invalidate_for_finding`, called from the same cascade): every non-terminal proposal for a just-recalculated finding is marked `needs_revalidation` (some support remains) or `suppressed` (none does), with `needs_revalidation_reason` recorded; approval and export are both blocked from that point on; a proposal already `exported_synthetic` keeps its `export_status: "exported"` record (audit history is preserved) but its `publication_status` moves off `export_approved`/`exported_synthetic`, so it reads as based on a superseded version. A proposal preview is never silently left stale.

## Errors (Phase 3 + 4 + 5 additions)

Phase 3: `extraction_not_permitted` 403 · `consent_denied` 403 · `ai_processing_denied` 403 · `retention_expired` 403 · `redaction_incomplete` 409 · `response_purged` 409 · `transcript_pending_deletion` 409 · `provider_timeout` 504 · `provider_error` 502 · `invalid_provider_output` 502 · `unsupported_excerpt` 400 · `duplicate_extraction` 409.

Phase 4: `invalid_transition` 409 · `source_immutable` 400 · `self_approval_forbidden` 403 · `observation_not_approved` 409 · `source_suppressed` 409 · `incompatible_segment` 400 · `incompatible_method` 400 · `missing_support` 400 · `stale_source_version` 409 · `candidate_not_reviewable` 409 · `finding_not_publishable` 409 · `finding_needs_revalidation` 409 · `quote_permission_denied` 403 · `consent_invalid` 403 · `contradiction_exclusion_requires_reason` 400.

Phase 5: `proposal_stale` 409 (the finding drifted since this proposal was generated/last approved) · `proposal_not_reviewable` 409 (wrong `workflow_status` for the attempted action) · `proposal_not_exportable` 409 (not approved, or `publication_status != export_approved`) · `non_synthetic_export_forbidden` 403 (with the future-prerequisites list) · `source_version_changed` 409 (already cascade-flagged `needs_revalidation`/`suppressed`) · `export_path_invalid` 400 (defense-in-depth only — unreachable in practice, since the export path is always server-computed from a regex-validated proposal ID) · `not_permitted` 403 · `not_found` 404 · `forbidden` 403 (reused from Phase 4's shared code set).

None of these ever include a provider response body or a stack trace.

## Audit (Phase 3 + 4 + 5)

Audited: extraction requested, eligibility denied (with error code), extraction completed (with proposed/accepted/rejected counts), rerun, supersession (with count); observation edit/approve/reject/merge; candidate create/update/submit/approve/reject/supersede; finding create/publish/suppress/recalculate (with before/after counts); proposal generate/edit/submit/approve/reject/approve_export/export_completed/export_blocked/invalidate. **Never audited:** answer text, transcript text, source excerpt content, review/proposal statement text, the provider payload, the prompt text, token values, or full exported file contents — safe audit fields are limited to IDs, counts, source/version hashes, provider/model label, error codes, the export path *relative to the approved intake folder*, and a `fields_changed` name list (never the changed values) for edits.

## Error shape

```json
{ "schema_version": "1.0", "error": { "code": "invalid_request", "message": "..." } }
```

`error.code` → HTTP status: `invalid_request` 400 · `unauthorized` 401 · `forbidden` 403 · `not_found` 404 · `conflict` 409 · `internal` 500 (see the Phase 3/4 error lists above for feature-specific codes). Messages never contain stack traces, tokens, or secrets.

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

`1.4` (Phase 1 + 2 + 3 + 4 + 5 subset). This document will grow additively as later phases land; existing Phase 1/2/3/4/5 fields will not be renamed or removed without a version bump and cross-workstream agreement.

## Streaming

Not applicable — this is a synchronous CRUD API, not a conversational endpoint.

---

## Future roadmap (NOT implemented — documented for context only, not active)

Phase 6+ is not designed yet. Whatever it turns out to be, it must not be documented here as active until built. What is explicitly **still not implemented** after Phase 5: authoritative Part A evidence-ID minting, promotion of a proposal/candidate/finding into Part A, any write to `knowledge-base/customer-evidence/records/`, automatic outreach to merchants, and any frontend. An approved Merchant Voice finding (Phase 4) and an approved, even exported-synthetic, Part A evidence proposal (Phase 5) are both explicitly **not** authoritative Part A evidence — that step is a separate, human, Workstream A action, and no automated path to it exists in this service.
