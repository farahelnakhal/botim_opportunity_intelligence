# Capability vs. claim — what is actually built

> Created 2026-07-20. Evidence-cited, decision-log-weight. Its job: stop
> aspirational or methodology language from being read as shipped software.
>
> **Why this exists.** Several of this repo's documents — `MASTER_PROMPT.md`,
> `WORKSTREAMS.md`, `docs/product-context.md`, and everything under
> `customer-intelligence/guides/` and `customer-intelligence/commands/` — are
> **operating instructions for a human + LLM "combined agent"** that authors the
> committed knowledge base by hand (via Git commits). They describe how that
> agent *should research and reason*, not features the runtime software
> executes. Read as a product spec they overstate what the deployed app does.
> This file is the reconciliation: claim → actual state → the code that exists →
> what would close the gap. When they disagree, **the code wins.**

## The one distinction that resolves most confusion

- **Runtime software** = the deployed app: `executive-ui/` (dashboard API +
  React UI + copilot proxy), `copilot-backend/` (grounded chat), `shared/`
  (research platform, workspace, email, documents), and the read-only engines
  it calls. This is what a user actually gets.
- **KB-authoring methodology** = `MASTER_PROMPT.md`, `WORKSTREAMS.md`, the
  `customer-intelligence/` and `opportunity-intelligence/` guides/prompts. These
  instruct a person-with-an-LLM to produce `knowledge-base/` records. "Mine
  Reddit in Hindi/Urdu", "diff the competitor's pricing page", "score the
  evidence" are **tasks for that operator**, executed by hand — not endpoints,
  jobs, or scrapers in the codebase.

The committed `knowledge-base/` is the *output* of the methodology layer; the
runtime app mostly **reads** it. No runtime code performs the A/B/C research
described in `WORKSTREAMS.md` — it is done by humans and committed.

## Claim reconciliation

| Claimed capability | Actual current state | Code that exists (evidence) | To close the gap |
|---|---|---|---|
| **Multi-language, multi-platform social scraping** — pulls customer opinion from Reddit / social / app-store reviews in 4 languages | **Not built (methodology-doc-only).** No social/app-store/Reddit integration; no language-specific search. Live research is a single general web-search adapter. | `shared/research/providers.py` = `BraveSearchProvider` only (sends `q`+`count`, no language param); `shared/research/retrieval.py` = generic http(s) fetch, zero `lang`/`hl`/`locale` handling. `customer-intelligence/tools/` = only `conformance_check.py` (a format validator). The Reddit/social/multilingual language lives in `WORKSTREAMS.md:20`, `customer-intelligence/commands/example-commands.md:14`, `customer-intelligence/guides/source-discovery.md` — operator instructions (they list *five* languages, not four). | Per-platform adapters (Reddit/app-store/etc.) behind the `providers.py` seam; language/locale params on search + fetch; provenance + tests per source type. Substantial. |
| **Verified-source stats → TAM/SAM/SOM computation** | **Not built as described.** No TAM/SAM/SOM anywhere in code. The engine computes a 17-dimension scorecard + commercial/unit-economics scenarios, but from **human-authored committed inputs**, not live "verified" web stats. "Verified sources" is not a real step. | `\b(TAM|SAM|SOM)\b` appears only in `knowledge-base/commercial-models/BENCHMARKS.md` and `customer-intelligence/SYSTEM_PROMPT.md` (docs). Engine: `opportunity-intelligence/tools/opportunity_engine/{scoring,commercial,subsidy,montecarlo,ramp}.py`, reading `knowledge-base/commercial-models/opp-*-inputs.json`. Research sources carry recorded quality signals + freshness + dedup (`shared/research/runner.py`), reviewed as candidates — not "verified". | A deterministic market-sizing calculator (roadmap **C1**, not built) with inputs→formula→outputs shown; a real source-quality/verification tier; wiring live figures in as *candidate* inputs, never silently into committed scores. |
| **Merchant interview — auto-suggested questions from gaps; answers update KB + models** | **Not built as described (manual workflow).** Campaigns/guide questions are human-authored; no gap-detection→question generation. Approved answers become **candidate** evidence needing human review, never an automatic model/score update. | `merchant-voice/app/campaigns.py:create()` takes `research_questions` from request data; `merchant-voice/app/guides.py` inserts human-entered questions validated against a taxonomy. Approved findings export synthetic-only to `knowledge-base/customer-evidence/merchant-voice-candidates/` (never `records/`, never EV ids); copilot reads them **read-only** via `merchant-voice/app/published_query.py`. No path writes the scoring engine or opportunity records. | A gap→question generator (consume assumption-register/evidence-gaps, propose questions); and — only if desired — a reviewed promotion path, still ending at human approval, never auto-writing committed scores. |
| **News updates — competitor/customer tracking, notifications, auto-updating models/data** | **Partially built.** Tracking + notifications exist; **automatic update of authoritative models/data does not** (by invariant). Monitoring/R6 output stays candidate/preliminary pending human review. | Built: `intelligence-monitoring/tools/monitoring_engine/` (KB-diff `kbwatch`, `events`, `alerts`, `digest`) + one offline-injectable external adapter (`adapter_regulator.py`); `executive-ui/api/monitoring_runner.py` (manual R4a runs → `MEVT-` events, runtime); R6 scheduled re-run + email (`shared/workspace/`, tick in `executive-ui/api/server.py`, `shared/email/`). The **only** writer to committed `knowledge-base/opportunity-scores/` is `impact/apply.py:apply_impact(ref, approver)` — **requires `--approver`, CLI-only** (`impact/cli.py`); nothing in monitoring/R6 imports it. | A reviewed apply path is deliberately human-gated; "auto-update" of authoritative data is out of scope by design (read-only-KB + human-approval invariants). Closing it would mean *removing* an invariant, not adding a feature. **Notification ≠ authoritative auto-update.** |
| **Executive brief — PDF summary of all data** | **Not built.** No PDF generation. Reports are web-only. PDF appears only as *input rejection*. | `shared/documents/extract.py` returns an honest 415 for uploaded PDFs (input, not output). Reports: `executive-ui/web/src/components/Report.tsx` + the brief serializer, web-only at `/report/{OPP-nnn\|UOPP-…}`. Not-built is stated in `docs/current-state.md` limitations and roadmap **P1**. | Server-side PDF rendering of the existing web report (roadmap P1). A web report does not satisfy this claim. |

## Broader-pass findings (other capability-sounding language to treat as methodology, not shipped)

Found while sweeping `product-context.md`, `MASTER_PROMPT.md`, `WORKSTREAMS.md`,
and the `customer-intelligence/` guides/commands — so a sixth surprise doesn't
surface later:

- **"Autonomous source discovery · Reddit/app reviews/forums/public communities
  · competitor tracking"** (`WORKSTREAMS.md:20`; `example-commands.md`) — these
  are **Workstream A operator tasks**, done by a human+LLM and committed. Runtime
  has no autonomous discovery or competitor-page diffing; it has one Brave
  web-search adapter feeding a human-reviewed candidate-evidence pipeline.
- **Workstream C "watch external sources … summarize, flag, and notify"**
  (`MASTER_PROMPT.md`) — runtime C is a **KB-change watcher** + **one** regulator
  adapter (offline-injectable) + **digest files**. It is not broad live
  competitor/social monitoring. Real outbound *notification* email exists only
  for the R6 workspace path (this branch), and only after live SMTP validation
  (see `docs/decision-log.md`).
- **"Predictions"** (product-context core journeys) — these are human/agent-
  authored calibrated entries in `knowledge-base/product-ideas/decision-journal.json`,
  surfaced read-only. There is no automated prediction/forecast engine.
- **"Run transparent analytical calculations"** (product-context vision) — the
  engine's calculations run **offline on committed inputs**; no deterministic
  calculators are exposed at chat/request time (roadmap **C1**, not built —
  stated in `current-state.md` limitations).

## How this was verified

Code-level inspection on branch `claude/phase-r6-scheduled-monitoring-har49j`
(2026-07-20): `grep` for `\b(TAM|SAM|SOM)\b`, `reddit|app-store|social|scrap`,
`lang|hl=|locale`, and `import impact|--approver` across the tree; reads of
`providers.py`, `retrieval.py`, `merchant-voice/app/{campaigns,guides}.py`,
`impact/{apply,cli}.py`, and the monitoring engine. Verdicts were assigned
built / partially built / not built / methodology-doc-only with no rounding-up
of partial matches. Re-run the same checks before treating any of the above as
shipped.
