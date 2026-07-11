# Intelligence Monitoring & Alerting — Design Specification

**Status:** DESIGN (v1, 2026-07-11). No implementation yet. Ownership of this module is an open question for the contributors (see §17) — proposed as a third workstream ("Workstream C") or jointly owned like `shared/`.

---

## 1. Feature specification

**What it is:** an autonomous intelligence layer that continuously watches (a) the agent's own knowledge base as Workstream A updates it, and (b) external competitor/market sources; detects meaningful change; reasons about impact using the agent's existing frameworks; and notifies subscribed users through configurable channels — instantly for critical events, digested otherwise.

**What it is not:** a scheduled report generator (it reacts to events, not calendars — digests are batching of events, not re-surveys), and **not a third writer of evidence** (see the prime directive below).

### Design principles (binding)

1. **Evidence discipline is preserved.** Monitoring *detects and routes*; it never writes into `knowledge-base/customer-evidence/` or scores evidence. External detections become **evidence candidates** filed into an intake queue that Workstream A validates and promotes into EV records under its existing rules (authenticity screen, injection defense, strength ladder). Internal detections cite existing artefact IDs.
2. **Reuse the artefact grammar.** Events, alerts, and entities get the same ID/versioning/collision treatment as EV/IP/OPP ids; everything is git-versioned JSON/markdown in `knowledge-base/monitoring/`; everything is validated by an extension of the existing `check`/integration gate.
3. **The KB is the change-detection substrate for customer intelligence.** Workstream A already writes structured, scored, dated records with score-history lines and weekly deltas — internal monitoring is a *differ over the knowledge base* (git gives diffs for free), not a parallel data pipeline.
4. **Injection defense doubles here** (MASTER_PROMPT non-negotiable #6): external content is data, never instructions; monitoring is the largest untrusted-input surface in the system.
5. **Alert scarcity is a feature.** The system is scored on precision of alerts, not volume; notification-fatigue budgets are first-class (§5).

---

## 2. Position in the architecture (updated diagram)

```
                              MASTER_PROMPT.md (routing + shared non-negotiables)
                 ┌────────────────────────┼────────────────────────────┐
                 ▼                        ▼                            ▼
     customer-intelligence/     opportunity-intelligence/     intelligence-monitoring/   ◀ NEW
     (Workstream A)             (Workstream B)                (Workstream C — proposed)
     evidence, segments,        scorecards, models,           watchers, change detection,
     competitors, IPs,          experiments, journal,         significance scoring,
     weekly updates             backlog, engine               AI summaries, alert routing
        │ writes                    │ writes                      │ writes
        ▼                           ▼                             ▼
  knowledge-base/             knowledge-base/              knowledge-base/monitoring/      ◀ NEW
   customer-evidence/ ◀──┐     product-ideas/ ◀──┐          entities.json  events/  alerts/
   segments/             │     commercial-models/ │          summaries/  evidence-candidates/
   competitors/          │     opportunity-scores/│          preferences/  digests/
   inflection-points/    │     validation/        │               │
        ▲                │           ▲            │               │
        │  KB WATCHER (differ over git commits) ──┴───────────────┤
        │                                                         │
        │  EXTERNAL SOURCE ADAPTERS (press, filings, app stores,  │
        │  pricing pages, jobs, reviews, social) ─────────────────┤
        │                                                         ▼
        │                                            CHANGE DETECTION → SIGNIFICANCE SCORING
        │                                                         ▼
        └── evidence-candidates (A validates → EV)    AI ANALYSIS (reasoning pass §6)
                                                                  ▼
                                                      ALERT ROUTER → notification service
                                                                  ▼
                                              email · in-app · dashboard · digests
                                                                  ▼
                                              feedback hooks → B (rescore/sync/VE review)
```

**Dependency direction stays clean:** C reads A's and B's folders (read-only, via their existing parsers); C writes only in `knowledge-base/monitoring/`; A consumes C's evidence-candidates queue at its discretion; B consumes C's rescore-flags via the existing REQ/sync mechanisms. Neither A nor B depends on C existing.

---

## 3. Monitoring sources

### 3.1 Customer intelligence (internal — the KB watcher)

The watcher diffs the knowledge base per commit (or per scan) and emits events. Every requested customer-monitoring category maps to an artefact the system *already produces*:

| Requested detection | Watched artefact / signal |
|---|---|
| New interview findings | new records citing `customer-interview` template; `records/*.md` diff |
| Survey results, new market evidence | new EV records (any class); source-log additions |
| Changing pain points | EV score-history lines (axis deltas); pain-taxonomy additions log |
| New feature requests | EV "Requested feature" field changes |
| Shifts in willingness to pay | WTP axis deltas across a segment's records |
| Behavioural changes | evidence-class transitions (stated → behavioural); workaround field changes |
| New jobs-to-be-done | segment profile "Main jobs-to-be-done" diffs |
| Adoption trends | IP records (status transitions emerging→confirmed/invalidated) |
| Validation experiment results | `validation/*-result.json` observed values filled; verdict transitions |
| Confidence-score changes | EV confidence field diffs; segment confidence upgrades; record status transitions (active→superseded/needs-more-evidence) |
| (bonus) Judgment quality | decision-journal resolutions; backlog classification changes |

### 3.2 Competitor intelligence (external — source adapters)

Adapters implement one interface (§12) so sources are added by dropping in a new adapter + registry row — no core changes:

| Signal (from the brief) | Adapter type | Cadence | Notes |
|---|---|---|---|
| Product launches, positioning, website changes | `web-page-differ` (pricing/product pages, hashed + semantic diff) | daily | per-entity URL list in registry |
| Pricing changes | `web-page-differ` on tariff/pricing pages | daily | numeric extraction where possible |
| Press releases, executive announcements | `rss/newsroom` + news search | hourly–daily | |
| Funding, acquisitions, partnerships | news search + registry watch | daily | |
| Banking licences, regulatory announcements | `regulator-watch` (CBUAE/DFSA/ADGM publications) | daily | highest-precision source class |
| Payment/lending capability changes | composite: docs pages + app-store changelogs + press | daily | |
| App updates / app-store releases | `app-store` adapter (version + release notes + rating deltas) | daily | extends A's existing App Store sourcing |
| Customer reviews | `review-platforms` (Trustpilot/G2/app stores) — **reuses A's source-discovery rules & access labels** | daily | volume + sentiment + theme deltas |
| Hiring trends | `jobs-boards` (roles signalling build: "issuing", "SME credit risk") | weekly | |
| Social media announcements | `social` (official accounts only, lawful access) | daily | |

All adapters obey Workstream A's **lawful-access rules** (no paywall/CAPTCHA/robots.txt bypass) and record provenance (`SRC-` linkage, access labels, fetch dates) — same ladder as evidence.

Monitored entities start from A's existing competitor profiles (wio, mamo) + watchlist (Ziina, Tap, CredibleX, Comfi…) and the funded competitors flagged by IP-2026-002.

---

## 4. Change detection

Pipeline per raw observation: **fingerprint → dedup/correlate → classify → score → tier**.

- **Fingerprint:** hash of (entity, signal-type, normalized content). Same complaint syndicated across platforms → one event with multiple sources (mirrors A's duplicate rule).
- **Correlate:** attach to related prior events (same entity+type within window → thread, not new event) and to KB artefacts (EV/IP/SEG/OPP ids touched).
- **Classify tier:** `insignificant | informative | important | critical` — derived from scores, never hand-picked first.

### Significance scoring (1–5 each, anchors follow the repo's scoring style)

| Axis | 1 | 3 | 5 |
|---|---|---|---|
| **Business impact** | no plausible effect on any backlog OPP or segment | touches one OPP's assumptions or one segment | invalidates a load-bearing assumption, opens/closes a wedge, or moves a live decision |
| **Urgency** | no decay in value of knowing | acting this month matters | acting this week/day matters (launch window, regulatory deadline) |
| **Confidence** | single weak/unverified source | one strong or several weak aligned sources | official/primary source or multiple independent confirmations |
| **Relevance** | outside UAE SME payments/lending scope | adjacent | squarely on a monitored entity/segment/OPP |
| **Novelty** | already known (KB or prior event) | new detail on known theme | genuinely new fact changing the picture |

**Tier rule (mechanical):** `critical` = impact ≥4 AND urgency ≥4 AND confidence ≥3; `important` = impact ≥3 AND confidence ≥3 AND novelty ≥3; `informative` = relevance ≥3 and not above; else `insignificant` (stored, never notified). Confidence <3 can never exceed `informative` — unverified bombshells go to A's verification queue, not to executives (the strength-ladder rule, applied to alerts).

### Fatigue budget

Per user per channel: max N instant alerts/day (default 3); overflow demotes to digest with an explicit "demoted by budget" marker; `critical` may exceed budget but requires the confidence gate above. Repeated same-thread events collapse into thread updates.

---

## 5. AI analysis (per `important`/`critical` event)

Generated summary object (schema §9.6) — every field mandatory, evidence-linked, honest about confidence:

1. **Executive summary** (≤2 sentences) · 2. **What changed** (facts only, quoted/sourced) · 3. **Why it matters** · 4. **Impact on BOTIM** · 5. **Impact on AstraTech** · 6. **Opportunities created** (link/propose OPP candidates) · 7. **Risks created** (map to named stress scenarios where possible) · 8. **Recommended actions** (each mapped to an existing mechanism: re-score OPP-nnn, review VE-nnn, open REQ-nnn, brief exec) · 9. **Confidence** (High/Medium/Low + why, per A's ladder) · 10. **Supporting evidence** (EV/IP/SRC ids + adapter provenance) · 11. **Sources** (URLs, access labels, fetch dates) · 12. **Related previous events** (thread ids).

### 6. The reasoning pass (not a forwarding rule)

Before an alert is emitted, the analyzer answers the seven questions with **artefact-level consequences**, reusing existing machinery rather than opining:

| Question | Mechanical consequence in the existing system |
|---|---|
| Materially changes our understanding? | novelty/impact scores; if no → tier ≤ informative |
| Invalidates previous assumptions? | list the specific (A)-labelled inputs / scorecard bases / IP falsifiers touched, by id |
| Creates a new opportunity? | file a backlog **candidate** row proposal (Unscored) + evidence-candidate for A |
| Increases competitive risk? | map to a named scenario (`funded_competitor_capture`, `rate_compression`…) or propose a new custom scenario |
| Re-score product hypotheses? | emit a **rescore flag**: OPP-nnn + dimension(s) + triggering event id → lands as a sync-style suggestion for B (report-only, human applies — same rule as the sync bridge) |
| Change validation experiments? | flag VE-nnn spec sections affected (never edits thresholds — pre-commitment is inviolable; a compromised experiment is flagged for redesign as a *new* VE) |
| Inform executives immediately? | tier = critical (which requires the confidence gate) |

Everything above is logged in the event record, so "why did/didn't I get alerted" is always answerable.

---

## 7. Notifications

**Channels:** email · in-app · dashboard feed · daily digest · weekly digest · instant (critical only).
**Routing:** `critical` → instant on all subscribed channels; `important` → next daily digest + in-app; `informative` → weekly digest + dashboard only; `insignificant` → dashboard archive only.

**User configuration** (schema §9.4/9.5): frequency (instant/daily/weekly/off per channel), competitor subscriptions (by entity id), industries, customer segments (SEG- ids), regions, product categories (pain-taxonomy codes reused as the category vocabulary), alert sensitivity (minimum tier per channel), quiet hours, fatigue budget override.

### Email design (executive format)

```
Subject: [BOTIM Intel] 2 critical, 3 important — Wio launches SME acquiring (Thu 11 Jul)

INTELLIGENCE BRIEF — 2026-07-11                    3 min read
────────────────────────────────────────────────────────────
🔴 CRITICAL — Wio Business launches merchant acquiring (UAE)
   What: Payments launch confirmed via press release + pricing page (official).
   Why it matters: Closes the timing window flagged in IP-2026-001; directly
   overlaps OPP-010's acceptance wedge.
   Impact: BOTIM — first-mover claim on settlement assurance weakens.
           AstraTech — hold-underwriting differentiator UNAFFECTED (Wio has
           no lending pairing) — the wedge narrows to the credit component.
   Recommended: Re-score OPP-010 defensibility (was 3); accelerate VE-003
   decision; exec brief before Thursday's product review.
   Confidence: High (official sources).       [Full analysis →]

🟠 IMPORTANT — F&B segment: WTP signals strengthening
   3 new evidence records this week moved willingness-to-pay axis 3→4 on
   SEG-uae-pos-merchants; supports OPP-001 pricing assumption (PRED-004).
   Recommended: no action — strengthens existing plan. [Records →]

── CUSTOMER CHANGES (2) ────────────  ── COMPETITOR MOVES (3) ──────────
 • VE-002 field results 60% complete    • Mamo same-day fee 0.75%→0.60%
 • EV-008 refresh confirms holds        • CredibleX hiring "Head of Cards"
────────────────────────────────────────────────────────────
Strategic read: acceptance is getting crowded; credit-paired
propositions (OPP-010/013) remain uncontested. Full dashboard →
You receive instant+daily alerts for 6 entities, 4 segments. [Preferences]
```

Rules: subject carries counts + the single headline; every item = what/why/impact/action in ≤5 lines; every claim links to the full summary and sources; confidence always stated; no item without a recommended action or an explicit "no action".

---

## 8. Dashboard (textual wireframe)

```
┌──────────────────────────────────────────────────────────────────────┐
│ BOTIM Opportunity Intelligence — Monitor        [prefs] [unread: 4]  │
├───────────────────────────┬──────────────────────────────────────────┤
│ ALERTS (filter: tier/date)│ COMPETITOR TIMELINE (per entity, zoom)   │
│ 🔴 Wio SME acquiring       │ Wio ────●launch───●pricing───▶           │
│ 🟠 F&B WTP shift           │ Mamo ──●fee cut────────▶                 │
│ 🟠 CredibleX card hire     │ CredibleX ───●hire──●funding?──▶         │
├───────────────────────────┼──────────────────────────────────────────┤
│ TRENDING CUSTOMER ISSUES  │ OPPORTUNITY / THREAT BOARD               │
│ holds/freezes ▲▲ (8 rec)  │ ⬆ OPP-010 wedge narrows (threat+opp)     │
│ x-border fees ▲ (7 rec)   │ ⬆ OPP-013 corridor unclaimed (opp)       │
│ min-balance ─ (unvoiced)  │ ⬇ acceptance-only plays (threat)         │
├───────────────────────────┼──────────────────────────────────────────┤
│ VALIDATION PROGRESS       │ MARKET ACTIVITY (30d)                    │
│ VE-001 ▓▓▓░ interviews 9/15│ events: 23 │ critical: 1 │ dedup: 9     │
│ VE-002 ▓░░░ offers 12/40   │ top source: app-store │ noisiest: social│
│ VE-003 not started         ├──────────────────────────────────────────┤
│ VE-004 not started         │ SAVED ALERTS / WATCHES        [+ new]   │
└───────────────────────────┴──────────────────────────────────────────┘
```

---

## 9. Data model (schemas — JSON, stored in `knowledge-base/monitoring/`)

**9.1 Monitored entity** (`entities.json`): `{id: "ENT-wio", kind: "competitor|segment|regulator|platform", ref: "knowledge-base/competitors/wio.md" | "SEG-…", name, region, categories: ["getting-paid/…"], sources: [{adapter, url|query, cadence, src_id}], status: active|paused, added, notes}` — competitor entities always reference A's profile as the canonical dossier.

**9.2 Event** (`events/YYYY-Wnn.jsonl`, one JSON per line): `{id: "EVT-2026-W28-001", entity, detected_at, adapter, signal_type, fingerprint, thread_id, title, facts: [{claim, quote, source_url, access_label, fetched}], kb_links: ["EV-…","IP-…","OPP-…"], scores: {impact, urgency, confidence, relevance, novelty}, tier, dedup_of: null|EVT-…, evidence_candidate: null|path, status: new|analyzed|alerted|archived}` — ids follow the EV collision protocol.

**9.3 Alert** (`alerts/YYYY-Wnn.jsonl`): `{id: "ALR-2026-W28-001", event_ids: [...], tier, summary_ref, channels_sent: [{user, channel, at, demoted_by_budget: bool}], acknowledged_by: [], created}`.

**9.4 Notification preferences** (`preferences/<user>.json`): `{user, email, channels: {email: instant|daily|weekly|off, in_app: …, digest_day}, min_tier: {email: important, in_app: informative}, quiet_hours, fatigue_budget: 3}`.

**9.5 Subscription** (same file): `{entities: ["ENT-wio", …], segments: ["SEG-…"], regions: ["UAE"], categories: ["credit-access/*"], industries: [...], opp_watch: ["OPP-010"]}` — empty list = all.

**9.6 AI summary** (`summaries/EVT-….md` + front-matter JSON): the twelve §5 fields, each mandatory; `rescore_flags: [{opp, dimensions, reason}]`, `ve_flags: [...]`, `req_proposals: [...]`.

**9.7 Event history / threads:** `thread_id` chains events; per-entity rollup derived, not stored. **9.8 Confidence scores:** embedded per event (axis) and per summary (H/M/L + basis), same vocabulary as A's ladder — no new confidence language.

---

## 10. Event flow & notification workflow

```
 adapter/KB-watcher observation
   → fingerprint (dup? → attach to thread, stop)
   → correlate (KB links, prior events)
   → score 5 axes → tier
   ├─ insignificant → store (dashboard archive) — END
   ├─ external + could-be-evidence → write evidence-candidate → A's intake
   ├─ informative → store → weekly digest queue
   └─ important/critical → AI analysis (§5–6)
        → summary + rescore/VE/REQ flags written
        → alert created → router applies per-user prefs + fatigue budget
        ├─ critical → instant (email/in-app) to subscribed users
        └─ important → daily digest queue + in-app
   Digest compiler (daily/weekly): dedupe threads, rank by tier→impact,
   render email template, send, mark events digested.
   Feedback loop: B picks up rescore flags (sync-style report) → re-scores
   → backlog changelog cites EVT id; A promotes/rejects evidence candidates.
```

---

## 11. Integration points

| Existing component | Integration |
|---|---|
| **Customer & Market Intelligence (A)** | KB watcher consumes A's records/updates via A's own parser semantics; external review-adapters reuse A's source rules; monitoring files evidence-candidates into an intake A reviews (A remains sole author of EV records); A's weekly update §5/§6 can cite EVT ids |
| **Product & Opportunity Intelligence (B)** | rescore flags surface exactly like `sync` suggestions (report-only); OPP/VE/REQ proposals land as backlog candidates via the existing rows; journal hooks: events resolving open PRED-nnn are flagged (never auto-resolved — same-day/authorship rules stand) |
| **Knowledge base** | monitoring's folder is a sibling with the same ID/versioning/validation discipline; `check` extended with a monitoring section (schema validation, id resolution, tier-math verification) |
| **Research pipeline** | detections generate research *leads* (next-week-focus proposals), not conclusions; A's verification queue is the promotion path |
| **External data sources** | adapter registry (§3.2) with one interface; provenance via SRC- linkage |
| **Notification service** | abstract `Notifier` interface (email/in-app/webhook implementations are deployment-specific; repo ships file-based outbox + rendered digests for auditability) |
| **User management** | out of scope to build; preferences keyed by user id, pluggable to whatever identity exists (start: a static users file for the two contributors + exec distribution list) |

---

## 12. Interface definitions (planned, not yet implemented)

**CLI** (extends `run.py` conventions, or a sibling `intelligence-monitoring/tools/monitor.py`):
`monitor scan [--adapters …] [--since …]` (run watchers, emit events) · `monitor events [--tier …] [--entity …]` · `monitor analyze EVT-…` (produce summary) · `monitor digest --daily|--weekly [--user …] [--write]` · `monitor entities add|pause` · `monitor prefs <user>` · `monitor check` (schema/id validation — wired into the integration gate).

**Python API:** `adapters.base.Adapter.fetch(entity, since) -> [Observation]` · `detect.process(observation) -> Event|Thread` · `score.significance(event, kb) -> scores, tier` · `analyze.summarize(event, kb) -> Summary` (LLM layer over deterministic inputs, same architecture as the rest of the agent) · `route.dispatch(alert, prefs) -> deliveries` · `digest.compile(period, user) -> markdown`.

**Contracts:** deterministic layers (fingerprint, dedup, scoring math, routing, budgets) are pure-stdlib testable; only `analyze` is LLM-backed, and its output is schema-validated like scorecards.

---

## 13. New files / folder structure

```
intelligence-monitoring/
├── DESIGN.md                    ← this document
├── SYSTEM_PROMPT.md             ← module operating prompt (Phase 1)
├── frameworks/significance-scoring.md · reasoning-pass.md
├── templates/event.md · summary.md · digest-email.md
├── adapters/README.md           ← adapter interface + registry docs
└── tools/monitor.py · monitoring_engine/ · tests/

knowledge-base/monitoring/
├── entities.json · events/ · alerts/ · summaries/
├── evidence-candidates/         ← A's intake (A promotes → EV records)
├── preferences/ · digests/
└── README.md
```

---

## 14. Testing design (per the brief's categories)

| Category | Test design |
|---|---|
| Duplicate events | same fact via 2 adapters / 3 platforms → one event, N sources, one alert; fingerprint collision fixtures; syndicated-press fixture |
| False positives | page-differ noise (cookie banners, dates) → normalized-content hash unchanged → no event; sensitivity: cosmetic vs semantic diff fixtures |
| Conflicting reports | two sources disagreeing → single event, confidence capped ≤2, tier ≤ informative, routed to verification — never alerted as fact (mirrors A's contradiction rule) |
| Noisy data | review-burst fixture → authenticity flag, excluded from sentiment trend (reuses A's manipulation screen) |
| Missing sources | adapter timeout/410 → event stream unaffected, source marked degraded, `monitor check` warns on stale entities (no silent gaps) |
| Rapid competitor updates | 10 events/entity/day → thread collapse, one evolving alert, budget respected |
| Sentiment changes | gradual axis drift (3.0→3.4 over weeks) → no event until threshold Δ≥1 or trend rule fires; step change → event |
| Notification fatigue | budget exhaustion → demotion marker; assert a user never receives >budget instant alerts except gated criticals |
| Simultaneous events | N critical events in one scan → single combined instant brief, ranked, not N emails |
| (extra) Injection | adapter fixture containing embedded instructions → recorded as suspicious content, never alters scores (extends the P-1 battery) |
| (extra) Pre-commitment integrity | event "suggesting" a VE threshold change → flag-for-redesign only; thresholds untouched |

Plus: schema round-trips, id-collision rules, tier math property tests, digest determinism, gate integration.

---

## 15. Implementation roadmap

| Phase | Scope | Effort |
|---|---|---|
| **P0 — KB watcher + digest (highest value/effort ratio)** | events schema + `monitoring_engine` deterministic core (fingerprint/score/tier/route) + KB differ over git + weekly digest markdown + `monitor check` wired into gate; users = 2 contributors, file-based outbox | ~3–5 days |
| **P1 — External adapters (precision-first order)** | regulator-watch → app-store → newsroom/RSS → pricing differ; entities seeded from A's watchlist; evidence-candidate intake | ~1–2 weeks incremental |
| **P2 — AI analysis + instant alerts** | summary generation against schema; critical-tier gating; email rendering + send abstraction | ~1 week |
| **P3 — Dashboard + preferences UI + broader users** | static-site dashboard from JSON (fits the stdlib ethos) or hosted app; user management integration | sized later |
| **Continuous** | precision review: monthly audit of alert precision (alerts acted on / alerts sent) and fatigue metrics | — |

---

## 16. Risks & trade-offs

1. **Noise is the existential risk.** An alerting system that cries wolf gets muted; hence tier math is mechanical, confidence-gated, budgeted — and precision is the KPI, not coverage.
2. **Injection/poisoning surface grows.** Continuous ingestion of adversarial-capable text; mitigations: non-negotiable #6, adapter provenance, confidence caps for unverified sources, A's promotion gate before anything becomes evidence.
3. **Evidence-discipline erosion** if monitoring shortcuts into the KB — prevented structurally (write-boundary + candidates queue), but it's the trade-off against speed: a critical alert may cite *unpromoted* observations, and must say so.
4. **Freshness vs cost:** polling cadences are per-adapter; hourly everything is wasteful. Trade-off encoded in the registry, revisable per entity.
5. **LLM summaries can overreach** — the summary schema forces evidence links and confidence, and reuses the reasoning-pass questions; still, summaries are labelled inference, and rescore flags are report-only (humans apply), same as the sync bridge.
6. **Two-person reality:** email/dashboard infra is deployment work beyond this repo's stdlib ethos; P0/P1 deliver full value inside the repo (digests as committed markdown; "notifications" = the two contributors' workflow) before any infra spend.
7. **Ownership ambiguity** (a third writer in the repo) — must be settled before code (§17).

---

## 17. Prioritized recommendations & open questions

1. **Decide ownership first** (blocking): Workstream C with its own owner, or jointly-owned like `shared/`. WORKSTREAMS.md amendment required — both contributors must agree.
2. **Build P0 only after that** — the KB watcher + weekly digest delivers most of the value with zero external-source risk, and VE-001/002 field results landing soon are exactly the events it should catch first.
3. Seed entities from A's competitor watchlist + IP-2026-002's funded competitors (Wio, Mamo, Ziina, Tap, CredibleX, Comfi) — they're already the ones that matter.
4. Adopt the **precision KPI** from day one: log every alert's disposition (acted/dismissed) so the significance thresholds can be tuned on data.
5. Defer P3 (dashboard/users) until the digest proves its value on the two real users.
6. Open questions: email-sending infrastructure choice; whether digests should auto-commit to the repo (recommended: yes, they're intelligence artefacts) ; retention/archival policy for insignificant events; whether critical alerts may cite unpromoted evidence candidates (recommended: yes, flagged as unverified).
