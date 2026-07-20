# Product context — BOTIM Opportunity Intelligence

> Durable product memory. Describes what this product is, who it serves, and the
> constraints every implementation decision must respect. For the technical map see
> `docs/architecture.md`; for what is actually built see `docs/current-state.md`.
>
> **This is vision + constraints, not a shipped-capability list.** Much of the
> language below (and in `MASTER_PROMPT.md` / `WORKSTREAMS.md` / the research
> guides) describes intended behavior or methodology for the human+LLM
> KB-authoring agent — not features the runtime executes. Before treating any
> capability here as built, check it against `docs/capability-vs-claim.md`.

## Vision

BOTIM Opportunity Intelligence is a **reusable, evidence-backed opportunity-intelligence
assistant** for BOTIM/AstraTech teams. It helps internal teams define business and
product opportunities, research markets/customers/competitors, organize internal
knowledge, gather current external evidence, separate facts from assumptions, surface
contradictions and gaps, save and reopen ongoing work, monitor relevant developments,
run transparent analytical calculations, and produce decision-ready recommendations
and briefs.

It supports **human** decision-making with evidence, traceability, and clearly stated
limitations. It never replaces the humans making the call.

## Target users

- BOTIM product managers
- Strategy and research teams
- SME- and merchant-focused teams
- Opportunity owners across other BOTIM teams (later)

## What this product is NOT

- Not a generic ask-anything chatbot
- Not an SME-card-only chatbot
- Not a static executive dashboard
- Not a visual-only prototype
- Not an autonomous high-stakes decision maker
- Not a replacement for product managers, analysts, lenders, compliance, or licensed
  financial institutions

## First major validation case: "SME Credit Cards" internship brief

The first demanding use case comes from an internship brief titled **SME Credit
Cards**: sizing the UAE/GCC SME corporate-card opportunity, benchmarking international
and regional players, designing the end-to-end product journey, identifying edge
cases, producing a strategy deck with recommendations, and an interactive live
prototype.

**This is a validation case, not the platform boundary.** Every new capability must
satisfy both rules:

1. It works extremely well for this SME-focused opportunity.
2. It stays reusable for other BOTIM opportunities.

Do not hardcode the platform around SME cards, rename it around the internship use
case, or narrow the existing knowledge base / architecture / broader
opportunity-intelligence direction.

## Critical constraint: BOTIM is not assumed to be a bank

Do **not** assume BOTIM is a bank, lender, card issuer, deposit-taking institution,
regulated credit institution, or balance-sheet funding provider.

"SME Credit Cards" is a **working problem-space title, not a predetermined product
answer**. The system investigates what product structure is viable instead of
automatically recommending that BOTIM issue cards or extend credit. Models to
evaluate include: licensed-bank-issued products, financial-partner-issued products,
co-branded programs, distribution/referral models, program management, embedded SME
spend-management tools, employee expense cards, debit/prepaid/charge/secured-credit/
credit structures, working-capital partnerships, payment controls and reconciliation,
merchant cash-flow tools, and non-card alternatives.

Always distinguish roles: issuer, lender, funding provider, program manager,
distributor, technology provider, data provider, servicing partner, regulated entity.
Never claim BOTIM can issue cards, extend credit, underwrite, hold deposits, or
perform regulated activities unless verified evidence establishes the legal and
operational structure. Never convert regulatory, licensing, funding, underwriting, or
partnership **assumptions** into facts.

The system's job on this case is to help determine: whether a card is actually the
right solution, BOTIM's realistic role in the value chain, which licensed partners
may be required, which structure is commercially and operationally viable, the real
customer need, the commercial model, regulatory and operational dependencies, risk
and compliance implications, and edge cases / failure modes. No flashy-but-unrealistic
financial-product recommendations.

(The existing `MASTER_PROMPT.md` non-negotiables already encode part of this: the
accepting merchant pays MDR; issuers earn interchange or a programme share — BOTIM
never earns "the full MDR".)

## Product principles

- Actual decision value over visual polish
- Repository-grounded behavior; current external research where appropriate
- Traceable evidence and citations; no fabricated sources
- No fabricated monitoring activity, no invented calculations, no fake scores
- Facts separated from assumptions; user claims clearly labelled
- Internal vs external evidence clearly distinguished
- Candidate evidence separated from approved evidence; human approval before
  authoritative writes
- Honest unavailable / partial / failed states; safe failure behavior
- Persistent user work
- Reusable architecture; no one-off demo hacks
- No broad rewrite of working systems; no silent product-scope changes
- Proportional testing during development; full integration testing at milestones
- Explicit trust boundaries

## Core user journeys (as built today)

1. **Explore the committed portfolio** (demo mode): ranked opportunities, 17-factor
   scorecards, evidence with provenance/freshness, assumptions, monitoring events,
   predictions, web reports (`/report/OPP-nnn`).
2. **Ask grounded questions in chat**: the copilot answers with citations from the
   committed knowledge base and approved Merchant Voice findings; honest "unavailable"
   when the backend is down; deterministic demo mode is disclosed with a badge.
3. **Analyze a genuinely new idea**: a grounded `new_opportunity_analysis` that reuses
   read-only tools, never invents a numeric score, and produces an *unsaved* draft.
4. **Save and manage user opportunities**: draft → saved → archived lifecycle in a
   runtime SQLite store (`UOPP-` ids), surviving refresh and backend restart; per-
   opportunity reports and copilot context.
5. **Configure monitoring intent**: editable topics/cadence per user opportunity,
   honestly labelled "Configured — awaiting monitoring run" (no runner exists yet).
6. **Merchant research pipeline** (Merchant Voice, synthetic-only prototype):
   campaigns → responses → AI-assisted extraction → human review → approved findings
   → non-authoritative Part A proposals; the copilot reads only approved+published
   findings.

## Origin note

The repository began as a two-person, prompt-driven "combined agent"
(`MASTER_PROMPT.md`, `WORKSTREAMS.md`): Workstream A (customer & market
intelligence), Workstream B (product & opportunity intelligence), Workstream C
(monitoring), operating on a Git-committed knowledge base. The software product
(React UI + APIs) was layered on top of those engines and their committed outputs.
Those documents remain accurate for the knowledge-base/engine layer and for KB
ownership boundaries; this `docs/` set is the product/engineering memory for the
application layer.
