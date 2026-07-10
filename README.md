# BOTIM Opportunity Intelligence — Workstreams

This repository is being developed by two people simultaneously using Claude Code.

## Shared objective

Build an internal AI research and product-discovery agent for BOTIM/AstraTech focused on:

- SME merchant pain points
- Customer interest and behaviour
- Competitor monitoring
- Market changes
- Product opportunities
- Payment and lending propositions
- Commercial models
- Validation experiments

The agent should not restart research from scratch each time. It should maintain reusable knowledge and update what has changed.

---

## Workstream A — Customer & Market Intelligence

Owner: Person 1

Primary branch:

customer-intelligence

Owned directories:

- customer-intelligence/
- knowledge-base/customer-evidence/
- knowledge-base/competitors/
- knowledge-base/segments/
- knowledge-base/inflection-points/

Responsibilities:

- Voice-of-customer research
- Autonomous source discovery
- Reddit, app reviews, forums and public communities
- Merchant pain-point analysis
- Customer-segment analysis
- Competitor tracking
- Market and product updates
- Evidence scoring
- Source logging
- Contradiction checking
- Weekly intelligence updates

Do not directly modify:

- opportunity-intelligence/
- commercial-models/
- product-scoring/
- validation-experiments/

---

## Workstream B — Product & Opportunity Intelligence

Owner: Person 2

Primary branch:

opportunity-intelligence

Owned directories:

- opportunity-intelligence/
- knowledge-base/product-ideas/
- knowledge-base/commercial-models/
- knowledge-base/validation/
- knowledge-base/opportunity-scores/

Responsibilities:

- Product opportunity generation
- Value propositions
- Commercial-model analysis
- MDR and interchange modelling
- Product stress tests
- Opportunity scoring
- BOTIM strategic advantage
- Seven-week MVP definition
- Validation experiments
- Product backlog
- Meeting-ready recommendations

Do not directly modify:

- customer-intelligence/
- source-discovery/
- competitor-tracking/
- customer-evidence/

---

## Shared files

The following files are shared and should not be modified without explicit agreement:

- MASTER_PROMPT.md
- README.md
- WORKSTREAMS.md
- context/
- shared/
- templates/

If a shared-file change is required:

1. Do not make it automatically.
2. Document the suggested change.
3. Continue working within the owned module.
4. Raise the change during the merge session.

---

## Git rules

- Always work on the assigned branch.
- Pull before starting work.
- Inspect repository status before editing.
- Stage only intentionally modified files.
- Do not force-push.
- Do not rewrite history.
- Do not delete another contributor's work.
- Do not modify files outside the assigned workstream without approval.
- Commit focused changes.
- Push the assigned branch after completing a coherent task.
- If a merge conflict occurs, stop and explain it instead of guessing.
