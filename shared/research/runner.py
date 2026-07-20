"""Research-run executor (Phase R2) — bounded, honest, offline-testable.

`execute_run` drives one persisted run end to end: execute its pending
queries against the injected search provider, record deduplicated sources
with recorded (never invented) metadata and quality signals, fetch a bounded
number of pages for excerpts, and finish the run with an honest terminal
status:

- every query executed, none failed          -> complete
- some queries/fetches succeeded, some failed -> partial (+ reason)
- nothing succeeded / provider missing        -> failed  (+ reason)

Rules inherited from the platform (see shared/research/store.py):
no fabrication, external content is data never instructions, candidate
boundary untouched (this module creates sources only — claim extraction and
review arrive in Phase R3).
"""

import time

from .providers import SearchProviderError
from .retrieval import fetch_page, make_excerpt, normalize_url

DEFAULT_LIMITS = {
    "max_queries": 20,        # queries executed per run
    "max_results_per_query": 8,
    "max_fetches": 12,        # pages fetched for excerpts per run
    "fetch_delay_s": 0.5,     # politeness delay between page fetches
}


def _quality_signals(result, fetched, preferred_domains, excluded_domains, domain):
    """Flat recorded observations about a source — no scoring model, no
    judgment. Downstream review (R3) interprets these; we only record."""
    signals = {
        "has_title": bool(result.get("title") or (fetched or {}).get("title")),
        "has_snippet": bool(result.get("snippet")),
        "has_publication_date": bool(result.get("published_at")),
        "page_fetched": bool(fetched and fetched.get("ok")),
    }
    if fetched and fetched.get("ok"):
        signals["excerpt_chars"] = len(fetched.get("text") or "")
        if fetched.get("truncated"):
            signals["truncated"] = True
    if domain in preferred_domains:
        signals["preferred_domain"] = True
    if domain in excluded_domains:
        signals["excluded_domain"] = True  # recorded, and the source is skipped
    # R9a — recorded verbatim from the provider (never computed here): a
    # source-provided rating (e.g. an App Store review's stars), and whether
    # the adapter CONSTRUCTED the URL rather than getting a real permalink
    # (so the "open source" link does not dereference to the exact item).
    if result.get("rating"):
        signals["rating"] = result["rating"]
    if result.get("url_synthesized"):
        signals["url_synthesized"] = True
    return signals


def execute_run(store, run_id, provider, fetch_fn=None, limits=None,
                preferred_domains=(), excluded_domains=(), sleep_fn=time.sleep,
                now_fn=None):
    """Execute a pending run. Returns the finished run dict. Never raises on
    provider/network failure — failures become recorded query errors and an
    honest terminal status."""
    cfg = dict(DEFAULT_LIMITS)
    for key, value in (limits or {}).items():
        if key in cfg and isinstance(value, int) and value > 0:
            cfg[key] = min(value, DEFAULT_LIMITS[key] * 5)
    preferred_domains = {d.lower() for d in preferred_domains if isinstance(d, str)}
    excluded_domains = {d.lower() for d in excluded_domains if isinstance(d, str)}

    run = store.get_run(run_id, include_children=True)
    if run["status"] == "pending":
        run = store.start_run(run_id)
        run = store.get_run(run_id, include_children=True)
    if run["status"] != "running":
        from .store import ResearchStoreError
        raise ResearchStoreError(
            f"cannot execute a run in status '{run['status']}'", status=409)

    if provider is None:
        return store.finish_run(run_id, "failed",
                                error="no search provider configured "
                                      "(set RESEARCH_SEARCH_PROVIDER)")

    pending = [q for q in run["queries"] if q["status"] == "pending"][:cfg["max_queries"]]
    if not pending:
        return store.finish_run(run_id, "failed",
                                error="run has no pending queries to execute")

    seen_urls = {}    # normalized url -> source id (within this run)
    seen_hashes = {}  # content hash -> source id
    for existing in run["sources"]:
        norm = normalize_url(existing["canonical_url"])
        if norm:
            seen_urls.setdefault(norm, existing["id"])
        if existing.get("content_hash"):
            seen_hashes.setdefault(existing["content_hash"], existing["id"])

    executed = failed = 0
    fetches_used = 0
    fetch_failures = 0

    for query in pending:
        try:
            results = provider.search(query["query_text"],
                                      max_results=cfg["max_results_per_query"])
        except SearchProviderError as exc:
            store.mark_query(query["id"], "failed", error=str(exc)[:500])
            failed += 1
            continue

        kept = 0
        for result in results:
            norm = normalize_url(result.get("url"))
            if norm is None:
                continue  # unsafe/malformed result URL — never stored
            domain = norm.split("/")[2].split(":")[0]
            if domain in excluded_domains:
                continue
            duplicate_of = seen_urls.get(norm)

            fetched = None
            if duplicate_of is None and fetches_used < cfg["max_fetches"]:
                if fetches_used:
                    sleep_fn(cfg["fetch_delay_s"])
                fetched = fetch_page(result["url"], fetch_fn=fetch_fn)
                fetches_used += 1
                if not fetched.get("ok"):
                    fetch_failures += 1
                elif fetched.get("content_hash") in seen_hashes:
                    duplicate_of = seen_hashes[fetched["content_hash"]]

            payload = {
                "canonical_url": result["url"],
                "query_id": query["id"],
                "title": (fetched or {}).get("title") or result.get("title"),
                "published_at": result.get("published_at"),
                "retrieved_at": ((now_fn() if now_fn else None)
                                 or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                "excerpt": make_excerpt((fetched or {}).get("text"))
                           or result.get("snippet"),
                "content_hash": (fetched or {}).get("content_hash"),
                "duplicate_of": duplicate_of,
                "quality_signals": _quality_signals(result, fetched, preferred_domains,
                                                    excluded_domains, domain),
            }
            source = store.add_source(run_id, payload)
            kept += 1
            if duplicate_of is None:
                seen_urls[norm] = source["id"]
                if payload["content_hash"]:
                    seen_hashes.setdefault(payload["content_hash"], source["id"])

        store.mark_query(query["id"], "executed", result_count=kept)
        executed += 1

    if executed == 0:
        return store.finish_run(run_id, "failed",
                                error=f"all {failed} queries failed against "
                                      f"provider '{provider.name}'")
    if failed or fetch_failures:
        parts = []
        if failed:
            parts.append(f"{failed} of {failed + executed} queries failed")
        if fetch_failures:
            parts.append(f"{fetch_failures} page fetches failed (search metadata kept)")
        return store.finish_run(run_id, "partial", error="; ".join(parts))
    return store.finish_run(run_id, "complete")
