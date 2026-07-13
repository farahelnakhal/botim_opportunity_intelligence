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

The assistant auto-routes each prompt (`api/router.py`) to the right read-model; the user never picks a module. Routing is rule-based and transparent — no LLM, no hidden state, no fabrication.

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
