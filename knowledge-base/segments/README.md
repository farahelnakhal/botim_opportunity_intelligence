# knowledge-base/segments/ (Workstream A)

One profile per customer segment, using `customer-intelligence/templates/customer-segment.md`. Files are named `SEG-<kebab-slug>.md`.

## Rules

- Never a segment called "SMEs" or "UAE SMEs" — segments are defined by shared *behaviour* (how money comes in, how it goes out, the working-capital cycle), not just industry labels.
- Example of the right altitude: `SEG-uae-importers-upfront-pay.md` — "Small UAE importers that pay suppliers upfront but collect from customers after 30–60 days."
- A segment profile is created only when at least one evidence record supports it; profiles list their `EV-…` evidence base.
- Segments may overlap; note relationships ("subset of…", "overlaps with…") rather than forcing a hierarchy.
- Mark under-observed segments explicitly (cash-heavy, non-English-speaking merchants are under-represented in online sources — absence of complaints there is not absence of pain).

## Index

| Segment | File | Confidence | Last verified |
|---|---|---|---|
| UAE micro/small online merchants on PSP gateways/payment links | `SEG-uae-online-sme-psp-merchants.md` | Medium | 2026-07-10 |
| UAE marketplace sellers (Amazon.ae/Noon) | `SEG-uae-marketplace-sellers.md` | Low–Medium | 2026-07-10 |
| UAE brick-and-mortar POS merchants | `SEG-uae-pos-merchants.md` | Low (stub) | 2026-07-11 |
| Small UAE importers paying suppliers upfront, collecting at 30–90 days | `SEG-uae-importers-upfront-pay.md` | Low (upgrade condition stated in profile) | 2026-07-11 |

(Keep this index current as profiles are added.)

Owned by Workstream A. Workstream B reads and cites segments by ID but does not modify them.
