# knowledge-base/monitoring/ (Workstream C)

Event store, alert ledger, preferences, and digests for the Intelligence Monitoring & Alerting module. Design: `intelligence-monitoring/DESIGN.md` · schemas: DESIGN §9 · validation: `python3 intelligence-monitoring/tools/monitor.py check` (part of the integration gate).

```
entities.json            monitored entities (competitor entities reference A's profiles)
events/YYYY-Wnn.jsonl    fingerprinted, deduplicated, mechanically-tiered events
state/kb-state.json      the KB watcher's last snapshot (diff baseline)
preferences/<user>.json  channels, min tiers, fatigue budgets, subscriptions
digests/                 compiled digests — committed intelligence artefacts
evidence-candidates/     external detections awaiting Workstream A validation (A promotes → EV)
summaries/               AI summaries for important/critical events (P2)
alerts/                  instant-alert ledger (P2)
```

Rules: Workstream C writes only in this folder; it never authors evidence — `evidence-candidates/` is an intake that **Workstream A** reviews and promotes under its own rules. Tiers are computed (`monitor.py check` recomputes them); event/alert ids follow the repo's collision rules.
