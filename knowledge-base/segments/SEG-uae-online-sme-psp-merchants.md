# SEG-uae-online-sme-psp-merchants — UAE micro/small online merchants collecting via PSP gateways and payment links, exposed to settlement lag and opaque fund holds

**Created:** 2026-07-10 · **Last verified:** 2026-07-10 · **Confidence:** Medium

### Identity

| Field | Value |
|---|---|
| Industry | E-commerce/retail, services, agencies, freelancers (mixed digital-first) |
| Business size | Micro to small (solo → ~20 staff) |
| Revenue band | Unknown; Mamo plan tiers suggest meaningful cluster below AED 50k/month collections, next tier to AED 500k/month |
| B2B or B2C | Mostly B2C; B2B services minority (invoicing/payment links) |
| Mainland or free-zone | Both (trade licence required by all PSPs; unlicensed micro-sellers excluded from mainstream gateways — see Shopify Community, SRC-010) |
| Digital or cash-heavy | Digital |
| Decision-maker | Owner |

### Money in

| Field | Value |
|---|---|
| How customers pay them | Cards via gateway/checkout (Telr, PayTabs, Tap, Stripe, Amazon Payment Services), payment links/QR (Ziina, Mamo), BNPL (Tabby/Tamara), some COD |
| Typical settlement timing | Policy baselines: T+3 (Tap) to T+5 (Stripe, Shopify Payments, Mamo standard) to T+7 (Telr contract). Same/next-day exists as paid add-on (Mamo +0.5–0.75%) or negotiated (Tap T+1) |
| Typical receivables delay | Settlement lag is the receivable; tail risk: compliance/risk holds of weeks to 540 days (EV-001…005, 007) |

### Money out

| Field | Value |
|---|---|
| How they pay suppliers | Bank transfer; supplier payments strained when payouts delayed (EV-2026-W28-002) |
| Working-capital cycle | Short but fragile: inventory/ad spend upfront → sales → 3–7-day settlement → tail-risk holds can stretch to months |

### Financial stack today

| Field | Value |
|---|---|
| Existing credit sources | Largely unobserved this run (banking-access research pending); eFunder/Zelo-style receivables advances existed via Mamo |
| Existing bank accounts | Business account required for gateway settlement; access friction is its own pain (pending research) |
| Existing cards | Mamo/Pemo/Alaan/Qashio corporate prepaid-debit cards available at this end of market |
| Existing wallets | PSP stored-value balances (Mamo, Ziina) function as de-facto wallets pre-settlement |

### Jobs, pains, switching

| Field | Value |
|---|---|
| Main jobs-to-be-done | Get paid online with a licence-light setup; get money to the bank fast and predictably; keep fees survivable |
| Main pain points | 1. Opaque fund holds/suspensions (EV-004, EV-005, EV-003, EV-001) — severity 5 tail; 2. settlement slower than promised/needed (EV-001, EV-002, EV-007 baseline); 3. support silence during money problems (EV-002, EV-005); 4. unexplained deductions (EV-006) |
| Current workarounds | Escalation loops; regulator complaints (Sanadak/DFSA — EV-004); re-billing via alternative rails (EV-007); paying same-day-settlement surcharges (willingness-to-pay signal) |
| Switching triggers | Fund holds and forced closures (switching is often forced, not chosen); degraded payout speed; fee surprises |
| Relevant competitor products | mamo.md; Ziina, Tap, Telr, PayTabs, Network International (profiles pending); wio.md (acquiring incoming — IP-2026-001) |

### Evidence base

- Evidence records: EV-2026-W28-001, -002, -003, -004, -005, -006, -007
- Under-observed: Arabic/Hindi/Urdu-language merchants (not yet searched); Reddit communities (lawfully inaccessible); satisfied merchants (review-site selection bias). The modal merchant experience is likely acceptable — the documented pain concentrates in the compliance-flagged tail, where communication collapses.
