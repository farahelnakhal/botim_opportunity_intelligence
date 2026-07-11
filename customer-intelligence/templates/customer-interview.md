# Template — Customer Interview Synthesis

Converts interview notes into knowledge-base evidence without overstating confidence. One synthesis file per interview: `knowledge-base/customer-evidence/interviews/YYYY-MM-DD-<anon-slug>.md`. Evidence records derived from it go into the normal weekly records file and cite this synthesis as their source.

**The cardinal rule: an interview is one merchant.** However vivid, a single interview can never, by itself, produce a High-confidence conclusion or a Frequency score above 2. Interviews generate *leads and depth*, not breadth.

---

## Interview — YYYY-MM-DD — <anonymised merchant slug>

**Interviewer:** · **Date:** · **Duration:** · **Recording/notes location:** (internal)
**Consent:** what the merchant agreed to (attribution level, quote usage)
**Logged in source log as:** SRC-… (Type: `other` — interview; Access: `direct`)

### Merchant profile

| Field | Value |
|---|---|
| Segment (SEG-… if one fits) | |
| Industry / size / geography | |
| B2B or B2C / digital or cash-heavy | |
| How recruited | (recruitment channel biases what you hear — record it) |

### Observed behaviour vs stated opinion

Sort every notable statement into exactly one column. This split decides evidence strength — do it during synthesis, not later.

| Observed behaviour (they DID/DO this) | Stated opinion (they SAY/THINK this) |
|---|---|
| e.g. "shows personal credit card used for stock purchases" | e.g. "says a business card would be useful" |
| e.g. "switched from Bank X in March, showed the app" | e.g. "thinks fees are too high generally" |

- **Behaviour** = past or current actions, workarounds in use, money actually spent, switches actually made — ideally corroborated in the session (screen shown, document seen, numbers given).
- **Stated opinion** = interest, intentions, hypotheticals ("I would pay for…"), generalisations. Evidence-ladder level 5: never more than weak evidence on its own.

### Verbatim quotes

Numbered, exact wording, each tagged `[behaviour]` or `[stated]`. These feed the `Exact customer wording` field of derived records.

### Contradictions & consistency

- Internal: did stated opinions match observed behaviour? (e.g. "fees don't bother me" but uses a fee-avoiding workaround)
- External: does anything contradict existing EV records? Cross-reference both ways per `guides/research-quality.md`.

### Derived evidence records

| Derived EV ID | Pain | Based on | Cap applied |
|---|---|---|---|
| EV-… | | behaviour / stated | see caps below |

**Confidence and scoring caps for interview-derived records:**

1. **Frequency ≤ 2** from a single interview (one merchant), whatever the severity.
2. Items from the *behaviour* column: Evidence strength ≤ 3 (one strong behavioural source).
3. Items from the *stated* column only: Evidence strength ≤ 2, confidence Low, status `needs-more-evidence`.
4. Confidence Medium requires corroboration from at least one independent source type beyond this interview (existing EV record, review evidence, policy document) — per the source-type rule in `guides/research-quality.md`. **A single interview cannot reach High on any conclusion.**
5. Leading questions taint: if the pain was suggested by the interviewer rather than raised by the merchant, note it in the derived record and treat the answer as stated opinion regardless of phrasing.

### Follow-ups

Open questions this interview raised; what breadth evidence (how many more merchants, which sources) would raise the derived records' confidence.
