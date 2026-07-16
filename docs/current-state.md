# Current state — verified 2026-07-15

> Baseline: `main` @ `38dee97` (merge of PR #34) + Phase R1. Every claim below was
> verified against code/git, not copied from handoff prompts. Update this file at
> the end of each merged phase.

## Verified completed work

| Phase | Commit / PR | Delivered (verified) |
|---|---|---|
| Workstreams A/B/C + engines | pre-#29 history | KB record formats, 17-dim scoring engine (assumption caps), evidence conformance, monitoring engine + regulator adapter, impact workflow, decision journal |
| React UI + read-only API | PRs #29–#30 | executive-ui/web, adapter, serialize, static fallback site |
| Merchant Voice | PR #31 (`df2bc82`) | Full synthetic-only research-to-evidence pipeline (campaigns → findings → Part A proposals), 12 read-only copilot tools |
| Phases 0–1 | `8b7b0fe` | Navigation/page state, clickable evidence/updates, DetailDrawer, Reports & Briefs naming, honest attachment UI, dark mode, frontend tests |
| Phase 2 | `7188bf8` | copilot-backend is the canonical chat backend; `/executive-api` vs `/copilot-api` separation; grounded `new_opportunity_analysis`; conversation ids; citations; honest unavailable |
| Phase 3 | `553f04d`, PR #32 | Intent-classification fixes (no junk stubs), stale-conversation recovery, scroll/composer/mobile fixes, safe Markdown, demo-mode disclosure badge, start.sh process lifecycle, legacy-route gating, proxy hardening |
| Phase 4 | `1bcff92`, PR #33 | Evidence provenance (SRC ids, source-log join) + deterministic freshness (`shared/freshness.py`), safe source links (`shared/source_urls.py` + `safeUrl.ts`), monitoring summary/detail + `GET /monitoring/summary/{id}`, clickable predictions, web reports `/report/OPP-nnn` + `GET /brief/{id}` |
| Phases 5–7 | `4b2655c`, PR #34 | `BOTIM_APP_MODE=normal\|demo\|test` (backend authoritative; normal hides demo corpus), SQLite user opportunities (`UOPP-`, draft→saved→archived, restart-safe), user reports `/report/UOPP-…`, copilot `context.user_opportunity`, monitoring configs (`MCFG-`, pause/resume/remove, honest never-run) |
| Phase R1 | PR #36 (`fd054d8`) | Research platform core: `shared/research/store.py` (runtime SQLite at `RESEARCH_DB_PATH`; `RRUN-/RQRY-/RSRC-/RCAND-` namespaces; pending→running→complete\|partial\|failed with mandatory reasons; candidate claims require ≥1 same-run source; http(s)-only source URLs; absent metadata stays null), contract `shared/contracts/research.schema.md`, read-only `GET /research/runs[/{id}]` |
| Phase R2 | PR #37 (`83687d0`) | Bounded research execution: provider seam (`providers.py`, Brave adapter via `RESEARCH_SEARCH_PROVIDER`/`BRAVE_SEARCH_API_KEY`; mock injectable in tests only, never via env), safe bounded retrieval (`retrieval.py`: http(s)-only, 500 KB cap, content-type allowlist, scripts stripped, injection stored as data), deterministic profiles (`profiles.py`: `generic` + `sme-financial-product`), executor (`runner.py`: dedup by normalized URL + content hash, recorded quality signals, honest complete/partial/failed), `POST /research/runs` + `POST /research/runs/{id}/execute` |
| Phase R3 | PR #38 (`364e358`) | Research integration: human-authored candidate claims (`POST …/candidates`, sources must belong to the run) + one-shot review (`POST /research/candidates/{id}/review`, approved ≠ authoritative, no EV ids) + review queue (`GET /research/candidates`); copilot tool `get_external_research` (approved-only) with `external_research_summary` intent, `research_candidate` citations, EXTERNAL-labelled grounding, deterministic stale-source warnings (freshness from publication date only); frontend Research workspace (runs list/create/execute, sources with freshness + safe links, review + claim entry), external-research citation chip, report appendix on both OPP and UOPP reports. Manual claims only — LLM-assisted extraction is a possible later enhancement |
| Phase R4a | PR #39 (`729028c`) | Manual monitoring runner: `POST /user-opportunities/{id}/monitoring/run` executes the MCFG config's topics/keywords/entities through the research platform (bounded, preferred/excluded domains honored) and records `MEVT-` events for genuinely new sources (unique per opportunity+URL, idempotent reruns, grounded in `RSRC-`/`RRUN-`); failures recorded honestly on the config (`error`/`last_error`/failure counter; `last_run_at` never advanced by a failed run); "Run monitoring now" button live with an events list; user-store schema v2 (in-place migration). Still no scheduler — cadence remains intent. Evidence revalidation deferred to R4b |
| Phase R4b | PR #40 (`56cf72e`) | Source revalidation: research-store schema v2 (`source_revalidations`, in-place migration), `revalidate_run` (re-fetch up to 20 non-duplicate sources; append-only `RREV-` outcomes `unchanged/changed/unreachable`; nothing auto-applied), `POST /research/runs/{id}/revalidate`, computed `source_health` on candidates, revalidation badges + "Revalidate sources" button in the Research UI, copilot warning when approved claims cite failed sources |

Handoff corrections found during verification:
- "Removal of fake report recipients" is **mode-gated, not deleted**: demo mode still
  shows `strategy@botim.ai`/`research@botim.ai` with a demo label; normal mode shows
  an honest "not available" note (`web/src/components/panels.tsx`).
- The handoff omitted: the `MCFG-` id namespace, suggested-topics derivation from
  saved fields only, and that mode is exposed via `meta.app_mode` (no dedicated route).

## Visible website behavior today

- **Normal mode** (default): clean empty state, no demo portfolio/identity/recipients;
  create/save/manage user opportunities; grounded chat works against the evidence
  corpus; demo detail routes 404.
- **Demo mode** (`BOTIM_APP_MODE=demo`; opt-in — the deploy image defaults to
  normal since PR1 production cleanup, demo showcases build with
  `--build-arg APP_MODE=demo`): the committed synthetic portfolio, visibly
  labelled; demo records read-only.
- Chat: grounded, cited answers; clarification for vague messages; exactly one
  opportunity draft per genuine new idea; "Demo mode — deterministic grounded output"
  badge under MockProvider; honest unavailable state when copilot is down (no silent
  fallback to the legacy router/scaffold).
- Reports: web-only at `/report/{OPP-nnn|UOPP-…}` (refresh/direct-nav safe). **No PDF
  export exists anywhere.**
- Monitoring: internal-KB events (demo corpus) + user monitoring configs; "Run
  monitoring now" performs one real manual run (R4a) when a search provider is
  configured, recording `MEVT-` events for genuinely new sources — otherwise it
  fails honestly and the config shows the error. Cadence remains stored intent
  (no scheduler).
- Research workspace (sidebar → Research): create/execute runs, review candidate
  claims; approved claims ground chat ("what did the external research find?")
  and appear in report appendices, always labelled external.

## Important routes and environment variables

See `docs/architecture.md` for the full route table. Key env vars:

| Var | Purpose |
|---|---|
| `BOTIM_APP_MODE` | `normal` (default) \| `demo` \| `test`; backend-authoritative |
| `USER_OPPORTUNITIES_DB_PATH` | runtime SQLite (default `runtime/user-opportunities.db`, gitignored) |
| `COPILOT_PROVIDER` | `anthropic` (default, needs `ANTHROPIC_API_KEY`) \| `mock` |
| `COPILOT_UPSTREAM_URL` | fixed proxy destination (default `http://127.0.0.1:8010`) |
| `ENABLE_LEGACY_UNGROUNDED_ROUTES` | opt-in for legacy `/chat` + `/analyze` (default off) |
| `COPILOT_HOST/PORT`, `COPILOT_API_TOKEN`, `COPILOT_MAX_*` | copilot bind/auth/bounds (`copilot-backend/app/config.py`) |
| `EXECUTIVE_API_HOST/PORT`, `COPILOT_READINESS_*`, `*_ENTRYPOINT` | `deploy/start.sh` lifecycle |
| `MV_TOKENS`, `MV_SYNTHETIC_ONLY` | merchant-voice auth / synthetic-only guard |
| `VITE_APP_MODE`, `VITE_EXECUTIVE_API_BASE_URL`, `VITE_COPILOT_API_BASE_URL` | frontend build hints |

## Test suites (file counts at baseline)

copilot-backend 8 · executive-ui/api 5 · executive-ui (adapter/render) 5 · shared 6 ·
merchant-voice 31 · opportunity-intelligence 9 · intelligence-monitoring 3 · impact 2 ·
deploy 1 · frontend Vitest 23 files. Gate: `python3 shared/integration_check.py`
(10 steps). PR #33 reported 1,041 tests green across suites at Phase 4.

## Current limitations (verified)

- **Live research requires operator configuration.** The research platform
  (R1–R3) can create, execute, review, and cite runs, but live execution needs
  `RESEARCH_SEARCH_PROVIDER` + key; otherwise it fails honestly. Claims are
  human-authored from sources (no LLM-assisted extraction); contradiction
  notes are manual (`contradicts` field) — automated KB-contradiction
  detection remains future work; the citation chip is informational (full
  traceability lives in the Research view, not a chip click-through).
- **No monitoring scheduler.** Manual monitoring runs (R4a) and source
  revalidation (R4b) work; cadence remains stored intent. Revalidation
  covers research-platform sources — committed KB evidence records still
  rely on Phase 4 freshness display only (re-checking KB source URLs and
  proposing impact updates remains future/H1 work).
- **No PDF export** (web reports only).
- **No real attachment processing** (file names noted only, disclosed in the UI).
- **No authentication/tenancy** on the executive API; copilot has optional bearer
  token; merchant-voice auth is prototype-grade (static token map, synthetic-only).
- **No deterministic calculation tools** exposed to chat (beyond the engines' own
  committed models).
- User-opportunity records are single-tenant/local (one SQLite file, no users).
- Merchant Voice has no researcher-facing frontend.
- Copilot `context.user_opportunity` hardening against adversarial payloads was
  deferred to the hardening milestone (noted in PR #34).

## Known defects

None currently tracked. (PR #34's deferred-risk list is captured above and in
`docs/roadmap.md`; no open bug reports in the repo.)

## Next recommended work

**Reusable live external research** (see `docs/roadmap.md` for the full order and
acceptance criteria). Confirmed from the repository: it unblocks the monitoring
runner (MCFG configs already wait on it), evidence revalidation, and the first
validation case's market/competitor sizing — and its natural seams (provider
abstraction, freshness/source-url modules, candidate-evidence pattern) already exist.
