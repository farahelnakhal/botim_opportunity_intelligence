# shared/contracts/ — UI/data contracts (jointly owned)

Stable JSON/Markdown contracts that Farah's UI (and any consumer) can rely on. Jointly owned like the rest of `shared/`; changes follow the shared-file rule (agreement between both contributors).

Each contract states: required / optional / nullable fields, enums, `schema_version`, the **authoritative source**, and whether the object is **persisted** or **derived** (regenerable). Producers live in the jointly-owned `impact/` package; all generated outputs are read models — never a second source of truth.

| Contract | Producer | Output kind |
|---|---|---|
| `executive-brief.schema.md` | `impact/brief.py` (`impact.cli brief`) | derived |
| `assumption-register.schema.md` | `impact/tracker.py` (`impact.cli assumptions`) | derived |
| `evidence-gaps.schema.md` | `impact/gaps.py` (`impact.cli gaps`) | derived |
| `research-request.schema.md` | `impact/research_request.py` (`impact.cli research-request`) | derived (draft) |

**Common `meta` block (every generated output):**
```json
{ "kind": "...", "schema_version": "1.0", "generator_version": "1.0.0",
  "engine": "opportunity_engine.scoring", "generated_at": "<ISO8601|null>",
  "source_files": ["repo-relative paths"], "source_hashes": {"path": "sha256:…|null"},
  "is_derived": true, "authoritative": false, "note": "…" }
```
`source_hashes` let the UI detect stale outputs: recompute a source's hash and compare. `generated_at` is the only volatile field (identical inputs otherwise regenerate identically).
