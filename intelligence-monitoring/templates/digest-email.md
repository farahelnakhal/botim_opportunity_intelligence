# Template — Executive Digest Email

Rendered from `monitor.py digest`; the committed markdown in `knowledge-base/monitoring/digests/` is the canonical artefact, email is a transport. Rules: subject = counts + single headline; every item = what/why/impact/action in ≤5 lines; confidence always stated; every item links to the full summary; "no action" is an explicit statement, never an omission; ≤3-minute read.

```
Subject: [BOTIM Intel] {n_critical} critical, {n_important} important — {headline} ({date})

INTELLIGENCE BRIEF — {date}                          {read_time} read
──────────────────────────────────────────────────────────────
{for each critical event}
🔴 CRITICAL — {title}
   What: {facts, sourced}. Why: {significance}.
   Impact: BOTIM — {…}. AstraTech — {…}.
   Recommended: {actions mapped to mechanisms}.
   Confidence: {H/M/L (why)}.                    [Full analysis →]

{for each important event — 2-line form}
🟠 {title} — {why it matters}. Recommended: {action | "no action — {reason}"}. [→]

── CUSTOMER CHANGES ({n}) ──────  ── COMPETITOR MOVES ({n}) ──────
 • {one-liners}                    • {one-liners}
──────────────────────────────────────────────────────────────
Strategic read: {≤2 sentences across events}.
You receive {frequency} alerts for {n} entities, {n} segments. [Preferences]
```
