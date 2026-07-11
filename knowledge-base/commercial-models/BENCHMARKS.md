# Commercial Benchmarks (sourced desk research)

Calibration data for model inputs and reference classes. Collected 2026-07-11 from public sources; each row states what it firms up. **Rule: an input may be relabelled (A)→(E) only with a row here; (F) only for official published schedules.**

## 1. Card economics — the big correction

| Finding | Value | Source | Model impact |
|---|---|---|---|
| Visa UAE **domestic commercial card interchange** (Business/Corporate/Purchasing), effective 2024-10-01 | **2.00%** product rate (2.05% downgrade); Platinum Business 2.05%, Signature Business 2.10% | Visa UAE Interchange Reimbursement Fees PDF (official, fetched 2026-07-11) | OPP-002 gross interchange was assumed 90–170 bps — official rack rate is ~200 bps for general merchant segments. Inputs re-based to 130/180/200 (E); downside covers segment programs (supermarket 1.05%, large ticket >US$150k at 0.95%+US$100) and downgrades |
| Visa UAE consumer credit interchange | 1.15% (Classic) to 2.20% (Infinite Qualified) | same | Bounds any consumer-side economics |
| Visa UAE debit consumer | CP 0.75% cap AED 37.50; CNP 1.00% cap AED 50 | same | Caps bind above ~AED 5,000 tickets — relevant to wallet-linked card ideas |
| Regulatory context | CBUAE Notice 1998/2024 harmonisation; Mastercard UAE tables also effective 2024-10-01 | Mastercard MEA interchange page | Mastercard tables still to be pulled for blend accuracy |

**Caveat honestly stated:** rack rates ≠ programme economics. BOTIM's net share still depends on BIN sponsor/processor splits (still (A)); and supplier-payment mixes may skew to segment/large-ticket programs below 200 bps. That's why the re-based inputs are (E) with a 130 bps downside, not (F) at 200.

## 2. SME credit context (UAE)

| Finding | Value | Source | Model impact |
|---|---|---|---|
| SME share of trade/industrial bank credit | **9.5–9.7%** (2024) | CBUAE via Zawya/Arab News | Confirms structural underserving → demand-side thesis for OPP-001/OPP-010 |
| Unsecured SME loan rejection rate | **up to 77%** (CBUAE 2020 MSME survey) | International Banker | "Credit access unavailable elsewhere" switching reason is evidence-based, not asserted |
| SMEs with any bank financing | ~25–28% | SME Finance Forum / Channel Capital | Same |
| GCC SME funding gap | ~US$250bn (Kearney via Channel Capital) | Channel Capital | Market-context only — per module rules, never lead with TAM |
| UAE system NPL ratio | 6.8% (Q3-22) → 3.4% (Q2-25) → **2.3% (Q1-26)**; 2026 bank guidance ~2.5% | Alvarez & Marsal UAE Banking Pulse; World Bank | System-wide, all lending. SME unsecured runs a multiple of system — our 6% base / 12% downside ECL stays (A) but is now bounded from below |

## 3. Pricing benchmarks (revenue-linked credit)

| Finding | Value | Source | Model impact |
|---|---|---|---|
| MCA factor rates | 1.1–1.5 typical; 1.2–1.35 common for established businesses | LendingTree, NerdWallet, Crestmont | Market-accepted pricing for revenue-linked products |
| MCA APR-equivalents | ~40% to >350% depending on term | Credible Law, Crestmont | OPP-001's 16–24% APR-equiv is *well below* the class — pricing risk is competition from banks, not merchant acceptance → PRED-004 resolved TRUE |
| Revenue-based financing factors | 1.05–1.2 over 6–24 months (≈10–40% APR-equiv) | LendingTree | The gentler comparable; our base 20% sits inside it |
| Funding-cost anchor | 3M EIBOR ~3.66% (Mar-26), ~3.9% (Jul-26); bank margins typically +1.0–1.5% on retail benchmarks | CBUAE, Trading Economics, Capital Zone | Our 8% base funding is conservative by ~150–250 bps; kept (A) pending AstraTech treasury confirmation — a real upside lever, not booked |

## 4. Validation benchmarks

| Finding | Value | Source | Model impact |
|---|---|---|---|
| Waitlist page-visitor→signup conversion | median ~11%; typical 2–5%; top 10–20% | GetWaitlist, Waitlister, ScaleMath | RC-8 sourced |
| Fintech/financial-services landing pages | **1.7–2.3%** visitor conversion | Landerlab industry data | VE-001/VE-003 thresholds (30–40%) use a different denominator — *offered, qualified merchants*, not page visitors — deliberately stricter; documented in the RC-8 row |

## Sources

- Visa UAE Interchange Reimbursement Fees (official PDF, effective 2024-10-01): https://ae.visamiddleeast.com/content/dam/VCOM/regional/cemea/unitedarabemirates/home-page/support-consumer/visa-uae-interchange-reimbursement-fees-1-october-2024.pdf
- Mastercard MEA interchange: https://mea.mastercard.com/en-region-mea/mea-interchange.html
- CBUAE SME facilities (Zawya): https://www.zawya.com/en/business/banking-and-insurance/banks-provide-222bln-in-financial-facilities-to-smes-by-end-of-q1-24-cbuae-fipt1d67 · (Arab News): https://www.arabnews.com/node/2576615/business-economy
- SME rejection/access: https://internationalbanker.com/banking/sme-banking-2-0-the-gap-remains/ · https://channelcapital.io/the-gccs-sme-financing-gap/
- UAE NPL: https://www.alvarezandmarsal.com/sites/default/files/2026-07/A&M_UAE%20Banking%20Pulse%20Q1_Rework_Landscape-Final_2.pdf · https://data.worldbank.org/indicator/FB.AST.NPER.ZS?locations=AE
- MCA/RBF pricing: https://www.lendingtree.com/business/understanding-factor-rates/ · https://www.nerdwallet.com/business/loans/calculators/merchant-cash-advance-mca · https://crediblelaw.com/merchant-cash-advance-apr-calculator/
- EIBOR: https://www.centralbank.ae/en/forex-eibor/eibor-rates/ · https://tradingeconomics.com/united-arab-emirates/interbank-rate
- Waitlist benchmarks: https://getwaitlist.com/blog/waitlist-benchmarks-conversion-rates · https://landerlab.io/blog/landing-page-conversion-rate · https://scalemath.com/blog/what-is-a-good-waitlist-conversion-rate/
