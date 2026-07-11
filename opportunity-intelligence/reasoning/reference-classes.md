# Reference Classes

Base rates to consult (protocol step 1) before classifying any proposition. **Every figure below is currently UNSOURCED (A)** — structural placeholders stating what to look up, not facts. Replace ranges with sourced numbers (and cite) as desk research lands; until then they bound intuitions, nothing more.

| # | Reference class | Question it answers | Placeholder range (A) | Source to find |
|---|---|---|---|---|
| RC-1 | SME digital-lending pilots (emerging markets) | What share of onboarded merchants actually draw credit? | 30–60% draw within 90 days | Fintech pilot post-mortems, lender annual reports |
| RC-2 | Merchant behaviour change: new acceptance rails | What share of merchants route meaningful volume to a new rail within 6 months? | 10–30% sustain it | Wallet/QR adoption studies (India UPI merchant data, GCC wallet reports) |
| RC-3 | Unsecured SME credit losses (UAE/GCC) | What ECL is normal for unsecured SME books? | 4–12% annualised; cold-start worse | Central bank data, listed-lender disclosures, AstraTech's own book |
| RC-4 | Merchant cash advance economics | What pricing do merchants actually accept for revenue-linked credit? | 1.2–1.5 factor rates ≈ 25–50% APR-equiv | MCA industry reports; regional BNPL-for-business pricing |
| RC-5 | Commercial card programme launches | How long from decision to first live card? | 6–12 months (scheme, BIN sponsor, processor) | Programme-manager case studies — directly bounds any 7-week card MVP |
| RC-6 | Cashback-led wallet acquisition | What happens when the promotion ends? | 40–80% of promo-acquired users lapse | Wallet cohort studies — the OPP-003 rejection's base rate |
| RC-7 | Supplier card acceptance (B2B wholesale) | What share of wholesale suppliers accept cards without surcharge? | 10–35%, sector-dependent | VE-002 measures this locally; industry acquiring data bounds it |
| RC-8 | Waitlist/fake-door conversion | What completion rate is "good" for a committed sign-up? | 5–15% typical; 40% is ambitious | Growth-experiment benchmarks — calibrates VE-001's thresholds |

## Usage rules

- Cite the RC id in the profile/recommendation where the base rate was consulted ("RC-2 says 10–30%; our base case assumes 30% — top of the class range, justified by …").
- When a base rate and our assumption diverge, the divergence must be argued explicitly — never silently assume above the class range.
- When real sources land, replace the range, cite, and note the date; keep the old placeholder struck through so drift is visible.
- RC-8 is a standing caution: VE-001's 40% success threshold sits *above* the typical waitlist class range — deliberate (we demand strong signal), but it means "inconclusive" outcomes are likely and the redesign path matters.
