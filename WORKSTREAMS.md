# BOTIM Opportunity Intelligence — Workstreams

This repository is developed by two people simultaneously using Claude Code. Since the 2026-07-11 integration, both modules are merged and **operated on `main`**; ownership boundaries below still govern who edits what.

## Shared objective

Build an internal AI research and product-discovery agent for BOTIM/AstraTech focused on: SME merchant pain points, customer interest and behaviour, competitor monitoring, market changes, product opportunities, payment and lending propositions, commercial models, and validation experiments. The agent maintains reusable knowledge and updates what has changed — it never restarts research from scratch. The combined agent is defined in `MASTER_PROMPT.md`.

---

## Workstream A — Customer & Market Intelligence (Person 1)

**Owned directories:**
- `customer-intelligence/`
- `knowledge-base/customer-evidence/`
- `knowledge-base/competitors/`
- `knowledge-base/segments/`
- `knowledge-base/inflection-points/`

**Responsibilities:** voice-of-customer research · autonomous source discovery · Reddit/app reviews/forums/public communities · merchant pain-point analysis · segment analysis · competitor tracking · market and product updates · evidence scoring · source logging · contradiction checking · weekly intelligence updates.

**Does not directly modify:** `opportunity-intelligence/`, `knowledge-base/{product-ideas, commercial-models, validation, opportunity-scores}/`.

---

## Workstream B — Product & Opportunity Intelligence (Person 2)

**Owned directories:**
- `opportunity-intelligence/`
- `knowledge-base/product-ideas/`
- `knowledge-base/commercial-models/`
- `knowledge-base/validation/`
- `knowledge-base/opportunity-scores/`

**Responsibilities:** product opportunity generation · value propositions · commercial-model analysis · MDR and interchange modelling · product stress tests · opportunity scoring · BOTIM strategic advantage · seven-week MVP definition · validation experiments · product backlog · meeting-ready recommendations.

**Does not directly modify:** `customer-intelligence/`, `knowledge-base/{customer-evidence, competitors, segments, inflection-points}/`.

---

## Workstream C — Intelligence Monitoring & Alerting (jointly owned)

Added 2026-07-11 at the repository owner's direction; jointly owned by both contributors pending Person 1's acknowledgement (like `shared/`). Design: `intelligence-monitoring/DESIGN.md`.

**Owned directories:**
- `intelligence-monitoring/`
- `knowledge-base/monitoring/`

**Responsibilities:** continuous knowledge-base watching (KB differ) · external competitor/source adapters · change detection and mechanical significance tiering · AI event summaries with the reasoning pass · alert routing, digests, notification preferences · evidence-candidate intake for Workstream A.

**Prime directive:** detects and routes — **never authors evidence, scores, or classifications**. External detections become candidates in `knowledge-base/monitoring/evidence-candidates/` that Workstream A promotes under its own rules; rescore suggestions surface to Workstream B report-only, like the sync bridge.

**Does not directly modify:** everything outside its two owned directories.

---

## Cross-module contract

- **A → B:** evidence by ID (`EV-YYYY-Wnn-nnn`), segments (`SEG-…`), inflection points (`IP-…`), and weekly-update §9 "Handoffs to Workstream B". B consumes read-only (`opportunity-intelligence/tools/` evidence parser + `sync`).
- **B → A:** evidence requests (`REQ-…`) in `knowledge-base/product-ideas/BACKLOG.md`; interview verbatims from B's experiments are handed to A to record — B never writes evidence records itself.
- Format changes to A's record template or B's citation format are breaking changes to the other module: agree first, and keep `shared/tests/test_integration.py` green.

## Shared files

Modified only by explicit agreement between both contributors:

- `MASTER_PROMPT.md` · `README.md` · `WORKSTREAMS.md` (this file) · `.gitignore` · `shared/` · `context/` · root `templates/`

If a shared-file change is needed and the other contributor isn't available: document the suggested change in your own module, continue working, raise it at the next sync.

## Git rules (integrated operation)

- Work happens on `main` (or short-lived branches merged promptly). Pull before starting; inspect status before editing.
- **Before every push: `python3 shared/integration_check.py` must pass with zero failures.**
- Stage only intentionally modified files. Commit focused changes with one-line messages.
- Do not force-push. Do not rewrite history. Do not delete or modify the other contributor's work.
- If a merge conflict occurs in the other workstream's files or shared files: stop and coordinate rather than guessing.
