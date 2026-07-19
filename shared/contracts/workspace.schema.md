# Analysis workspace (Phase R5, PR4; scheduled monitoring R6) — schema v5

Persistence + build contract for versioned preliminary analysis workspaces.
Implementation: `shared/workspace/` (`store.py` — runtime SQLite at
`WORKSPACE_DB_PATH`, default `runtime/workspace.db`, gitignored;
`kb_context.py` — bounded deterministic KB context search; `builder.py` —
the build chain) plus the R6 scheduled-monitoring surface (subscriptions,
tick, and `shared/email/` for delivery). Changes to this contract are
**additive only**. Schema history: v1 base · v2 `document_evidence` (R7) ·
v3 monitoring subscriptions + recipients (R6) · v4 recipient confirmation
(R6) · v5 signed unsubscribe (drops the obsolete token-hash column, R6).

Everything a workspace contains is machine-generated **PRELIMINARY**
analysis: never authoritative knowledge, never written to `knowledge-base/`.
Human review attaches to the candidate claims themselves (research store,
`RCAND-`), never to a workspace version — an approval therefore survives
every later refresh. Design rationale: `docs/decision-log.md`, 2026-07-16.

## ID namespace

| Prefix | Object | Shape |
|---|---|---|
| `AWV-` | analysis workspace version | `AWV-<12 hex>` |
| `WSUB-` | monitoring-subscription recipient row (R6) | `WSUB-<12 hex>` |

Cannot collide with any other namespace (`OPP-`, `UOPP-`, `RRUN-`, …).

## Version lifecycle

```
running -> complete | failed
```

- Versions are **append-only**: a refresh creates a new version with a
  per-opportunity incrementing `version` number; terminal versions are
  immutable (attempted writes → 409).
- `failed` **requires** an honest `error`; `complete` must not carry one.
- Readers (chat, GET routes) take the **latest `complete`** version — a
  running or failed build can never corrupt what is being read.
- Retention: builds prune to the newest 10 versions per opportunity.
  Claims and their approvals live in the research store and are unaffected.

## Triggers

`first_analysis | manual_refresh | meaningful_change | stale | monitoring` —
the locked set from the decision log. **An ordinary chat message is not a
trigger**: follow-up questions reuse the latest stored version.

## Version object

| Field | Type | Notes |
|---|---|---|
| `id` | `AWV-…` | |
| `opportunity_id` | `OPP-nnn` \| `UOPP-…` | required |
| `version` | int ≥1 | increments per opportunity |
| `status` | `running\|complete\|failed` | |
| `trigger` | trigger enum | required |
| `question` | string ≤4000 \| null | the question that prompted the build |
| `error` | string ≤1000 \| null | required iff `failed` |
| `research_run_id` | `RRUN-…` \| null | the run this build executed |
| `kb_evidence` | `[{id, title, segment, status, evidence_confidence, match}]` | committed records matched by deterministic keyword overlap |
| `claim_ids` | `RCAND-…[]` | claims extracted by this build (PR3 pipeline; always `pending_review` at birth) |
| `document_evidence` | `[{document_id, filename, chunk_seq, match, excerpt}]` | Phase R7 (schema v2, in-place migration): bounded verbatim excerpts from the user's uploaded documents that matched this build — USER-PROVIDED data, snapshotted on the version (kept even if the file is later deleted) |
| `preliminary_score` | object \| null | see below |
| `gaps` | string[] | honest record of everything that was skipped/missing |
| `provenance` | object \| null | `{question, trigger, queries, kb_record_ids, research_run_id, search_provider, extraction_model, builder}` |
| `created_at` / `completed_at` | UTC ISO-8601 \| null | |

### Preliminary score

Computed by the **real engine** (`opportunity_engine.scoring.evaluate`) on a
synthetic all-assumption scorecard (every dimension score 3, `assumption:
true`) — the same pattern as `generate.py`: because all 17 dimensions are
assumptions, the engine's own cap applies and a workspace build can never
come out above "promising". Fields: `preliminary: true`, `engine`,
`composite`, `assumption_count`, `assumption_capped`, `max_classification`,
`classification` ("promising (preliminary, unvalidated)"), `confidence`
("low"), `basis_note`, `inputs_found {kb_evidence_records,
accepted_candidate_claims}` (context counts — they never change the score).

## Build chain (`builder.build_workspace`)

1. **KB context** — deterministic keyword search over committed evidence
   records (read-only). No match → an honest gap.
1b. **Uploaded documents** (Phase R7) — deterministic chunk retrieval over
   the opportunity's attached documents (`shared/documents/`); matching
   excerpts are quoted verbatim and snapshotted. No documents / no match →
   honest gaps.
2. **External research** — a bounded research run (existing R2 runner) from
   queries derived ONLY from the opportunity's own fields + the question
   (never a hardcoded market/product). No search provider → gap, never
   fabricated sources. Failed/partial runs are recorded as gaps.
3. **Claim extraction** — the PR3 pipeline (model proposes, deterministic
   verification disposes); accepted claims land `pending_review`,
   `origin='extracted'`. No model (`BOTIM_LLM_API_KEY`) → gap.
4. **Preliminary score** — as above, via the real engine.

Missing providers and empty results produce a **complete version with
gaps**; the version fails only when the build itself breaks (with the
reason stored and the error re-raised).

`compare_versions(older, newer)` returns the deterministic diff
(`composite_delta`, `new_claim_ids`, `removed_claim_ids`, `new_gaps`,
`resolved_gaps`) — the seed for R6 change notifications. R6 **reuses** it and
layers a normalized-claim-**text** comparison on top for materiality (see
below); it never forks a second diff.

## Scheduled monitoring + email-on-change (Phase R6)

A saved chat may opt into scheduled re-runs. Persistence (workspace store):

- `workspace_subscriptions` — one row per chat: `opportunity_id` (PK),
  `owner_user_id` (required), `enabled` (**derived**: true iff ≥1 recipient is
  enabled AND confirmed), `cadence_hours` (bounded
  `MONITORING_MIN_CADENCE_HOURS`..720, default `MONITORING_DEFAULT_CADENCE_HOURS`),
  `last_run_at`, `next_run_at`, `last_notified_version`, `last_outcome`.
- `workspace_subscription_recipients` — N per chat (`WSUB-` id):
  `recipient_user_id` (a `USER-`), `recipient_email` (the account's own
  registered address — **no free-text recipients**), `confirmed`,
  `confirm_token_hash` (SHA-256; raw token 48h-expiring,
  `MONITORING_CONFIRM_TTL_HOURS`), `enabled`, `opted_in_at`. Unique on
  `(opportunity_id, recipient_user_id)`.

**Double opt-in:** a new/changed/unconfirmed recipient is stored unconfirmed;
the opt-in route emails a confirm link; **no mail (including the tick's) goes
out until confirmed** — enforced by the derived `enabled` flag AND an
`EXISTS(confirmed recipient)` guard in the tick's due-selection query.

**Unsubscribe:** deterministic signed token
`"<WSUB-id>.<base64url(HMAC-SHA256(MONITORING_UNSUBSCRIBE_SIGNING_KEY, WSUB-id))>"`,
verified by recomputation — stateless, stable across every email, nothing
stored per row. Rotating the key invalidates all previously-emailed links.

**Outcomes** recorded in `last_outcome`: run results `built`/`emailed`/
`no_change`/`partial_no_email`/`email_unavailable`/`skipped_in_progress`/
`skipped_quota`/`failed`, and dormancy reasons `dormant_pending_confirmation`/
`dormant_all_unsubscribed`/`dormant_no_recipients`.

### Tick (external cron)

`POST /api/monitoring/tick` — **shared-secret** (`MONITORING_TICK_TOKEN`;
`X-Monitoring-Token` header, constant-time; unset → 404; mismatch → 401), no
user session. For each due subscription (`enabled AND next_run_at<=now AND
EXISTS confirmed recipient`, capped by `MONITORING_TICK_MAX_CHATS`): atomic
claim-and-advance (idempotent under an at-least-once cron), skip if a version
is already `running`, quota check
(`QUOTA_MONITORING_WORKSPACE_RUN_PER_DAY` × active subscriptions), then the
**same** `build_workspace(..., trigger='monitoring')`. Returns
`{claimed, <outcome counts>, chats:[{opportunity_id, outcome}]}`.

### Materiality + email

Baseline = `last_notified_version` (fallback: previous complete version; the
first complete version only seeds the baseline). **Material** iff a genuinely
new claim *text* (normalized; dedupes `RCAND-` id churn) OR
`|composite_delta| ≥ 0.01`. Degraded runs (research failed/partial/skipped
markers) and gap-only changes are never material. Only a material change
emails confirmed recipients (`shared/email/monitoring_digest.py`; overclaim
guard aborts rather than sending an overclaim); everything else records an
honest outcome and sends nothing. Delivery uses the pure-stdlib
`shared/email/` SMTP seam (`SMTP_*`; unconfigured → honest no-op).

### Monitoring HTTP (owner-scoped like the rest of `/user-opportunities`)

| Route | Behavior |
|---|---|
| `GET /user-opportunities/{UOPP-id}/workspace/monitoring` | `{subscription, quota}` — subscription (recipients with `confirmed`/`pending_confirmation`, never token hashes) + scaled quota `{used, limit, remaining}`. Requires sign-in enabled (else 403) |
| `POST …/workspace/monitoring` | the signed-in user opts THEMSELVES in `{cadence_hours?}`; sends a confirmation email; returns `{subscription, confirmation:{required,email_sent,sent_to,note}}`. Re-POST while pending resends |
| `DELETE …/workspace/monitoring` | the signed-in user opts themselves out |
| `GET /api/monitoring/confirm?token=` | login-free double-opt-in confirmation (HTML page); 404 unknown/used, 410 expired |
| `GET /api/monitoring/unsubscribe?token=` | login-free unsubscribe via the signed token (HTML page); 404 on an invalid/rotated-key token |

## HTTP (executive API; `/api/` and `/executive-api/` aliases)

| Route | Behavior |
|---|---|
| `POST /user-opportunities/{UOPP-id}/workspace/refresh` | run the chain; body `{question?}`. First build → trigger `first_analysis`, later → `manual_refresh`. Providers resolved from the environment; missing ones become gaps. 201 with the finished version (enriched view below) |
| `GET /user-opportunities/{UOPP-id}/workspace` | latest complete version, or `{workspace: null, note}` when none exists (honest empty) |
| `GET /user-opportunities/{UOPP-id}/workspace/versions` | version summaries, newest first |
| `GET /user-opportunities/{UOPP-id}/workspace/diff` | deterministic `compare_versions` of the two newest **complete** versions; `{diff: null, note}` when fewer than two exist (PR4-UI) |

The enriched view adds `is_stale` (deterministic: `completed_at` older than
`WORKSPACE_STALE_HOURS`, default 24) and `claims` — each claim id resolved
to its **current** review status from the research store.

## Copilot integration (additive to conversation-api.schema.md)

- New read-only tool `get_analysis_workspace(opportunity_ref)` returns the
  latest complete version with claims resolved to their current review
  status. Reading **never** triggers a build.
- Grounding presents it as "PRELIMINARY ANALYSIS WORKSPACE …" facts:
  approved claims are cited as `research_candidate` citations; pending
  claims are explicitly labelled "PENDING HUMAN REVIEW"; gaps become
  unknowns; a stale workspace emits a deterministic warning; confidence for
  the workspace source is always "low"; the no-decision banner applies.
- The orchestrator prepends this read when a saved user opportunity is
  selected as context or referenced by `UOPP-` id in the message.

No PUT/DELETE routes exist. Errors are structured `{error: message}` with
no SQL/paths/keys in messages.
