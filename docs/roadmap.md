# Roadmap — recommended remaining implementation order

> Derived from actual dependencies and code maturity at `main` @ `38dee97`
> (2026-07-15), not from any single external prompt. Re-evaluate at each phase end.
> Each phase follows the workflow in `CLAUDE.md` (plan → implement → proportional
> tests → docs → PR → merge → sync).

## Ordering rationale

The monitoring runner, evidence revalidation, and the SME validation case's
market/competitor research all depend on one missing platform capability: **safe,
persisted, traceable external research**. Everything else (PDF, attachments, auth) is
independent polish or hardening that neither blocks nor is blocked by research.

## Phase R1 — Research platform core (foundations, no live network yet) — ✅ DONE

**Value:** the schema and persistence layer every later research feature reuses.
**Depends on:** nothing new. Reuses `shared/freshness.py`, `shared/source_urls.py`.

- Research-run store (runtime SQLite, same patterns as `user_store.py`): research
  runs (`RR-` or similar new namespace), research plans/objectives, queries, sources,
  candidate evidence records; states `pending/running/partial/complete/failed`.
- Normalized source metadata: title, publisher, author (when available), publication
  date, retrieval timestamp, canonical URL, excerpt, quality signals,
  preferred/blocked domains.
- Contract doc: `shared/contracts/research.schema.md`.
- **Acceptance:** persisted runs survive restart; partial/failed states honest;
  claim→source→run traceability fields exist; zero fabricated fields (absent = null).
- **Exclusions:** no live fetching yet; no UI beyond minimal state display.
- **Risks:** schema churn — keep additive, version the schema like user-opportunities.
- **Delivered:** `shared/research/store.py` + `shared/contracts/research.schema.md`
  + read-only `GET /research/runs[/{id}]`; namespaces `RRUN-/RQRY-/RSRC-/RCAND-`;
  25 new tests (20 store + 5 routes). Acceptance criteria all verified by test.

## Phase R2 — Bounded retrieval + provider adapters (first live capability) — ✅ DONE

> Delivered: `providers.py` (Brave adapter + injectable mock, env-selected,
> keys never logged), `retrieval.py` (safe bounded fetch + text extraction),
> `profiles.py` (`generic` + `sme-financial-product`), `runner.py`
> (dedup, quality signals, honest outcomes), `POST /research/runs[/{id}/execute]`;
> 32 new tests, all offline. **Deferred to R3:** KB-contradiction flagging
> (belongs with claim extraction/review, which R3 owns).

**Value:** actual external evidence for any opportunity; unblocks the SME case's
market sizing / competitor benchmarking.
**Depends on:** R1.

- Provider-adapter seam (search provider(s) + safe page retrieval) with bounded
  execution: timeouts, retries, rate limits, robots/lawful-access posture matching
  `adapter_regulator.py`'s rules; network injectable so all tests run offline.
- Duplicate/near-duplicate detection; source-quality assessment; contradiction
  flagging against existing KB records.
- Objective-based query generation from a research profile; the **first validation
  profile** covers the SME financial-product opportunity (market size, SME
  definitions/segmentation, spending/working-capital behavior, card and non-card
  adoption, competitors intl+regional, features/pricing/revenue/interchange,
  partnership/issuer/program models, underwriting, onboarding/KYB/KYC, limits,
  repayment, fraud, collections, regulation/licensing, journeys, edge cases) — as a
  *profile*, not hardcoded platform behavior.
- External results land as **candidate evidence only** — never silently promoted to
  the committed KB (same boundary as Merchant Voice / monitoring candidates).
- **Acceptance:** a research run for an arbitrary objective produces persisted,
  cited, quality-scored candidate sources with honest partial/failure handling; all
  external content treated as data, never instructions.
- **Risks:** prompt injection via fetched pages (mitigate: existing non-negotiable
  #6 patterns, wordguard-style validation); provider cost/rate control.

## Phase R3 — Research integration (chat, review, reports) — ✅ DONE

**Value:** research becomes usable in the product, not just stored.
**Depends on:** R2.

- Candidate-evidence review UI (approve/reject → still never auto-mints EV ids).
- Chat integration: copilot can cite research-run sources (new citation type,
  additive to `conversation-api.schema.md`), clearly labelled external + freshness.
- Reports include a sources appendix from research runs.
- **Acceptance:** claim-to-source traceability visible end-to-end; internal vs
  external evidence visually distinct; stale external sources flagged.
- **Delivered:** claim entry + one-shot review + review-queue routes; copilot
  `get_external_research` tool / `external_research_summary` intent /
  `research_candidate` citations with stale warnings; Research workspace UI;
  external-research appendix on OPP and UOPP reports. **Still open (moved to
  H1/backlog):** automated KB-contradiction detection (manual `contradicts`
  notes exist), LLM-assisted claim extraction, citation-chip click-through to
  the run detail.

## Phase R4 — Monitoring runner (R4a ✅) + source revalidation (R4b ✅) — DONE

**Value:** existing `MCFG-` configs stop being intent-only; freshness becomes
actionable.
**Depends on:** R2 (retrieval) — this is why monitoring execution comes after
research, despite the UI existing first.

- Manual "Run monitoring now" first (the button already exists, disabled); scheduled
  cadences only after manual runs are trustworthy.
- Monitoring events link to run + config ids (fields already prepared); no
  fabricated events; failures recorded on the config (`last_error`, failure count —
  fields already exist).
- Evidence revalidation: re-check stale sources, propose (never auto-apply) updates.
- **Acceptance:** a configured UOPP can be run manually and produces real, cited
  events or an honest empty/failed result.
- **R4a delivered:** manual runner (`executive-ui/api/monitoring_runner.py`)
  reusing the research platform; `MEVT-` events grounded in `RSRC-` sources with
  idempotent URL dedup; honest error/failure-counter discipline on the config;
  run + events routes; frontend Run button + events list; user-store schema v2.
- **R4b delivered:** source revalidation for research-platform sources —
  append-only `RREV-` re-check history (`unchanged/changed/unreachable`),
  `POST /research/runs/{id}/revalidate`, computed candidate `source_health`,
  Research-UI badges/button, copilot warnings on failed sources; nothing is
  ever auto-applied. **Remaining/moved:** re-checking committed KB evidence
  source URLs (would propose impact updates — belongs with H1 or a dedicated
  KB-maintenance phase) and any scheduler discussion (only after manual runs
  prove trustworthy in real use).

## Phase R5 — Chat-orchestrated analysis workspace (the priority feature)

> Full design + rationale: `docs/decision-log.md` 2026-07-16 "Versioned
> preliminary analysis workspace". This is the current top priority.

**Value:** asking a strategic question runs the customer-intel →
opportunity-intel → scoring chain once, produces a persisted **preliminary
analysis workspace**, and the copilot answers from it (sources + logic);
follow-ups reuse the stored workspace cheaply.
**Depends on:** PR3 (claim extraction) first.

Ships as a sequence of focused PRs:
- ✅ **PR3 — claim extraction (DONE, PR #46):** Merchant-Voice-grade source-verified extraction
  turning research/document text into `pending_review` candidate claims
  (exact-substring source verification, quantitative-claim safeguards,
  single-source claims never market-wide, provenance). No orchestration yet.
- ✅ **PR4 — workspace store + orchestrator (DONE, this branch):** versioned per-chat workspace
  (new runtime store, sibling of user/research stores), snapshotted with
  first-class per-version provenance; orchestrator composes existing engines;
  **preliminary score via the real 17-dim engine on a synthetic scorecard**
  (never an LLM guess); trigger model (first / manual refresh / meaningful
  change / stale / monitoring); follow-ups read the latest complete version;
  approvals attach to claims, inherited across versions; per-run cost/timeout
  caps; retention policy. Graceful degradation when search/LLM unavailable.
- ✅ **PR4-UI (DONE, this branch):** the Analysis tab on saved user
  opportunities — honest "running the chain" state (real step names, no fake
  per-step completion), PRELIMINARY badges on all machine numbers with the
  engine cap stated, approved-vs-pending claim separation, gaps always
  listed, version history, provenance, stale banner, and the diff surface
  (`GET …/workspace/diff`, `compare_versions` of the two newest complete
  versions — the same diff R6 will email).
- **Acceptance:** the critical test — "Analyse the value proposition of SME
  cards for UAE SMEs" from a fresh account — produces a coherent workspace-
  backed analysis distinguishing confirmed / preliminary / assumed / unknown,
  with a recommendation and next steps; follow-ups don't re-run the chain.

## Phase R6 — Scheduled monitoring re-run + email-on-change — ✅ DONE (this branch)

**Depends on:** R5 (re-run the chain), R8 (recipients need identity), an
always-on scheduler, and email infrastructure.
- Per-saved-chat re-run on a configurable cadence; snapshot + diff the
  workspace; email the delta of changed numbers/predictions to opted-in
  recipients; changed items stay preliminary until reviewed.
- **Delivered (PR6a–d, decision-log 2026-07-19):** per-chat
  `workspace_subscriptions` + multi-recipient child table (workspace-store
  schema v5) with **double-opt-in** confirmation and **deterministic signed
  unsubscribe** links; external-cron tick `POST /api/monitoring/tick`
  (`.github/workflows/monitoring-tick.yml`, hourly, shared-secret, idempotent
  claim-and-advance, skip-if-running) calling the same `build_workspace`
  orchestrator with `trigger='monitoring'`; `shared/email/` pure-stdlib SMTP
  seam + `monitoring_digest.py` emailing confirmed recipients **only on a
  material change** (normalized-claim-text diff over `compare_versions`,
  composite ≥0.01; degraded/no-change/failed send nothing; overclaim guard);
  per-user quota scaled by active subscriptions; Analysis-tab opt-in/cadence/
  quota UI; all env declared in `render.yaml`. Nothing writes `knowledge-base/`.
- **Gotchas (decided, per decision-log):** the free tier sleeps → **external
  GitHub Actions cron** (not an in-process scheduler); email is **stdlib
  `smtplib`** against an operator SMTP relay (no SDK); throttling via the R8b
  quota mechanism; concurrency handled by claim-and-advance + skip-if-running.
- **Deferred to backlog (not R6):** chat-sharing/multi-recipient teammate flow
  (schema already supports N recipients), `List-Unsubscribe` one-click headers,
  HTML email bodies, and password reset (now unblocked by the email seam).
- **Known tradeoffs — intentional for now, revisit deliberately (not defects):**
  - *Tick is not wall-clock-bounded.* `MONITORING_TICK_MAX_CHATS` caps the chat
    *count* per tick but not total *time* (each build runs live research + LLM).
    The cron curl has a `--max-time` ceiling on the trigger side; the endpoint
    itself does not abort a long backlog. Deciding the in-handler behavior
    (abort mid-backlog vs. finish the current chat vs. warn-only) is a real
    design call, deferred rather than made silently.
  - *Confirmation email is sent synchronously in the opt-in request.* "Turn on
    monitoring" blocks the HTTP response for the SMTP round-trip (≤15s timeout).
    Fine on the threading server (doesn't block other requests); moving to an
    async/queued send is a deliberate future choice, not a drive-by change.
  - *Quota is consumed on attempt, not on delivery.* A build that runs then
    fails to email still counts against `monitoring_workspace_run` — so a chat
    stuck in `email_send_failed` burns its daily quota retrying. Intentional
    (an attempt is real work); revisit if it proves noisy in practice.

## Phase R7 — Attachments + internal-document ingestion

**Depends on:** PR3, R5; best after R8 (documents are user-private).
- ✅ **DONE (this branch):** upload (.txt/.md/.csv/.docx, 2 MB cap, base64
  JSON) → stdlib extraction (PDF = honest 415, see decision-log) →
  deterministic chunking + transparent lexical retrieval (embedding seam
  ready) → verbatim excerpts snapshotted into workspace versions
  (schema v2 `document_evidence`) and grounded in chat as USER-PROVIDED
  data-never-instructions; Files tab with upload/list/permanent-delete;
  ownership + `document_upload` quota (R8 policies). **Open:** PDF support
  (needs a dependency decision), document-driven claim extraction into the
  research store (candidates from documents, not just excerpts).

## Phase R8 — Authentication + tenancy (sign-in)

**Depends on:** nothing hard; **gates R6 and R7** (email recipients and
private documents must be scoped to a user).
- ✅ **R8a (DONE, this branch):** email+password accounts (PBKDF2, stdlib),
  hashed session tokens in an HttpOnly cookie, `/auth/*` routes, opt-in
  enforcement via `BOTIM_AUTH_MODE` (default off; typos fail closed), all
  `/api` routes + copilot proxy gated under required mode, per-user
  ownership of user opportunities (legacy NULL-owner rows stay shared),
  `AUTH_ALLOW_REGISTRATION` switch, frontend sign-in gate + session bar.
  Design: decision-log 2026-07-17. Password reset needs R6 email — honest
  UI note until then.
- ✅ **R8b (DONE, this branch):** conversation ownership in copilot-backend
  (session-validated identity forwarded as `X-Botim-User` by the proxy,
  honored only with `COPILOT_TRUST_PROXY_USER=1`; foreign conversations =
  `conversation_not_found`), research-run ownership (store schema v4;
  create/list/detail/execute/candidates/review/revalidate/extract all
  scoped; legacy NULL-owner rows shared), per-user daily quotas
  (`quota_events` in the auth DB; chat 200/day, research execute / extract /
  workspace refresh / monitoring run 25/day; `QUOTA_*_PER_DAY` overrides;
  honest 429). **Still open (small):** merchant-voice static-token
  replacement (standalone service, not exposed through the proxy),
  grounding-side per-user filter for `get_external_research` (approved
  claims are human-reviewed external research), password reset once R6
  email exists.

## Phase C1 — Deterministic calculations — ✅ DONE

**Value:** transparent market-sizing / unit-economics math for briefs and the SME
case's deck. Independent of R-phases; can run in parallel after R1.

- Server-side deterministic calculators (inputs, formula, outputs all shown);
  no LLM arithmetic; results embeddable in reports/chat with full working shown.
- **Acceptance:** same inputs → same outputs; every number traceable to inputs.
- **Delivered (decision-log 2026-07-20 "C1 deterministic calculators"):**
  `shared/calculators/` — a pure typed-step engine (self-consistency check;
  F/E/A provenance with worst-of label propagation; raw-vs-display rounding
  split; honest never/undefined) with **9 calculators** (`market_sizing`
  top-down TAM/SAM/SOM + bottom-up, `growth_projection`, `implied_cagr`,
  `adoption_forecast`, `unit_contribution`, `breakeven`, `payback_period`,
  `payments_take` with a not-gross-MDR / not-an-issuer guard) + a `CALC-`
  owner-scoped store (re-derivable: envelope + `calculator_version` + inputs);
  executive API `GET /calculators`, `POST /calculators/{name}[/compute]`,
  `GET/DELETE /calculators/results`; copilot `run_calculator`/`list_calculators`
  tools + `deterministic_calculation` intent + grounding + a wordguard
  numeric-fidelity guard (the model narrates the tool's numbers, never
  computes); Calculators UI panel; contract `calculators.schema.md`. The C2
  `source_id` seam is reserved. Reports embed a saved calculation's shown
  working via the same envelope; PDF export of it remains **P1**.

## Phase P1 — Executive outputs (PDF export, answer orchestration polish)

**Depends on:** nothing hard; more valuable after R3 (reports carry research).
- PDF export of web reports (server-rendered; no client-only hacks).
- First-answer orchestration improvements in chat.

## Phase H1 — Hardening milestone (the deferred full sweep)

**Depends on:** whenever the above stabilize; explicitly owed from PR #34.
- Adversarial tests for copilot `context.user_opportunity` and for workspace/
  document ingestion (prompt injection from uploaded/fetched content).
- Full combined test matrix, browser/e2e sweeps across modes, persistence/restart,
  service-failure, mobile, dark mode, citation integrity, research partial/failed
  states, security/trust-boundary tests.
- (Auth/tenancy and attachments are now first-class phases R8/R7, no longer
  deferred here.)

## Capability-vs-claim build-out (planned 2026-07-20)

> Committed build-out of the gaps in `docs/capability-vs-claim.md`. Roadmap-
> scale (each phase ≈ an R1–R8-sized effort). Approved **one phase at a time**;
> **R9a is the foundation everything else builds on** and is fully specified
> below — the rest are sketches to be deepened in turn (same cadence as R6).
> Claim #4 ("auto-update models/data") produced **no phase**: it was a
> mis-wording of an already-shipped behavior and a deliberate non-goal (the
> read-only-KB + human-approval invariant stands). Decisions locked in the
> 2026-07-20 decision-log entries.

### Phase R9a — Social-listening source adapters + source tiering (foundation) — SPEC

**Value:** first-party voice-of-customer evidence (app-store reviews, Reddit)
beyond generic web search, feeding the existing candidate-evidence pipeline;
plus the shared **source-tier/provenance** layer that C2's "verified sources"
also needs.
**Depends on:** R1–R3 (research store, provider seam, candidate review); reuses
`shared/research/providers.py`, `retrieval.py`, `freshness.py`, `source_urls.py`.
**Blocked on:** the Merchant-Voice-style **privacy/security review** before any
LIVE ingestion of real (non-synthetic) content (decision log 2026-07-20).
> ⚠️ **OPEN non-code deliverable — NOT done (as of 2026-07-20):** the human
> privacy/security review of ingesting real Reddit / App Store content has
> **not** been performed. The `RESEARCH_ALLOW_LIVE_SOCIAL` env gate (PR9a-3)
> only *enforces* that decision fail-closed — it is **not** the decision, and
> its existence must never be read as the review being complete. Flipping the
> flag before this item is closed (by the product owner) is a policy breach,
> not just an ops toggle. Close-out belongs with H2 (PII/ToS hardening) or an
> explicit sign-off, whichever comes first.
**Ships as (approved 2026-07-20):** PR9a-1 (source-tier registry) → PR9a-2
(Apple App Store adapter + provider registry) → PR9a-3 (Reddit adapter +
privacy gate) → PR9a-4 (multi-language querying + docs). Reviewed one PR at a
time, R6 cadence.

- **Two new provider adapters behind the existing seam** (no new architecture,
  no scraping aggregator):
  - **Apple App Store customer-reviews RSS** — public, per-app/per-country, no
    auth; bounded/polite like the Brave adapter.
  - **Reddit** — official API (OAuth key, rate-limited); keyed, ToS/cost
    accepted as an ops decision, injectable in tests.
  - **Explicitly out of scope** (decision log): Google Play reviews, X,
    Instagram, TikTok, Facebook (no clean API / ToS-hostile), and
    WhatsApp/Telegram (private, consent-gated — belongs to Merchant Voice).
- **Source-tier/provenance layer** on the research store: each source tagged
  **T1** (govt/regulator/official statistics) · **T2** (industry/analyst) ·
  **T3** (reputable press) · **T4** (general web/forums/social) from a
  **human-curated registry** (domain/publisher → tier); the tier is **never
  LLM-inferred**. Reused by C2.
- **Network injectable / offline-testable** exactly like the Brave adapter and
  `adapter_regulator.py`; live use is an explicit ops opt-in
  (`RESEARCH_SEARCH_PROVIDER`-style) AND gated behind the privacy review.
- **Multi-language querying (querying only)** — issue/localize search terms per
  configured language: **Arabic + English first-class, Hindi + Urdu second,
  Malayalam + Tagalog deferred** (behind config, off by default); results tagged
  with the query language. **Not** source-content translation (that is R9c).
- Output is **candidate evidence only** (existing review pipeline); external
  content stays **data, never instructions**.

**Acceptance:**
- Apple-RSS and Reddit adapters return persisted, cited, **tier-labelled**
  candidate sources with honest partial/failure states; **all tests offline**
  (injected fetch), no live key required.
- Source tier is stored, surfaced on candidates, and registry-driven/auditable.
- No live PII-bearing ingestion path is reachable until the privacy/security
  gate passes (enforced like the Merchant Voice synthetic-only guard).
**Risks:** Reddit ToS/rate/cost; **PII/privacy** (why the review gates it);
prompt-injection surface grows (mitigated by data-never-instructions + H2);
tier-registry curation burden; Apple RSS shape changes.
**Exclusions:** no Play/X/IG/TikTok/FB/WhatsApp/Telegram; no aggregator; no
non-English source-content handling (that is R9c). Multi-language **querying**
is in R9a (above) — the earlier standalone "R9b" sketch is folded in and
dropped (reconciled 2026-07-20).

### Phase R9c — Non-English source-content handling — SKETCH (deferred)
**Value:** fetch/store/ground non-English source *text*. **Scope (separate,
not bundled):** translation + making the evidence/wordguard/grounding pipeline
handle non-English (preserve original, mark translations as derived, never let
a translation fabricate a claim); Malayalam/Tagalog as stretch. Scoped only
after R9a/b prove out.

### Phase C1 — Deterministic calculators — ✅ DONE
Prerequisite for C2, now built (see the C1 section earlier in this file and the
2026-07-20 decision-log entry). C2 builds on `shared/calculators/` (the
`market_sizing` calculator + the reserved `source_id` input seam).

### Phase C2 — Verified-source market sizing (TAM/SAM/SOM) — SKETCH
**Value:** traceable TAM/SAM/SOM for the SME case. **Depends on:** C1 +
R9a source-tier layer. **"Verified" =** ≥2 independent **T1/T2** sources
agreeing within a **conservative (tight) tolerance** band, else flagged
low-confidence (decision to be logged with C2; starting tight so disagreeing
sources are never quietly treated as agreeing). Figures are **extracted** from
sources (PR3 exact-substring discipline), **never computed/estimated by the
LLM**; the C1 calculator derives TAM→SAM→SOM via shown formulas, every input
traced to an `RSRC-` id. Results are **candidate/preliminary**, human-reviewed,
never auto-written to committed scores. **Risks:** sizing figures often
single-source/paywalled → frequent honest low-confidence; tolerance tuning.

### Phase R10 — Evidence-gap-driven research-question generation — SKETCH
**Value:** turn "weakest links" into targeted next questions. **Gap signals:**
fewest approved evidence records; assumption-capped scorecard dimensions;
contradictory evidence; stale load-bearing evidence (>180d); open
`REQ-`/evidence-gap items (`impact/gaps`). **Gate:** questions are **proposals
only** — LLM-drafted, taxonomy-validated → **human reviewer approves/edits the
set** → only then attached to a guide/campaign. **No auto-send to a real
merchant.** Answers flow into the existing candidate→review pipeline; never
auto-update models. **Depends on:** the gap/assumption engine + Merchant Voice;
benefits from R9 but not blocked by it.

### Phase P1 — PDF export — (existing phase above)
Confirmed not built; web reports only. Architecturally independent — recommend
sequencing **last** (a brief is more valuable once C2/R9 add real data), but it
is not blocked and can slot in anytime.

### Phase H2 — External-content ingestion hardening — SKETCH
**Value:** R9's real-external-content ingestion sharply widens the untrusted-
content + PII + ToS surface the deferred H1 sweep doesn't cover. **Scope:**
adversarial prompt-injection tests over scraped review/forum content; PII
detection/redaction; per-adapter ToS/rate-limit conformance; translation-
fidelity checks (with R9c). **Depends on:** R9 (and C2 ingestion).

### Suggested sequence
```
R9a (adapters + tiering + multi-lang querying) ─┬─▶ R9c (non-EN content, later)
                                                └─▶ C2 (market sizing) ◀── C1 (calculators, parallel)
R10 (gap→questions) — deps exist now; richer after R9
P1 (PDF) — last / anytime · H2 (hardening) — after R9/C2
```

## Explicit exclusions (do not build without a product decision)

- Anything assuming BOTIM issues cards / extends credit (see
  `docs/product-context.md`).
- Auto-promotion of any candidate evidence into the committed KB.
- A scheduler before manual monitoring runs are trustworthy.
- Real merchant data in Merchant Voice (synthetic-only until a privacy/security
  review and hardened auth).
