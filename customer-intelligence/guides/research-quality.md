# Research-Quality Guide

Rules every workflow applies before a conclusion enters the knowledge base.

## For every important conclusion

1. **Search for supporting evidence** — at least two independent sources for any conclusion marked Medium confidence or above.
   **Source-type rule:** Medium or High confidence normally requires evidence from **at least two independent source *types*** (e.g. a review site *and* a forum thread; a first-person post *and* an official policy document) — not just two reviews on the same platform, which share that platform's selection bias. Exception allowed only where explicitly documented in the record's `Evidence confidence` cell (e.g. "single source type: dated first-person account corroborated by the provider's own published policy"), stating why one type suffices in this case.
2. **Search for contradictory evidence** — run the mirror-image query (e.g. if concluding "merchants are leaving provider X over settlement delays", also search for merchants praising X's settlement speed, and for the same complaint about X's competitors — the pain may be industry-wide, not X-specific).
   **Query-logging rule:** record the *actual* counter-search queries in the record's `Contradictory evidence` field — both when contradiction is found (which queries surfaced it) and when it is not ("none found (searched: `<provider> fast payout`, `<provider> same day settlement review`)"). "None found" without the queries is unverifiable and does not count as a completed counter-search.
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

**Definition — load-bearing record:** a record is *load-bearing* if any of the following cites it: (a) a headline in a weekly update, (b) a segment profile's "Main pain points", (c) an inflection-point record's evidence, or (d) a Workstream B scorecard or opportunity profile. Load-bearing records get priority in the verification queue and must not sit below Medium confidence without an explicit `needs-more-evidence` status.

## Evidence-strength ladder (strong → weak)

1. Merchant **switched** providers (and says why).
2. Merchant **pays** for an imperfect workaround (personal cards for business, multiple tools for one workflow, informal borrowing, tolerating high fees).
3. Merchant **actively asks** for alternatives or requests a feature, unprompted.
4. Merchant **describes** recurring operational/financial pain with specifics (amounts, delays, fees).
5. Merchant **states interest** in a described product.
6. Survey aggregates, single anonymous comments, vendor claims, analyst assumptions.

Levels 1–4 are behavioural and can support High confidence. Levels 5–6 alone cap a conclusion at Low.

## The six evidence classes (controlled vocabulary)

Every signal cited in a record narrative or research synthesis names exactly one class. The classes map onto the ladder:

| Class | What it is | Ladder level | Demand signal |
|---|---|---|---|
| **actual switching** | Merchant moved provider (voluntarily or forced — say which; forced switching signals provider failure, not preference) | 1 | Strongest |
| **switching intent** | Concrete plan or active trialling of alternatives, not yet moved | 1–3 | Strong |
| **workaround spending** | Money/risk already spent on an imperfect substitute (fees tolerated, tools stacked, personal cards, informal borrowing, paid consultants) | 2 | Strong — the price they already pay is revealed demand |
| **observed behaviour** | Any other verifiable action (escalated to a regulator, asked unprompted for alternatives, padded balances) | 2–3 | Moderate–strong |
| **stated interest** | "That would be useful" / "I'd pay for that" — hypotheticals | 5 | Weak alone |
| **complaint** | Expression of dissatisfaction with no action attached | 4–6 by specificity | Weak alone — volume of complaints is never, by itself, demand |

Use these class names in the `Switching signal`, `Willingness-to-pay signal`, and `Current workaround` cell values (e.g. "workaround spending: pays +0.75% for same-day settlement") — vocabulary inside existing fields, not new fields.

## Contradiction handling

When new evidence contradicts an existing record:

1. Do not delete or silently edit the old record.
2. Add the contradiction to **both** records' `Contradictory evidence` fields, with IDs.
3. Re-derive the conclusion; downgrade confidence if unresolved.
4. If the contradiction resolves (e.g. the provider fixed the issue), record it as a potential inflection point.
