# Commercial Model Template

Use for every payment-and-credit proposition. **All figures are ranges (downside / base / upside), in AED unless noted.** Every input is labelled Fact (F), Estimate (E), or Assumption (A) with its source.

## 1. Volume drivers

| Input | Downside | Base | Upside | F/E/A | Source |
|---|---|---|---|---|---|
| Active merchants (month 12) | | | | | |
| Monthly spend per merchant | | | | | |
| Share of spend routed through BOTIM | | | | | |
| Online / offline mix | | | | | |
| Eligible transaction volume (product of the above) | | | | | |

## 2. Revenue lines

| Line | Downside | Base | Upside | Notes |
|---|---|---|---|---|
| Gross interchange (eligible volume × blended interchange rate) | | | | Use scheme-published commercial-card rates; do NOT use full MDR |
| BOTIM net interchange share (after issuer-processor / BIN sponsor / programme splits) | | | | State the assumed split explicitly |
| Acquiring revenue (only if BOTIM acquires) | | | | Net of interchange paid away + scheme fees |
| Financing revenue (drawn balance × rate × duration) | | | | |
| Subscription revenue | | | | |
| Transfer revenue | | | | |
| FX revenue | | | | |
| Supplier commissions | | | | |
| **Total revenue** | | | | |

## 3. Cost lines

| Line | Downside | Base | Upside | Notes |
|---|---|---|---|---|
| Cost of capital (avg drawn balance × funding rate × avg credit duration) | | | | |
| Average credit duration (days) — input | | | | |
| Expected credit loss (drawn balance × ECL rate) | | | | Show ECL rate assumption separately |
| Fraud loss | | | | |
| Processing cost (per txn and/or bps) | | | | |
| Scheme fees | | | | |
| Rewards / cashback | | | | |
| Servicing cost (support, collections, ops) | | | | |
| Customer-acquisition cost (amortised) | | | | Distinguish organic BOTIM-channel CAC from paid CAC |
| **Total cost** | | | | |

## 4. Outputs

| Output | Downside | Base | Upside |
|---|---|---|---|
| Contribution margin (AED / merchant / month) | | | |
| Contribution margin (% of revenue) | | | |
| **Break-even point** (merchants and months, at base-case unit economics) | | | |
| Maximum affordable free-credit period (days) | | | |
| Maximum affordable cashback (% of spend) | | | |
| Maximum affordable fee subsidy (AED / merchant / month) | | | |

Derive the three "maximum affordable" lines with `mdr-interchange-subsidy-model.md` — the binding constraint is BOTIM's **net** payment economics plus lending margin, not gross MDR.

## 5. Assumption register

List every (A)-labelled input with: value used, why, sensitivity (what happens to contribution margin if it is 50% worse), and the evidence or experiment that would firm it up.

## 6. Verdict

- Under which case does the model break even, and on what does that most depend?
- The one number to validate first.

Store completed models in `knowledge-base/commercial-models/<idea-slug>.md`.
