# knowledge-base/validation/

Owned by Workstream B (Product & Opportunity Intelligence).

Holds validation experiment specs and their results.

## Contents

- `VE-###-<slug>.md` — one file per experiment (from `opportunity-intelligence/templates/validation-experiment.md`): hypothesis, participants, method, sample size, pre-committed success/failure thresholds, duration, data collected, decision informed — with the result record appended after the run.

## Rules

- Thresholds are committed **before** data collection and never edited afterwards; if a threshold was wrong, say so in the result record.
- Interview/survey scripts live with the experiment file so question wording (non-leading) is reviewable.
- Raw verbatims that constitute customer evidence should be handed to Workstream A for `customer-evidence/` via the evidence-request queue — do not write into their folders.
