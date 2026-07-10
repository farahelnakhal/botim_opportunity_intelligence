# Mamo

**Category:** SME payments & cards (payment collection + corporate cards + payouts)
**Countries:** UAE (merchants must be UAE-registered); KSA testing announced Jul 2024, no launch verified as of 2026-07-10 · **Last verified:** 2026-07-10

### Product & positioning

| Field | Value |
|---|---|
| Products | Payment links; invoicing (VAT); QR codes (no POS hardware); WhatsApp payment-link bot; e-commerce checkout/plugins (Shopify, WooCommerce, Magento) + APIs; subscriptions/recurring; corporate cards (unlimited virtual + physical, free) with spend controls, receipt capture, accounting sync (QuickBooks, Xero, Zoho Books); payouts (domestic AED 5/transfer, international 0.5%, bulk, API); Tabby BNPL acceptance. **No POS terminals** (help article, updated Feb 2025) |
| Target customers | UAE-registered SMEs and freelancers; "4,000+ businesses" claimed; industry pages: agencies, e-commerce, education, law, marketplaces, tourism, veterinary, maintenance |
| Pricing | (checked 2026-07-10) Growth AED 0/mo; Premium AED 99/mo (AED 50k+/mo collectors); Enterprise custom (AED 500k+/mo). UAE cards 2.9%+AED 1 (Growth) / 2.7%+AED 0.80 (Premium); intl cards 3.4%/3.2%; non-AED surcharge +2%/+1.5%; Tabby 6.9%+AED 1; card hold fee AED 3.50/3. Settlement: standard 5 business days; same-day +0.75%/+0.5%. Cashback 0.4–0.5% AED spend (8% non-AED intro promo, capped AED 7,500). New-customer payment cap AED 50k. USD 1,000 closure fee if fraud-related |
| Revenue model | MDR + SaaS subscription + FX surcharges + fast-settlement fees + payout fees; interchange share and float income inferred (not disclosed); possible referral economics on partner credit |

### Card & banking capability

| Field | Value |
|---|---|
| Card network | Visa |
| Issuer | **Not disclosed** — could not verify (a "Nymcard" claim circulates but is unconfirmed on any Mamo/Nymcard page). Inference: Mamo's DFSA licence covers "issuing payment instruments and issuing stored value", so may self-issue with a Visa principal-member processor |
| Direct or partner issuance | Could not verify |
| Card type | Marketed as "debit"; legal terms describe access to loaded funds — i.e. prepaid/stored-value funded from the Mamo balance |

### Lending capability

| Field | Value |
|---|---|
| Lending capability | Via partner only — terms: Mamo "acts solely as a facilitator… All terms, obligations, and recourse actions are managed exclusively by the Credit Partner"; Mamo shares platform data for credit assessment |
| Underwriting | Partner-side, using Mamo gateway payout data (eFunder partnership offered ~4 weeks' future sales in advance; eFunder now redirects to zelofinance.ai — current status unclear) |
| Repayment structure | Per credit partner (receivables-style advances historically) |

### Regulatory

DFSA-regulated (Mamo Limited, DIFC): money transmission, payment accounts, issuing payment instruments and stored value. First local UAE startup fully authorised for DFSA money-services licence (Oct 2022; ITL from Jun 2021). Registered payments facilitator with Visa and Mastercard; PCI-DSS. No CBUAE retail payments licence found — DIFC-routed.

### Market activity

| Field | Value |
|---|---|
| Partnerships | eFunder/Zelo (receivables financing, status unclear); Tabby (BNPL acceptance); accounting: QuickBooks, Xero, Zoho Books |
| Product launches | Jun 3, 2025: crossed AED 1.2bn total payment volume (Zawya, latest press item as of check) |
| Product changes | Same-day settlement surcharge tiers live; 8% non-AED cashback promo (3 months, first-time card users) — pricing page 2026-07-10 |
| Strategic direction | **Inference:** consolidating collection + spend + payouts for micro/small digital SMEs on one stored-value account; KSA ambition (Jul 2024 raise earmarked testing) unrealised so far; funding modest (~$13M total: $8M pre-A 2021, $3.4M 2024) → likely focused, not blitzscaling |

### Voice of their customers

| Field | Value |
|---|---|
| Customer reviews summary | Capterra/G2 praise: expedited same/next-day settlements, easy onboarding. Trustpilot: fund-hold and suspension complaints |
| Complaints | Account suspended without notice, all funds held 540 days, reasons undisclosed → EV-2026-W28-004 (merchant escalated to Sanadak + DFSA, Oct 2025) |
| Feature requests | Hold-reason disclosure, proportionate hold terms (from complaint threads) |
| Review authenticity notes | No manipulation bursts observed this run (shallow check — snippets only) |

### Gaps & implications

- **Gaps:** no POS/in-store hardware; no first-party lending; stored-value account, not a bank account/IBAN; new-customer AED 50k payment cap; 5-day standard settlement (same-day costs extra); suspension/hold policy opaque (own help centre confirms non-disclosure).
- **Implication for BOTIM (inference):** Mamo validates demand for SME collection+card+payout bundles in UAE, but its stored-value + partner-credit model leaves the working-capital and business-IBAN layer open — exactly where AstraTech lending + potential business IBANs could differentiate. Its paid same-day-settlement tiers show merchants pay for settlement speed.

### Change log

| Date | What changed | Source |
|---|---|---|
| 2026-07-10 | Profile created (facts as of this date) | SRC-020, SRC-021, SRC-004, SRC-019, SRC-030 |
