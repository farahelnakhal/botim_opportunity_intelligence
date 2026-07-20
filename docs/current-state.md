# Current state — verified 2026-07-15

> Baseline: `main` @ `38dee97` (merge of PR #34) + Phase R1. Every claim below was
> verified against code/git, not copied from handoff prompts. Update this file at
> the end of each merged phase.
>
> **Before citing any capability as shipped, see
> [`docs/capability-vs-claim.md`](capability-vs-claim.md)** — it reconciles
> aspirational/methodology language in `product-context.md` / `MASTER_PROMPT.md`
> / `WORKSTREAMS.md` / the research guides against what the runtime code
> actually does (with the code cited). When they disagree, the code wins.

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
| PR3 | PR #46 (`94dfda9`) | LLM claim extraction with source verification: research-store schema v3 (`candidate_evidence.origin`/`extraction_meta`, in-place migration), `shared/research/extract.py` (model proposes → deterministic validation: exact-substring supporting quote, quantitative-claim guard, single-source-universal guard; injected page directives can't become claims), `POST /research/runs/{id}/extract`. Accepted claims are `pending_review` `origin='extracted'` — never shortcut human review, never touch the committed KB |
| R5 PR4 | this branch | Versioned analysis workspace: `shared/workspace/` (`store.py` — `AWV-` append-only versions in runtime SQLite at `WORKSPACE_DB_PATH`, running→complete\|failed, latest-complete reads, deterministic staleness via `WORKSPACE_STALE_HOURS`, prune-to-last-10, `compare_versions` diff; `kb_context.py` — deterministic KB keyword search; `builder.py` — KB context → bounded research run from the opportunity's OWN fields → PR3 extraction → preliminary score via the REAL engine on an all-assumption card, capped at "promising"; missing providers → honest gaps on a complete version), routes `POST /user-opportunities/{id}/workspace/refresh` + `GET …/workspace[/versions]` (claims resolved to CURRENT review status — approvals live on claims, survive refreshes), copilot `get_analysis_workspace` tool + PRELIMINARY-labelled grounding (approved cited, pending explicitly labelled, stale warning), orchestrator reads the workspace for any selected/`UOPP-`-referenced opportunity, contract `shared/contracts/workspace.schema.md`. Reading never triggers a build |
| R5 PR4-UI | this branch | Analysis tab for saved user opportunities (`WorkspacePanel.tsx` + `lib/workspaceApi.ts`): "Run first analysis"/"Refresh analysis" with an honest running state (names the real chain steps, no fake per-step completion), PRELIMINARY badges on every machine number with the engine cap stated, approved claims separated from pending-review ones, gaps always listed, related KB evidence, version history, provenance, stale banner; new `GET /user-opportunities/{id}/workspace/diff` (deterministic `compare_versions` of the two newest complete versions — the seed of R6 notifications), rendered as the "changes since previous version" surface |
| R8a | this branch | Sign-in + tenancy core: `auth_store.py` (PBKDF2-HMAC-SHA256 600k-iteration password hashes, sessions stored as SHA-256 token hashes, in-process login lockout, `USER-` namespace, `AUTH_DB_PATH`), `POST /auth/register\|login\|logout` + `GET /auth/me` (mode probe, sessionless), HttpOnly SameSite=Lax cookie (Secure outside test mode / `AUTH_COOKIE_SECURE`), `BOTIM_AUTH_MODE` opt-in enforcement (default off; unknown values fail closed) gating every `/api` route + the copilot proxy, user-store v3 `owner_user_id` (creator-owned records; legacy NULL rows shared; foreign records → indistinguishable 404), `AUTH_ALLOW_REGISTRATION`, frontend `AuthGate` (sign-in/register screen, session bar + sign-out, honest unreachable state). Password reset deferred to R6 email (stated in UI). R8b (chat/research scoping, quotas) remains |
| R8b | this branch | Tenancy completion: copilot conversations owner-scoped (proxy forwards the session identity as `X-Botim-User`, never client-supplied; honored only with `COPILOT_TRUST_PROXY_USER=1`, set in the single-container image; foreign conversations → `conversation_not_found`; legacy NULL rows shared), research-store schema v4 `research_runs.owner_user_id` (create/list/detail/execute/candidates/review/revalidate/extract owner-guarded with indistinguishable 404s; candidate listings follow run ownership), per-user daily quotas in the auth DB (`check_quota`; defaults chat 200, research_execute/research_extract/workspace_refresh/monitoring_run 25; `QUOTA_*_PER_DAY` overrides; honest 429 with the limit stated; no quota when auth is off). Deferred: MV static-token replacement, grounding-side external-research filter, password reset (R6) |
| R6 | this branch | Scheduled monitoring re-run + email-on-change. Per-chat `workspace_subscriptions` + a multi-recipient child table in the workspace store (schema v3→v5) with **double opt-in** (hashed, 48h `MONITORING_CONFIRM_TTL_HOURS` confirm tokens; no mail until confirmed, enforced at the persistence layer) and **deterministic signed unsubscribe links** (`MONITORING_UNSUBSCRIBE_SIGNING_KEY`, RFC 8058-style, nothing stored per row). External-cron tick `POST /api/monitoring/tick` (`.github/workflows/monitoring-tick.yml`, hourly; shared secret `MONITORING_TICK_TOKEN`; idempotent claim-and-advance; skip-if-running) calls the SAME `build_workspace` orchestrator with `trigger='monitoring'`. `shared/email/` (pure-stdlib `smtplib` seam, MockEmailSender in tests, honest unconfigured no-op) + `monitoring_digest.py` email confirmed recipients ONLY on a **material change** (normalized-claim-**text** diff layered on `compare_versions` so `RCAND-` id churn can't spam; composite ≥0.01; degraded/no-change/failed send nothing, recorded honestly; overclaim guard fails safe). Per-user daily quota scaled by active subscriptions (`QUOTA_MONITORING_WORKSPACE_RUN_PER_DAY`, surfaced as `quota_used`/`quota_limit`); Analysis-tab opt-in/cadence/quota UI; `render.yaml` declares all R6 env. Nothing writes `knowledge-base/`; changed items stay preliminary. HuggingFace deploy path removed (Render only) |
| R7 | this branch | Document attachments: `shared/documents/` (extract .txt/.md/.csv/.docx via stdlib — PDF is an honest 415; 2 MB cap; deterministic paragraph chunking + transparent keyword-overlap retrieval as the scoped-RAG seam; `DOC-` store at `DOCUMENTS_DB_PATH` with cascade-deleted chunks), routes `POST/GET /user-opportunities/{id}/documents` (base64 upload, synchronous honest extraction, `document_upload` quota) + `DELETE /documents/{DOC-id}` (real deletion, double ownership guard), workspace builder step 1b snapshots verbatim excerpts (`document_evidence`, workspace schema v2) with `document_ids` provenance, copilot grounds excerpts as USER-PROVIDED data-never-instructions, frontend Files tab (upload/list/delete, honest errors) + workspace excerpt section, contract `shared/contracts/documents.schema.md`. Open: PDF (dependency decision), document→claim extraction |

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
  fallback to the legacy router/scaffold). **PR2 baseline synthesis:** with a live
  provider, answers are decision-oriented synthesis (executive-summary → …→
  recommendation structure for strategic questions; grounding facts are private
  context, never echoed; no "## Evidence used" id appendix — citations travel
  structured). Under MockProvider the answer remains the deterministic facts block
  by design, disclosed by the badge and the PR1 startup warning.
- Reports: web-only at `/report/{OPP-nnn|UOPP-…}` (refresh/direct-nav safe). **No PDF
  export exists anywhere.**
- Monitoring: internal-KB events (demo corpus) + user monitoring configs; "Run
  monitoring now" performs one real manual run (R4a) when a search provider is
  configured, recording `MEVT-` events for genuinely new sources — otherwise it
  fails honestly and the config shows the error. The `MCFG-` cadence remains
  stored intent (no runner). Separately, a saved chat's Analysis tab can opt
  into **scheduled workspace monitoring** (R6): confirm your account email, pick
  a cadence, and the external-cron tick re-runs the analysis and emails you only
  when a material change is found.
- Research workspace (sidebar → Research): create/execute runs, review candidate
  claims; approved claims ground chat ("what did the external research find?")
  and appear in report appendices, always labelled external.

## Important routes and environment variables

See `docs/architecture.md` for the full route table. Key env vars:

| Var | Purpose |
|---|---|
| `BOTIM_APP_MODE` | `normal` (default) \| `demo` \| `test`; backend-authoritative |
| `USER_OPPORTUNITIES_DB_PATH` | runtime SQLite (default `runtime/user-opportunities.db`, gitignored) |
| `WORKSPACE_DB_PATH` / `WORKSPACE_STALE_HOURS` | analysis-workspace runtime SQLite (default `runtime/workspace.db`) and staleness threshold (default 24h) |
| `MONITORING_TICK_TOKEN` / `MONITORING_TICK_MAX_CHATS` | R6 tick shared secret (unset → `POST /api/monitoring/tick` 404s, scheduler off) / max chats processed per tick (default 25) |
| `MONITORING_MIN_CADENCE_HOURS` / `MONITORING_DEFAULT_CADENCE_HOURS` | R6 per-chat cadence floor (default 4) / default when opt-in omits it (default 6); ceiling fixed at 720 |
| `MONITORING_CONFIRM_TTL_HOURS` | R6 double-opt-in confirm-link lifetime (default 48h; expired → 410, re-opt-in reissues) |
| `MONITORING_UNSUBSCRIBE_SIGNING_KEY` | R6 HMAC key for signed unsubscribe links (unset → links can't be minted; a material run records `email_unavailable`, never sends). **Rotating it dead-links every already-emailed unsubscribe link.** |
| `MONITORING_PUBLIC_BASE_URL` | R6 absolute base for links in emails (unset → derived from the request `Host` header) |
| `QUOTA_MONITORING_WORKSPACE_RUN_PER_DAY` | R6 scheduled-run daily cap **per active subscription** (default 6; effective limit = base × active subs) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_STARTTLS` / `SMTP_SSL` | R6 outbound email relay (pure-stdlib `smtplib`, provider-neutral; unset `SMTP_HOST`/`SMTP_FROM` → honest "not sent (no SMTP)" no-op, never a crash) |
| `DOCUMENTS_DB_PATH` | R7 uploaded-document runtime SQLite (default `runtime/documents.db`) |
| `QUOTA_CHAT_PER_DAY`, `QUOTA_RESEARCH_EXECUTE_PER_DAY`, `QUOTA_RESEARCH_EXTRACT_PER_DAY`, `QUOTA_WORKSPACE_REFRESH_PER_DAY`, `QUOTA_MONITORING_RUN_PER_DAY` / `COPILOT_TRUST_PROXY_USER` | R8b per-user daily quotas (required-auth mode only) / copilot honors the proxy's identity header (single-container deploy sets it) |
| `BOTIM_AUTH_MODE` / `AUTH_DB_PATH` / `AUTH_ALLOW_REGISTRATION` / `AUTH_COOKIE_SECURE` | R8a auth: enforcement (`off` default; anything unrecognized fails closed to required), accounts/sessions SQLite (default `runtime/auth.db`), registration switch (default open), cookie Secure flag override |
| `BOTIM_LLM_API_KEY` / `BOTIM_LLM_MODEL` / `BOTIM_LLM_BASE_URL` / `BOTIM_LLM_PROVIDER` | **canonical LLM config** (all services). Provider inferred: base_url→openai_compatible; claude-*/sk-ant→anthropic; no key→unconfigured (honest errors). Mock only when explicitly set (or defaulted by start.sh in demo/test mode) |
| `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `COPILOT_MODEL`, `COPILOT_PROVIDER` | optional **aliases** resolving into the canonical values (Groq alias implies the Groq endpoint) |
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

Phase R6 adds test files `shared/tests/{test_workspace_subscriptions,test_email_sender,test_monitoring_digest}.py`
and `executive-ui/api/tests/test_workspace_monitoring_routes.py`, plus render-blueprint
and WorkspacePanel cases. Full-suite tallies at the R6 tip: shared **228**,
executive-ui/api **158**, executive-ui adapter/render 44, deploy **23**,
copilot-backend 131, frontend Vitest **156**. The integration gate's last two
steps (`executive-ui/api/tests`, `shared/tests`) exercise the new tick/email/
digest/subscription paths — not just pre-existing ones.

## Current limitations (verified)

- **Live research requires operator configuration.** The research platform
  (R1–R3) can create, execute, review, and cite runs, but live execution needs
  `RESEARCH_SEARCH_PROVIDER` + key; otherwise it fails honestly. Claims are
  human-authored from sources (no LLM-assisted extraction); contradiction
  notes are manual (`contradicts` field) — automated KB-contradiction
  detection remains future work; the citation chip is informational (full
  traceability lives in the Research view, not a chip click-through).
- **Scheduled *workspace* monitoring exists (R6); other schedulers do not.**
  Saved chats can opt into scheduled analysis re-runs + email-on-change via the
  external-cron tick (R6). Separately, the `MCFG-` monitoring config (R4a, which
  mints `MEVT-` events) is still **manual-run only** — its cadence remains
  stored intent with no runner. Source revalidation (R4b) covers
  research-platform sources; committed KB evidence records still rely on Phase 4
  freshness display only (re-checking KB source URLs and proposing impact
  updates remains future/H1 work).
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

## Post-audit hardening (branch `claude/repo-audit-integration-8jab15`)

A live end-to-end audit (frontend proxy → executive API → copilot → live Groq
model) confirmed the stack works; three fixes landed from it:

1. **Chat resilience under provider rate limits.** The copilot's tool loop
   re-sent the full ~33-tool catalog on every iteration, and retryable
   provider errors (429/5xx/timeout) failed the whole turn with no retry — so
   the default Groq free tier (12k tokens/min) tripped a fatal 429 on
   multi-iteration questions. Now the tool catalog is offered only on the
   first model pass (later passes fold in results and write prose), and
   `Orchestrator._generate_with_retry` retries *retryable* errors with a
   bounded, capped backoff (honoring `Retry-After` when sent, capped by
   `COPILOT_PROVIDER_RETRY_MAX_S`, default 4s; `COPILOT_PROVIDER_MAX_RETRIES`,
   default 2). Non-retryable errors still fail immediately and honestly.
   Verified live: the previously-failing portfolio question now completes in
   two calls (~7.6k tokens) with proper executive-summary synthesis.
2. **Generic research profile is genuinely generic.** `profiles.py` no longer
   applies a single UAE/SME/corporate-card default to every profile; each
   profile declares its own `defaults` (`generic` = none, whitespace collapsed;
   `sme-financial-product` keeps its documented validation-case defaults).
3. **Monitoring runner UI copy corrected.** The status note claimed manual
   runs "will become available"; the R4a runner already ships, so the note now
   states manual runs work (given a search provider) and that only the
   scheduler is still absent.

## Known defects

None currently tracked. (PR #34's deferred-risk list is captured above and in
`docs/roadmap.md`; no open bug reports in the repo.)

## Next recommended work

**Reusable live external research** (see `docs/roadmap.md` for the full order and
acceptance criteria). Confirmed from the repository: it unblocks the monitoring
runner (MCFG configs already wait on it), evidence revalidation, and the first
validation case's market/competitor sizing — and its natural seams (provider
abstraction, freshness/source-url modules, candidate-evidence pattern) already exist.
