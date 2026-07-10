# Example Commands

Five worked examples of how to invoke this module. Each command implies: read the existing knowledge base first, follow `SYSTEM_PROMPT.md`, use the templates, log sources, and update — don't duplicate — existing records.

---

## 1. Pain-point deep-dive

```
Research settlement-delay pain (getting-paid/settlement-delay) among UAE
online retail merchants. Mine 1–2 star reviews of payment gateways and POS
providers, Reddit, and seller forums (English + Hindi/Urdu where relevant).
Create scored evidence records for each distinct pain instance, check for
contradictions, and update SEG- profiles it touches.
```

**Expected output:** new `EV-…` records with ten-axis scores, source-log rows, updated segment links, explicit contradictory-evidence search noted.

## 2. Competitor refresh

```
Refresh the competitor profile for Mamo. Diff their site, pricing page,
changelog, app-store listings and recent reviews against the profile's
last-verified date. Update the change log, complaints, feature requests
and gaps; flag anything that looks like an inflection point.
```

**Expected output:** updated `knowledge-base/competitors/mamo.md` with dated change-log entries; possible new `IP-…` record; new `EV-…` records from fresh complaints.

## 3. Segment discovery

```
Split "UAE F&B SMEs" into behaviour-defined segments. Use POS-vendor
communities, delivery-platform partner forums, and Google Reviews to
distinguish segments by how they get paid, settlement timing, and
working-capital cycle. Create a SEG- profile per segment with evidence.
```

**Expected output:** 2–4 new `SEG-…` files with money-in/money-out behaviour filled from evidence, plus an under-observed note where sources are thin.

## 4. Weekly market update

```
Produce the weekly market update for this week. Start from last week's
update, re-check high-yield sources and any load-bearing record >90 days
old, capture competitor moves, and list handoffs to Workstream B.
```

**Expected output:** `knowledge-base/customer-evidence/weekly-updates/YYYY-Wnn.md` following the template — deltas only, contradictions section honest, next week's focus set.

## 5. Contradiction check

```
Stress-test the conclusion "small UAE importers rely on personal credit
cards for supplier payments" (EV-…). Search specifically for evidence
against it: importers using corporate cards, trade finance, or supplier
credit terms. Rescore and adjust confidence on the affected records.
```

**Expected output:** both supporting and contradicting evidence documented on the records, confidence re-marked with reasoning, queries used listed (including the ones that found nothing).
