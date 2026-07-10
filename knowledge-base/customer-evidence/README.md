# knowledge-base/customer-evidence/ (Workstream A)

Scored customer-evidence records, the shared source log, and weekly intelligence updates.

## Structure

```
customer-evidence/
├── README.md              ← this file
├── source-log.md          ← append-only log of every source consulted (template: source-log.md)
├── records/               ← one file per ISO week: YYYY-Wnn.md, containing that week's EV- records
└── weekly-updates/        ← one delta report per week: YYYY-Wnn.md
```

## Conventions

- Evidence IDs: `EV-YYYY-Wnn-nnn`, sequential within the week, never reused or renumbered.
- Each `records/YYYY-Wnn.md` file holds that week's records using `customer-intelligence/templates/customer-evidence.md`.
- Updating an old record happens **in its original file** (status, scores, contradiction fields), with the score history appended — records don't move between weekly files.
- Weekly updates follow `customer-intelligence/templates/weekly-market-update.md` and report deltas only.
- Before creating a record, grep existing records for the provider/pain to catch duplicates.

Owned by Workstream A. Workstream B reads and cites these records by ID but does not modify them.
