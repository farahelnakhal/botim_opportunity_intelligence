# Merchant Voice & Validation — backend (Phase 1 + Phase 2 + Phase 3)

> **PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY. NOT APPROVED FOR REAL MERCHANT DATA. NOT FOR PRODUCTION USE.**
> This service uses a static token→role map compared with `hmac.compare_digest` — it is **not** production identity/access management (no user directory, no session revocation, no token rotation, no TLS termination). Real merchant data requires a separate privacy/security review and a hardened deployment before use.

A human-reviewed research-to-evidence pipeline for BOTIM merchant feedback: research campaigns and guides → participants and responses (manual, CSV bulk, and text transcript ingestion — consent-gated and redacted) → AI-assisted extraction of structured **pending-review** observations → (Phase 4+) human review → evidence candidates → approved findings → a **proposal** for Part A evidence (never an authoritative write). The model may only *propose* observations — it never approves, scores, or finalizes anything. **Pure Python 3 standard library — nothing to install**, matching the rest of the repository.

## Scope so far

**Phase 1:** shared provider wiring, configuration, mandatory token/role auth, the `mv.db`/`identity.db` schema foundation, **campaigns** and **research guides**.

**Phase 2:** pseudonymous **participants** (merchant identity kept separately in `identity.db`, never exposed via API), deterministic **consent/privacy gating**, manual **response** ingestion, **CSV bulk import**, text-only **transcript** ingestion, deterministic **redaction**, and **withdrawal / retention-expiry / deletion-request** suppression (including recoverable transcript deletion with a maintenance retry).

**Phase 3:** the canonical **extraction eligibility gate** (`app/eligibility.py` — every check must pass before any provider call); **provider-backed structured extraction** (`app/extraction.py`, using the shared `shared.llm.provider` abstraction — no second provider); **deterministic output validation** (`app/extraction_validate.py` — exact-substring source verification, quote/paraphrase enforcement, willingness-to-pay/frequency/severity safeguards, single-response aggregate-claim rejection, link/contradiction cleanup); and **observation persistence as `pending_review`** with an idempotent/rerun-aware `extraction_runs` ledger.

**Not yet implemented** (later phases): reviewer approval/rejection, duplicate observation merge, evidence candidates, approved findings, strength bands, campaign aggregation, Part A proposal preview, synthetic export, Copilot Merchant Voice tools.

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
│   └── api.py             Phase 1 + 2 + 3 routes
└── tests/
```

Storage: `merchant-voice/data/mv.db` (campaigns, guides, questions, participants, responses, raw answers, transcript metadata, CSV import tokens, observations, extraction runs, audit — operational, authoritative for Merchant Voice's own domain) and `merchant-voice/data/identity.db` (a **separate file** holding only merchant identity + its own audit log) plus `merchant-voice/data/transcripts/` (transcript text files, not web-served). All gitignored; nothing here is authoritative Part A evidence, a Part B scorecard, an assumption, or impact state — those systems are untouched by this service.

## Shared provider package (Gate E)

The model-provider abstraction (`ConversationModel`, `ModelResponse`, `ProviderError`, `MockProvider`, `AnthropicProvider`, `make_provider`) lives canonically in **`shared/llm/provider.py`**, imported directly by both this service and `copilot-backend` (whose `app/provider.py` is a thin re-export shim). No new provider logic is duplicated — Phase 3 extraction is the first Merchant Voice code that actually calls it, and only after `app/eligibility.py`'s gate passes.

## Privacy design

- **Identity separation:** merchant identity lives only in `identity.db`; participants in `mv.db` reference it by ID and may only **narrow**, never widen, its grant.
- **Consent gate:** enforced before any AI call — consent granted, not suppressed, retention not expired, `ai_processing_permission` true, every answer's redaction `complete`, response not blocked/suppressed, transcript not pending deletion. `app/eligibility.py` is the single function every extraction entry point must call.
- **Redaction is a floor, not a ceiling:** deterministic regex-based detection — it does not claim perfect PII detection.
- **Suppression:** withdrawal blocks read access without deleting storage; retention-expiry and deletion-requests purge raw content and schedule transcript deletion (recoverable, with a maintenance retry).
- **Extraction never trusts the model:** source excerpts are exact-substring-verified against the redacted answer they claim to come from (never fuzzy); a model-claimed direct quote is downgraded unless it is materially identical to the source *and* the participant's `quote_permission` is true; willingness-to-pay/frequency/severity claims require explicit source support or are cleared/downgraded; a single-response statement that reads as a market-wide generalization is rejected outright; invalid segment/opportunity/assumption links are removed (never replaced with an invented ID); every observation is created `pending_review` — nothing here can approve itself, and no route in Phase 3 changes that status.

## Security (Phase 1 + 2 + 3)

Mandatory bearer-token auth with four roles (`viewer < researcher < reviewer < admin`) — **viewer has no access at all** to any Phase 2/3 route; `hmac.compare_digest` comparison; token values never logged, returned, or exposed; CORS restricted to the configured frontend origin; request-body size caps; bounded concurrency (including a `duplicate_extraction` guard against concurrent runs on the same response); parameterized SQL only; structured JSON errors with no stack traces or provider payloads; no shell/code execution anywhere; the extraction system prompt and tool schema are never returned by any endpoint.

## Tests

```bash
python3 -m unittest discover merchant-voice/tests
```

All offline (MockProvider; no network call in standard tests). A Merchant-Voice-specific live-provider smoke test is gated on **both** `ANTHROPIC_API_KEY` and `MV_RUN_LIVE_TESTS=1`. All fixtures use synthetic IDs (`MVC-TEST-…`, `MVG-TEST-…`, `MVP-…`, `MVR-…`, `MVO-…`, `MER-…`) only — no real merchant data anywhere in source, fixtures, or examples.
