# Merchant Pain-Point Taxonomy

Canonical categories for the `Pain category` field of evidence records. Use `<category>/<subcategory>`; add subcategories as evidence warrants (append here with a dated note), but do not rename existing ones — IDs and records reference them.

## 1. `getting-paid` — Accepting customer payments

- `getting-paid/settlement-delay` — payout/settlement slower than promised or needed
- `getting-paid/acceptance-fees` — MDR, gateway, POS fees felt as too high
- `getting-paid/payment-failures` — declines, gateway downtime, lost sales
- `getting-paid/method-gaps` — can't accept a method customers want (links, wallets, BNPL, cards)
- `getting-paid/cash-dependence` — stuck handling cash: safety, reconciliation, deposit trips
- `getting-paid/cross-border-collection` — collecting from foreign customers; FX loss

## 2. `banking-access` — Accounts and basic banking

- `banking-access/onboarding` — slow/rejected business account opening; document burden
- `banking-access/minimum-balance` — high minimum balances and penalty fees
- `banking-access/account-fees` — maintenance and transaction fees
- `banking-access/freezes-compliance` — account freezes, compliance queries, de-risking
- `banking-access/no-iban` — operating without a business IBAN (using personal accounts)

## 3. `credit-access` — Borrowing and working capital

- `credit-access/rejection` — declined by banks/lenders; collateral or vintage requirements
- `credit-access/slow-approval` — financing too slow for the need
- `credit-access/cost` — rates/fees felt as unaffordable
- `credit-access/informal-borrowing` — borrowing from family, friends, suppliers, or money circles
- `credit-access/personal-credit-for-business` — personal loans/cards funding the business
- `credit-access/limit-stagnation` — limits that don't grow with the business

## 4. `paying-out` — Paying suppliers, staff, and bills

- `paying-out/supplier-terms` — must pay suppliers upfront while collecting late
- `paying-out/cross-border-payments` — international supplier payments: cost, speed, friction
- `paying-out/payroll` — paying staff (incl. WPS friction)
- `paying-out/no-business-card` — no corporate card; personal cards for business spend

## 5. `cash-flow` — Timing gaps and visibility

- `cash-flow/receivables-delay` — customers pay 30–90+ days late
- `cash-flow/seasonality` — seasonal troughs without buffers
- `cash-flow/visibility` — can't see position across accounts/tools

## 6. `admin-tools` — Operational and compliance overhead

- `admin-tools/reconciliation` — matching payments to invoices/orders manually
- `admin-tools/expense-control` — tracking/controlling staff spend
- `admin-tools/invoicing` — creating, sending, chasing invoices
- `admin-tools/tax-compliance` — VAT/corporate-tax filing burden
- `admin-tools/tool-sprawl` — several paid tools to complete one workflow

## 7. `provider-experience` — How current providers treat merchants

- `provider-experience/support` — unreachable or unhelpful support
- `provider-experience/hidden-fees` — surprise charges, opaque pricing
- `provider-experience/product-instability` — features removed, limits cut, sudden policy shifts
- `provider-experience/trust` — fear of funds being held; horror stories driving avoidance

## Usage rules

- One evidence record may carry a primary category plus secondary tags.
- If nothing fits, use `uncategorised/<free-text>` and propose a taxonomy addition below.

## Proposed additions log

| Date | Proposed category | Rationale | Status |
|---|---|---|---|
| — | — | — | — |
