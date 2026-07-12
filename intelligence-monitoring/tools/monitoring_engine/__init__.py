"""Intelligence Monitoring & Alerting engine (Workstream C).

Deterministic layer under the module's LLM reasoning, mirroring the
architecture of opportunity_engine:

- significance: 5-axis scoring validation + mechanical tier rule
- events: event schema, fingerprinting, dedup/threading, JSONL store
- kbwatch: the knowledge-base differ (state snapshots, git-ref baselines)
- route: alert routing per user preferences + fatigue budgets
- digest: daily/weekly digest compilation
- alerts: alert ledger + instant-alert outbox (file-based transport)
- summaries: AI-summary schema validation (12 sections + flags block)
- adapters: adapter framework + the manual-intake adapter

Pure standard library (kbwatch shells out to `git` for --from-ref baselines
only). Writes ONLY under knowledge-base/monitoring/. Reads the other
modules' artefacts via Workstream B's parsers — reuse over reimplementation.
"""

__all__ = ["significance", "events", "kbwatch", "route", "digest"]
