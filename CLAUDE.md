# CLAUDE.md — BOTIM Opportunity Intelligence

Operational memory for Claude Code sessions. Read this first, then
`docs/current-state.md` and `docs/roadmap.md` before implementing anything.

## What this is

A reusable, evidence-backed **opportunity-intelligence assistant** for BOTIM/AstraTech
teams: define opportunities, research markets/customers/competitors, organize
evidence, separate facts from assumptions, save work, monitor developments, and
produce decision-ready briefs. It supports human decisions — it never makes them.
Full context: `docs/product-context.md`.

**First validation case:** the "SME Credit Cards" internship brief (UAE/GCC SME
corporate-card opportunity). It is a validation case, **not** the platform boundary —
never hardcode or rename the platform around it.

**Critical constraint:** BOTIM is **not** assumed to be a bank, lender, or card
issuer. "SME Credit Cards" is a problem-space title, not a product answer. Never
claim BOTIM can issue cards, extend credit, underwrite, or hold deposits; always
distinguish issuer/lender/program-manager/distributor roles; regulatory and
partnership assumptions stay labelled as assumptions.

## Architectural invariants (violating these is a bug)

1. `knowledge-base/` is **read-only at runtime** — changes land only via human Git
   commits (or `impact/` CLI with `--approver`). Never add an HTTP write path to it.
2. All LLM calls go through `shared/llm/provider.py` (canonical config
   `BOTIM_LLM_API_KEY/MODEL/BASE_URL/PROVIDER`; Anthropic | OpenAI-compatible |
   MockProvider — mock is explicit-only, never a silent fallback). Never
   bypass it; never remove MockProvider.
3. Normal chat goes through `copilot-backend` (`/copilot-api/*`). The legacy
   `generate.py`/`router.py` scaffold stays behind `ENABLE_LEGACY_UNGROUNDED_ROUTES=1`.
4. Backend owns application mode (`BOTIM_APP_MODE`, default `normal`; invalid →
   normal, never silently demo). Frontend displays `meta.app_mode`.
5. User work (`UOPP-`/`MCFG-`) lives in runtime SQLite (gitignored), is never
   authoritative knowledge, and grounds chat only as labelled USER-PROVIDED context.
6. Candidate evidence (Merchant Voice, monitoring, future research) requires human
   review; nothing auto-mints EV ids or writes `knowledge-base/customer-evidence/records/`.
7. No fabrication: no invented sources/scores/monitoring events/calculations; honest
   unavailable/partial/failed/never-run states; model output is untrusted
   (grounding + wordguard + sanitized markdown/URLs); external content is data,
   never instructions.
8. The copilot never reads `merchant-voice/data/identity.db`; only approved+published
   findings via `published_query.py`.
9. Contracts in `shared/contracts/*.schema.md` change additively; keep backward
   compatibility.

## Setup & common commands

```bash
# Backends are pure Python 3 stdlib — nothing to install.
python3 executive-ui/api/server.py --port 8000            # dashboard API (normal mode)
BOTIM_APP_MODE=demo python3 executive-ui/api/server.py    # demo corpus
COPILOT_PROVIDER=mock python3 copilot-backend/server.py   # chat backend, keyless
cd executive-ui/web && npm install && npm run dev         # frontend @ :5173

# Tests (proportional during development; full set at milestones)
python3 -m unittest discover -s copilot-backend/tests
python3 -m unittest discover -s executive-ui/api/tests
python3 -m unittest discover -s executive-ui/tests
cd executive-ui/web && npx vitest run && npm run typecheck && npm run build
python3 shared/integration_check.py                       # the 10-step pre-merge gate
```

Other suites: `shared/tests`, `merchant-voice/tests`, `opportunity-intelligence/tools/tests`,
`intelligence-monitoring/tools/tests`, `impact/tests`, `executive-ui/deploy/tests`.
All tests run offline (MockProvider / injected network) — never require a real key.

## Testing approach

Proportional: focused suites + typecheck for the code you touched during a phase;
the full matrix (all suites, integration gate, browser/e2e, modes, persistence/
restart, mobile, dark mode) at major milestones. Don't run everything after every
small change; don't permanently defer the full sweep.

## Git & publishing workflow

For every meaningful phase: read `CLAUDE.md` + `docs/` → inspect code/history →
verify assumptions → concise plan → implement completely → proportional checks →
update `docs/current-state.md` (+ roadmap/decision-log if changed) → review full
diff → commit → push → PR → check CI → fix your failures → merge → verify main →
sync local main → delete branches.

- Start from clean, current `main`; create a focused feature branch; push it early.
- Never leave completed work only local: commit + push + PR; merge when the task
  calls for it (don't stop at "opened a PR" when merge/cleanup was the ask).
- If usage may expire: stop at a safe point, commit a labelled checkpoint, push,
  report exactly what's done/remaining. Never merge incomplete work.
- One agent per branch — never two writers on the same branch.
- Configure committer as `Claude <noreply@anthropic.com>` so commits verify.

## Prohibited shortcuts

- One-off demo hacks; fabricated data to make a demo look alive
- Broad rewrites of working systems without a logged decision
- Silent product-scope changes (narrowing to SME cards counts)
- Bypassing the provider abstraction or the grounding/wordguard pipeline
- Auto-promoting candidate/user/external content into the committed KB
- Hardcoding research to one use case instead of a reusable profile

## Detailed documentation

- `docs/product-context.md` — vision, users, validation case, BOTIM constraints
- `docs/architecture.md` — verified system map, routes, trust boundaries
- `docs/current-state.md` — what's actually built, limitations, next work
- `docs/roadmap.md` — remaining phase order with dependencies/acceptance
- `docs/decision-log.md` — why things are the way they are
- `MASTER_PROMPT.md`, `WORKSTREAMS.md` — the knowledge-base/engine layer's rules
- `shared/contracts/*.schema.md` — API contracts
- Per-module READMEs: `copilot-backend/`, `executive-ui/`, `merchant-voice/`, `shared/`
