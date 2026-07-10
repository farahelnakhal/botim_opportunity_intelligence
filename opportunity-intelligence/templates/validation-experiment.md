# Validation Experiment Template

One file per experiment. Every proposition needs at least one experiment before it can be classified "Strong opportunity". Pick the cheapest method that can actually falsify the hypothesis.

**Method menu:** merchant interviews · surveys · landing-page tests · fake-door tests · waitlists · pricing tests · concierge pilots · prototype usability tests · card-spend simulations · internal merchant-data analysis · revenue-routing tests · supplier-payment pilots.

## Specification (all fields mandatory)

- **Experiment ID:** VE-###
- **Proposition tested:** link to `knowledge-base/product-ideas/<idea-slug>.md`
- **Hypothesis:** a single falsifiable sentence with a number in it. ("≥40% of F&B merchants with 2+ outlets will join a waitlist for activity-linked credit" — not "merchants want credit".)
- **Target participants:** segment, size band, geography.
- **Recruitment criteria:** inclusion AND exclusion rules (exclude friendlies and anyone with an existing BOTIM relationship bias where that would contaminate results).
- **Method:** from the menu above; describe the exact mechanics.
- **Sample size:** with a one-line justification (enough to distinguish success from failure thresholds, not a vanity number).
- **Success threshold:** the pre-committed number at/above which the hypothesis is supported.
- **Failure threshold:** the pre-committed number at/below which it is refuted. The gap between the two is the "inconclusive — extend or redesign" zone.
- **Duration:** start/end; hard stop.
- **Data collected:** fields captured, where stored (`knowledge-base/validation/`), consent notes.
- **Decision informed:** the specific go/no-go or design decision this result feeds, and who makes it.

## Question-design rules (interviews & surveys)

- No leading questions. Ask about past behaviour ("How did you cover your last stock purchase?") before concepts.
- Never ask "would you use X?" as the primary signal; use commitment proxies (waitlist sign-up, deposit, document upload, time given).
- Randomise concept order in pricing tests; test one variable at a time.
- Record verbatims; tag them with evidence IDs for Workstream A cross-reference.

## Anti-patterns (reject the design if present)

- Success threshold set after seeing data.
- Sample drawn only from existing enthusiasts.
- "Interest" measured without cost to the participant.
- No failure threshold.

## Result record (append after the experiment)

- Outcome vs thresholds · surprises · verbatim highlights · classification change triggered · next experiment or archive decision.

Store in `knowledge-base/validation/VE-###-<slug>.md`.
