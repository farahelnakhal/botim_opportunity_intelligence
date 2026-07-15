# User opportunities, application modes, and monitoring configuration (Phases 5–7)

## Application modes (Phase 5)

One backend field is the source of truth:

| variable | values | default |
|---|---|---|
| `BOTIM_APP_MODE` | `normal` \| `demo` \| `test` | `normal` |

The effective mode is reported in `GET /executive-api/overview` →
`meta.app_mode`. `VITE_APP_MODE` is a **build-time hint only**, used solely to
decide whether the bundled demo seed may serve as an offline fallback when the
API is unreachable — it never overrides the backend. An invalid
`BOTIM_APP_MODE` resolves to `normal` (the safe default), never to demo data;
no silent fallback between modes exists.

- **normal** (default; production-oriented): the overview returns no demo
  opportunities/briefs/predictions/feed items; demo detail endpoints
  (`/brief/OPP-…`, `/opportunities/OPP-…`, `/commercial/OPP-…`,
  `/monitoring/summary/EVT-…`) return 404; the reference evidence corpus
  stays available to the grounded copilot; the UI shows a clean empty state
  with no invented identity or email recipients.
- **demo**: serves the committed synthetic corpus, visibly labelled ("Demo
  data" badge, labelled sidebar/home sections, demo persona). Demo records
  are read-only: the user-opportunity API only ever operates on `UOPP-` ids.
- **test**: like demo for read-model content, for deterministic test setup;
  point `USER_OPPORTUNITIES_DB_PATH` at a temp path so production user data
  is never touched and fixtures never leak into normal mode.

How to start: `BOTIM_APP_MODE=demo python3 executive-ui/api/server.py` (demo
showcase — also what `executive-ui/deploy/Dockerfile` pins), or leave the
variable unset for normal mode. Demo frontend builds set `VITE_APP_MODE=demo`.

## Runtime user-opportunity store (Phase 6)

| variable | default |
|---|---|
| `USER_OPPORTUNITIES_DB_PATH` | `runtime/user-opportunities.db` (repo root; gitignored) |

SQLite with a versioned schema (`meta.schema_version`, currently **1**),
initialized on first use; future migrations run per-version inside the
initialization transaction. Foreign keys ON, parameterized SQL only, UTC ISO
timestamps, bounded field sizes (title ≤ 200, text fields ≤ 4000, arrays
≤ 50 × 500 chars). The committed Git knowledge base is never written.

### Record

`id` (`UOPP-<12 hex>` — cannot collide with committed `OPP-nnn`), `title`,
`status` (= lifecycle state: `draft → saved → archived`; restore: `archived →
saved`), five text fields (`product_definition`, `problem_statement`,
`target_segment`, `customer_description`, `value_proposition`), four string
arrays (`assumptions`, `risks`, `unknowns`, `next_actions`),
`source_conversation_id`, `created_from_analysis`, `monitoring_enabled`,
`version` (optimistic lock — a stale `version` in PATCH returns 409),
`created_at`, `updated_at`, `archived_at`, `source: "user"`.

A draft/saved record is never presented as validated or scored.

### Endpoints (all under `/executive-api`, structured `{"error": …}` on failure)

| method + path | behavior |
|---|---|
| `GET /user-opportunities[?include_archived=1]` | list (archived hidden by default) |
| `POST /user-opportunities` | create (`title` required; status `draft`/`saved`) → 201 |
| `GET /user-opportunities/{id}` | fetch |
| `PATCH /user-opportunities/{id}` | edit fields; `draft→saved` promotion; optional `version` lock; archived records are read-only (409) |
| `POST /user-opportunities/{id}/archive` | archive (non-destructive default) |
| `POST /user-opportunities/{id}/restore` | archived → saved |
| `DELETE /user-opportunities/{id}` | **deletion policy**: drafts delete permanently; saved → 409 (archive instead); archived deletes only with `?confirm=archived` |
| `GET /executive-api/brief/UOPP-…` | web-report read model (`record_type: "user_opportunity"`), honest partial sections, no fabricated scores/evidence |

Unknown fields, malformed ids, oversized values, and illegal transitions are
rejected with 400/409; SQL errors are never exposed.

### localStorage migration (documented decision)

Pre-Phase-6 browser-only "generated" stubs had fabricated shape and no
persisted fields, so the frontend performs a **one-time reset**: the old
`botim.generated` key is discarded and `botim.migration.v1` marks the reset.
Conversations (`botim.conversations`) and copilot conversation-id mappings
(`botim.copilotConversationIds`) are preserved and, on save, remapped from the
stub id to the persisted `UOPP-` id. Nothing is silently persisted twice.

### Copilot context (additive)

`POST /copilot-api/chat` accepts `context.user_opportunity` (id + the fields
above, bounded/allowlisted server-side). The orchestrator grounds them as a
clearly labelled `USER-PROVIDED OPPORTUNITY DRAFT … NOT repository evidence`
block, adds a matching entry to `assumptions`, and remembers the context for
follow-ups. Copilot output is never written into the persisted record without
an explicit user save.

## Monitoring configuration (Phase 7)

One configuration per user opportunity (`monitoring_configs`, id
`MCFG-<12 hex>`, FK → user opportunity, cascade on delete): `enabled`,
`status` (`not_configured` \| `active` \| `paused` \| `error` \|
`never_run`), `cadence` (`manual` \| `daily` \| `weekly` \| `monthly` — no
cron expressions), `topics`/`keywords`/`entities`/`source_categories`/
`preferred_domains`/`excluded_domains` (bounded arrays), `geographic_scope`,
`language`, `notes`, `last_error`, `consecutive_failure_count`,
`last_run_at`, `next_run_at`, timestamps.

**Honesty rule:** no monitoring runner exists yet, so an enabled
configuration that has never run is stored/presented as `never_run` —
"Configured — awaiting monitoring run" — never as actively monitoring; the
cadence is intended configuration (no scheduler); "Run monitoring now" is
disabled with "Manual run will become available when live research is
enabled". No monitoring events are fabricated; existing events remain
read-only. Future live-research runs can link events via the user opportunity
id + configuration id.

| method + path | behavior |
|---|---|
| `GET /user-opportunities/{id}/monitoring` | config, or `{status:"not_configured"}` plus editable `suggested_topics` derived only from the saved fields (never auto-enabled) |
| `PUT /user-opportunities/{id}/monitoring` | create/replace config (validated; archived opportunities → 409) |
| `POST …/monitoring/pause` / `…/monitoring/resume` | enabled flag + honest status transitions |
| `DELETE …/monitoring` | remove configuration |

`GET /executive-api/monitoring` additionally returns `user_monitoring:
{configs, note}` in every mode; in normal mode the demo/KB event stream is
hidden and `summary_state` reflects only real user configurations. Committed
demo/reference opportunities can never be configured through these endpoints
(UOPP-only routes).

## Intentionally deferred

Live internet research and the monitoring runner, automatic source
refetching, PDF export, deterministic financial calculations, real file
uploads, production authentication and tenancy, automatic promotion of user
drafts into the Git knowledge base, authoritative evidence writes, automated
score changes.

## Manual monitoring runs and events (Phase R4a)

No scheduler exists — cadence remains **intended** configuration. Two routes
were added (both under `/executive-api/user-opportunities/{UOPP-id}/monitoring`):

| Route | Behavior |
|---|---|
| `POST …/monitoring/run` | Execute ONE manual monitoring run. The config's topics/keywords/entities become bounded queries (max 10) executed through the research platform (`shared/research`) with the config's preferred/excluded domains. Requires an enabled config (409 if paused, 409 if the config has nothing to search, 404 if not configured) and a configured search provider — **no provider ⇒ the run finishes `failed`, the config records `status: error` + `last_error` + an incremented `consecutive_failure_count`, and `last_run_at` is NOT advanced** (a failed run monitored nothing). Success (complete/partial) sets `status: active`, advances `last_run_at`, resets the failure counter, and returns `{run_id, run_status, events_created, new_events, note, config}`. Zero new events is an honest, successful outcome. |
| `GET …/monitoring/events[?limit=…]` | `{events: […]}` newest first. |

**Monitoring event** (`MEVT-<12 hex>`): exactly "a new, non-duplicate source
recorded by a monitoring run" — grounded in its `RSRC-` research source and
traceable via `research_run_id` to the full run. Fields: `id`,
`opportunity_id`, `config_id`, `research_run_id`, `source_id`, `title`,
`canonical_url`, `domain`, `published_at`, `detected_at`. Uniqueness on
`(opportunity_id, canonical_url)` makes reruns idempotent: an already-seen
URL never becomes a second "new" event. No summaries, significance scores,
or tiers are generated — nothing is fabricated.

Runtime store schema is now **v2** (v1 databases migrate in place on first
open; the migration only adds the `monitoring_events` table).
