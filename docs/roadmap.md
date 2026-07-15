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

## Phase R3 — Research integration (chat, review, reports)

**Value:** research becomes usable in the product, not just stored.
**Depends on:** R2.

- Candidate-evidence review UI (approve/reject → still never auto-mints EV ids).
- Chat integration: copilot can cite research-run sources (new citation type,
  additive to `conversation-api.schema.md`), clearly labelled external + freshness.
- Reports include a sources appendix from research runs.
- **Acceptance:** claim-to-source traceability visible end-to-end; internal vs
  external evidence visually distinct; stale external sources flagged.

## Phase R4 — Monitoring runner + evidence revalidation

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

## Phase C1 — Deterministic calculations

**Value:** transparent market-sizing / unit-economics math for briefs and the SME
case's deck. Independent of R-phases; can run in parallel after R1.

- Server-side deterministic calculators (inputs, formula, outputs all shown);
  no LLM arithmetic; results embeddable in reports/chat with full working shown.
- **Acceptance:** same inputs → same outputs; every number traceable to inputs.

## Phase P1 — Executive outputs (PDF export, answer orchestration polish)

**Depends on:** nothing hard; more valuable after R3 (reports carry research).
- PDF export of web reports (server-rendered; no client-only hacks).
- First-answer orchestration improvements in chat.

## Phase H1 — Hardening milestone (the deferred full sweep)

**Depends on:** whenever the above stabilize; explicitly owed from PR #34.
- Real authentication/tenancy for executive API + user store; merchant-voice auth
  replacement before any non-synthetic data.
- Adversarial tests for copilot `context.user_opportunity`.
- Full combined test matrix, browser/e2e sweeps across modes, persistence/restart,
  service-failure, mobile, dark mode, citation integrity, research partial/failed
  states, security/trust-boundary tests.
- Real attachment processing (if still wanted) enters here, not before.

## Explicit exclusions (do not build without a product decision)

- Anything assuming BOTIM issues cards / extends credit (see
  `docs/product-context.md`).
- Auto-promotion of any candidate evidence into the committed KB.
- A scheduler before manual monitoring runs are trustworthy.
- Real merchant data in Merchant Voice (synthetic-only until a privacy/security
  review and hardened auth).
