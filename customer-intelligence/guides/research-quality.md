# Research-Quality Guide

Rules every workflow applies before a conclusion enters the knowledge base.

## For every important conclusion

1. **Search for supporting evidence** — at least two independent sources for any conclusion marked Medium confidence or above.
2. **Search for contradictory evidence** — run the mirror-image query (e.g. if concluding "merchants are leaving provider X over settlement delays", also search for merchants praising X's settlement speed, and for the same complaint about X's competitors — the pain may be industry-wide, not X-specific).
3. **Separate fact from inference.** Facts are quoted, dated, sourced. Inferences are labelled `Inference:` and tied to the facts they rest on.
4. **Mark confidence** explicitly:
   - **High** — multiple independent, recent, behavioural sources; no unresolved contradiction.
   - **Medium** — one strong behavioural source or several weak ones pointing the same way; minor unresolved gaps.
   - **Low** — stated interest only, single source, old data, or unresolved contradictions.
5. **Show dates** on every piece of evidence and every "last verified" field.

## Traps to avoid

| Trap | Rule |
|---|---|
| Duplicated evidence | The same complaint reposted/quoted across platforms counts once. Check existing evidence IDs before creating a record; mark duplicates in the `Duplicate status` field. |
| Promotional or suspicious reviews | Exclude review bursts, affiliate content, vendor-planted praise. Note suspected manipulation in the competitor profile. |
| Outage ≠ structure | A provider's bad week is not a permanent weakness. Require the complaint to recur across months before treating it as structural. |
| One complaint ≠ demand | A single merchant's pain is a lead to investigate, not evidence of broad demand. Frequency scoring (axis 1) must reflect how many distinct merchants exhibit it. |
| Survivorship | Communities over-represent the angry and the digital-savvy. Note when a segment (e.g. cash-heavy, Arabic-first merchants) is under-observed rather than pain-free. |
| Stale conclusions | Every record carries a `Last verified` date. Weekly updates re-verify anything load-bearing that is >90 days old. |

## Evidence-strength ladder (strong → weak)

1. Merchant **switched** providers (and says why).
2. Merchant **pays** for an imperfect workaround (personal cards for business, multiple tools for one workflow, informal borrowing, tolerating high fees).
3. Merchant **actively asks** for alternatives or requests a feature, unprompted.
4. Merchant **describes** recurring operational/financial pain with specifics (amounts, delays, fees).
5. Merchant **states interest** in a described product.
6. Survey aggregates, single anonymous comments, vendor claims, analyst assumptions.

Levels 1–4 are behavioural and can support High confidence. Levels 5–6 alone cap a conclusion at Low.

## Contradiction handling

When new evidence contradicts an existing record:

1. Do not delete or silently edit the old record.
2. Add the contradiction to **both** records' `Contradictory evidence` fields, with IDs.
3. Re-derive the conclusion; downgrade confidence if unresolved.
4. If the contradiction resolves (e.g. the provider fixed the issue), record it as a potential inflection point.
