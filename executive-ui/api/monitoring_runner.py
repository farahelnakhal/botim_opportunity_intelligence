"""Manual monitoring runner (Phase R4a).

Executes ONE monitoring run for a user opportunity's MCFG- configuration by
reusing the research platform end to end (shared/research): the config's
topics/keywords/entities become bounded queries, execution happens through
the configured search provider with the config's preferred/excluded domains,
and every genuinely NEW non-duplicate source becomes a monitoring event
(MEVT-) grounded in its RSRC record.

Honesty rules:
- Manual only — no scheduler, no cadence execution (cadence stays intended
  configuration; see docs/roadmap.md R4).
- No provider configured / provider failure -> the config records an honest
  'error' state with last_error and an incremented failure counter;
  last_run_at is NEVER advanced by a failed run.
- Zero new sources is an honest, successful outcome ("no new developments
  found"), not an error and not padded with fabricated events.
- Events are exactly "new source recorded by this run" — no summaries, no
  significance scores, no tiers are invented here.
"""

MAX_QUERIES = 10


class MonitoringRunError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def build_queries(config, opportunity_title):
    """Deterministic, bounded queries from the stored configuration.
    Topics are used as-is; keywords/entities are contextualized with the
    opportunity title so bare terms aren't searched in a vacuum."""
    queries = []
    for topic in config.get("topics") or []:
        queries.append(("topic", topic))
    for kw in config.get("keywords") or []:
        queries.append(("keyword", f"{opportunity_title} {kw}".strip()))
    for entity in config.get("entities") or []:
        queries.append(("entity", f"{entity} news update"))
    return queries[:MAX_QUERIES]


def run_monitoring(user_store, research_store, opp_id, provider,
                   execute_run_fn=None, **execute_kwargs):
    """One manual monitoring run. Returns
    {run_id, run_status, events_created, new_events, note} or raises
    MonitoringRunError for client-fixable states (no config / paused /
    nothing to search). Provider/network failure is NOT raised — it is
    recorded on the config and returned as an honest failed outcome."""
    from shared.research.runner import execute_run as default_execute
    execute = execute_run_fn or default_execute

    opp = user_store.get(opp_id)  # 404s for unknown ids
    config = user_store.monitoring_get(opp_id)
    if config.get("status") == "not_configured":
        raise MonitoringRunError("monitoring is not configured for this opportunity",
                                 status=404)
    if not config.get("enabled"):
        raise MonitoringRunError("monitoring is paused for this opportunity — resume it first",
                                 status=409)
    queries = build_queries(config, opp["title"])
    if not queries:
        raise MonitoringRunError("the monitoring configuration has no topics, keywords, "
                                 "or entities to search", status=409)

    run = research_store.create_run({
        "title": f"Monitoring run: {opp['title']}"[:200],
        "objective": "manual monitoring run for a saved user opportunity",
        "opportunity_ref": opp_id,
        "profile": "monitoring",
    })
    for objective, query_text in queries:
        research_store.add_query(run["id"], {"objective": objective,
                                             "query_text": query_text[:4000]})

    finished = execute(research_store, run["id"], provider,
                       preferred_domains=config.get("preferred_domains") or (),
                       excluded_domains=config.get("excluded_domains") or (),
                       **execute_kwargs)

    if finished["status"] == "failed":
        user_store.monitoring_record_result(opp_id, ok=False, error=finished["error"])
        return {"run_id": finished["id"], "run_status": "failed",
                "events_created": 0, "new_events": [],
                "note": f"Monitoring run failed: {finished['error']}"}

    detail = research_store.get_run(finished["id"], include_children=True)
    candidates = [{
        "research_run_id": detail["id"], "source_id": s["id"],
        "title": s.get("title"), "canonical_url": s["canonical_url"],
        "domain": s["domain"], "published_at": s.get("published_at"),
    } for s in detail.get("sources", []) if not s.get("duplicate_of")]

    events = user_store.monitoring_add_events(opp_id, config["id"], candidates)
    user_store.monitoring_record_result(opp_id, ok=True)

    if finished["status"] == "partial":
        note = (f"Monitoring run completed partially ({finished['error']}); "
                f"{len(events)} new development(s) recorded.")
    elif events:
        note = f"{len(events)} new development(s) recorded."
    else:
        note = "No new developments found — nothing previously unseen matched the configuration."
    return {"run_id": finished["id"], "run_status": finished["status"],
            "events_created": len(events), "new_events": events, "note": note}
