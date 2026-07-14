# Merchant Voice & Validation — backend (Phase 1 + 2 + 3 + 4 + 5)

> **PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY. NOT APPROVED FOR REAL MERCHANT DATA. NOT FOR PRODUCTION USE.**
> This service uses a static token→role map compared with `hmac.compare_digest` — it is **not** production identity/access management (no user directory, no session revocation, no token rotation, no TLS termination). Real merchant data requires a separate privacy/security review and a hardened deployment before use.

A human-reviewed research-to-evidence pipeline for BOTIM merchant feedback: research campaigns and guides → participants and responses (manual, CSV bulk, and text transcript ingestion — consent-gated and redacted) → AI-assisted extraction of structured **pending-review** observations → human review (edit/approve/reject/merge) → evidence candidates → immutable approved Merchant Voice findings → a human-reviewed Part A evidence **proposal** (draft → submit → approve → approve-export → synthetic-only export) — never an authoritative write. The model may only *propose* observations — it never approves, scores, or finalizes anything, and an approved finding (or an approved, even exported, proposal) is still **not** authoritative Part A evidence. The Product Discovery Copilot reads approved+published findings through a dedicated read-only query layer — it has no write path here. **Pure Python 3 standard library — nothing to install**, matching the rest of the repository.

## Scope so far

**Phase 1:** shared provider wiring, configuration, mandatory token/role auth, the `mv.db`/`identity.db` schema foundation, **campaigns** and **research guides**.

**Phase 2:** pseudonymous **participants** (merchant identity kept separately in `identity.db`, never exposed via API), deterministic **consent/privacy gating**, manual **response** ingestion, **CSV bulk import**, text-only **transcript** ingestion, deterministic **redaction**, and **withdrawal / retention-expiry / deletion-request** suppression (including recoverable transcript deletion with a maintenance retry).

**Phase 3:** the canonical **extraction eligibility gate** (`app/eligibility.py` — every check must pass before any provider call); **provider-backed structured extraction** (`app/extraction.py`, using the shared `shared.llm.provider` abstraction — no second provider); **deterministic output validation** (`app/extraction_validate.py` — exact-substring source verification, quote/paraphrase enforcement, willingness-to-pay/frequency/severity safeguards, single-response aggregate-claim rejection, link/contradiction cleanup); and **observation persistence as `pending_review`** with an idempotent/rerun-aware `extraction_runs` ledger.

**Phase 4:** the human-governed review workflow — **observation review/edit/approve/reject/merge** (`app/observation_review.py`, re-running Phase 3's safeguards on every edit; source fields immutable; separation-of-duties self-approval guard); **evidence candidates** (`app/candidates.py`, scoped to one campaign, counts always computed from linked observations, known-contradiction discovery); **deterministic strength bands** (`app/strength.py` — the model never assigns strength); **immutable approved Merchant Voice findings** (`app/findings.py`, created only by approving a candidate, with an explicit publish/suppress action); **campaign-level analysis** (`app/analysis.py` — always numerator/denominator/segment-grouped, never a bare percentage); and full **withdrawal/revalidation integration** with the Phase 2 suppression cascade (a published finding is never left stale).

**Phase 5:** a human-reviewed **Part A evidence proposal** workflow (`app/part_a_proposal.py` — generate from an approved+published finding, draft/edit/submit/approve/reject, a separate export-approval step, and withdrawal-driven invalidation that mirrors the Phase 4 finding cascade); **synthetic-only export** into `knowledge-base/customer-evidence/merchant-voice-candidates/` (server-generated filename, synthetic-data banner, never an EV ID, never `.../records/`); and a **read-only query layer** (`app/published_query.py` — never opens `identity.db`, exposes only approved+published, non-superseded, consent/retention-valid content) that `copilot-backend/` calls directly for grounded, cited Merchant Voice answers. Authoritative Part A evidence-ID minting and promotion of anything into Part A are **not** deferred future work — they are a separate, human Workstream A action this service never automates, now or later. Real-merchant-data export is out of scope for v1 (synthetic-only).

## Run

```bash
cp merchant-voice/.env.example merchant-voice/.env   # fill in real tokens locally; never commit .env
set -a; source merchant-voice/.env; set +a
python3 merchant-voice/server.py
# → http://127.0.0.1:8020 (binds localhost only by default)
```

The server **refuses to start** if `MV_TOKENS` is empty. On startup it prints the prototype/synthetic-only warning banner.

```bash
curl -s http://127.0.0.1:8020/health

# campaign -> guide -> approve -> activate
curl -s -X POST http://127.0.0.1:8020/api/merchant-voice/campaigns \
  -H "Authorization: Bearer $RESEARCHER_TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"MVC-TEST-001 pilot","objective":"Understand supplier-payment pain","method":"interview","data_classification":"synthetic"}'

# participant (with an inline synthetic merchant identity)
curl -s -X POST http://127.0.0.1:8020/api/merchant-voice/participants \
  -H "Authorization: Bearer $RESEARCHER_TOKEN" -H 'Content-Type: application/json' \
  -d '{"campaign_id":"MVC-...","merchant_identity":{"consent_status":"granted","permitted_use":"internal_research_only","quote_permission":true,"ai_processing_permission":true,"data_classification":"synthetic"},"consent_status":"granted","permitted_use":"internal_research_only","quote_permission":true,"ai_processing_permission":true,"data_classification":"synthetic"}'

# manual response
curl -s -X POST http://127.0.0.1:8020/api/merchant-voice/responses \
  -H "Authorization: Bearer $RESEARCHER_TOKEN" -H 'Content-Type: application/json' \
  -d '{"campaign_id":"MVC-...","participant_id":"MVP-...","guide_id":"MVG-...","method":"interview","answers":[{"question_id":"...","answer":"We lose sales every week to late supplier payments."}]}'

# extraction (requires MV_PROVIDER=anthropic + ANTHROPIC_API_KEY for a live model; MockProvider by default)
curl -s -X POST http://127.0.0.1:8020/api/merchant-voice/responses/MVR-.../extract \
  -H "Authorization: Bearer $RESEARCHER_TOKEN" -H 'Content-Type: application/json' -d '{}'
```

## Architecture

```
merchant-voice/            (separate process, port 8020, own storage — Gate A/B)
├── server.py              stdlib HTTP server; refuses to start without MV_TOKENS
├── app/
│   ├── config.py          env-driven config; synthetic_only defaults ON
│   ├── auth.py            bearer token -> role (hmac.compare_digest); no token echoing
│   ├── db.py               separate mv.db / identity.db; forward-only migrations; WAL
│   ├── models.py          validation, enums, transitions, taxonomy, deterministic safeguard word lists
│   ├── audit.py           append-only audit_events (hashes/safe diffs only)
│   ├── campaigns.py       campaign service (Phase 1)
│   ├── guides.py          versioned, immutable-once-approved research guides (Phase 1)
│   ├── identity.py        merchant identity service — identity.db only, never API-exposed (Phase 2)
│   ├── participants.py    pseudonymous participants — mv.db only (Phase 2)
│   ├── consent.py         deterministic consent/AI-processing/quote gates (Phase 2)
│   ├── responses.py       manual response + raw-answer ingestion (Phase 2)
│   ├── csv_import.py      CSV preview/commit — token-bound, transactional (Phase 2)
│   ├── transcripts.py     text-only transcript ingestion + metadata (Phase 2)
│   ├── redaction.py       deterministic PII redaction (Phase 2)
│   ├── suppression.py     withdrawal/retention/deletion + recoverable transcript deletion (Phase 2)
│   ├── counting.py        denominator foundation (Phase 2)
│   ├── eligibility.py     the ONE canonical extraction eligibility gate (Phase 3)
│   ├── extraction_prompt.py  redacted-content-only prompt + tool schema, never API-exposed (Phase 3)
│   ├── extraction_validate.py  deterministic acceptance/rejection of model output (Phase 3)
│   ├── extraction.py      orchestration: eligibility -> provider call -> validate -> persist (Phase 3)
│   ├── observation_review.py  human review: queue/edit/approve/reject/merge (Phase 4)
│   ├── strength.py        deterministic strength-band computation — model never assigns this (Phase 4)
│   ├── candidates.py      evidence candidates: draft -> submit -> approve/reject (Phase 4)
│   ├── findings.py        immutable approved findings; publish/suppress; revalidation (Phase 4)
│   ├── analysis.py        campaign-level analysis: numerator/denominator, segment-grouped (Phase 4)
│   ├── part_a_proposal.py  Part A evidence proposals: generate/edit/submit/approve/reject/export (Phase 5)
│   ├── published_query.py  read-only, Copilot-facing query layer — never opens identity.db (Phase 5)
│   └── api.py             Phase 1 + 2 + 3 + 4 + 5 routes
└── tests/
```

Storage: `merchant-voice/data/mv.db` (campaigns, guides, questions, participants, responses, raw answers, transcript metadata, CSV import tokens, observations, extraction runs, evidence candidates, candidate-observation links, merchant findings, Part A proposals, audit — operational, authoritative for Merchant Voice's own domain) and `merchant-voice/data/identity.db` (a **separate file** holding only merchant identity + its own audit log) plus `merchant-voice/data/transcripts/` (transcript text files, not web-served). All gitignored; nothing here is authoritative Part A evidence, a Part B scorecard, an assumption, or impact state — those systems are untouched by this service. The one exception: `POST /part-a-proposals/{id}/export` writes a single, synthetic-only, server-named markdown file to the **tracked** `knowledge-base/customer-evidence/merchant-voice-candidates/` directory — never `.../records/`, never an EV ID.

## Shared provider package (Gate E)

The model-provider abstraction (`ConversationModel`, `ModelResponse`, `ProviderError`, `MockProvider`, `AnthropicProvider`, `make_provider`) lives canonically in **`shared/llm/provider.py`**, imported directly by both this service and `copilot-backend` (whose `app/provider.py` is a thin re-export shim). No new provider logic is duplicated — Phase 3 extraction is the first Merchant Voice code that actually calls it, and only after `app/eligibility.py`'s gate passes.

## Privacy design

- **Identity separation:** merchant identity lives only in `identity.db`; participants in `mv.db` reference it by ID and may only **narrow**, never widen, its grant.
- **Consent gate:** enforced before any AI call — consent granted, not suppressed, retention not expired, `ai_processing_permission` true, every answer's redaction `complete`, response not blocked/suppressed, transcript not pending deletion. `app/eligibility.py` is the single function every extraction entry point must call.
- **Redaction is a floor, not a ceiling:** deterministic regex-based detection — it does not claim perfect PII detection.
- **Suppression:** withdrawal blocks read access without deleting storage; retention-expiry and deletion-requests purge raw content and schedule transcript deletion (recoverable, with a maintenance retry).
- **Extraction never trusts the model:** source excerpts are exact-substring-verified against the redacted answer they claim to come from (never fuzzy); a model-claimed direct quote is downgraded unless it is materially identical to the source *and* the participant's `quote_permission` is true; willingness-to-pay/frequency/severity claims require explicit source support or are cleared/downgraded; a single-response statement that reads as a market-wide generalization is rejected outright; invalid segment/opportunity/assumption links are removed (never replaced with an invented ID); every observation is created `pending_review` — nothing here can approve itself.
- **Human review is never bypassable:** approved/rejected observations and approved candidates/findings are immutable to normal edits — a correction always creates a new reviewed revision or superseding object, never a silent overwrite. Every edit re-runs the Phase 3 safeguards. Self-approval requires `MV_ALLOW_SELF_APPROVAL=1` *and* synthetic-only mode, and is always audited with `self_approval: true`.
- **Withdrawal cascades all the way through:** a suppressed participant's observations are excluded from candidate/finding counts immediately; a published finding whose support has weakened becomes `needs_revalidation`, and one with zero remaining support becomes `suppressed` — never left stale. The cascade now reaches Part A proposals too: any non-terminal proposal for a recalculated finding is marked `needs_revalidation`/`suppressed`, blocking approval and export; a previously exported synthetic file's audit record is preserved, but the proposal reads as based on a superseded version.
- **A Part A proposal is never authoritative, and never becomes so automatically:** `suggested_strength` is explicitly labelled non-authoritative ("Workstream A decides final evidence strength"); `authoritative_ev_id` is always `null`; synthetic-only export writes only to the demo intake folder, with a prominent banner, and only when the source campaign's `data_classification == "synthetic"` — any other classification returns `non_synthetic_export_forbidden` with the real prerequisites listed.

## Security (Phase 1 + 2 + 3 + 4 + 5)

Mandatory bearer-token auth with four roles (`viewer < researcher < reviewer < admin`) — **viewer has no access at all** to Phase 2/3 routes, the review queue, observation editing, evidence-candidate routes, or Part A proposal routes (viewer may only read published findings, aggregate campaign analysis, and the read-only `/published/*` surface); `hmac.compare_digest` comparison; token values never logged, returned, or exposed; CORS restricted to the configured frontend origin; request-body size caps; bounded concurrency (including a `duplicate_extraction` guard against concurrent runs on the same response); parameterized SQL only; structured JSON errors with no stack traces or provider payloads; no shell/code execution anywhere; the extraction system prompt and tool schema are never returned by any endpoint; no identity.db access from the analysis, finding, published-query, or proposal layers. The synthetic-only export path takes no caller-supplied path or filename — the target directory and filename are both server-computed from a regex-validated proposal ID, never user input.

## Copilot integration (Phase 5)

`copilot-backend/app/mv_tools.py` calls `app/published_query.py` directly against a genuinely **read-only** SQLite connection (`mode=ro`) to `mv.db` — it never opens `identity.db`, never writes, and only ever sees approved, published, non-superseded, consent/retention-valid, permission-safe content. Because both services happen to name their own package `app`, the Copilot loads Merchant Voice's package under the distinct alias `mv_app` to avoid a collision — see `mv_tools.py`'s docstring. See `shared/contracts/conversation-api.schema.md` for the additive `merchant_finding` citation type.

## Tests

```bash
python3 -m unittest discover merchant-voice/tests
```

All offline (MockProvider; no network call in standard tests). A Merchant-Voice-specific live-provider smoke test is gated on **both** `ANTHROPIC_API_KEY` and `MV_RUN_LIVE_TESTS=1`. All fixtures use synthetic IDs (`MVC-TEST-…`, `MVG-TEST-…`, `MVP-…`, `MVR-…`, `MVO-…`, `MER-…`, `MEP-…`) only — no real merchant data anywhere in source, fixtures, or examples. Synthetic-export tests always write to a temporary directory (`MV_EXPORT_ROOT` override) — never to the real `knowledge-base/`.
