# Computed subsidy model — OPP-002 Supplier-payment commercial card - free-credit-days package test

Issuer-interchange/programme-share based; the accepting merchant's MDR is not BOTIM revenue and is not an input to this model.

**⚠ PRE-CREDIT-COST FIGURES:** expected credit loss and servicing are not modelled (ecl_bps/servicing_bps inputs omitted). For a free-credit-days product this structurally overstates affordability — treat every 'affordable' verdict below as an upper bound until credit costs are added.

| Line | Downside | Base | Upside |
|---|---|---|---|
| Net payment margin (bps) | 65.0 | 110.0 | 120.0 |
| Monthly budget M (AED/merchant) | 195.0 | 880.0 | 1,800.0 |
| Lending contribution top-up | 0.0 | 0.0 | 0.0 |
| Total budget | 195.0 | 880.0 | 1,800.0 |
| Cost: offered free-credit days | 131.5 | 350.7 | 657.5 |
| Cost: offered cashback | 0.0 | 0.0 | 0.0 |
| Cost: offered fee subsidy | 0.0 | 0.0 | 0.0 |
| Total package cost (stacked on one budget) | 131.5 | 350.7 | 657.5 |
| **Residual** | 63.5 | 529.3 | 1,142.5 |
| Package affordable? | YES | YES | YES |
| Ceiling: GRACE DAYS on monthly card spend if M funds free days only (not comparable to the commercial model's drawn-balance days) | 29.7 | 50.2 | 54.7 |
| Ceiling: max cashback % if M spent on cashback only | 0.65 | 1.10 | 1.20 |

Assumption-labelled inputs (base): fraud_bps, funding_rate_annual, lending_contribution, monthly_card_spend, offered_free_days, processing_bps, programme_split_bps, scheme_fee_bps
