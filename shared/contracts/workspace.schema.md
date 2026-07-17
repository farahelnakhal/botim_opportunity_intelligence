# Analysis workspace (Phase R5, PR4) — schema v1

Persistence + build contract for versioned preliminary analysis workspaces.
Implementation: `shared/workspace/` (`store.py` — runtime SQLite at
`WORKSPACE_DB_PATH`, default `runtime/workspace.db`, gitignored;
`kb_context.py` — bounded deterministic KB context search; `builder.py` —
the build chain). Changes to this contract are **additive only**.

Everything a workspace contains is machine-generated **PRELIMINARY**
analysis: never authoritative knowledge, never written to `knowledge-base/`.
Human review attaches to the candidate claims themselves (research store,
`RCAND-`), never to a workspace version — an approval therefore survives
every later refresh. Design rationale: `docs/decision-log.md`, 2026-07-16.

## ID namespace

| Prefix | Object | Shape |
|---|---|---|
| `AWV-` | analysis workspace version | `AWV-<12 hex>` |

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
`resolved_gaps`) — the seed for R6 change notifications.

## HTTP (executive API; `/api/` and `/executive-api/` aliases)

| Route | Behavior |
|---|---|
| `POST /user-opportunities/{UOPP-id}/workspace/refresh` | run the chain; body `{question?}`. First build → trigger `first_analysis`, later → `manual_refresh`. Providers resolved from the environment; missing ones become gaps. 201 with the finished version (enriched view below) |
| `GET /user-opportunities/{UOPP-id}/workspace` | latest complete version, or `{workspace: null, note}` when none exists (honest empty) |
| `GET /user-opportunities/{UOPP-id}/workspace/versions` | version summaries, newest first |

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
