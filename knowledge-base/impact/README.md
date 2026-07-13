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
└── .lock              runtime repo-wide operation lock (gitignored)
```

## Rules

- `score-history.jsonl` is append-only. Rollback and recovery add new entries; originals are never removed — the audit trail is complete.
- Nothing here is modified except through the workflow. Scorecard/segment changes require an approved proposal (`apply-impact <id> --approver …`); segment-confidence changes additionally require `--confirm-segment-upgrade`.
- The workflow never sends email. `email-previews/` holds previews only.
- An unresolved transaction (manifest status preparing/applying/recovering) blocks new apply/rollback until it is automatically recovered.

Commands: `python3 -m impact.cli {propose|apply|reject|rollback|recover|email} …`.
