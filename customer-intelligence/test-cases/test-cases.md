# Test Cases

Three realistic scenarios to validate the module behaves per `SYSTEM_PROMPT.md`. Run them as prompts; check the outputs against the pass criteria. They test *process discipline* — scoring honesty, contradiction handling, duplication control — not whether the market facts turn out true.

---

## Test 1 — Evidence discipline on a hot lead

**Prompt:** "A founder posted on Reddit that their UAE e-commerce business nearly died because their gateway held funds for 45 days. Investigate whether fund-holding by gateways is a significant pain for UAE online sellers."

**Pass criteria:**

- Creates an `EV-…` record with the exact wording, source, date, and access label.
- Does **not** score Frequency above 2 from a single post; searches for additional distinct merchants before any rescore.
- Distinguishes fund-holding-as-policy (structural) from a one-off compliance freeze (incident) — per the outage-vs-structure rule.
- Runs the mirror search (sellers reporting fast payouts; same complaint about other gateways) and records it in `Contradictory evidence`, even if empty.
- Marks confidence Low or Medium with reasoning; flags `needs-more-evidence` if only one merchant found.

**Fail signals:** a confident "gateways holding funds is a major UAE pain point" conclusion from one post; no contradiction search; missing source-log row.

## Test 2 — Competitor change that might be an inflection point

**Prompt:** "Wio has reportedly launched a credit product for SMEs. Update the knowledge base."

**Pass criteria:**

- Verifies the claim against primary sources (Wio's own pages, app changelog, credible press) with dates; separates confirmed fact from rumour.
- Updates `knowledge-base/competitors/wio.md`: lending capability, underwriting, repayment structure, change log — without deleting prior history.
- Evaluates against the inflection-point framework: creates an `IP-…` record **only if** it marks a behaviour/market shift, with `What would invalidate it` filled.
- Adds a "Handoffs to Workstream B" note rather than writing anything into Workstream B's directories.

**Fail signals:** treating a press rumour as confirmed; overwriting the profile without a change-log entry; editing `knowledge-base/product-ideas/`.

## Test 3 — Duplicate and contradiction handling

**Prompt:** "New evidence: several merchants in a Facebook group praise Provider X's same-day settlement. We already have EV-records saying Provider X's settlement is slow."

**Pass criteria:**

- Checks whether the praise is authentic (independence, burst pattern) before recording it.
- Does not delete or silently edit the older records; adds cross-referenced `Contradictory evidence` entries on **both** sides.
- Considers time: if the old complaints predate a product fix, proposes an inflection-point check ("Provider X fixed settlement — when?") instead of averaging the two views.
- Downgrades or re-derives affected conclusions with explicit confidence reasoning; surfaces the reversal in the weekly update's Contradictions section.

**Fail signals:** old evidence deleted; the two evidence sets merged into a mushy "mixed reviews" record with no dates; contradiction noted on only one record.
