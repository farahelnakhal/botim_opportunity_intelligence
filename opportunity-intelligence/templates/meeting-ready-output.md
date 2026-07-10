# Meeting-Ready Output Template

The format for presenting product recommendations to BOTIM/AstraTech leadership. One page of decision material first; appendices carry the detail. Never present a composite score without the individual scores attached.

---

## Page 1 — Decision view

### Recommendation
One sentence: what we recommend doing next and why now.

### The opportunity
- **Proposition:** (one line) · **Segment:** · **Classification:** Strong / Promising but unvalidated / Weak / Reject
- **Organic switching reason:** why merchants move without promotions.
- **BOTIM advantage / AstraTech advantage:** the specific unfair advantages used.

### The numbers (base case, with downside in brackets)
- Contribution margin per merchant/month: AED — (AED —)
- Break-even: — merchants / — months (—)
- Max affordable free-credit days / cashback within net payment economics: — / —%

### What we are confident about vs not
| Confident (evidence-backed) | Not confident (assumption) |
|---|---|
| | |

### Main invalidation risk
The single finding that would kill this, and how likely we think it is.

### The ask
The specific decision requested (approve experiment VE-###, approve 7-week MVP, provide data access, reject and redirect) — with cost and duration.

---

## Appendices

- **A. Scorecard:** all 17 individual scores with basis (from `opportunity-scores/`).
- **B. Stress test:** strongest case against, why competitors haven't built it, adverse selection/fraud/credit risks, classification rationale.
- **C. Commercial model:** downside/base/upside tables, subsidy budget math, assumption register.
- **D. Value proposition & loop:** which links of the payments→data→credit loop are active.
- **E. Validation plan:** experiments with success/failure thresholds and durations.
- **F. Seven-week MVP:** week-by-week plan, dependencies, kill thresholds.
- **G. Evidence register:** evidence IDs consumed from Customer & Market Intelligence, plus open evidence requests.

## Presentation rules

- Ranges, not point estimates. AED unless stated.
- If the recommendation is Weak/Reject, present it with the same rigour — killing an idea cleanly is a deliverable, not a failure.
- If the module's evidence confidence is Low, the recommendation may be at most "run the experiment", never "build".

Store issued outputs in `knowledge-base/product-ideas/<idea-slug>-recommendation-YYYY-MM-DD.md`.
