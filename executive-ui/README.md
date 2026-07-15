# Executive UI — BOTIM Product Discovery Copilot

A read-only, executive-facing view over the three workstreams' committed outputs. It answers: what opportunities are we investigating, which segment, what evidence supports each, what assumptions remain, what changed, why a score changed, what to do next — and, prominently, **whether anything has been validated or selected (it has not).**

There are two front-ends over the **same read-only adapter** (`adapter/collect.py`, the single source of truth):

1. **`web/` — a modern React + TypeScript assistant** (the primary UI): a chat-first, project-workspace interface matching the approved design mockup, wired to a live Python JSON API.
2. **stdlib static site** (`build.py` + `render/`): a zero-dependency server-rendered fallback/export.

## Two backends, one frontend (Integration Phase 2)

The React app talks to **two** independent backends over two explicit, non-overlapping
prefixes — never one ambiguous shared `/api`:

- **`/executive-api/*`** → `executive-ui/api/server.py` (port **8000** locally) — read-only
  dashboard data: overview, commercial models, experiments, journal/reports, monitoring,
  and the legacy `/analyze` + `/chat` compatibility endpoints (see "generate.py" below).
- **`/copilot-api/*`** → `copilot-backend/server.py` (port **8010** locally) — the
  conversational, grounded copilot: chat, follow-ups, new-product analysis, Merchant
  Voice questions, citations. This is the only backend the chat UI calls.

Both prefixes are environment-configurable on the frontend (`VITE_EXECUTIVE_API_BASE_URL`,
`VITE_COPILOT_API_BASE_URL` — see `web/.env.example`); left unset they default to the
relative paths above, which work with both the Vite dev-server proxy (`web/vite.config.ts`)
and a single-origin production deploy.

## Run the assistant (React app + both APIs)

```bash
# 1. read-only dashboard API over the engines (stdlib only)
python3 executive-ui/api/server.py --port 8000

# 2. the conversational copilot backend — runs without any key using the
#    deterministic MockProvider (never fabricates; see copilot-backend/README.md)
COPILOT_PROVIDER=mock python3 copilot-backend/server.py
#    …or with a real Anthropic key instead:
# ANTHROPIC_API_KEY=sk-ant-… python3 copilot-backend/server.py

# 3. React dev server (proxies /executive-api → :8000, /copilot-api → :8010)
cd executive-ui/web && npm install && npm run dev      # http://localhost:5173

# --- or a single-process deploy (see executive-ui/deploy/start.sh) ---
cd executive-ui/web && npm run build                    # emits web/dist
executive-ui/deploy/start.sh                             # runs both backends; serves web/dist
```

## Application modes, user opportunities, monitoring setup (Phases 5–7)

Full contract: `shared/contracts/user-opportunities.schema.md`.

- **`BOTIM_APP_MODE=normal|demo|test`** (default `normal`) — the backend is
  the source of truth and reports the effective mode in
  `GET /executive-api/overview` → `meta.app_mode`. Normal mode serves no
  synthetic demo portfolio (clean empty state, no fake identity/recipients);
  demo mode serves the committed corpus clearly labelled ("Demo data" badge);
  test mode exists for deterministic tests. Start the demo showcase with
  `BOTIM_APP_MODE=demo python3 executive-ui/api/server.py` (the deploy
  Dockerfile pins this); leave unset for normal mode. Demo **frontend builds**
  also set `VITE_APP_MODE=demo`, which only gates whether the bundled demo
  seed may act as an offline fallback — normal builds show an honest
  unavailable/empty state when the API is down, never demo data.
- **User opportunities** persist in a runtime SQLite DB
  (`USER_OPPORTUNITIES_DB_PATH`, default `runtime/user-opportunities.db`,
  gitignored — never inside the committed knowledge base). Lifecycle:
  `draft → saved → archived` (drafts deletable; saved records archive
  instead; archived delete only with explicit confirmation). CRUD under
  `/executive-api/user-opportunities`; the web report route supports
  `/report/UOPP-…` with honest partial sections.
- **Monitoring setup** (per user opportunity): editable suggested topics,
  cadence (`manual|daily|weekly|monthly` — intended configuration only, no
  scheduler yet), pause/resume/remove. No runner is connected yet, so an
  enabled configuration is honestly labelled "Configured — awaiting
  monitoring run"; no events are fabricated.

If the dashboard API is unreachable, the React app falls back to a bundled snapshot of
**real** engine output (`web/src/seed.json`) for *dashboard* reads only — it always
renders truthful data and never fabricates. If copilot-backend is unreachable, the chat
UI shows an honest "grounded analysis is temporarily unavailable" message instead —
it never silently substitutes seed data, the deterministic router, or the legacy
direct-LLM scaffold for a live chat response (see "generate.py" below).

### `executive-ui/api/generate.py` and `router.py` — legacy/compatibility only

Before Integration Phase 2, `generate.py` (a direct-LLM scaffold with no tool retrieval)
answered "new analysis" requests, and `router.py` (a deterministic keyword router)
answered existing-opportunity questions. **The chat UI no longer calls either
automatically.** copilot-backend's grounded `new_opportunity_analysis` intent and its
existing per-record intents now own both flows. Both old endpoints remain reachable
directly (`POST /executive-api/analyze`, `GET|POST /executive-api/chat`) as an explicit,
disclosed compatibility path — e.g. for scripts or a future non-conversational dashboard
widget — but nothing in the normal UI falls back to them silently.

## Run the static site (no Node needed)

```bash
python3 executive-ui/build.py            # render static HTML into executive-ui/dist/
python3 executive-ui/build.py --serve    # build, then serve dist/ at http://localhost:8000
```

`dist/`, `web/node_modules/` and `web/dist/` are gitignored; only source is committed.

## The read-only JSON API (`api/`)

`GET`-only, stdlib `http.server`, no write routes — it cannot mutate scorecards, evidence, the KB, or impact state:

| Endpoint | Returns |
|---|---|
| `/api/overview` | opportunities (17 factors each), archived, evidence, assumptions, feed, briefs |
| `/api/opportunities/OPP-nnn` | one opportunity |
| `/api/commercial/OPP-nnn` | commercial model (downside/base/upside) from committed inputs |
| `/api/experiments` | VE specs with pre-committed success/kill thresholds |
| `/api/journal` | decision-journal predictions + calibration (Brier) |
| `/api/monitoring` | monitoring events, alerts, summaries |
| `/api/chat?q=…` | deterministic intent router → progress stages + typed cards |
| `/api/analyze?q=…` | on-demand analysis of ANY opportunity → generated scorecard + research plan |

The assistant auto-routes each prompt (`api/router.py`) to the right read-model; the user never picks a module. Routing is rule-based and transparent — no LLM, no hidden state, no fabrication.

## Analyze any opportunity (new conversation)

A **new conversation** from the Home screen runs a fresh customer-search + opportunity analysis for whatever you describe — any market, not just the committed SME set. It produces a new "analysis" project with a segment, job-to-be-done, hypothesis, a full 17-dimension scorecard, evidence gaps, and a non-leading customer-research plan.

Honesty is enforced **by construction** (`api/generate.py`), not by trusting the model:

- Every dimension of a generated scorecard is `assumption = true` (there is no evidence yet), so the **real engine** (`opportunity_engine.scoring.evaluate`) caps it at *"promising (unvalidated)"* — a generated opportunity can never come out "strong", and confidence is always "low".
- The engine, not the LLM, computes the composite, assumption count, and critical flags.
- Nothing is written to the knowledge base — the analysis is ephemeral.

**Engine selection** — chosen automatically in this order:

1. **Anthropic (cloud, needs a key)** — set `ANTHROPIC_API_KEY`.
2. **Local model, NO API KEY** — any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM). Set `BOTIM_LLM_BASE_URL`.
3. **Deterministic offline scaffold** — no setup at all; a labelled frame to run the analysis yourself.

| Env var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(unset)* | Use Claude (cloud). |
| `BOTIM_ANALYSIS_MODEL` | `claude-sonnet-5` | Claude model. |
| `BOTIM_LLM_BASE_URL` | *(unset)* | OpenAI-compatible local endpoint, e.g. `http://localhost:11434/v1` for Ollama. **No key needed.** |
| `BOTIM_LLM_MODEL` | `llama3.1` | Local model name. |
| `BOTIM_ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Override the Anthropic base URL. |

```bash
# Option 1 — cloud (needs a key)
export ANTHROPIC_API_KEY=sk-ant-...

# Option 2 — local, NO API KEY (run a model on your own machine)
#   ollama pull llama3.1 && ollama serve
export BOTIM_LLM_BASE_URL=http://localhost:11434/v1
export BOTIM_LLM_MODEL=llama3.1

python3 executive-ui/api/server.py --port 8000

# verify which engine actually answers (works for all three):
python3 executive-ui/api/server.py --check-llm "Invoice financing for UAE logistics SMEs"
```

**Conversation memory.** Follow-up questions inside a generated analysis send the full conversation history to the model, so it refines the same opportunity in context (e.g. "now focus on Saudi Arabia" updates the segment, market, and scores). Conversations and generated analyses are persisted in the browser (`localStorage`), so they survive a page reload.

## Deploy for free (a public link, no paid API key, no card)

`executive-ui/deploy/Dockerfile` bundles the built React app and the
read-only API into one lightweight container (no local model — small enough
to run comfortably on any free tier). AI analysis of new opportunities is
delegated to a **free, hosted, OpenAI-compatible LLM API** at runtime instead
of self-hosting a model — self-hosting an actual model (e.g. Ollama) for free
turns out to be impractical: every free Docker-capable host either requires a
card on file for verification (Hugging Face Docker Spaces, Fly.io, GCP,
Oracle) or gives too little RAM to run it reliably. Using a hosted API
sidesteps that entirely.

**Recommended stack — both steps are genuinely free, no card, ~10 minutes:**

1. **LLM: [Groq](https://console.groq.com)** — sign up (email only, no
   card *as far as we could confirm — if it asks you for one, stop and tell
   us, we'll switch providers*), then **API Keys → Create API Key**. Copy it.
2. **Hosting: [Render](https://render.com)** — sign up, then **New + →
   Blueprint**, connect this GitHub repo. Render reads `render.yaml` at the
   repo root automatically and asks you to fill in:
   - `BOTIM_LLM_API_KEY` = the Groq key from step 1
   - `ANTHROPIC_API_KEY` — leave blank (that's the alternative, paid path)

   Click **Apply**. Render builds the Docker image and gives you a public
   URL like `https://botim-opportunity-intelligence.onrender.com` — share
   that link with anyone.

Render auto-redeploys on every push to your connected branch. Honest
tradeoffs: the free web service **sleeps after ~15 minutes of inactivity**
(the next visitor waits ~30-60s for it to wake), and it's one shared
lightweight instance, not built for heavy concurrent traffic — fine for a
team or a demo, not for a public launch.

Every honesty guarantee still holds: the **real scoring engine**, not the
LLM, computes and caps every generated opportunity (never "strong", always
"low confidence" — see "Analyze any opportunity" above).

**Alternative model providers.** Swap `BOTIM_LLM_BASE_URL`/`BOTIM_LLM_MODEL`
in `render.yaml` (or the Render dashboard) for any other OpenAI-compatible
endpoint — a self-hosted Ollama if you later get access to a Docker-capable
host, or a different free/paid provider.

**If you *do* get Docker-Space access on Hugging Face later** (e.g. after
card verification), `executive-ui/deploy/space_readme.md` and
`.github/workflows/deploy-huggingface.yml` still work unchanged — same
Dockerfile, same environment variables, auto-mirrored from this repo on push
to `main` (needs repo secret `HF_TOKEN` + variable `HF_SPACE`; see that
workflow file for details).

## Plain-language UI (no codes)

The interface is written for a non-technical audience: internal identifiers (opportunity, evidence, experiment, segment, and prediction codes) never appear on screen. Opportunities are shown by name, evidence by its title, experiments by their title, and monitoring "affected" items are mapped back to opportunity names (`web/src/lib/labels.ts`). The identifiers still exist in the engines and API — they're just not surfaced in the UI.

## Architecture (read-only, single source of truth)

```
repository outputs ──► adapter/collect.py ──► UIModel ──► render/*.py ──► static HTML + app.css/app.js
   (scorecards,          (reuses B's scoring,     (dataclasses)   (server-rendered,
    evidence, backlog,    evidence, backlog,                       stdlib string
    journal, monitoring)  journal + C's monitoring                templating)
                          engines — NO recompute)
```

- **No second scoring engine.** The adapter calls `opportunity_engine.scoring.evaluate` etc.; the UI never recalculates scores or reinterprets confidence.
- **Never writes to the knowledge base.** Reads only; the sole output is `dist/`.
- **No invented data.** Missing fields render as "—"; empty inputs render honest empty states.

## Screens

Overview · Opportunity Detail (all 17 factors, never hidden) · Evidence Traceability (weak evidence visually separated as "leads, not findings") · Assumptions & Gaps (client-side filtering) · Intelligence Feed · Rescore Review (read-only) · Executive Brief (consumes recommendation docs).

## Honest scope notes (features the brief assumed that don't exist yet)

- **No impact-proposal / approval / rollback workflow exists** in the system. Screens 5–6 are read-only and show the closest real analogue (monitoring alerts / report-only rescore suggestions); **no fake approval controls** are rendered.
- **No executive-brief generator exists** — the Brief screen consumes committed recommendation docs where present (currently OPP-001) and shows honest empty states elsewhere.
- **Assumption status/sensitivity/owner and per-factor score history are not structured fields** — derived where possible, shown as "—" otherwise.

## React app structure (`web/src`)

```
lib/api.ts        typed client (live API + real-data seed fallback)
lib/format.ts     presentation helpers (no score computation)
store.tsx         app state: theme, view, active opportunity, per-project conversations
types.ts          mirrors the API payloads
components/
  Sidebar, Home, Updates, ProjectWorkspace, Drawer, Chat
  cards.tsx       OpportunityCard, Scorecard (17 dims), CommercialModel, Experiment,
                  MonitoringAlert, DecisionJournalEntry, ExecutiveSummary, Evidence, Banner
  panels.tsx      Knowledge · Experiments · Reports · Monitoring · Files · Sources · Settings
  Icon, ScoreRing, Collapsible
```

Design system (tokens, sidebar, cards, drawer, chat) lives in `src/index.css` as theme-aware CSS variables mirroring the mockup; Tailwind is available for utilities. The score ring shows the engine's own `raw/max` proportion — it never invents a 0–100 score. There is **no approval button**: score changes go through the impact CLI (`apply-impact --approver`), stated plainly in Settings.

## Tests

```bash
python3 -m unittest discover -s executive-ui/tests       # adapter + static-render tests
python3 -m unittest discover -s executive-ui/api/tests   # read-only API + router tests
cd executive-ui/web && npm run build                     # type-checks + bundles the React app
```

Adapter correctness, render/empty-state tests, weak-vs-strong evidence display, score before/after, the "no affirmative validated/selected claim" guard, and the EV-TEST-001 synthetic scenario in an isolated sandbox. The API tests assert 17 factors, `raw = sum(factors)` (no recompute), the decision banner on every response, pre-committed experiment thresholds, and that the server exposes **no write methods**. Both Python suites are wired into `shared/integration_check.py`.
