# MDR / Interchange Subsidy Model

Tests the hypothesis that card transaction economics can subsidise free-credit days, lower financing fees, cashback, free account services, transfers, or higher limits. Uses correct terminology throughout.

## 1. Who pays and who earns — do not skip

- The **accepting merchant** (where the BOTIM cardholder-merchant spends, e.g. a supplier) pays **MDR** to its **acquirer**.
- MDR is distributed among: **acquirer** (keeps MDR minus interchange minus scheme fees), **issuer** (receives **interchange**), **card scheme** (scheme/assessment fees), **processor**, and other programme participants (BIN sponsor, programme manager).
- BOTIM, as issuer or programme partner, earns **issuer interchange or an agreed programme share — never the full MDR.**
- If BOTIM also acquires on the accepting side, model acquiring margin as a separate line; do not double-count.

## 2. Per-transaction economics (bps of spend)

| Line | Downside | Base | Upside | Notes |
|---|---|---|---|---|
| Gross interchange rate (commercial card, by online/offline mix) | | | | From scheme tables for UAE commercial products |
| − Programme splits (BIN sponsor, issuer-processor, programme manager) | | | | |
| − Scheme fees borne by issuer side | | | | |
| − Processing cost | | | | |
| − Fraud loss (bps) | | | | |
| **= BOTIM net payment margin (bps)** | | | | This is the subsidy budget per AED of spend |

## 3. The subsidy budget

For a merchant with monthly card spend `S` routed through the BOTIM card:

```
Monthly payment margin  M = S × net_margin_bps / 10,000
```

`M` is the **total** monthly budget available from payment economics. Every subsidy draws from it:

### 3a. Maximum affordable free-credit days

Free-credit days cost funding on the outstanding balance:

```
cost_per_day = S × funding_rate_annual / 365
max_free_days = (M − other_subsidies) / cost_per_day
             = (net_margin_bps / 10,000) × 365 / funding_rate_annual   [if M is fully allocated to free days]
```

Worked shape: at 110 bps net margin and 8% funding, max ≈ 0.011 × 365 / 0.08 ≈ **50 days** — *before* ECL, servicing, and rewards, which reduce it substantially. Always show the post-cost figure.

### 3b. Maximum affordable cashback

```
max_cashback_% = (M − funding_cost_of_offered_free_days − other_subsidies) / S × 100
```

### 3c. Maximum affordable fee subsidy (free account / transfers / services)

```
max_fee_subsidy_AED = M + lending_contribution − funding − ECL − servicing − rewards
```

Lending contribution may top up the budget **only** if the lending model in `commercial-model.md` is itself positive after risk.

## 4. Cross-checks (all must pass)

1. **No full-MDR error:** confirm the model uses interchange/programme share, not MDR.
2. **Routing realism:** `S` uses the *routed* share of merchant spend from the commercial model, not total merchant spend.
3. **Stacking:** free days + cashback + fee subsidies are summed against one budget `M` (+ lending contribution), never each granted the full budget.
4. **Downside case:** the offered subsidy package must survive the downside net-margin case, or be explicitly flagged as a loss-leader with a stated payback period.

## 5. Output

State, for downside/base/upside: net margin (bps), monthly budget `M` per merchant, chosen subsidy package, residual contribution, and the assumption most likely to break the model (usually routed share or interchange rate).

Store completed models in `knowledge-base/commercial-models/<idea-slug>-subsidy.md`.
