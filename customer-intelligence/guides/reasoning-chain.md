# Reasoning Chain — the module's operating loop

Every research task walks this chain. Sources are inputs to the chain, never the output. A step with no evidence is answered "unknown" — explicitly, in the synthesis — not skipped and not padded with plausibility.

## The fourteen steps

| # | Step | The question | Answered when | Captured in | Failure mode |
|---|---|---|---|---|---|
| 1 | Customer | Who exactly is this? | A behaviour-defined segment, not a demographic label | `Customer segment` field; SEG- profile | "UAE SMEs" |
| 2 | Job-to-be-done | What are they trying to complete? | The job stated from the merchant's side ("get paid tonight so I can restock tomorrow"), not the product's side | SEG "Main jobs-to-be-done" | Describing our product category as their job |
| 3 | Pain | What payment/credit pain blocks the job? | A taxonomy-coded pain with the merchant's own words | EV record: `Pain category`, `Exact customer wording` | Pain named only in analyst vocabulary |
| 4 | Severity/frequency/cost | How bad, how often, how expensive? | Scored 1–5 with anchors; amounts/durations quoted where stated | EV scores + `Financial impact` | Adjectives instead of anchored scores |
| 5 | Workaround | What do they do instead today? | The actual current behaviour named (or "no workaround found") | `Current workaround` | Assuming inaction |
| 6 | Workaround signal | What does the workaround reveal about demand? | The cost/risk they already accept is stated — that is the price they're paying today | `Workaround cost`, `Willingness-to-pay signal` | Treating a workaround as mere colour, not as revealed demand |
| 7 | Behavioural evidence | What did merchants *do* (not say)? | Each signal tagged with its evidence class (see below) | `Switching signal`, evidence class labels | Complaint counts presented as behaviour |
| 8 | Contradiction | What weakens or reverses this? | Counter-queries run and logged; contradicting evidence recorded on both sides | `Contradictory evidence` (with actual queries) | "None found" with no queries listed |
| 9 | Competitor | Who serves this customer now? | Named providers mapped to the segment, profiles linked | Competitor profiles; SEG "Relevant competitor products" | Ignoring incumbents because they're boring |
| 10 | Competitor failure | Where do they *structurally* fail? | Failure tied to their model/economics/licence (can't fix it cheaply), distinguished from incident-level noise | Competitor "Gaps"; EV records | Treating an outage or one bad review as structural |
| 11 | Inflection point | Why does this matter more now? | A dated change linked, or explicitly "no timing driver found" | IP- record reference | Inventing urgency; every finding "urgent now" |
| 12 | Product implication | What does the evidence point at? | An evidence-led handoff citing IDs — direction and rationale, not a spec | `Product implication`; weekly Handoffs | Writing a product recommendation (Workstream B's job) |
| 13 | Uncertainty | What remains unknown? | Confidence stated; the specific unknowns that cap it listed | `Evidence confidence`; synthesis | Hiding unknowns to make the finding look stronger |
| 14 | Next action | What's the next best question? | One concrete research question or customer-validation action, answerable by evidence | Weekly "Next week's focus" | Ending with a summary instead of a next step |

## The six evidence classes

Defined fully in `guides/research-quality.md` (mapped to the evidence-strength ladder). In ascending strength: **complaint → stated interest → observed behaviour → workaround spending → switching intent → actual switching.** Every signal cited in a synthesis or record narrative names its class. The classes keep the module honest about the difference between "merchants are angry" (complaint), "merchants say they'd pay" (stated interest), and "merchants already pay for a worse version" (workaround spending — the strongest demand signal short of switching).

## Query generation follows the chain

Steps 1–2 and 5 generate the search queries (what would *this merchant* type when *this job* fails, what tools does *the workaround* involve) — see `guides/source-discovery.md`. Provider-anchored queries are the correct tool for competitor passes (steps 9–10) and for explicit competitor-research tasks; they are not the default for pain discovery.

## The 14-point research-run synthesis

Every research run ends with a synthesis block covering the fourteen numbered outputs (segment · JTBD · ranked pains · observed behaviour · workaround · workaround cost · supporting evidence · contradicting evidence · competitors · structural failures · inflection point · implication · confidence+unknowns · next action). Format lives in `templates/weekly-market-update.md`. Cite existing EV/SEG/IP/SRC IDs wherever they exist; a synthesis may rest entirely on existing records — a run is not obliged to mint new ones.

## Worked micro-example (from the live knowledge base)

Chain applied to the W28 hold-pain finding: **(1)** SEG-uae-online-sme-psp-merchants, **(2)** "get card revenue into my bank account predictably so I can pay suppliers," **(3)** `getting-paid/settlement-delay` — "funds held for more than 2 months" (EV-001), **(4)** severity 5 at the tail (540-day holds, EV-004/005), **(5)** workaround: regulator escalation, re-billing via other rails, **(6)** merchants pay +0.5–0.75% for same-day settlement (mamo.md) — workaround spending, revealed demand, **(7)** actual switching mostly *forced* (closures), one Sanadak/DFSA escalation (EV-004), **(8)** counter-evidence: modal experience is fine — Ziina "usually next day" praise (EV-003); conclusion narrowed to the compliance-flagged tail, **(9)** Mamo, Tap, Ziina, Telr, PayTabs, Stripe, **(10)** structural failure: PSPs can't underwrite chargeback risk, so they hold funds — a lender could, **(11)** IP-2026-001 (Wio assembling acceptance+credit, window narrowing), **(12)** handoff: hold-underwriting/settlement-reliability wedge (EV-003/004/005 + mamo.md pricing), **(13)** Medium confidence — snippet-derived quotes, Arabic-speaking majority unobserved, **(14)** next: verify Trustpilot quotes on-page; Arabic pass on the same pain.
