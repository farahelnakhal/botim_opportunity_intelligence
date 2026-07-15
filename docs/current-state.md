# Current state — verified 2026-07-15

> Baseline: `main` @ `38dee97` (merge of PR #34). Every claim below was verified
> against code/git, not copied from handoff prompts. Update this file at the end of
> each merged phase.

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
- **Demo mode** (`BOTIM_APP_MODE=demo`; pinned by the deploy Dockerfile): the
  committed synthetic portfolio, visibly labelled; demo records read-only.
- Chat: grounded, cited answers; clarification for vague messages; exactly one
  opportunity draft per genuine new idea; "Demo mode — deterministic grounded output"
  badge under MockProvider; honest unavailable state when copilot is down (no silent
  fallback to the legacy router/scaffold).
- Reports: web-only at `/report/{OPP-nnn|UOPP-…}` (refresh/direct-nav safe). **No PDF
  export exists anywhere.**
- Monitoring: internal-KB events (demo corpus) + user monitoring configs shown as
  intent only ("Configured — awaiting monitoring run"); "Run monitoring now" disabled.

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

- **No live external research.** The only external fetch is the regulator-feed
  monitoring adapter (network-injected, offline-testable). No search API, no page
  retrieval, no research runs.
- **No monitoring runner/scheduler.** `MCFG-` configs are stored intent only.
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
