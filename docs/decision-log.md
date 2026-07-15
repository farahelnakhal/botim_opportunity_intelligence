# Decision log

> Major product/architecture decisions, newest first. Add an entry whenever a
> decision would surprise a future maintainer or constrains future work.
> Format: date · decision · reasoning · alternatives · consequences.

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
