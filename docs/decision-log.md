# Decision log

> Major product/architecture decisions, newest first. Add an entry whenever a
> decision would surprise a future maintainer or constrains future work.
> Format: date · decision · reasoning · alternatives · consequences.

## 2026-07-19 — R6 diff-to-email: materiality gate, claim-text diffing, and a signed unsubscribe token

- **Decision:** After a scheduled `monitoring` build completes, the tick decides
  whether to email by comparing the new version to a **baseline** (the version
  in `last_notified_version`; fallback: the previous complete version). The
  first-ever complete version establishes the baseline and sends nothing. It
  **reuses `compare_versions`** for the composite/gap diff, then layers a
  **claim-TEXT diff** on top: because every build mints fresh `RCAND-` ids,
  `compare_versions.new_claim_ids` is always the whole new set, so materiality
  is decided on *normalized claim text* resolved through the research store
  (with each claim's current review status), not on raw ids. **Material** iff
  there is ≥1 genuinely new claim text OR the preliminary composite moved by
  **≥ 0.01** (the smallest meaningful unit at the engine's current 2-decimal
  composite precision — anything smaller is rounding noise). Gap-set changes
  alone (e.g. a search provider flapping in and out) are **never** material. A
  **degraded run** — any `external research failed/was partial/skipped` marker
  in the new version's gaps — never emails (`partial_no_email`). Non-material
  runs record `no_change` and advance the baseline; only a material run emails
  eligible (enabled+confirmed) recipients, records `emailed`, and advances
  `last_notified_version`. The rendered body passes through an **overclaim
  guard reusing `impact/email.py`'s discipline**; a tripped guard aborts the
  send (fail-safe) rather than emailing an overclaim.
  **Unsubscribe links are deterministic signed tokens** (RFC 8058-style):
  `token = "<recipient_id>.<base64url(HMAC-SHA256(MONITORING_UNSUBSCRIBE_SIGNING_KEY,
  recipient_id))>"`, verified by recomputation. Stateless, stable across every
  email, and **nothing secret is stored per row** — the `unsubscribe_token_hash`
  column from the first cut is dropped (schema v5). Sending requires both a
  configured SMTP relay AND the signing key; absent either, the run records an
  honest "found a change but could not email" outcome and does not advance the
  baseline (so it retries once configured).
- **Reasoning:** The id-churn trap would otherwise mark every run material and
  spam recipients forever. Claim-text diffing is the minimal honest fix that
  still builds on the single `compare_versions` implementation. The signed
  token is the only unsubscribe mechanism that needs zero per-row secret
  storage (keeping the hash-only discipline used since R8a session tokens),
  gives links that stay valid across every past email (a rotated random token
  would 404 an old digest's unsubscribe link — unacceptable on a
  compliance-adjacent feature), and matches the one-click-unsubscribe
  convention if `List-Unsubscribe` headers are wanted later. The 0.01 gate ties
  materiality to real scoring precision rather than a magic number.
- **`MONITORING_UNSUBSCRIBE_SIGNING_KEY` is a real secret**, handled exactly
  like `MONITORING_TICK_TOKEN`: never committed, set per environment (distinct
  per deployment), documented in the env table, `sync: false` in `render.yaml`.
- **Alternatives rejected:** (a) diff on raw `RCAND-` ids — always "all new",
  guaranteed spam; (b) store the raw unsubscribe token in plaintext — breaks
  the hash-only discipline for a "it's low-stakes" reason, the kind of quiet
  erosion that compounds; (c) rotate a fresh random unsubscribe token per email
  — a six-week-old digest's unsubscribe link would 404, a real user-facing
  regression; (d) emailing on gap changes / removed claims alone — provider
  flapping and source staleness are not new findings; (e) a fixed magic
  threshold with no rationale — replaced with the precision-based 0.01.
- **Consequences:** A new `shared/email/monitoring_digest.py` (pure, offline-
  testable: `evaluate` + `render`). Workspace-store schema **v5** drops
  `unsubscribe_token_hash` and its index; `subscribe` no longer returns a raw
  unsubscribe token (links are minted at send time from `recipient_id` + key);
  `unsubscribe_by_token` now verifies a signed token. **Key-rotation caveat
  (logged like the 48h confirm-TTL tradeoff):** rotating
  `MONITORING_UNSUBSCRIBE_SIGNING_KEY` **silently invalidates every
  already-emailed unsubscribe link** — acceptable because rotation should be
  rare, but recipients holding old emails would then have to use the in-app
  toggle instead. The digest links back to the opportunity's report for full,
  labelled review; nothing in the email is presented as validated.

## 2026-07-19 — R6 double opt-in: recipients confirm control of their address before any mail

- **Decision:** Before a recipient can receive ANY monitoring mail it must
  **confirm control of its address** via a tokened link. On opt-in, the store
  marks the recipient row unconfirmed, mints an **opaque single-use
  confirmation token stored only as a SHA-256 hash** (identical discipline to
  R8a session tokens and the R6 unsubscribe token), and the opt-in route emails
  a confirm link through the existing `shared/email/` seam. The confirmation
  token **expires after 48h** (`MONITORING_CONFIRM_TTL_HOURS`; R8a's 30-day
  session TTL is far too long for a confirm link, so 48h is the sane default,
  not the session convention). The **tick and the PR6c send path treat an
  unconfirmed recipient exactly like a disabled one** — enforced at the
  persistence layer: a subscription's parent `enabled` flag is recomputed to
  true only when it has ≥1 recipient that is both enabled AND confirmed, so a
  chat with only unconfirmed recipients is never scheduled and never emailed.
  **Re-opting-in while unconfirmed resends** a fresh token (a natural "resend
  confirmation"); an expired link is refused (410) and re-opting-in issues a new
  one. A confirm/unsubscribe link works with no session, even under
  required-auth mode. Workspace-store **schema v4** adds
  `confirmed`/`confirm_token_hash`/`confirm_expires_at` to the recipient table
  (additive, PRAGMA-guarded).
- **Reasoning:** R8a stores an account's email at sign-up but never confirms the
  account controls it — so "registered" is not "confirmed" (the open decision
  flagged in the recipient entry). Because R6 sends real outbound mail, an
  account registered with someone else's address (typo or otherwise) would
  receive unsolicited email. R6 is exactly where the email infrastructure to
  close that gap first exists, so the confirmation step is built here, reusing
  patterns already in the repo (hashed opaque tokens, the `shared/email/` seam,
  tokened login-free link endpoints) rather than inventing anything. Enforcing
  eligibility at the `enabled` recompute means "no mail until confirmed" is a
  data-model invariant, not a check a future send path could forget.
- **Alternatives rejected:** (a) send to the registered address without
  confirmation — rejected: unsolicited mail to an unproven address, the exact
  honesty gap; (b) conflate unconfirmed with the `enabled` unsubscribe flag —
  rejected: loses the pending-vs-unsubscribed distinction a resend needs;
  (c) a long/session-length TTL — rejected: a confirm link is a bearer
  capability and should be short-lived; (d) verifying the email at R8a sign-up
  instead — rejected: out of R8a's scope and it had no email sender; doing it
  here is the minimal place it becomes possible.
- **Consequences:** Opt-in no longer returns a token in the API response; it
  reports an honest confirmation status (`required`/`email_sent`/`sent_to`).
  When SMTP is unconfigured the recipient simply stays unconfirmed and the
  response says the confirmation email could not be sent — no mail, no fake
  success. A new `GET /api/monitoring/confirm?token=` endpoint (login-free) and
  `MONITORING_PUBLIC_BASE_URL` (absolute link base for emails) are added. This
  **resolves the open decision** recorded in the recipient entry below.

## 2026-07-19 — R6 scheduler: external cron against a protected endpoint, not an in-process timer

- **Decision:** Scheduled workspace re-runs are driven by an **external cron
  trigger** (a GitHub Actions scheduled workflow,
  `.github/workflows/monitoring-tick.yml`) that issues an authenticated
  `POST /api/monitoring/tick` to the deployed executive API. The endpoint is a
  *dispatcher*: it finds subscriptions whose `next_run_at <= now`, atomically
  claims each (advancing `next_run_at` inside the same transaction), then runs
  the existing orchestrator for each claimed chat. It is protected by a shared
  secret (`MONITORING_TICK_TOKEN`, constant-time compared; 404/401 without it),
  caps work per call (`MONITORING_TICK_MAX_CHATS`), and does **no** work beyond
  what is due. There is **no in-process scheduler thread**. The workflow runs
  **hourly** (`cron: '0 * * * *'`) plus `workflow_dispatch`.
- **Reasoning:** The deploy target (Render free tier) **sleeps on idle** — an
  in-process timer would silently stop firing exactly when no user is active,
  fabricating a reliability we don't have. An
  external cron is the pattern the repo already uses for deploys, needs no
  always-on plan, and is idempotent by design (claim-and-advance makes a
  double-fired cron a no-op). GitHub's scheduler is itself best-effort — runs
  are commonly delayed minutes and can be dropped under load — but because the
  tick is driven by `next_run_at`, a dropped or late run is **recovered** by
  the next hourly tick with no lost work, only bounded extra latency. The
  endpoint reuses the existing stdlib `http.server` routing and the
  `check_quota`/owner-scoping machinery in `server.py`.
- **Alternatives rejected:** (a) in-process scheduler — dies with the sleeping
  container, needs a paid always-on plan to be honest; (b) a paid always-on
  plan purely to host a timer — cost with no other benefit and still less
  robust than an idempotent trigger; (c) cron-job.com — viable but adds a
  third-party account; GitHub Actions is already wired and auditable in-repo.
  Operators on an always-on plan can point any scheduler at the same endpoint —
  the mechanism is decoupled from the trigger.
- **Consequences:** A new `MONITORING_TICK_TOKEN` secret and
  `.github/workflows/monitoring-tick.yml`. Worst-case delivery latency for a
  due chat ≈ the cron granularity (up to ~1h) **plus** GitHub's own scheduling
  delay (typically minutes, occasionally longer). The cron frequency only needs
  to be ≤ the smallest allowed cadence; per-chat cadence is enforced by
  `next_run_at`, never by the cron frequency. The endpoint must stay safe to
  call at any frequency and must record every run outcome on the subscription
  (never fabricate a run that didn't happen).

## 2026-07-19 — R6 email: stdlib `smtplib`/`email` over an operator-configured SMTP relay — no SDK

- **Decision:** Email is sent with the Python **standard library only**
  (`smtplib` + `email.message.EmailMessage`, STARTTLS/SSL) against an
  **operator-configured SMTP relay** (`SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/
  `SMTP_PASSWORD`/`SMTP_FROM`/`SMTP_STARTTLS`). No provider SDK and **no new pip
  dependency** is added. The backing provider (Amazon SES, Postmark, Resend, or
  any SMTP server) is an **operator/deployment** choice — all expose SMTP, so
  the code stays provider-neutral. A `MockEmailSender` (records to memory, never
  opens a socket) is the explicit default in tests and when SMTP is
  unconfigured — mirroring `MockProvider` in `shared/llm/provider.py`:
  unconfigured is an honest "email not sent (no SMTP configured)" state,
  **never** a silent success. The sender lives behind a `shared/email/` seam
  (`sender.py`), injectable exactly like the research/LLM providers.
- **Reasoning:** "Pure stdlib, nothing to pip-install" is a hard, load-bearing
  invariant (`architecture.md`; reaffirmed by the R7 PDF and R8a auth
  decisions). `smtplib`/`email` satisfy the requirement *without* deviating from
  it, so — unlike the R7 PDF-library discussion — **no dependency sign-off is
  needed**. SMTP is the lowest common denominator every candidate provider
  supports, avoiding coupling to one vendor's REST SDK. The `render()`/no-send
  split and overclaim guard already established in `impact/email.py` give a
  proven honesty pattern to reuse for the body.
- **Alternatives rejected:** (a) Postmark/Resend/SES **REST SDKs** — each adds a
  pip dependency, violating the invariant and requiring sign-off; (b) a provider
  REST API over `urllib` (stdlib but vendor-locked) — more brittle and
  vendor-specific than SMTP for no gain; (c) a local `sendmail` binary — not
  present in the slim container, unreliable deliverability. A future REST
  provider SDK would be a separate logged deviation, same bar as the PDF library.
- **Consequences:** Deliverability, SPF/DKIM, and a verified sending domain are
  the **operator's** responsibility (documented in `deploy/` env docs), not the
  app's. Recipients are restricted to session-authenticated account emails (see
  the recipient decision); we do not do bulk/marketing sending. Send failures are caught and
  recorded as an honest failed-notification state on the subscription; a failed
  send is never logged as a delivered update.

## 2026-07-19 — R6 cadence + recipients: per-chat `workspace_subscriptions` with a multi-recipient child table, owner-scoped, distinct from `MCFG-`

- **Decision:** Scheduled-workspace-re-run configuration lives in **new tables**
  in the workspace store (`WORKSPACE_DB_PATH`), separate from the `MCFG-`
  monitoring config: a parent `workspace_subscriptions` row per chat
  (`opportunity_id` unique; `owner_user_id` **required**; `enabled`,
  `cadence_hours` per-chat, bounded `MONITORING_MIN_CADENCE_HOURS`..720, default
  6 resolved against `MONITORING_DEFAULT_CADENCE_HOURS`; `last_run_at`,
  `next_run_at`, `last_notified_version`, `last_outcome`), and a **child
  `workspace_subscription_recipients` table** (one row per recipient:
  `recipient_user_id` = a `USER-` account, `recipient_email` snapshot,
  hashed `unsubscribe_token`, `enabled`, `opted_in_at`; unique on
  `(opportunity_id, recipient_user_id)`). The **schema supports N recipients per
  chat from day one** so adding teammates later needs no migration. Every
  recipient is a **session-authenticated account's own registered email**, added
  only through a **per-recipient, session-scoped opt-in** (a signed-in user opts
  *themselves* in for a chat they can see — reusing the existing
  ownership/visibility guard); there is **no free-text recipient entry** — an
  address is never typed for someone else. Note the honest limitation: R8a
  stores the registered email at sign-up but does **not** confirm the account
  controls it (there is no email-confirmation flow yet), so "registered" is not
  "confirmed" — see the open decision in consequences. Unsubscribe is a tokened
  `GET /api/monitoring/unsubscribe?...` per recipient (and a UI toggle) that
  flips that recipient's `enabled` off without a login.
- **Reasoning:** The roadmap's explicit exclusions forbid changing how `MCFG-`
  works "outside the scheduled-workspace-re-run path — that's R4, already done."
  `MCFG-` drives the R4a runner that mints `MEVT-` events; R6 drives *workspace
  versions + email*. Conflating them would repurpose R4's cadence field and blur
  two runners, so R6 gets dedicated per-chat tables next to the versions they
  govern. A separate recipients child table (rather than owner-only) means
  teammates can be added with **zero schema churn** — the stated requirement —
  while the per-recipient session-scoped opt-in keeps the "recipients tied to a
  signed-in account, never a free-text address" constraint intact: consent is
  proven by the recipient's own session, never by the owner typing an
  address. Per-chat cadence (not global, not per-user) matches the R5 per-chat
  workspace model; a global default + bounds keeps it configurable without a
  hardcoded interval.
- **Alternatives rejected:** (a) reuse `MCFG-` cadence — violates the R4
  exclusion, couples two runners; (b) owner-email-only column (no child table) —
  rejected per the explicit ask: would force a migration to add teammates
  later; (c) free-text recipient list on the parent row — would email arbitrary
  third-party addresses with no account behind them, breaking the R8
  identity-scoping constraint;
  (d) global-only cadence — the task explicitly rules out a hardcoded global
  interval; (e) storing recipients in the auth DB — the subscription is per-chat
  workspace state, so it belongs with the workspace store; identity is
  referenced by `USER-` id, not duplicated.
- **Consequences:** Workspace-store schema **v3** (additive, PRAGMA-guarded like
  v2). PR6d's UI ships the **owner self-opt-in** path only (the owner adding
  themselves); the store/routes already accept additional recipients, so once a
  chat-sharing model exists (out of scope here) teammates opt in through the
  same flow with no data-model change. If an account's email changes, the
  recipient snapshot refreshes on the next opt-in touch. Bulk/external
  recipients remain out of scope (each needs a controlling account + session).
- **Resolved (see the 2026-07-19 "R6 double opt-in" entry above):** R8a never
  confirms that an account controls its registered email, so R6 adds a
  lightweight double-opt-in email-confirmation step — a one-time, hashed,
  48h-expiring confirm link; only a confirmed recipient is eligible for mail,
  enforced at the persistence layer. Until a recipient confirms, the current
  model is honestly "registered email + session opt-in, pending confirmation"
  — never described as "verified."

## 2026-07-19 — R6 throttling: reuse the R8b `quota_events` mechanism, scaled by active subscriptions

- **Decision:** Every scheduled re-run passes through the existing
  `AuthStore.check_quota(owner_user_id, action, limit)` with a **new action**
  `monitoring_workspace_run` and per-subscription base env
  `QUOTA_MONITORING_WORKSPACE_RUN_PER_DAY` (default 6 ≈ one chat at the ~4h end
  of the cadence). The **effective daily limit scales with the user's active
  enabled subscriptions**: `limit = base × max(1, active_subscription_count)`,
  computed at call time and passed to `check_quota` — so a user monitoring
  several chats is **never silently cut off** at a flat cap. The scheduled path
  counts against this action, **not** the interactive `workspace_refresh` pool,
  so scheduled load can't exhaust a user's manual-refresh budget or vice-versa.
  The subscription read payload also **surfaces `quota_used`/`quota_limit`** so
  the PR6d UI can show remaining runs. Over quota → the tick **skips** that chat
  honestly (`last_outcome='skipped_quota'`), sends no email, and continues.
- **Reasoning:** "Reuse the existing `quota_events`/`QUOTA_*_PER_DAY` pattern
  rather than inventing a new quota mechanism" is a direct task constraint; the
  pattern already stores per-action rows in the auth DB surviving restarts. A
  distinct action prevents cross-contaminating the interactive budget. Scaling
  the cap by active subscriptions is the structural fix for the "silently cut
  off mid-day" risk (a flat cap punishes users who monitor more chats);
  surfacing used/limit gives the UI an honest indicator on top.
- **Alternatives rejected:** (a) flat per-user cap — silently cuts off
  multi-chat users mid-day (the exact failure called out); (b) reuse
  `workspace_refresh` quota — scheduled runs would eat the interactive budget;
  (c) a new bespoke throttle table — duplicates `quota_events`, violates the
  task constraint; (d) a global (not per-user) rate cap — doesn't scope cost to
  the owner and breaks the R8b per-user model.
- **Consequences:** One new action string + one env var, documented in
  `current-state.md`. `check_quota` runs **once**, immediately before the
  expensive chain (it both counts and enforces), so a run skipped for other
  reasons is never counted. The effective limit shifts as the user
  enables/disables subscriptions during the day — acceptable and honest, and
  always ≥ the flat base.

## 2026-07-19 — R6 concurrency: skip-if-running lock + claim-and-advance idempotency

- **Decision:** Two rules. (1) **Manual-vs-scheduled lock:** before building,
  the scheduled path checks `ws.latest(opp_id, status="running")`; if a version
  is already `running` (a manual refresh or a prior tick in flight), the
  scheduled run is **skipped** (`last_outcome='skipped_in_progress'`), not
  queued — reusing the R5 rule that in-progress versions are visible but not
  readable and that readers only ever see the latest `complete` version.
  (2) **Idempotent claim:** the tick selects due subscriptions
  (`enabled AND next_run_at <= now`) and, in the **same transaction**, advances
  `next_run_at = now + cadence_hours` before running the chain, so a
  double-fired cron or an overlapping tick finds nothing due. Diffing and
  emailing baseline on `last_notified_version`, so a retry cannot re-send an
  already-sent delta.
- **Reasoning:** The append-only version model already makes concurrent builds
  *safe for readers*; the remaining risks are (a) wasted cost from a scheduled
  run duplicating a manual one and (b) duplicate emails from a re-fired trigger.
  Skip-if-running addresses (a) with the existing running/complete distinction;
  claim-and-advance + `last_notified_version` addresses (b) at the persistence
  layer — the only place idempotency can hold against an at-least-once external
  trigger.
- **Alternatives rejected:** (a) queue scheduled runs behind manual ones — adds
  a job queue the stdlib server lacks, and a slightly-stale scheduled run adds
  no value over waiting for the next tick; (b) a global in-process lock —
  doesn't survive multi-tick/at-least-once delivery or a restart; (c) diffing
  against "previous version" unconditionally — re-emails the same delta every
  cycle until a human approves; baselining on `last_notified_version` gives true
  "new since last notified/approved."
- **Consequences:** `next_run_at` is authoritative for scheduling; the cron
  frequency only needs to be ≤ the smallest cadence. The email diff is
  `compare_versions(baseline, newest)` with `baseline = last_notified_version`
  (fallback: previous complete version); each `new_claim_id` is then resolved to
  its **current** review status via the research store (the same lookup
  `_workspace_view` already does) so the email labels "new since last approved"
  and marks each claim approved/pending — **no second diff implementation**.

## 2026-07-17 — R7 documents: stdlib extraction, honest PDF gap, lexical retrieval seam

- **Decision:** Document attachments support `.txt/.md/.csv/.docx` with pure
  stdlib extraction (DOCX = zip + XML paragraphs). **PDF returns an honest
  415 "not supported yet"** rather than shipping a fragile pure-stdlib PDF
  parser that silently yields garbage. "Scoped RAG" is implemented as
  deterministic chunking + transparent keyword-overlap retrieval
  (`search_chunks`) — the same discipline as the KB search — with vector
  embeddings able to replace the scorer behind the same signature later.
  Retrieved excerpts are quoted verbatim, bounded, snapshotted onto the
  workspace version (kept even if the file is deleted), and labelled
  USER-PROVIDED DATA — never instructions, never repository evidence.
  Deletion is real (document + all chunks). Uploads travel as base64 JSON
  (2 MB cap) to keep the stdlib server free of multipart parsing.
- **Reasoning:** No dependencies is a hard constraint; honesty beats
  capability theater (a bad PDF extractor fabricates content); deterministic
  retrieval is testable offline and transparent to reviewers.
- **Alternatives rejected:** bundling a PDF library (violates the stdlib
  constraint — revisit only as a logged decision); embedding-based RAG now
  (needs a model + storage; the seam is ready); multipart upload parsing
  (complexity without user value at 2 MB caps).
- **Consequences:** PDF users must export to .docx/.txt (stated in the UI).
  R6 monitoring diffs already include document-driven changes because
  excerpts live on versions.

## 2026-07-17 — R8a authentication: stdlib email+password, opt-in enforcement, legacy rows shared

- **Decision:** Accounts are email + password hashed with PBKDF2-HMAC-SHA256
  (600k iterations, per-user salt, versioned hash format), sessions are opaque
  256-bit tokens stored **only as SHA-256 hashes** and delivered as an
  HttpOnly/SameSite=Lax cookie (Secure outside test mode). Enforcement is
  **opt-in per deployment** via `BOTIM_AUTH_MODE` (default `off`; any
  unrecognized value fails CLOSED to required). Under required mode every
  `/api` route and the copilot proxy demand a session; `/auth/*` and static
  files stay reachable. Tenancy: `user_opportunities.owner_user_id` — new
  records belong to their creator; pre-auth rows keep a NULL owner and remain
  **visible to all signed-in users** (legacy shared), never silently
  reassigned; another user's record answers an indistinguishable 404.
  `AUTH_ALLOW_REGISTRATION=0` closes sign-ups once the intended accounts exist.
- **Reasoning:** Pure-stdlib backends rule out OAuth SDKs and external IdPs;
  magic-link sign-in needs the R6 email infrastructure that does not exist
  yet. Password auth with honest limitations (no reset until R6, stated in
  the UI) is the smallest real implementation that unblocks R6/R7. Opt-in
  enforcement means existing single-tenant deployments and the offline test
  matrix keep working unchanged; fail-closed parsing means a typo can never
  silently disable auth.
- **Alternatives rejected:** OAuth/Google sign-in (external dependency +
  operator registration; can be added later behind the same session layer);
  auto-assigning legacy rows to the first registrant (silent data grab);
  default-on enforcement (breaks every existing deploy on upgrade).
- **Consequences:** R8b remains: per-user scoping of copilot conversations
  and research runs (identity propagation through the fixed proxy),
  merchant-voice token replacement, per-user quotas, password reset with R6
  email. Email recipients (R6) and private documents (R7) now have an
  identity to scope to.

## 2026-07-16 — Versioned preliminary analysis workspace per saved chat (R5 model)

- **Decision:** Each saved chat gets a **versioned, snapshotted analysis
  workspace**. The full customer-intelligence → opportunity-intelligence →
  scoring/calculation chain runs only on defined triggers (below); normal
  follow-up questions reuse the latest complete workspace version instead of
  re-running the chain. Everything machine-generated in a workspace is
  labelled **preliminary until a human reviews it**, and nothing auto-writes
  the committed knowledge base.
- **Concrete triggers** (a re-run producing a new version): first analysis of
  the chat; explicit manual "refresh analysis"; a *meaningful change* —
  defined narrowly as a new attachment, an edited opportunity field, or newly
  **approved** evidence attached (NOT an ordinary follow-up message);
  *staleness* — workspace age exceeds a configured threshold; or a monitoring
  trigger (R6). Anything else reads the stored version.
- **Retrieval split:** structured records/claims/scores/calculations stay in
  the existing traceable tool/ID system (`shared/research`, engines, impact);
  RAG (chunk + embed) is used **only** for unstructured content — uploaded
  documents and long fetched source bodies — and its chunks feed the same
  candidate-evidence → review → grounding pipeline.
- **Preliminary scores use the REAL engine, not an LLM guess:** a workspace
  score is produced by building a synthetic in-memory scorecard from the
  workspace's (preliminary) evidence and running it through the existing
  17-dimension `opportunity_engine` — so the assumption-cap discipline and
  determinism hold — then labelling the result preliminary and never writing
  it to committed scores. The LLM never estimates a numeric score.
- **Approvals attach to claims/evidence, not to the version:** a re-run
  (v3→v4) re-evaluates but inherits prior human approvals for unchanged
  claims; monitoring diffs highlight "new since last approved," not "new
  since last version."
- **Per-version provenance is first-class:** each version records the KB
  state, research runs, documents, and model/prompt it used — this record IS
  the "share sources / explain logic" surface and the reproducibility
  guarantee, not a later add-on.
- **Reasoning:** Gives the desired UX (ask → chain runs once → answer from the
  generated dataset with sources and logic; cheap follow-ups) without turning
  the tool into something that fabricates validated conclusions or re-runs an
  expensive chain per message. Fits existing store/orchestrator/review
  patterns; breaks no invariant.
- **Alternatives considered:** (a) run the full chain on every message —
  rejected (cost, latency, and it still wouldn't help follow-ups); (b) feed
  auto-generated evidence into *committed* scores — rejected (violates the
  human-review invariant); (c) replace grounded tool retrieval with vector
  RAG wholesale — rejected (loses traceability/precision for a small
  structured corpus; RAG scoped to unstructured content instead).
- **Consequences:** New versioned per-chat workspace store (a sibling of
  `user_store`/research store); an orchestrator composing existing engines;
  concurrency rule (append versions, chat reads latest *complete*, in-progress
  runs visible but not readable); per-run cost/timeout caps still required;
  version retention/pruning policy (keep last N + all human-approved). Depends
  on PR3 (claim extraction). Monitoring email/scheduler (R6) and attachments
  (R7) build on this; sign-in/tenancy (R8) gates R6 and R7.

## 2026-07-16 — Canonical vendor-neutral LLM configuration (BOTIM_LLM_*)

- **Decision:** All live-model functionality resolves configuration through
  `BOTIM_LLM_API_KEY` / `BOTIM_LLM_MODEL` / `BOTIM_LLM_BASE_URL` /
  `BOTIM_LLM_PROVIDER` (`shared.llm.provider.resolve_llm_env`). Vendor
  variables (`ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `COPILOT_*`) are optional
  aliases only. An OpenAI-compatible provider removes the Anthropic hard
  dependency. The deterministic mock responder is selected ONLY explicitly
  (or defaulted by start.sh in demo/test mode) — a missing key in normal
  mode yields an "unconfigured" provider with honest chat errors, never
  silent demo output.
- **Reasoning:** The deployment configured `BOTIM_LLM_*`, but those were
  read only by the deprecated legacy scaffold; the chat path keyed on
  `ANTHROPIC_API_KEY` and silently fell back to mock — exactly the failure
  the honesty rules exist to prevent.
- **Consequences:** `GET /api/health` on the copilot reports the active
  provider/model/config source (never keys); startup logs the same;
  non-Anthropic endpoints need `BOTIM_LLM_BASE_URL` unless implied by the
  Groq alias.

## 2026-07-15 — Committed knowledge base stays read-only at runtime

- **Decision:** No HTTP route or model output ever writes `knowledge-base/`.
  Authoritative changes are human Git commits (or the impact CLI with `--approver`).
- **Reasoning:** Evidence discipline and auditability; a runtime write path would
  make fabrication and silent mutation possible.
- **Alternatives:** Runtime-writable KB with audit log — rejected (weaker guarantee,
  merge conflicts with the human workstreams).
- **Consequences:** All user/runtime state needs separate stores (see next entries);
  research output must land as candidates, not KB records.

## 2026-07-15 — User work lives in separate runtime persistence (Phase 6)

- **Decision:** User-created opportunities persist in runtime SQLite
  (`USER_OPPORTUNITIES_DB_PATH`, gitignored) under a distinct `UOPP-` namespace;
  monitoring configs under `MCFG-`.
- **Reasoning:** Keeps the Git KB clean and read-only; namespaces cannot collide
  with committed `OPP-nnn`; survives refresh/restart without touching Git.
- **Alternatives:** localStorage only (lost across browsers, was the pre-Phase-6
  state, migrated away); committing drafts to Git (violates the KB boundary).
- **Consequences:** Single-tenant until auth/tenancy (H1); backup/ops story is the
  SQLite file.

## 2026-07-15 — Backend is the source of truth for application mode (Phase 5)

- **Decision:** `BOTIM_APP_MODE` (normal|demo|test, default normal, invalid→normal)
  is resolved server-side and reported via `meta.app_mode`; the frontend only
  displays it. `VITE_APP_MODE` only gates the offline demo seed in demo builds.
- **Reasoning:** Prevents a stale/mismatched frontend from showing demo data as
  real; "never silently demo" is a safety default.
- **Consequences:** Demo-corpus tests must pin `BOTIM_APP_MODE=demo` explicitly.

## 2026-07-15 — SME financial-product opportunity is the first validation case, not the platform boundary

- **Decision:** The internship brief ("SME Credit Cards") validates the platform;
  capabilities must serve it well AND stay reusable for other opportunities.
- **Reasoning:** The product's value is reusability across BOTIM teams; overfitting
  to one case would strand the KB, engines, and architecture already built.
- **Consequences:** Research profiles, not hardcoded SME research; no renaming;
  roadmap phases are platform capabilities with an SME validation profile.

## 2026-07-15 — BOTIM is not assumed to be a bank, issuer, or lender

- **Decision:** No output may claim BOTIM can issue cards, extend credit,
  underwrite, hold deposits, or perform regulated activities without verified
  evidence of the legal/operational structure. Issuer/lender/program-manager/
  distributor roles are always distinguished.
- **Reasoning:** "SME Credit Cards" is a problem-space title; recommending regulated
  activities BOTIM cannot perform would be fabrication with real-world consequences.
- **Consequences:** The system evaluates partnership/program structures as first-
  class alternatives; regulatory/licensing claims stay labelled as assumptions until
  evidenced. (Consistent with the existing MASTER_PROMPT MDR/interchange honesty
  rule.)

## 2026-07-15 — No fabricated research or monitoring; honest not-yet-run states

- **Decision:** Monitoring configs without a runner display "Configured — awaiting
  monitoring run"; no events are invented; failed/partial states are shown honestly.
  The same rule binds future research runs.
- **Reasoning:** Fabricated activity would poison the evidence base and user trust.
- **Consequences:** The monitoring runner (R4) must exist before cadences mean
  anything; "Run monitoring now" stays disabled until then.

## 2026-07-15 — Candidate evidence requires human review; user drafts are not authoritative

- **Decision:** Merchant Voice findings, monitoring evidence candidates, and future
  external-research output are candidates. Humans approve; nothing auto-mints EV ids
  or writes `knowledge-base/customer-evidence/records/`. User `UOPP-` drafts ground
  chat as labelled USER-PROVIDED context only.
- **Reasoning:** Preserves the evidence-quality bar and Workstream A's ownership.
- **Consequences:** Every ingestion feature needs a review surface (R3 includes one).

## 2026-07-15 — External research must be traceable and never silently promoted

- **Decision:** When live research ships, every claim links source → research run;
  sources carry normalized metadata + quality signals; results persist with partial/
  failed states; external content is data, never instructions.
- **Reasoning:** Extends the existing citation/grounding discipline to external
  content; guards against prompt injection via fetched pages.
- **Consequences:** R1 (schema/persistence) precedes any live fetching (R2).

## 2026-07-15 — Preserve working architecture unless change is justified

- **Decision:** The stdlib-Python services, shared LLM-provider abstraction
  (`shared/llm/provider.py` — never bypassed), `/executive-api` vs `/copilot-api`
  separation, and Farah's frontend design are kept. Legacy ungrounded routes stay
  disabled by default rather than deleted.
- **Reasoning:** The system is tested and coherent; rewrites reset test confidence
  and burn schedule without user value.
- **Consequences:** New capabilities integrate at existing seams (adapters,
  contracts, stores) rather than replacing layers.
