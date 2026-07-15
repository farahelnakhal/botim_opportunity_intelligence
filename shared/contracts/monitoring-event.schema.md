# Monitoring event contract (additive — Integration Phase 4)

The single documented shape for a monitoring event as it flows end-to-end:

```
knowledge-base/monitoring/events/YYYY-Wnn.jsonl   (one JSON object per line)
  → intelligence-monitoring/tools/monitoring_engine/events.py  (validation)
  → executive-ui/api/serialize.py monitoring_payload()          (serialization — fields passed through, never dropped)
  → executive-ui/web/src/types.ts MonitoringEvent               (frontend type)
  → Monitoring cards / Updates feed → DetailDrawer monitoring detail
```

## Event object

Required (validated by `monitoring_engine.events.validate_event`):

| field | type | notes |
|---|---|---|
| `id` | string | `EVT-YYYY-Wnn-nnn`, sequential per week, never reused |
| `entity` | string | monitored entity or KB record id the event is about |
| `detected_at` | string | `YYYY-MM-DD` |
| `adapter` | string | `kb-watcher` = **internal knowledge-base change** (no external source URL applies — the UI labels it that way and never fabricates a source) |
| `signal_type` | string | e.g. `new_evidence_record`, `new_opportunity` |
| `fingerprint` | string | stable identity of the observation |
| `title` | string | non-empty |
| `scores` | object | the five significance axes, each 1–5 |
| `tier` | string | computed from scores — never chosen |
| `status` | string | `new · analyzed · alerted · digested · archived` |

Optional (preserved through the API — a serializer must pass these through,
not drop them):

| field | type | notes |
|---|---|---|
| `facts` | object/array | verbatim facts behind the event |
| `kb_links` | string[] | affected KB records (`OPP-…`, `EV-…`, `SEG-…`, …) |
| `thread_id`, `dedup_of` | string | related monitoring events |
| `details` | object | adapter detail (confidence, status, previous/current values; for external adapters may carry `source_title`, `source_url`, `fetched_at` — `source_url` is subject to the http(s)-only policy in `shared/source_urls.py`) |
| `score_note`, `summary_ref`, `evidence_candidate` | | as produced by the engine |

## API additions (Phase 4, additive)

`GET /executive-api/monitoring` now also returns:

- `summary_state` — current-state summary computed only from committed
  artefacts: `status` (`active | no-recent-updates | no-events | never-run |
  unavailable`), `status_note`, `last_checked` (null — no run timestamp is
  committed anywhere; never invented), `latest_event_at`, `event_count`,
  `open_alert_count`, `unresolved_warning_count`, `monitored_entity_count`,
  `external_source_count`, `internal_only`. A count the backend cannot
  calculate is `null`.
- `summaries` entries are `{id, available, flags}` — the summary **file
  path is never exposed**.

`GET /executive-api/monitoring/summary/{event_id}` (Phase 4):

- `event_id` must match `EVT-YYYY-Wnn-nnn` exactly (400 otherwise); the file
  is resolved only inside `knowledge-base/monitoring/summaries/` (no
  caller-supplied paths, traversal attempts never reach the filesystem).
- 404 when no summary exists; response is `{event_id, markdown, truncated}`
  with a 128 KiB size cap.
- The markdown is repository content but is still rendered with the safe
  Markdown renderer (raw HTML disabled) in the UI.
