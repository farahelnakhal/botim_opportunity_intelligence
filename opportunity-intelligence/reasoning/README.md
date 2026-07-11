# Reasoning Layer

The scoring framework and engine keep the module *honest*; this layer makes it *well-calibrated*. Three pillars, each with a concrete artefact — none of this is advisory prose, all of it produces checkable output:

| Pillar | Artefact | Enforced by |
|---|---|---|
| 1. Outside view before inside view | `reference-classes.md` — base rates consulted before any classification | Protocol step 1; profiles cite the reference class used |
| 2. Structured adversarial reasoning | `reasoning-protocol.md` — the 6-step pass run at every decision point | Stress-test framework requires steps 2–3 |
| 3. Measurable judgment | `knowledge-base/product-ideas/decision-journal.json` — probabilistic predictions, Brier-scored on resolution | `run.py predict / resolve / calibration`; journal validated by `check` |

## Why a decision journal

Classifications ("Promising but unvalidated") are unfalsifiable; probabilities are not. Every material judgment gets logged as a dated prediction with a probability *before* the outcome is knowable. When outcomes land, `run.py resolve` scores them. Over time the calibration report answers the question no framework can: **is this module's judgment actually any good, and in which direction does it err?** Systematic overconfidence → widen assumption flags; systematic underconfidence → the caps are too harsh.

## Rules

- A prediction is one falsifiable sentence with a deadline. "OPP-001 is promising" is not a prediction; "VE-001 reaches ≥40% waitlist completion by 2026-08-31" is.
- Probabilities are set before field work starts and never edited — a wrong prediction is data, an edited one is contamination. Corrections go in a new prediction.
- Every classification, recommendation, and experiment design should generate at least one journal entry.
- Resolve promptly and honestly; unresolved predictions past their deadline are flagged by `check`.
