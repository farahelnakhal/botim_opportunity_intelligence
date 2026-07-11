# Template — Customer Evidence Record

One record per distinct pain point per segment. File location: `knowledge-base/customer-evidence/records/YYYY-Wnn.md` (records batched per ISO week). Copy everything below the line.

> **⚠ Compatibility contract with Workstream B.** Live records in this format are machine-parsed by Workstream B (`opportunity-intelligence/tools/opportunity_engine/evidence.py`) so scorecards can cite EV IDs. The following are load-bearing and MUST NOT change without integration agreement at a merge session: **field names** (table row labels), **heading structure** (`## EV-… — title`, the `**Status:**` line), and **score-line formatting** (`Axis name .... N` inside the Scores block). Cell *values* may change freely. `Evidence confidence` values must begin with exactly `High`, `Medium`, or `Low` — nuance goes after a dash, never as a compound value ("Medium-High" is invalid). Run `customer-intelligence/tools/conformance_check.py` before committing records.

---

## EV-YYYY-Wnn-nnn — <short title>

**Status:** active | needs-more-evidence | superseded-by:EV-… | resolved
**Created:** YYYY-MM-DD · **Last verified:** YYYY-MM-DD

### Who

| Field | Value |
|---|---|
| Customer segment | SEG-… (link) |
| Industry | |
| Company size | |
| Geography | |
| Business model | |
| B2B or B2C | |
| Digital or cash-heavy | |

### What

| Field | Value |
|---|---|
| Pain category | `category/subcategory` (per pain-point taxonomy) |
| Provider mentioned | |
| Exact customer wording | > "…verbatim quote…" |
| Frequency (narrative) | how often this occurs for the merchant |
| Financial impact | amounts/fees/losses if stated |
| Operational impact | |
| Current workaround | |
| Workaround cost | |
| Switching signal | |
| Willingness-to-pay signal | |
| Requested feature | |

### Source

| Field | Value |
|---|---|
| Source | URL / platform + SRC-… (source log) |
| Date of evidence | |
| Access label | direct / api / search-snippet / rss / archived / aggregator / public-index / licensed / manual-collection-needed |
| Language | |

### Assessment

| Field | Value |
|---|---|
| Evidence confidence | High / Medium / Low — why |
| Duplicate status | unique / duplicate-of:EV-… / corroborates:EV-… |
| Contradictory evidence | EV-… (list the counter-queries that surfaced it) or "none found (searched: <the actual queries run>)" — always record the real counter-search queries, in both outcomes |
| Product implication | 1–2 sentences; inference, labelled as such |

### Scores (1–5, per frameworks/evidence-scoring.md)

```
Frequency ................ _
Severity ................. _
Financial cost ........... _
Urgency .................. _
Dissatisfaction .......... _
Workaround cost .......... _
Switching intent ......... _
Willingness to pay ....... _
BOTIM relevance .......... _
Evidence strength ........ _
(mean _._ — convenience only)
```

**Score history:** YYYY-MM-DD initial · (append on rescore: date + which axes moved and why)
