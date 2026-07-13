# Merchant Voice & Validation — backend (Phase 1: foundation)

> **PROTOTYPE-GRADE AUTHENTICATION. SYNTHETIC-DATA-ONLY. NOT APPROVED FOR REAL MERCHANT DATA. NOT FOR PRODUCTION USE.**
> This service uses a static token→role map compared with `hmac.compare_digest` — it is **not** production identity/access management (no user directory, no session revocation, no token rotation, no TLS termination). Real merchant data requires a separate privacy/security review and a hardened deployment before use.

A human-reviewed research-to-evidence pipeline for BOTIM merchant feedback: research campaigns and guides → (Phase 2+) merchant responses → AI-assisted extraction → human review → evidence candidates → approved findings → a **proposal** for Part A evidence (never an authoritative write). **Pure Python 3 standard library — nothing to install**, matching the rest of the repository.

## Phase 1 scope (this delivery)

Implemented: shared provider wiring, configuration, mandatory token/role auth, the `mv.db`/`identity.db` schema foundation, **campaigns** and **research guides** only.

**Not yet implemented** (later phases): participants, merchant identity storage, responses, raw answers, CSV import, transcript ingestion, redaction, AI extraction, observation review, evidence candidates, findings, aggregation/analysis, Part A proposal preview, synthetic export, Copilot Merchant Voice tools.

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
curl -s -X POST http://127.0.0.1:8020/api/merchant-voice/campaigns \
  -H "Authorization: Bearer $RESEARCHER_TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"MVC-TEST-001 pilot","objective":"Understand supplier-payment pain","method":"interview","data_classification":"synthetic"}'
```

## Architecture

```
merchant-voice/            (separate process, port 8020, own storage — Gate A/B)
├── server.py              stdlib HTTP server; refuses to start without MV_TOKENS
├── app/
│   ├── config.py          env-driven config; synthetic_only defaults ON
│   ├── auth.py            bearer token -> role (hmac.compare_digest); no token echoing
│   ├── db.py               separate mv.db / identity.db; forward-only migrations; WAL
│   ├── models.py          campaign & guide validation, enums, transitions
│   ├── audit.py           append-only audit_events (hashes/safe diffs only)
│   ├── campaigns.py       campaign service (Phase 1)
│   ├── guides.py          versioned, immutable-once-approved research guides (Phase 1)
│   └── api.py             Phase 1 routes only
└── tests/
```

Storage: `merchant-voice/data/mv.db` (campaigns, guides, questions, audit — operational, authoritative for Merchant Voice's own domain) and `merchant-voice/data/identity.db` (schema only in Phase 1; participant/identity tables land in Phase 2, in a **separate file** for least-privilege separation from research content). Both gitignored; nothing here is authoritative Part A evidence, a Part B scorecard, an assumption, or impact state — those systems are untouched by this service.

## Shared provider package (Gate E)

The model-provider abstraction (`ConversationModel`, `ModelResponse`, `ProviderError`, `MockProvider`, `AnthropicProvider`, `make_provider`) now lives canonically in **`shared/llm/provider.py`**, imported directly by both this service and `copilot-backend` (whose `app/provider.py` is now a thin re-export shim for backward compatibility). No new provider logic is duplicated.

## Security (Phase 1)

Mandatory bearer-token auth with four roles (`viewer < researcher < reviewer < admin`); `hmac.compare_digest` comparison; token values never logged, returned, or exposed (only label/role/enabled via any future introspection endpoint); CORS restricted to the configured frontend origin; request-body size cap; bounded concurrency; parameterized SQL only; structured JSON errors with no stack traces; no shell/code execution anywhere.

## Tests

```bash
python3 -m unittest discover merchant-voice/tests
```

All offline; all fixtures use synthetic IDs (`MVC-TEST-…`, `MVG-TEST-…`) only — no real merchant data anywhere in source, fixtures, or examples.
