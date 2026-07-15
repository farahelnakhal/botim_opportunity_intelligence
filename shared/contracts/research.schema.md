# Research runs (Phase R1) — schema v1

Persistence contract for external-research runs. Implementation:
`shared/research/store.py` (runtime SQLite at `RESEARCH_DB_PATH`, default
`runtime/research.db`, gitignored). Read-only HTTP exposure:
`GET /executive-api/research/runs` and `GET /executive-api/research/runs/{id}`.
Changes to this contract are **additive only**.

Phase R1 is storage + read-only display. **Nothing creates runs over HTTP yet**;
run creation/execution arrives with the research runner (Phase R2 — see
`docs/roadmap.md`). Nothing here is authoritative knowledge: candidate evidence
is pending human review and never auto-promotes into `knowledge-base/`.

## ID namespaces

| Prefix | Object | Shape |
|---|---|---|
| `RRUN-` | research run | `RRUN-<12 hex>` |
| `RQRY-` | query within a run | `RQRY-<12 hex>` |
| `RSRC-` | retrieved/recorded source | `RSRC-<12 hex>` |
| `RCAND-` | candidate evidence (claim) | `RCAND-<12 hex>` |

These cannot collide with committed KB ids (`EV-`, `OPP-nnn`, …) or the runtime
`UOPP-`/`MCFG-` namespaces.

## Run lifecycle

```
pending -> running -> complete | partial | failed
pending -> failed                    (setup failure before execution)
```

- `partial` and `failed` **require** a human-readable `error`/reason;
  `complete` must not carry one. Terminal states are immutable.
- `partial` is a first-class honest outcome: successful queries/sources are
  kept, the reason records what did not happen.

## Objects

### Research run
| Field | Type | Notes |
|---|---|---|
| `id` | `RRUN-…` | |
| `title` | string ≤200 | required |
| `objective` | string ≤4000 \| null | free-text overall objective |
| `objectives` | string[] ≤50×500 | structured objective list |
| `profile` | string ≤120 \| null | research-profile name (e.g. a future `sme-financial-product` profile) — a label, not hardcoded behavior |
| `opportunity_ref` | `OPP-nnn` \| `UOPP-…` \| null | optional link to a committed or user opportunity |
| `status` | `pending\|running\|partial\|complete\|failed` | |
| `error` | string ≤1000 \| null | required for `partial`/`failed` |
| `notes` | string ≤4000 \| null | |
| `created_at` / `updated_at` / `started_at` / `completed_at` | UTC ISO-8601 \| null | absent = null, never invented |
| `counts` | `{queries, sources, candidates}` | computed on read |
| `queries` / `sources` / `candidate_evidence` | arrays | detail view only |

### Query
`id`, `run_id`, `objective?`, `query_text` (required), `provider?`,
`status pending|executed|failed`, `error?` (required iff failed),
`result_count?` (recorded, never invented), `created_at`, `executed_at?`.

### Source
`id`, `run_id`, `query_id?` (must belong to the same run),
`canonical_url` (**must pass `shared.source_urls.safe_url` — absolute http(s)
only**), `domain` (derived from the URL), `title?`, `publisher?`, `author?`,
`published_at?`, `retrieved_at?`, `language?`, `excerpt?` (≤2000),
`content_hash?`, `duplicate_of?` (a source in the same run),
`quality_signals` (flat object ≤20 entries of recorded string/number/boolean
signals — recorded observations, never computed here), `created_at`.

### Candidate evidence
`id`, `run_id`, `claim` (required ≤4000), `source_ids` (**non-empty**, each an
`RSRC-` in the same run — a claim without a source is fabrication and is
rejected), `status pending_review|approved|rejected` (starts `pending_review`;
review semantics arrive in Phase R3; even `approved` never means authoritative
Part A evidence), `review_note?`, `contradicts?` (free-text note of what
existing record/claim it contradicts), `created_at`, `updated_at`.

## Traceability guarantee

`candidate_evidence.source_ids → research_sources.query_id → research_queries
→ research_runs`: every claim is traceable to sources, the query that found
them, and the run that executed it. Cross-run references are rejected.

## HTTP (read-only, both `/api/` and `/executive-api/` aliases)

| Route | Returns |
|---|---|
| `GET /research/runs[?status=…&opportunity_ref=…&limit=…]` | `{runs: [run…]}` — summaries with counts, newest first; honest empty list when nothing exists |
| `GET /research/runs/{RRUN-id}` | full run with `queries`, `sources`, `candidate_evidence`; 404 if absent; 400 on malformed id |

No write routes exist in R1. Errors are structured `{error: message}` with no
SQL/paths/fetched content in messages.
