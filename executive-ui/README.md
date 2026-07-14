# Executive UI — BOTIM Product Discovery Copilot

A read-only, executive-facing view over the three workstreams' committed outputs. It answers: what opportunities are we investigating, which segment, what evidence supports each, what assumptions remain, what changed, why a score changed, what to do next — and, prominently, **whether anything has been validated or selected (it has not).**

There are two front-ends over the **same read-only adapter** (`adapter/collect.py`, the single source of truth):

1. **`web/` — a modern React + TypeScript assistant** (the primary UI): a chat-first, project-workspace interface matching the approved design mockup, wired to a live Python JSON API.
2. **stdlib static site** (`build.py` + `render/`): a zero-dependency server-rendered fallback/export.

## Run the assistant (React app + live API)

```bash
# 1. read-only JSON API over the engines (stdlib only)
python3 executive-ui/api/server.py --port 8000

# 2. React dev server (proxies /api → :8000)
cd executive-ui/web && npm install && npm run dev      # http://localhost:5173

# --- or a single-process deploy ---
cd executive-ui/web && npm run build                   # emits web/dist
python3 executive-ui/api/server.py --port 8000         # also serves web/dist
```

If the API is unreachable, the React app falls back to a bundled snapshot of **real** engine output (`web/src/seed.json`) so it always renders truthful data and never fabricates.

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

## Deploy for free (a public link, no paid API key)

`executive-ui/deploy/` bundles the built React app, the read-only API, and a
small local model (Ollama) into **one Docker container**, deployable for free
on [Hugging Face Spaces](https://huggingface.co/spaces) (their free CPU tier:
no GPU, no credit card). A GitHub Action redeploys it automatically on every
push to `main`. Costs nothing to run; the tradeoffs are honest: a free Space
**sleeps after inactivity** (the next visitor waits ~30-60s for it to wake),
and CPU-only inference of even a small model takes several seconds per
analysis, not instantly.

**One-time setup (about 5 minutes):**

1. Create a free account at [huggingface.co](https://huggingface.co/join).
2. Create a new Space: **New → Space** → pick a name → **SDK: Docker** →
   **Hardware: CPU basic (free)** → **Public**. Leave it empty otherwise —
   the GitHub Action fills it in.
3. Create an access token: **Settings → Access Tokens → New token** →
   role **Write**. Copy it.
4. In this GitHub repo: **Settings → Secrets and variables → Actions**
   - Add **secret** `HF_TOKEN` = the token from step 3.
   - Add **variable** `HF_SPACE` = `your-hf-username/your-space-name`.
5. Push to `main` (or run the **"Deploy to Hugging Face Space"** workflow
   manually from the **Actions** tab). The Space builds automatically —
   watch progress on the Space's own page — and your public link is:
   `https://huggingface.co/spaces/your-hf-username/your-space-name`.

The Space bakes a small model (`llama3.2:1b` by default) into the image at
*build* time — not pulled at container start — so waking from sleep never
re-downloads model weights. Swap the model by editing the `ARG OLLAMA_MODEL`
line in `executive-ui/deploy/Dockerfile` (bigger models answer better but are
slower on free CPU hardware and make the image larger).

Every honesty guarantee still holds in this deployment: the real scoring
engine (not the model) computes and caps every generated opportunity.

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
