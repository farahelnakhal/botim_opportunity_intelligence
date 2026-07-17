# Decision log

> Major product/architecture decisions, newest first. Add an entry whenever a
> decision would surprise a future maintainer or constrains future work.
> Format: date · decision · reasoning · alternatives · consequences.

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
