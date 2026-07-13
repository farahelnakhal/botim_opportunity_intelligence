# Merchant Voice & Validation — backend (Phase 1 + Phase 2)

> **PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY. NOT APPROVED FOR REAL MERCHANT DATA. NOT FOR PRODUCTION USE.**
> This service uses a static token→role map compared with `hmac.compare_digest` — it is **not** production identity/access management (no user directory, no session revocation, no token rotation, no TLS termination). Real merchant data requires a separate privacy/security review and a hardened deployment before use.

A human-reviewed research-to-evidence pipeline for BOTIM merchant feedback: research campaigns and guides → participants and responses (manual, CSV bulk, and text transcript ingestion — consent-gated and redacted) → (Phase 3+) AI-assisted extraction → human review → evidence candidates → approved findings → a **proposal** for Part A evidence (never an authoritative write). **Pure Python 3 standard library — nothing to install**, matching the rest of the repository.

## Scope so far

**Phase 1:** shared provider wiring, configuration, mandatory token/role auth, the `mv.db`/`identity.db` schema foundation, **campaigns** and **research guides**.

**Phase 2:** pseudonymous **participants** (merchant identity kept separately in `identity.db`, never exposed via API), deterministic **consent/privacy gating** (including the AI-processing gate a future Phase 3 extraction step will have to pass — no provider is called anywhere in Phase 2), manual **response** ingestion, **CSV bulk import** (preview/commit with a single-use expiring token), text-only **transcript** ingestion (`.txt`/`.md`/`.vtt`), deterministic **redaction**, and **withdrawal / retention-expiry / deletion-request** suppression (including recoverable transcript deletion with a maintenance retry).

**Not yet implemented** (later phases): AI extraction, observation review, evidence candidates, approved findings, aggregation/analysis, Part A proposal preview, synthetic export, Copilot Merchant Voice tools.

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
```

## Architecture

```
merchant-voice/            (separate process, port 8020, own storage — Gate A/B)
├── server.py              stdlib HTTP server; refuses to start without MV_TOKENS
├── app/
│   ├── config.py          env-driven config; synthetic_only defaults ON
│   ├── auth.py            bearer token -> role (hmac.compare_digest); no token echoing
│   ├── db.py               separate mv.db / identity.db; forward-only migrations; WAL
│   ├── models.py          campaign/guide/participant/response validation, enums, transitions
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
│   └── api.py             Phase 1 + Phase 2 routes
└── tests/
```

Storage: `merchant-voice/data/mv.db` (campaigns, guides, questions, participants, responses, raw answers, transcript metadata, CSV import tokens, audit — operational, authoritative for Merchant Voice's own domain) and `merchant-voice/data/identity.db` (a **separate file** holding only merchant identity + its own audit log, for least-privilege separation from research content) plus `merchant-voice/data/transcripts/` (transcript text files, not web-served, never joined into any DB row). All gitignored; nothing here is authoritative Part A evidence, a Part B scorecard, an assumption, or impact state — those systems are untouched by this service.

## Shared provider package (Gate E)

The model-provider abstraction (`ConversationModel`, `ModelResponse`, `ProviderError`, `MockProvider`, `AnthropicProvider`, `make_provider`) lives canonically in **`shared/llm/provider.py`**, imported directly by both this service and `copilot-backend` (whose `app/provider.py` is now a thin re-export shim for backward compatibility). No new provider logic is duplicated. Phase 2 never imports or calls the provider layer at all — it only implements the *gate* a future Phase 3 extraction step will have to pass.

## Privacy design (Phase 2)

- **Identity separation:** merchant identity (consent, permitted use, quote/AI-processing permission, retention/deletion timestamps) lives only in `identity.db`; participants in `mv.db` reference it by ID and may only **narrow**, never widen, its grant.
- **Consent gate:** enforced before any future AI call could ever happen — consent granted, not suppressed, retention not expired, `ai_processing_permission` true, and every answer's redaction `complete`.
- **Redaction is a floor, not a ceiling:** deterministic regex-based detection of phone/email/IBAN/account numbers, a small set of name-introduction patterns, and explicitly-flagged entity strings — it does not claim perfect PII detection.
- **Suppression:** withdrawal blocks read access without deleting storage; retention-expiry and deletion-requests purge raw content and schedule transcript deletion. Transcript deletion is never claimed atomic with the DB commit — a failure leaves it `pending_deletion`/`deletion_failed` for a maintenance retry, and no transcript content or file path is ever logged or audited.

## Security (Phase 1 + Phase 2)

Mandatory bearer-token auth with four roles (`viewer < researcher < reviewer < admin`) — **viewer has no access at all** to any Phase 2 route; `hmac.compare_digest` comparison; token values never logged, returned, or exposed; CORS restricted to the configured frontend origin; request-body size cap plus CSV (2 MB) and transcript (1 MB) specific limits; bounded concurrency; parameterized SQL only; CSV cells defensively neutralized against spreadsheet formula injection; transcript filenames are server-generated only; structured JSON errors with no stack traces; no shell/code execution anywhere.

## Tests

```bash
python3 -m unittest discover merchant-voice/tests
```

All offline; all fixtures use synthetic IDs (`MVC-TEST-…`, `MVG-TEST-…`, `MVP-…`, `MVR-…`) only — no real merchant data anywhere in source, fixtures, or examples.
