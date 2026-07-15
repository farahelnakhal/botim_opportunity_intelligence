"""Source revalidation (Phase R4b) — re-check a run's recorded sources.

Re-fetches each non-duplicate source of a run (bounded, polite, offline-
testable via the same injected fetch as retrieval.py) and APPENDS a
revalidation record per source:

    unchanged   — reachable, extracted-content hash matches the stored one
    changed     — reachable, content differs (or no baseline hash existed)
    unreachable — fetch failed, non-200, or unsupported content type

Propose, never auto-apply: the original source rows, candidate claims, and
review decisions are never modified. Outcomes are surfaced (run detail,
candidate `source_health`, copilot warnings) so a HUMAN decides whether to
re-run research or revise claims.
"""

import time

from .retrieval import fetch_page

MAX_CHECKS = 20
CHECK_DELAY_S = 0.5


def revalidate_run(store, run_id, fetch_fn=None, sleep_fn=time.sleep,
                   max_checks=MAX_CHECKS):
    """Re-check up to `max_checks` non-duplicate sources of the run.
    Returns {run_id, checked, unchanged, changed, unreachable, skipped}.
    Never raises on network failure — a dead page is an 'unreachable'
    outcome, not an error."""
    run = store.get_run(run_id, include_children=True)
    sources = [s for s in run.get("sources", []) if not s.get("duplicate_of")]
    skipped = max(0, len(sources) - int(max_checks))
    counts = {"unchanged": 0, "changed": 0, "unreachable": 0}
    checked = 0
    for source in sources[:int(max_checks)]:
        if checked:
            sleep_fn(CHECK_DELAY_S)
        result = fetch_page(source["canonical_url"], fetch_fn=fetch_fn)
        checked += 1
        if not result.get("ok"):
            store.add_revalidation(source["id"], "unreachable",
                                   http_status=result.get("status"),
                                   note=result.get("error"))
            counts["unreachable"] += 1
        elif source.get("content_hash") and result.get("content_hash") == source["content_hash"]:
            store.add_revalidation(source["id"], "unchanged",
                                   http_status=result.get("status"),
                                   new_content_hash=result.get("content_hash"))
            counts["unchanged"] += 1
        else:
            note = (None if source.get("content_hash")
                    else "no baseline content hash was recorded at retrieval time")
            store.add_revalidation(source["id"], "changed",
                                   http_status=result.get("status"),
                                   new_content_hash=result.get("content_hash"),
                                   note=note)
            counts["changed"] += 1
    return {"run_id": run_id, "checked": checked, "skipped": skipped, **counts}
