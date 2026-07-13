# Copilot Backend — BOTIM Product Discovery Copilot (read-only)

Conversational HTTP JSON API for product-discovery questions: which segment, what pain, what evidence, what's assumed, what changed, what to validate next. **Pure Python 3 standard library — nothing to install.**

The repository is the copilot's evidence and decision-support layer. All facts (scores, classifications, confidence, assumption counts, evidence roles, citations) are computed deterministically from the existing engines and read models — the model writes prose only. The backend is **read-only**: no evidence/segment/scorecard/assumption/impact/monitoring mutation, no email, no shell, no file paths from the model. Chat-generated drafts are ephemeral.

## Run

```bash
cp copilot-backend/.env.example copilot-backend/.env   # fill in ANTHROPIC_API_KEY (never commit)
set -a; source copilot-backend/.env; set +a
python3 copilot-backend/server.py
# → http://127.0.0.1:8010  (binds localhost only by default)
```

Keyless local development / demos: `COPILOT_PROVIDER=mock python3 copilot-backend/server.py` (deterministic grounded answers, zero network).

## API

See **`shared/contracts/conversation-api.schema.md`** (the contract Farah's UI consumes — endpoints, request/response shapes, citation objects, errors, lifecycle, CORS/auth, fetch example). Quick check:

```bash
curl -s http://127.0.0.1:8010/api/chat -H 'Content-Type: application/json' \
  -d '{"conversation_id": null, "message": "Why is OPP-013 still unvalidated?"}'
```

## Architecture

```
POST /api/chat → api.py → orchestrator.py
  → security.py        validation + refusal of state-changing/injection requests
  → intents.py         deterministic product-discovery intent + initial tool plan
  → tools_registry.py  allowlisted read-only tools over EXISTING engines
                       (scoring, evidence parser, impact tracker/gaps/brief/
                        research-request/history, monitoring outputs)
  → provider.py        provider-neutral ConversationModel (Anthropic | mock);
                       bounded tool loop (max 3 iterations, dedupe)
  → grounding.py       deterministic facts, citations, confidence, unknowns
  → wordguard.py       overclaim validation (falls back to grounded text)
  → store.py           SQLite conversation memory (gitignored data/; not evidence)
```

## Security defaults

Localhost bind (non-local requires `COPILOT_API_TOKEN`); CORS restricted to the configured UI origin; body/message-length limits; bounded concurrency; strict ID validation on every tool argument; no state-changing tools exist in the registry; `safe_tool_trace` empty unless `COPILOT_DEBUG_TRACE=1`; keys only from env, never logged.

## Tests

```bash
python3 -m unittest discover copilot-backend/tests
```

Offline and deterministic (MockProvider); includes a module-level checksum proving chat operations modify no knowledge-base/UI/contract sources. The live-provider smoke runs only with `ANTHROPIC_API_KEY` **and** `COPILOT_RUN_LIVE_TESTS=1`.
