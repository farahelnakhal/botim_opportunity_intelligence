# Reference Classes

Base rates to consult (protocol step 1) before classifying any proposition. Rows marked **SOURCED** were calibrated in the 2026-07-11 desk-research pass — details and links in `knowledge-base/commercial-models/BENCHMARKS.md`. Remaining rows are unsourced placeholders bounding intuition only.

| # | Reference class | Question it answers | Placeholder range (A) | Source to find |
|---|---|---|---|---|
| RC-1 | SME digital-lending pilots (emerging markets) | What share of onboarded merchants actually draw credit? | 30–60% draw within 90 days | Fintech pilot post-mortems, lender annual reports |
| RC-2 | Merchant behaviour change: new acceptance rails | What share of merchants route meaningful volume to a new rail within 6 months? | 10–30% sustain it | Wallet/QR adoption studies (India UPI merchant data, GCC wallet reports) |
| RC-3 | Unsecured SME credit losses (UAE/GCC) | What ECL is normal for unsecured SME books? | **PART-SOURCED:** UAE system NPL 2.3% (Q1-26), 3.4% (Q2-25) — all lending; SME unsecured runs a multiple. Our 6%/12% base/downside now bounded from below | SME-specific split still needed: AstraTech book, lender disclosures |
| RC-4 | Merchant cash advance economics | What pricing do merchants actually accept for revenue-linked credit? | **SOURCED:** factors 1.1–1.5 (1.2–1.35 common); APR-equiv ~40% to >350%; RBF 1.05–1.2 over 6–24 mo | BENCHMARKS.md §3 — grounds PRED-004 resolution: our 16–24% is below class |
| RC-5 | Commercial card programme launches | How long from decision to first live card? | 6–12 months (scheme, BIN sponsor, processor) | Programme-manager case studies — directly bounds any 7-week card MVP |
| RC-6 | Cashback-led wallet acquisition | What happens when the promotion ends? | 40–80% of promo-acquired users lapse | Wallet cohort studies — the OPP-003 rejection's base rate |
| RC-7 | Supplier card acceptance (B2B wholesale) | What share of wholesale suppliers accept cards without surcharge? | 10–35%, sector-dependent | VE-002 measures this locally; industry acquiring data bounds it |
| RC-8 | Waitlist/fake-door conversion | What completion rate is "good" for a committed sign-up? | **SOURCED:** page-visitor→signup median ~11% (typical 2–5%, top 10–20%); fintech landing pages 1.7–2.3% | BENCHMARKS.md §4. NB: VE-001/VE-003 thresholds (30–40%) use a stricter denominator — *offered qualified merchants*, not page visitors |
| RC-9 | UAE SME formal-credit access | How underserved is the segment, really? | **SOURCED:** SMEs get 9.5–9.7% of trade/industrial bank credit; unsecured rejection up to 77% (CBUAE 2020); ~25–28% have any bank financing | BENCHMARKS.md §2 — "credit access unavailable elsewhere" is an evidenced switching reason |
| RC-10 | UAE domestic card interchange | What does the issuer side actually earn? | **SOURCED (official):** commercial cards 2.00–2.10% general segments; consumer credit 1.15–2.20%; debit CP 0.75% cap AED 37.50; segment programs 0.50–1.05%; large ticket 0.95%+US$100 | Visa UAE schedule, effective 2024-10-01 (BENCHMARKS.md §1); Mastercard tables still to pull |

## Usage rules

- Cite the RC id in the profile/recommendation where the base rate was consulted ("RC-2 says 10–30%; our base case assumes 30% — top of the class range, justified by …").
- When a base rate and our assumption diverge, the divergence must be argued explicitly — never silently assume above the class range.
- When real sources land, replace the range, cite, and note the date; keep the old placeholder struck through so drift is visible.
- RC-8 is a standing caution: VE-001's 40% success threshold sits *above* the typical waitlist class range — deliberate (we demand strong signal), but it means "inconclusive" outcomes are likely and the redesign path matters.
