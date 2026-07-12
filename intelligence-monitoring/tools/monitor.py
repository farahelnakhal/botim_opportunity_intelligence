#!/usr/bin/env python3
"""CLI for the Intelligence Monitoring & Alerting module (Workstream C).

Usage (from repo root):
  python3 intelligence-monitoring/tools/monitor.py scan [--from-ref REF]
  python3 intelligence-monitoring/tools/monitor.py events [--tier critical|important|...]
  python3 intelligence-monitoring/tools/monitor.py digest [--period weekly|daily] [--week 2026-W28] [--write]
  python3 intelligence-monitoring/tools/monitor.py entities
  python3 intelligence-monitoring/tools/monitor.py check

Writes ONLY under knowledge-base/monitoring/. `check` is part of the
integration gate.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from monitoring_engine import adapters as adapters_mod  # noqa: E402
from monitoring_engine import alerts as alerts_mod  # noqa: E402
from monitoring_engine import digest as digest_mod  # noqa: E402
from monitoring_engine import events as ev_mod  # noqa: E402
from monitoring_engine import kbwatch, route, summaries  # noqa: E402
from monitoring_engine.significance import AXES, MonitorError, TIERS, tier  # noqa: E402

MON = Path("knowledge-base/monitoring")
ENTITY_KINDS = ("competitor", "segment", "regulator", "platform")
KNOWN_ADAPTERS = ("kb-watcher", "manual-intake", "web-page-differ", "rss-newsroom",
                  "regulator-watch", "app-store", "review-platforms", "jobs-boards",
                  "social", "news-search")


def _entity_ids(root):
    path = Path(root) / MON / "entities.json"
    if not path.exists():
        return set()
    return {e["id"] for e in json.loads(path.read_text(encoding="utf-8"))["entities"]}


def _week(date=None):
    d = date or datetime.date.today()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def cmd_scan(args):
    root = Path(args.root)
    state_path = root / MON / "state" / "kb-state.json"
    events_dir = root / MON / "events"
    existing = ev_mod.load_events(events_dir)

    new_state = kbwatch.build_state(root)
    if args.from_ref:
        old_state = kbwatch.build_state_at_ref(root, args.from_ref)
    elif state_path.exists():
        old_state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, indent=2, sort_keys=True), encoding="utf-8")
        print("baseline created — no prior state to diff; future scans will emit events")
        return 0

    observations = kbwatch.diff_states(old_state, new_state)
    today = datetime.date.today().isoformat()
    created = kbwatch.observations_to_events(observations, existing, today, _week())

    intake_events, candidate_stubs = adapters_mod.process_intake(
        root / MON, existing + created, _week(), today, _entity_ids(root))
    created += intake_events
    for fname, md in candidate_stubs:
        cand = root / MON / "evidence-candidates" / fname
        cand.write_text(md, encoding="utf-8")
        print(f"  evidence candidate filed for Workstream A: {cand}")

    if created:
        ev_mod.append_events(events_dir, _week(), created)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, indent=2, sort_keys=True), encoding="utf-8")

    by_tier = {}
    for e in created:
        by_tier.setdefault(e["tier"], []).append(e)
    print(f"scan: {len(observations)} observation(s) → {len(created)} new event(s) "
          f"({len(observations) - len(created)} deduplicated)")
    for t in reversed(TIERS):
        for e in by_tier.get(t, []):
            print(f"  [{t:>13}] {e['id']}  {e['title']}")
    return 0


def cmd_events(args):
    all_events = ev_mod.load_events(Path(args.root) / MON / "events")
    shown = [e for e in all_events if not args.tier or e["tier"] == args.tier]
    for e in shown:
        print(f"{e['id']}  {e['tier']:>13}  {e['detected_at']}  {e['title']}")
    print(f"\n{len(shown)} of {len(all_events)} events")
    return 0


def cmd_digest(args):
    root = Path(args.root)
    week = args.week or _week()
    all_events = ev_mod.load_events(root / MON / "events")
    week_events = [e for e in all_events if e["id"].startswith(f"EVT-{week}-")]
    report = digest_mod.compile_digest(week, week_events, args.period)
    print(report, end="")
    if args.write:
        out = root / MON / "digests" / f"{week}-{args.period}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\n[written to {out}]", file=sys.stderr)
    return 0


def cmd_analyze(args):
    root = Path(args.root)
    all_events = {e["id"]: e for e in ev_mod.load_events(root / MON / "events")}
    if args.event_id not in all_events:
        sys.exit(f"monitor error: no event {args.event_id}")
    out = root / MON / "summaries" / f"{args.event_id}.md"
    if out.exists():
        summaries.validate_summary_text(out.read_text(encoding="utf-8"), out.name)
        print(f"{out} exists and validates")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(summaries.skeleton(all_events[args.event_id]), encoding="utf-8")
    print(f"skeleton written to {out} — fill all 12 sections + flags, then re-run analyze to validate")
    return 0


def cmd_alert(args):
    root = Path(args.root)
    week = args.week or _week()
    evs = ev_mod.load_events(root / MON / "events")
    prefs = route.load_preferences(root / MON / "preferences")
    existing = alerts_mod.load_alerts(root / MON / "alerts")
    summ = summaries.load_summaries(root / MON / "summaries")
    today = datetime.date.today().isoformat()
    new = alerts_mod.create_alerts(evs, prefs, existing, week, today, summ)
    if new:
        alerts_mod.append_alerts(root / MON / "alerts", week, new)
    by_id = {e["id"]: e for e in evs}
    for a in new:
        instants = [d for d in a["deliveries"] if d["mode"] == "instant"]
        if a["tier"] == "critical" and instants:
            out = alerts_mod.write_outbox(root / MON / "outbox", by_id[a["event_ids"][0]], a,
                                          a.get("summary_ref"))
            print(f"  outbox: {out}")
        print(f"  {a['id']} [{a['tier']}] {by_id[a['event_ids'][0]]['title']} → "
              f"{len(a['deliveries'])} deliveries ({len(instants)} instant)")
    print(f"alert: {len(new)} new alert(s) from {len(evs)} events")
    return 0


def cmd_entities(args):
    path = Path(args.root) / MON / "entities.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for e in data["entities"]:
        srcs = ", ".join(s["adapter"] for s in e.get("sources", [])) or "none configured"
        print(f"{e['id']:<16} {e['kind']:<11} {e['status']:<7} sources: {srcs}")
    return 0


def cmd_check(args):
    root = Path(args.root)
    mon = root / MON
    failures = []

    def ok(msg):
        print(f"  ok    {msg}")

    def fail(msg):
        failures.append(msg)
        print(f"  FAIL  {msg}")

    # entities
    entities_path = mon / "entities.json"
    if entities_path.exists():
        try:
            data = json.loads(entities_path.read_text(encoding="utf-8"))
            seen = set()
            for e in data["entities"]:
                for f in ("id", "kind", "name", "status"):
                    if f not in e:
                        raise MonitorError(f"entity missing '{f}': {e}")
                if e["kind"] not in ENTITY_KINDS:
                    raise MonitorError(f"{e['id']}: kind {e['kind']!r} not in {ENTITY_KINDS}")
                if e["id"] in seen:
                    raise MonitorError(f"duplicate entity id {e['id']}")
                seen.add(e["id"])
                if e.get("ref") and not (root / e["ref"]).exists():
                    raise MonitorError(f"{e['id']}: ref {e['ref']} does not exist")
                for s in e.get("sources", []):
                    if s.get("adapter") not in KNOWN_ADAPTERS:
                        raise MonitorError(f"{e['id']}: unknown adapter {s.get('adapter')!r}")
            ok(f"entities.json: {len(data['entities'])} entities valid")
        except (MonitorError, json.JSONDecodeError, KeyError) as exc:
            fail(f"entities.json: {exc}")
    else:
        print("  note  no entities.json yet")

    # events (schema + tier math + id/fingerprint uniqueness via load)
    try:
        evs = ev_mod.load_events(mon / "events")
        ok(f"events: {len(evs)} valid (schema, computed tiers, unique ids)")
    except MonitorError as exc:
        fail(f"events: {exc}")

    # preferences
    try:
        prefs = route.load_preferences(mon / "preferences")
        ok(f"preferences: {len(prefs)} user(s) valid")
    except MonitorError as exc:
        fail(f"preferences: {exc}")

    # summaries (validated; important/critical events without one are noted)
    try:
        summ = summaries.load_summaries(mon / "summaries")
        evs_by_id = {e["id"]: e for e in ev_mod.load_events(mon / "events")}
        for eid in summ:
            if eid not in evs_by_id:
                raise MonitorError(f"summary for unknown event {eid}")
        ok(f"summaries: {len(summ)} valid")
        missing = [e["id"] for e in evs_by_id.values()
                   if e["tier"] in ("important", "critical") and e["id"] not in summ]
        if missing:
            print(f"  note  {len(missing)} important/critical event(s) without summaries yet")
    except MonitorError as exc:
        fail(f"summaries: {exc}")

    # alerts (schema + event references resolve)
    try:
        alerts = alerts_mod.load_alerts(mon / "alerts")
        evs_by_id = {e["id"]: e for e in ev_mod.load_events(mon / "events")}
        for a in alerts:
            for eid in a["event_ids"]:
                if eid not in evs_by_id:
                    raise MonitorError(f"{a['id']}: references unknown event {eid}")
        ok(f"alerts: {len(alerts)} valid, all event references resolve")
    except MonitorError as exc:
        fail(f"alerts: {exc}")

    # intake queue (unprocessed observations must at least parse/validate)
    intake = mon / "intake"
    if intake.is_dir():
        pending = list(intake.glob("*.json"))
        try:
            for path in pending:
                adapters_mod._validate_observation(
                    json.loads(path.read_text(encoding="utf-8")), path.name, _entity_ids(root))
            if pending:
                print(f"  note  {len(pending)} intake observation(s) pending — run `monitor.py scan`")
        except (MonitorError, json.JSONDecodeError) as exc:
            fail(f"intake: {exc}")

    # state
    state_path = mon / "state" / "kb-state.json"
    if state_path.exists():
        try:
            json.loads(state_path.read_text(encoding="utf-8"))
            ok("state/kb-state.json parses")
        except json.JSONDecodeError as exc:
            fail(f"state/kb-state.json: {exc}")
    else:
        print("  note  no baseline state yet — run `monitor.py scan` to create it")

    print(f"\nMONITOR CHECK {'FAILED — ' + str(len(failures)) + ' failure(s)' if failures else 'PASSED'}")
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="diff the KB against last state (or a git ref) and emit events")
    p.add_argument("--from-ref", help="build the baseline from a git ref instead of the state file")

    p = sub.add_parser("events", help="list stored events")
    p.add_argument("--tier", choices=list(TIERS))

    p = sub.add_parser("digest", help="compile a digest for a week's events")
    p.add_argument("--period", choices=["weekly", "daily"], default="weekly")
    p.add_argument("--week", help="ISO week like 2026-W28 (default: current)")
    p.add_argument("--write", action="store_true")

    p = sub.add_parser("analyze", help="write/validate the AI summary for an event")
    p.add_argument("event_id")

    p = sub.add_parser("alert", help="route un-alerted important/critical events into the alert ledger + outbox")
    p.add_argument("--week", help="ISO week for alert ids (default: current)")

    sub.add_parser("entities", help="list monitored entities")
    sub.add_parser("check", help="validate all monitoring artefacts (part of the integration gate)")

    args = ap.parse_args(argv)
    try:
        return {"scan": cmd_scan, "events": cmd_events, "digest": cmd_digest,
                "analyze": cmd_analyze, "alert": cmd_alert,
                "entities": cmd_entities, "check": cmd_check}[args.cmd](args)
    except MonitorError as exc:
        sys.exit(f"monitor error: {exc}")


if __name__ == "__main__":
    sys.exit(main())
