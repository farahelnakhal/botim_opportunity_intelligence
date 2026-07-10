# Source-Discovery Guide

How the agent finds evidence sources autonomously. The starting list below is a floor, not a ceiling — every research run should attempt to discover at least one new relevant source, and every source used (or ruled out) is logged per `templates/source-log.md`.

## Starting sources

**Reviews & ratings:** Apple App Store, Google Play, Huawei AppGallery, Trustpilot, G2, Capterra, Product Hunt, Google Reviews.

**Communities & social:** Reddit, YouTube comments, TikTok comments, Instagram comments, LinkedIn comments, X posts, public Facebook groups, public Telegram groups, public Discord communities.

**Merchant & seller forums:** Shopify Community, Amazon Seller forums, Noon seller communities, UAE entrepreneur forums, free-zone business communities, accounting-software forums, POS support communities, payment-gateway forums.

**Vendor-published:** public help centres, public support boards, feature-request boards, product changelogs, public complaint sites.

**Long-form:** podcasts, founder interviews, merchant case studies.

**Demand signals:** search-demand tools (e.g. keyword volume for "delayed settlement <provider>", "<provider> alternative").

**Local-language communities** in Arabic, Hindi, Urdu, Malayalam, and Tagalog.

## How to infer new sources

Work backwards from the customer, not forwards from a source list. For the segment under study, ask:

1. **Where does this merchant already spend time?** (industry, geography, platforms used)
   - A Dubai dropshipper → Shopify Community, dropshipping subreddits, TikTok Shop seller groups.
   - A cash-heavy Deira trader → WhatsApp/Telegram trade groups, Arabic/Urdu forums, Google Reviews of local banks.
   - A restaurant owner → POS vendor forums (Foodics, Loyverse), delivery-platform seller communities (Talabat, Deliveroo partner hubs).
2. **What tools does the workaround involve?** Every workaround tool has its own reviews, forum, and feature-request board — mine those for the underlying pain.
3. **Who else hears this complaint?** Accountants, PRO services, free-zone helpdesks, business-setup consultants — their content and Q&A pages surface recurring merchant pain.
4. **What would this merchant search for?** Generate the queries a frustrated merchant would type ("Stripe UAE payout delay", "business account without minimum balance UAE", "شركة تمويل للمشاريع الصغيرة") and follow where the results lead.
5. **Which language does this merchant complain in?** Match search language to the segment's likely community language.

## Query patterns that surface behavioural evidence

- `"<provider>" + (alternative | switch | leaving | fed up | cancel)`
- `"<pain>" + (workaround | how do you | anyone else)`
- `site:reddit.com <provider> UAE`
- Review filters: 1–2 star reviews, sorted by recent, on every competitor app.
- Feature-request boards sorted by votes.
- Changelogs diffed against last verified date in the competitor profile.

## Access rules

Never bypass paywalls, authentication, CAPTCHAs, robots.txt, anti-bot controls, rate limits, or private groups.

When direct access is unavailable, use lawful alternatives and label the evidence accordingly:

| Alternative | Label in evidence record |
|---|---|
| Official API | `api` |
| Public search snippet | `search-snippet` |
| Public RSS feed | `rss` |
| Internet Archive | `archived` |
| Review aggregator | `aggregator` |
| Publicly indexed page | `public-index` |
| Licensed database | `licensed` |
| Manual review instructions (for a human) | `manual-collection-needed` |

`manual-collection-needed` items go in the source log with exact instructions (where to look, what to capture) so a human can collect them.

## Source quality screen

Before relying on a source, check:

- **Independence** — is it customer-authored, or vendor/affiliate content?
- **Recency** — is the complaint dated, and still plausible given product changes since?
- **Authenticity** — burst of similar-wording 5-star reviews = suspicious; exclude and note it in the competitor profile.
- **Specificity** — does it name amounts, delays, fees, providers? Specific beats generic.
