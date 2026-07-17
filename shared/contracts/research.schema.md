# Research runs (Phases R1–R4b, PR3) — schema v3

Persistence + execution contract for external-research runs. Implementation:
`shared/research/` (`store.py` — runtime SQLite at `RESEARCH_DB_PATH`, default
`runtime/research.db`, gitignored; `providers.py` — search-provider seam;
`retrieval.py` — safe bounded page fetch; `profiles.py` — deterministic query
generation; `runner.py` — the executor). Changes to this contract are
**additive only**.

Nothing here is authoritative knowledge: candidate evidence never
auto-promotes into `knowledge-base/`. Human review (Phase R3) moves a
candidate `pending_review -> approved | rejected` exactly once; **approved
still means candidate external research, never Part A evidence — no EV id
exists or is implied.** Claims may be human-authored (R3) or LLM-extracted
with source verification (PR3, `origin='extracted'`) — both start
`pending_review`; machine origin never shortcuts human review.

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

## HTTP (both `/api/` and `/executive-api/` aliases)

| Route | Behavior |
|---|---|
| `GET /research/runs[?status=…&opportunity_ref=…&limit=…]` | `{runs: [run…]}` — summaries with counts, newest first; honest empty list when nothing exists |
| `GET /research/runs/{RRUN-id}` | full run with `queries`, `sources`, `candidate_evidence`; 404 if absent; 400 on malformed id |
| `POST /research/runs` (R2) | create a pending run; body `{title, objective?, objectives?, profile?, context?, queries?, opportunity_ref?, notes?}`. A `profile` pre-plans queries deterministically (`shared/research/profiles.py`; unknown profile → 400 listing available ones); otherwise `queries` (string list) may be supplied. Returns 201 with the full run |
| `POST /research/runs/{RRUN-id}/execute` (R2) | execute pending queries with the configured provider. **No provider configured → the run finishes `failed` with "no search provider configured"** — never fabricated results. Returns the finished run (`complete`/`partial`/`failed` with reasons) |
| `POST /research/runs/{RRUN-id}/candidates` (R3) | record a human-authored claim: `{claim, source_ids[], contradicts?}`; sources must belong to the run; a failed run (no sources) refuses; allowed on finished runs (curation ≠ execution). 201 |
| `POST /research/candidates/{RCAND-id}/review` (R3) | `{action: "approve"\|"reject", note?}` — exactly once; 409 if already reviewed |
| `GET /research/candidates[?status=…&opportunity_ref=…]` (R3) | cross-run candidate listing (review queue / report appendix); rows carry `run_title`, `run_status`, `opportunity_ref` |

GET run detail enriches each source with deterministic freshness
(`freshness_status/reference_date/age_days/reason`) computed from the stored
**publication date only** — automated retrieval time is deliberately excluded
(it is always recent and would mark every source permanently "fresh"); a
source without a publication date is honestly `unknown`.

## Copilot integration (Phase R3, additive to conversation-api.schema.md)

- New read-only tool `get_external_research(opportunity_ref?)` returns
  **approved** candidates only (pending/rejected never ground answers), each
  with its recorded sources + freshness.
- New citation type `research_candidate` (role `external_research`): id =
  `RCAND-…`, target = internal route `/research/runs/{run_id}`, metadata
  `{run_id, run_title, external: true, sources: [{url, title, published_at,
  freshness_status}]}`. Grounded facts are prefixed "EXTERNAL RESEARCH …
  NOT authoritative repository evidence"; stale cited sources produce a
  deterministic warning.

No PUT/DELETE routes exist. Errors are structured `{error: message}` with no
SQL/paths/keys/fetched content in messages.

## Execution rules (Phase R2)

- **Provider seam** (`providers.py`): selected via `RESEARCH_SEARCH_PROVIDER`
  (currently `brave`, requiring `BRAVE_SEARCH_API_KEY` — sent only as a
  request header, never logged/stored/echoed). Unset ⇒ no provider ⇒ honest
  failure. The deterministic `MockSearchProvider` is injectable in code for
  tests but **deliberately not reachable via environment configuration** —
  a deployment can never serve synthetic results as real.
- **Bounded**: per-run caps (default 20 queries, 8 results/query, 12 page
  fetches), 10s timeouts, at most one retry per request, politeness delay
  between fetches, 500 KB page cap (truncation recorded).
- **Safe retrieval** (`retrieval.py`): http(s)-only (`shared.source_urls`),
  text-ish content types only, scripts/styles stripped, fetched text stored
  verbatim as DATA — never interpreted as instructions.
- **Dedup**: normalized-URL (tracking params/fragments stripped) and
  content-hash duplicates are stored with `duplicate_of`, never re-fetched.
- **Quality signals**: recorded observations only (has_title,
  has_publication_date, page_fetched, excerpt_chars, preferred/excluded
  domain flags) — no invented scores; interpretation belongs to review (R3).
- **Honest outcomes**: all queries executed → `complete`; some queries or
  page fetches failed → `partial` with the counts in `error`; nothing
  succeeded → `failed`. Failed pages keep their search-result metadata
  (title/snippet) with `page_fetched: false`.

## Source revalidation (Phase R4b) — schema v2

Research-store schema is now **v2** (v1 databases migrate in place; the
migration only adds `source_revalidations`). A revalidation re-fetches a
source and APPENDS an outcome record — **the source row, candidate claims,
and review decisions are never modified** (propose, never auto-apply):

| Outcome | Meaning |
|---|---|
| `unchanged` | reachable; extracted-content hash matches the stored baseline |
| `changed` | reachable; content differs (or no baseline hash was recorded) |
| `unreachable` | fetch failed, non-200, or unsupported content type |

**Revalidation record** (`RREV-<12 hex>`): `id`, `source_id`, `outcome`,
`http_status?`, `new_content_hash?`, `note?`, `checked_at`.

- `POST /research/runs/{RRUN-id}/revalidate` — re-checks up to 20
  non-duplicate sources (bounded, polite, one retry per fetch); returns the
  refreshed run detail plus `revalidation_summary
  {checked, skipped, unchanged, changed, unreachable}`. Works on finished
  runs (that is the point). Requires no search provider — it is a plain
  re-fetch of already-recorded URLs.
- Run detail attaches `last_revalidation` to each source and a computed
  `source_health` (`ok | changed | unreachable`; worst cited-source outcome;
  never-revalidated counts as `ok` — absence of a check is not a failure) to
  each candidate. Computed at read time, never stored.
- Copilot: `get_external_research` sources carry `check_outcome` +
  `last_checked`; grounding emits a deterministic warning when an approved
  claim's `source_health` is `changed`/`unreachable`. The claim still
  grounds (its approval is untouched) — re-review is a human decision.

## Per-user ownership (Phase R8b) — schema v4

Schema v4 adds `research_runs.owner_user_id` (nullable, in-place idempotent
migration). Under required-auth deployments (`BOTIM_AUTH_MODE`, see
docs/decision-log.md R8a/R8b): runs created via the API carry their
creator's `USER-` id; listings (`GET /research/runs`,
`GET /research/candidates`) show a user their own rows plus legacy
NULL-owner rows; acting on another user's run (detail, execute, candidates,
review, revalidate, extract) answers an **indistinguishable 404**.
Candidates follow their run's ownership. With auth off nothing changes.
Known, documented limitation until grounding-side scoping lands: the
copilot's `get_external_research` tool reads approved candidates without a
per-user filter (approved claims are human-reviewed, clearly-external
research).

## Machine claim extraction (PR3) — schema v3

Schema v3 adds two columns to `candidate_evidence` (v2 databases migrate in
place): `origin` (`human` | `extracted`, default `human`) and
`extraction_meta` (JSON: the model and per-source supporting quotes).

`POST /research/runs/{RRUN-id}/extract` runs LLM-assisted extraction over the
run's recorded source text (`shared/research/extract.py`) and persists
**verified** claims as `pending_review` candidates with `origin='extracted'`.
Needs a configured model (`BOTIM_LLM_API_KEY`; else honest 400). Returns the
run detail plus `extraction_summary {proposed, accepted, rejected:[{reason}],
candidate_ids}`.

Verification is deterministic — the model proposes, validation disposes. A
claim is rejected unless: it cites ≥1 same-run source; each cited source
carries a `supporting_quote` that is an **exact (normalized) substring** of
that source's stored text; every number/percent/currency in the claim also
appears in a supporting quote (`unsupported_quantitative_claim` otherwise);
and a market-wide universal ("all/every/always/...") is backed by ≥2 sources
(`single_source_universal_claim` otherwise). External source text is data,
never instructions — a claim survives only if grounded in a verbatim quote,
so injected directives in a page cannot become an accepted claim. **Machine
origin never shortcuts human review:** every accepted claim is
`pending_review` and nothing is written to the committed knowledge base.
