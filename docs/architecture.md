# Architecture — BOTIM Opportunity Intelligence

> Verified against `main` @ `38dee97` (2026-07-15). Update when service boundaries or
> trust boundaries change.

## System map

```
executive-ui/web  (React + TS + Vite, port 5173 dev)
   │  /executive-api/*                      │  /copilot-api/*
   ▼                                        ▼
executive-ui/api/server.py (8000)   ──proxy──▶  copilot-backend/server.py (8010)
   read-only dashboard API +                     grounded conversational API
   user-opportunity store +                        │ read-only tools
   static host + fixed-dest proxy                  ▼
   │                                   engines + knowledge base + mv.db (ro)
   ▼
executive-ui/adapter/collect.py  ← single read-only adapter over engine output
   │
   ▼
opportunity-intelligence/ · customer-intelligence/ · intelligence-monitoring/
impact/ · knowledge-base/ (committed, Git, read-only at runtime)

merchant-voice/server.py (8020) — separate service, own storage (mv.db + identity.db)
```

All backends are **pure Python 3 stdlib** (nothing to pip-install). The frontend is the
only Node dependency surface.

## Components

### executive-ui/web — React frontend (primary UI)
- Chat-first project workspace; design system in `src/index.css` (theme-aware CSS
  variables, dark mode). State in `src/store.tsx` (localStorage persistence for
  conversations + copilot conversation-id mappings).
- Two API clients: `lib/api.ts` (executive dashboard) and `lib/copilotApi.ts`
  (copilot; one-shot stale-conversation retry; `runtime_mode` passthrough).
- Safe rendering: `components/Markdown.tsx` (react-markdown + remark-gfm, no raw
  HTML, unsafe protocols inert), `lib/safeUrl.ts` (http(s)-only links).
- Shared answer renderer `components/AssistantAnswer.tsx` (demo-mode badge,
  honest-unavailable banner, citations).
- Minimal pushState routing incl. `/report/{OPP-nnn|UOPP-…}` (`components/Report.tsx`),
  refresh/direct-navigation safe via SPA fallback on the API's static host.
- `seed.json` offline fallback is **demo builds only** (`VITE_APP_MODE=demo`); normal
  builds show honest unavailable/empty states.

### executive-ui/api — read-only dashboard API + user store (port 8000)
- Read-only over the knowledge base: GET routes read engine output via
  `adapter/collect.py` and `api/serialize.py`. No route mutates the KB.
- **Application modes** (`api/modes.py`): `BOTIM_APP_MODE=normal|demo|test`, default
  `normal`, invalid → normal (never silently demo). Backend is the source of truth;
  reported as `meta.app_mode` in `/overview`. Normal mode hides the demo corpus
  (404s on demo detail routes) while keeping the evidence corpus available to the
  copilot.
- **User opportunities** (`api/user_store.py`): runtime SQLite at
  `USER_OPPORTUNITIES_DB_PATH` (default `runtime/user-opportunities.db`, gitignored).
  `UOPP-<12hex>` ids (collision-proof vs committed `OPP-nnn`); lifecycle
  draft → saved → archived with restore; deletion policy enforced (drafts delete;
  saved must archive; archived delete needs `?confirm=archived`); optimistic version
  locking (409 on stale writes); bounded fields; parameterized SQL.
- **Monitoring configs** (`MCFG-<12hex>`): per-UOPP intent-only configuration
  (cadence manual|daily|weekly|monthly, topics/keywords/entities/domains) with
  pause/resume/remove. **No runner/scheduler exists** — enabled configs are honestly
  `never_run` ("Configured — awaiting monitoring run"); no events fabricated.
- **Copilot proxy**: `/copilot-api/*` forwards to fixed `COPILOT_UPSTREAM_URL`
  (never caller-supplied), 30s timeout, body-size 413 pre-check before buffering,
  forwards Authorization without logging it.
- **Legacy** ungrounded `/chat` + `/analyze` (pre-Phase-2 scaffold in `generate.py` /
  `router.py`): disabled by default, opt-in via `ENABLE_LEGACY_UNGROUNDED_ROUTES=1`.
  Nothing in the normal UI falls back to them.

Route inventory (each also under the `/executive-api/` alias):

| Group | Routes |
|---|---|
| Engine read-only (GET) | `/overview`, `/opportunities/OPP-nnn`, `/commercial/OPP-nnn`, `/experiments`, `/journal`, `/monitoring`, `/monitoring/summary/{event_id}`, `/brief/{OPP-nnn\|UOPP-…}` |
| User opportunities | `GET/POST /user-opportunities`, `GET/PATCH/DELETE /user-opportunities/{id}`, `POST …/archive`, `POST …/restore` |
| Monitoring config | `GET/PUT/DELETE …/{id}/monitoring`, `POST …/monitoring/pause`, `POST …/monitoring/resume` |
| Copilot proxy | `GET/POST/DELETE /copilot-api/*` |
| Legacy (opt-in) | `GET/POST /chat`, `/analyze` |
| Static | everything else from `web/dist`, SPA fallback |

### copilot-backend — grounded conversational API (port 8010)
Pipeline (`app/`): `api.py` → `orchestrator.py` → `security.py` (validation, injection
refusal) → `intents.py` (deterministic intent + tool plan; `new_opportunity_analysis`
requires positive new-product evidence; greetings → clarification) →
`tools_registry.py` (allowlisted read-only tools over existing engines) + `mv_tools.py`
(12 read-only Merchant Voice tools via `published_query`, `mode=ro` SQLite, never
`identity.db`) → `provider.py` → `grounding.py` (deterministic facts, citations,
confidence, freshness warnings) → `wordguard.py` (overclaim guard) → `store.py`
(SQLite conversation memory, gitignored — not evidence).

Contract: `shared/contracts/conversation-api.schema.md` (versioned, additive-only).
Key behaviors: `conversation_not_found` (404) error for stale conversations;
`runtime_mode` field (`deterministic_demo` for MockProvider vs `live_model`);
`context.user_opportunity` sanitized server-side and grounded as clearly labelled
USER-PROVIDED fields, never written back. New-opportunity analysis never computes a
numeric score/classification for an uncommitted idea.

### shared/ — integration layer
- `llm/provider.py` — **the single provider abstraction** (`ConversationModel`):
  AnthropicProvider + deterministic MockProvider (zero network, echoes grounded
  facts). Used by copilot-backend and merchant-voice. Never bypass it.
- `freshness.py` — deterministic evidence-freshness bands (fresh ≤90d, aging ≤180d,
  stale >180d, unknown) and reference-date priority. Pure date math.
- `source_urls.py` — http(s)-only source-link policy (backend half of the defense
  in depth with `web/src/lib/safeUrl.ts`).
- `contracts/*.schema.md` — the API contracts (conversation, user-opportunities,
  monitoring-event, merchant-voice, brief, etc.).
- `integration_check.py` — the 10-step pre-merge gate.

### Engines + knowledge base (the "combined agent" layer)
- `knowledge-base/` — committed Markdown records (EV/SEG/IP/OPP/MVC/VE/REQ/EVT ids).
  **Read-only at runtime; changes land only via Git commits** (human-approved).
  Ownership boundaries in `WORKSTREAMS.md`; behavior rules in `MASTER_PROMPT.md` and
  the per-module `SYSTEM_PROMPT.md`s.
- `opportunity-intelligence/tools/` — scoring engine (17 dimensions, raw/85,
  assumption caps: fully-assumed ideas can never classify above "promising"),
  evidence parser (with Phase 4 provenance), stress tests, sync bridge.
- `customer-intelligence/tools/` — evidence conformance checker etc.
- `intelligence-monitoring/tools/` — KB change watcher, tiering, alerting; one
  external adapter (`adapter_regulator.py`, injectable network, offline-testable).
- `impact/` — evidence-impact workflow, gaps, briefs, research requests; writes only
  via its own CLI with `--approver` (human approval).

### merchant-voice — research-to-evidence pipeline (port 8020, prototype)
Synthetic-data-only, static-token auth, own storage (`mv.db` operational +
`identity.db` identity, never exposed). Pipeline: campaigns → participants/responses
(consent-gated, redacted) → AI-assisted extraction (via shared provider) → human
review → evidence candidates → immutable approved findings → non-authoritative Part A
proposals → synthetic-only export to `knowledge-base/customer-evidence/
merchant-voice-candidates/` (never `records/`, never an EV id). The copilot reads
approved+published findings only, through `published_query.py`.

## Trust boundaries (verified)

1. **Committed KB is read-only at runtime.** No HTTP route writes it. Authoritative
   changes are human Git commits (or the impact CLI with an approver).
2. **User drafts ≠ authoritative knowledge.** UOPP records live in runtime SQLite,
   labelled USER-PROVIDED when grounding chat; never promoted automatically.
3. **Candidate vs approved evidence.** Merchant Voice findings and monitoring
   evidence-candidates require human review; nothing mints EV ids automatically.
4. **Model output is untrusted.** Grounding computes facts deterministically;
   wordguard validates wording; extraction output is validated against source text;
   markdown/URLs are sanitized on both ends; external content is data, never
   instructions (MASTER_PROMPT non-negotiable #6).
5. **Backend is the mode authority.** Frontend displays `meta.app_mode`; build-time
   `VITE_APP_MODE` only gates the offline demo seed.
6. **Fixed-destination proxy.** `/copilot-api` never honors caller-supplied upstreams;
   copilot binds localhost by default and refuses non-local binds without a token.
7. **Merchant identity isolation.** `identity.db` is never opened by the copilot path;
   published_query exposes only approved, consent-valid, redacted content.
8. **Provider abstraction.** All LLM calls go through `shared/llm/provider.py`;
   MockProvider keeps every test and demo offline and deterministic.

## Deployment

Single container (`executive-ui/deploy/Dockerfile` + `start.sh`): builds the React
app, runs copilot-backend (localhost-only) behind the executive API's proxy on one
origin. `start.sh` supervises both processes (readiness-gated startup, signal
forwarding, non-zero exit on required-service failure). The image defaults to
NORMAL mode; the demo showcase is an explicit `--build-arg APP_MODE=demo`
build, and a normal-mode deployment running on the mock chat provider prints
a loud startup warning (never a silent fallback). Lifecycle tests: `executive-ui/deploy/tests/`.

## Future research architecture (not yet built — direction only)

Live external research, when implemented, must be a **reusable platform capability**
(see `docs/roadmap.md`): structured research plans, objective-based queries, provider
adapters, bounded/safe retrieval, normalized source metadata, quality signals,
dedup/contradiction detection, persisted research runs with partial/failed states,
and claim→source→run traceability — feeding **candidate** evidence only, never
silently promoted into the committed KB. The natural seams already exist: the
provider abstraction (`shared/llm`), the freshness/source-url modules, the
monitoring-config records awaiting a runner (`MCFG-`), and the candidate-evidence
patterns established by Merchant Voice and monitoring.
