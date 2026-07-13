# knowledge-base/impact/ (jointly owned — Workstream A + B)

Data for the human-governed evidence-impact workflow (code in `impact/`, registered in `WORKSTREAMS.md`).

```
impact/
├── proposals/         PROP-*.json — generated impact proposals (pending until applied/rejected)
├── transactions/      TXN-*.json manifests + per-txn backups (operational; gitignored)
├── score-history.jsonl   append-only audit log (applied / rollback / recovery) — never edited or deleted
├── assumptions/       <opp>.json — per-opportunity assumption register
├── monitoring/        <opp>-summary.md — regenerated monitoring summary (transactional output)
├── email-previews/    <PROP>.md — executive email previews (preview only; nothing is ever sent)
├── assumptions/       <opp>.json — AUTHORITATIVE assumption store (mutated only by approved impacts)
├── assumption-registers/  <opp>.json — DERIVED rich read model (regenerable; gitignored)
├── assumption-metadata/   <opp>.json — OPTIONAL human enrichment (owners, target dates, rejection conditions, manual/regulatory assumptions)
├── briefs/            <opp>.{md,json} + portfolio.* — executive briefs (derived; gitignored)
├── research-requests/ REQ-*.json — draft Part A research requests (derived; gitignored)
├── evidence-gaps.{json,md}  portfolio gap report (derived; gitignored)
└── .lock              runtime repo-wide operation lock (gitignored)
```

## Authoritative vs generated (read model)

- **Authoritative:** `assumptions/<opp>.json` (assumption status + supporting/contradicting evidence) — changed ONLY by approved impacts. `score-history.jsonl` is the append-only audit.
- **Generated read models** (`assumption-registers/`, `briefs/`, `evidence-gaps.*`, `research-requests/`): derived, regenerable, **not independently editable, never a second source of truth**. They carry `meta.source_hashes` so the UI can detect staleness. Reporting commands are read-only by default; they write only with `--write`/`--output`.

## Rules

- `score-history.jsonl` is append-only. Rollback and recovery add new entries; originals are never removed — the audit trail is complete.
- Nothing here is modified except through the workflow. Scorecard/segment changes require an approved proposal (`apply-impact <id> --approver …`); segment-confidence changes additionally require `--confirm-segment-upgrade`.
- The workflow never sends email. `email-previews/` holds previews only.
- An unresolved transaction (manifest status preparing/applying/recovering) blocks new apply/rollback until it is automatically recovered.

Commands: `python3 -m impact.cli {propose|apply|reject|rollback|recover|email} …`.
