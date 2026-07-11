# Reasoning Protocol

Run this 6-step pass at every decision point: before classifying a proposition, before issuing a recommendation, and before committing an experiment design. Output of each step goes into the artefact being produced (profile, recommendation, VE spec) — a step with no written trace didn't happen.

## 1. Outside view first

Before reasoning about *this* idea's specifics, ask: **what usually happens to things in this class?** Consult `reference-classes.md`; if no class fits, add one (marked unsourced). State the base rate and only then argue why this case differs — the burden of proof is on the difference, not the base rate. Anchoring on the inside view ("our loop is special") is the module's most likely systematic error.

## 2. Pre-mortem

Write 2–3 sentences dated 6 months ahead: *"This failed because …"*. The most plausible failure story must appear in the stress test's case-against and map to a named scenario in `stress.py` (or a new custom scenario). If the pre-mortem surfaces a failure mode no scenario covers, that's a finding — add the scenario.

## 3. Disconfirmation search

List what was **not** looked for: which evidence would contradict the conclusion, and whether anyone actually searched for it. "None found" is only valid with the searches stated (mirror of Workstream A's contradiction rule). For every load-bearing claim, name the cheapest observation that would refute it.

## 4. Probability, not adjectives

Convert the judgment into at least one dated, falsifiable prediction with a probability and deadline, logged via `run.py predict`. If you cannot phrase the judgment as a prediction, the judgment is too vague to act on — sharpen it first.

## 5. Sensitivity awareness

Before stating a conclusion that depends on a model, run `sensitivity` and name the single input that flips it. The conclusion must be stated *conditionally on that input* ("viable if routed share ≥ ~25%"), not absolutely.

## 6. Change-my-mind record

End every classification/recommendation with one line: **"This changes if: …"** — the specific observation that would trigger reclassification. This is what makes revisiting mechanical instead of political.

## Anti-patterns this protocol exists to catch

- Inside-view-only enthusiasm (step 1 missing) — the "generic idea generator" failure.
- Case-against written as a strawman (step 2 produces the real one).
- Confidence stated as adjectives that can never be wrong (step 4).
- Unconditional conclusions from assumption-heavy models (step 5).
- Classifications that quietly become permanent (step 6).
