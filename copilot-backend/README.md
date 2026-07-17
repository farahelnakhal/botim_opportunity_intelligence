# Copilot Backend — BOTIM Product Discovery Copilot (read-only)

Conversational HTTP JSON API for product-discovery questions: which segment, what pain, what evidence, what's assumed, what changed, what to validate next. **Pure Python 3 standard library — nothing to install.**

The repository is the copilot's evidence and decision-support layer. All facts (scores, classifications, confidence, assumption counts, evidence roles, citations) are computed deterministically from the existing engines and read models — the model writes prose only. The backend is **read-only**: no evidence/segment/scorecard/assumption/impact/monitoring mutation, no email, no shell, no file paths from the model. Chat-generated drafts are ephemeral.

## Run

```bash
cp copilot-backend/.env.example copilot-backend/.env   # fill in BOTIM_LLM_API_KEY (+MODEL; never commit)
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
                        research-request/history, monitoring outputs) PLUS
                       app/mv_tools.py — read-only Merchant Voice tools
  → provider.py        provider-neutral ConversationModel (Anthropic | mock);
                       bounded tool loop (max 3 iterations, dedupe)
  → grounding.py       deterministic facts, citations, confidence, unknowns
  → wordguard.py       overclaim validation (falls back to grounded text)
  → store.py           SQLite conversation memory (gitignored data/; not evidence)
```

### Merchant Voice tools (Phase 5)

`app/mv_tools.py` exposes 12 read-only tools (`list_merchant_campaigns`, `get_merchant_campaign`, `get_campaign_summary`, `get_approved_merchant_findings`, `get_segment_feedback`, `get_opportunity_merchant_feedback`, `get_assumption_feedback`, `get_merchant_objections`, `get_merchant_workarounds`, `get_merchant_quotes`, `compare_segment_feedback`, `get_campaign_limitations`) that read `merchant-voice/data/mv.db` through a genuinely **read-only** SQLite connection (`mode=ro` — a write attempt raises, it isn't merely a convention) via `merchant-voice/app/published_query.py`, Merchant Voice's own read-only, Copilot-facing query layer. **Never opens `identity.db`.** Only approved, published, non-superseded, non-suppressed, consent/retention-valid content ever surfaces — no unreviewed observations, no draft proposals, no researcher-only review notes, no raw transcripts, no identity fields.

A returned Merchant Voice finding is a research signal, not authoritative Part A evidence — the Copilot never mints an EV ID, never proposes a score/assumption/impact change, and never presents a `concept_reaction` finding as proof of pain, frequency, or willingness to pay. Citations use the new `merchant_finding` type (`/merchant-findings/{id}`, additive — see `shared/contracts/conversation-api.schema.md`).

Because Merchant Voice's `app` package and this backend's own `app` package share a name, `mv_tools.py` loads Merchant Voice's package under the distinct alias `mv_app` (never the bare name `app`) — see that module's docstring.

### New-opportunity analysis (Integration Phase 2)

`new_opportunity_analysis` handles a genuinely new product/opportunity with no `OPP-`
record yet — selected deterministically when the conversation is new, no explicit
OPP/EV/SEG/ASM/MVC id is present, and no opportunity/segment is already selected (see
`intents.classify`). It reuses existing read-only tools only — `search_product_knowledge`
(now also covering competitor profiles and inflection points), `get_evidence_gaps`,
`get_recent_changes`, `get_approved_merchant_findings` — never a new write path, never a
vector index. **No numeric score, composite, or classification is ever computed for a new
idea** (the scoring engine requires a real, committed scorecard, which a brand-new idea
never has); if nothing relevant is found, `unknowns` says so explicitly. See
`shared/contracts/conversation-api.schema.md` for the response shape and
`tests/test_new_opportunity_analysis.py` for the behavioral tests.

### Frontend wiring (Integration Phase 2)

`executive-ui/web` now calls this backend directly for all conversational requests
(`lib/copilotApi.ts`) — dashboard reads still go to `executive-ui/api` (`lib/api.ts`).
See `executive-ui/README.md`, "Two backends, one frontend", for local run instructions
and `executive-ui/deploy/start.sh` for the single-container deploy path.

## Security defaults

Localhost bind (non-local requires `COPILOT_API_TOKEN`); CORS restricted to the configured UI origin; body/message-length limits; bounded concurrency; strict ID validation on every tool argument; no state-changing tools exist in the registry; `safe_tool_trace` empty unless `COPILOT_DEBUG_TRACE=1`; keys only from env, never logged.

## Tests

```bash
python3 -m unittest discover copilot-backend/tests
```

Offline and deterministic (MockProvider); includes a module-level checksum proving chat operations modify no knowledge-base/UI/contract sources. The live-provider smoke runs only with `ANTHROPIC_API_KEY` **and** `COPILOT_RUN_LIVE_TESTS=1`.
