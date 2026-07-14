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

Added 2026-07-11 at the repository owner's direction. **Shared ownership accepted by both contributors (Person 1 and Person 2), 2026-07-11** — Workstream C is jointly owned like `shared/`; changes to it follow the shared-file rule (agreement between both contributors). Design: `intelligence-monitoring/DESIGN.md`.

**Owned directories:**
- `intelligence-monitoring/`
- `knowledge-base/monitoring/`

**Responsibilities:** continuous knowledge-base watching (KB differ) · external competitor/source adapters · change detection and mechanical significance tiering · AI event summaries with the reasoning pass · alert routing, digests, notification preferences · evidence-candidate intake for Workstream A.

**Prime directive:** detects and routes — **never authors evidence, scores, or classifications**. External detections become candidates in `knowledge-base/monitoring/evidence-candidates/` that Workstream A promotes under its own rules; rescore suggestions surface to Workstream B report-only, like the sync bridge.

**Does not directly modify:** everything outside its two owned directories.

---

## Evidence-Impact Workflow (jointly owned)

Added 2026-07-13 at the repository owner's direction. **Shared ownership accepted by both contributors (Workstream A and Workstream B), 2026-07-13** — jointly owned like `shared/`; changes follow the shared-file rule (agreement between both contributors). A human-governed workflow: new/changed evidence → impact proposal → explicit human approval (`apply-impact --approver …`) → transactional application (lock + manifest + complete backups + staged validation + automatic recovery) → append-only score history → executive email preview; with rollback. It reuses, and never modifies, the Part B scoring engine and the Part A evidence parser; Part B scorecard changes flow only through an approved proposal.

**Jointly owned paths:**
- `impact/`
- `knowledge-base/impact/`

---

## Copilot Backend — conversational product-discovery API (jointly owned)

Added 2026-07-13 at the repository owner's direction; jointly owned like `shared/` (changes by agreement).

**Owned directory:** `copilot-backend/`

**Purpose:** a **read-only** conversational backend for the Product Discovery Copilot: it answers product-discovery questions (segments, pain, evidence, assumptions, gaps, briefs, next validation, and — since Merchant Voice Phase 5 — merchant research feedback) by reusing the existing engines and read models as single sources of truth, plus Merchant Voice's own read-only query layer for approved, published research findings. It cannot modify evidence, segments, scorecards, assumptions, impact state, monitoring history, backlogs, or anything in Merchant Voice; chat-generated drafts (research requests, briefs, impact-proposal drafts) are ephemeral and never persisted to the knowledge base. Real changes remain exclusively in the human-approved impact workflow (and, for merchant research, Merchant Voice's own human review workflow).

**Boundary from `executive-ui/`:** the executive UI is the presentation layer and consumes this backend over HTTP via the shared contract `shared/contracts/conversation-api.schema.md`; the backend never modifies `executive-ui/**`, and neither replaces the other's logic.

---

## Merchant Voice & Validation — research-to-evidence backend (jointly owned)

Added 2026-07-13 at the repository owner's direction; jointly owned like `shared/` (changes by agreement).

**Owned directory:** `merchant-voice/`

**Purpose:** a human-reviewed pipeline that turns BOTIM merchant feedback (surveys, interviews, concept tests) into traceable Part A evidence *proposals*. v1 (Phase 1 + 2 + 3 + 4 + 5, delivered) implements research campaigns, versioned research guides, pseudonymous participants, consent/privacy gating, manual and CSV-bulk response ingestion, text transcript ingestion, deterministic redaction, withdrawal/retention/deletion, AI-assisted extraction of structured observations (the model may only *propose*), the full human-governed review workflow (observation review/edit/approve/reject/merge, evidence candidates, immutable approved Merchant Voice findings with deterministic strength bands and campaign-level analysis), a human-reviewed Part A evidence-**proposal** workflow (draft → submit → approve → approve-export → synthetic-only export), and a read-only query layer the Product Discovery Copilot uses for grounded, cited answers. **An approved Merchant Voice finding — and an approved, even exported, Part A evidence proposal — are still NOT authoritative Part A evidence** — nothing here writes there, mints an EV ID, changes Part B scores, or changes assumptions.

**Storage boundary:** its own operational database (`merchant-voice/data/mv.db`) and a separate identity database (`merchant-voice/data/identity.db`), both gitignored and never shared with `copilot-backend/`'s conversation store. `copilot-backend/` reads `mv.db` (never `identity.db`) through a genuinely read-only connection and Merchant Voice's own read-only query layer (`app/published_query.py`) — it has no write path back into Merchant Voice. **v1 is synthetic-data-only** (`MV_SYNTHETIC_ONLY=1` by default) — no real merchant data, not approved for production use, prototype-grade authentication only.

**Write boundary:** Merchant Voice never writes directly into authoritative Part A evidence records, never mints Part A evidence IDs, and never directly changes Part B scores or assumptions. A Part A evidence proposal is generated and stored inside `merchant-voice/data/mv.db` for preview only; the only file-writing action anywhere in this service is a **synthetic-only** demo export to `knowledge-base/customer-evidence/merchant-voice-candidates/` (never `.../records/`, never an EV ID) — export of real merchant-derived findings to the authoritative knowledge base requires a separate privacy/redaction/quote-permission review, human reviewer approval, and explicit Workstream A acceptance, none of which exist as an automated path here.

**Boundary from `executive-ui/`:** Merchant Voice has no UI in this delivery; a researcher-facing frontend is scheduled after the current Product Discovery Copilot frontend is stable, and will not modify Farah's existing frontend when it lands.

**Shared contract:** `shared/contracts/merchant-voice-api.schema.md` (Phase 1 + 2 + 3 + 4 + 5 subset; Phase 6+ is documented there as an explicitly-labelled, not-yet-active future roadmap). The Copilot-facing citation addition is documented additively in `shared/contracts/conversation-api.schema.md` (`merchant_finding` citation type — backward compatible, `schema_version` unchanged).

---

## Executive UI — read-only presentation layer (jointly owned)

Added 2026-07-11 on `feature/executive-ui`. A read-only, executive-facing static UI over all three workstreams' committed outputs. **Jointly owned** like `shared/` (changes by agreement).

**Owned directory:** `executive-ui/`

**Prime directive:** **read-only.** It reuses the existing engines as the single source of truth (no second scoring engine, no recomputation, no confidence reinterpretation), never writes to the knowledge base, and never implies a product has been validated or selected. Its only output is the gitignored `executive-ui/dist/`. It consumes the Evidence-Impact Workflow's read-only outputs (e.g. `impact/uicontract.py`) for its Intelligence Feed, Rescore/Impact Review, Brief, and Assumptions screens.

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
