"""Alert ledger + instant-alert outbox.

An alert is the routed form of an important/critical event: which users, which
channels, instant or digest, demoted or not. Alerts live in
knowledge-base/monitoring/alerts/YYYY-Wnn.jsonl; instant deliveries are
rendered into knowledge-base/monitoring/outbox/ as email-format markdown (the
auditable file-based transport — a real mail sender is a deployment adapter
that consumes the same records)."""

import json
import re
from pathlib import Path

from . import route as route_mod
from .significance import MonitorError, TIERS

ALERT_ID_RE = re.compile(r"^ALR-\d{4}-W\d{2}-\d{3}$")
REQUIRED = ("id", "event_ids", "tier", "deliveries", "created")


def validate_alert(a):
    for f in REQUIRED:
        if f not in a:
            raise MonitorError(f"alert missing field '{f}'")
    if not ALERT_ID_RE.match(a["id"]):
        raise MonitorError(f"alert id {a['id']!r} must match ALR-YYYY-Wnn-nnn")
    if a["tier"] not in TIERS:
        raise MonitorError(f"{a['id']}: bad tier {a['tier']!r}")
    if not a["event_ids"]:
        raise MonitorError(f"{a['id']}: no event ids")
    for d in a["deliveries"]:
        for f in ("user", "channel", "mode", "demoted_by_budget"):
            if f not in d:
                raise MonitorError(f"{a['id']}: delivery missing '{f}'")


def load_alerts(alerts_dir):
    out, seen = [], set()
    alerts_dir = Path(alerts_dir)
    if not alerts_dir.is_dir():
        return out
    for path in sorted(alerts_dir.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            a = json.loads(line)
            validate_alert(a)
            if a["id"] in seen:
                raise MonitorError(f"duplicate alert id {a['id']}")
            seen.add(a["id"])
            out.append(a)
    return out


def next_id(existing, week):
    year, wk = week.split("-W")
    prefix = f"ALR-{year}-W{wk}-"
    ns = [int(a["id"].rsplit("-", 1)[1]) for a in existing if a["id"].startswith(prefix)]
    return f"{prefix}{max(ns, default=0) + 1:03d}"


def create_alerts(events, prefs, existing_alerts, week, created_date, summaries=None):
    """One alert per un-alerted important/critical event. Returns new alerts."""
    alerted_events = {eid for a in existing_alerts for eid in a["event_ids"]}
    summaries = summaries or {}
    new = []
    ledger = {}  # fatigue budget shared across this run
    pool = list(existing_alerts)
    for e in events:
        if e["tier"] not in ("important", "critical") or e["id"] in alerted_events:
            continue
        deliveries = route_mod.route_event(e, prefs, ledger)
        a = {
            "id": next_id(pool, week),
            "event_ids": [e["id"]],
            "tier": e["tier"],
            "summary_ref": summaries.get(e["id"], {}).get("path"),
            "deliveries": deliveries,
            "created": created_date,
        }
        validate_alert(a)
        new.append(a)
        pool.append(a)
    return new


def append_alerts(alerts_dir, week, new_alerts):
    path = Path(alerts_dir) / f"{week}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for a in new_alerts:
            f.write(json.dumps(a, sort_keys=True) + "\n")
    return path


def render_instant(event, alert, summary_path=None):
    """Email-format instant brief for a critical event (outbox transport)."""
    s = event["scores"]
    lines = [
        f"Subject: [BOTIM Intel] CRITICAL — {event['title']}",
        "",
        f"🔴 CRITICAL — {event['title']}",
        f"Event {event['id']} · {event['entity']} · detected {event['detected_at']} via {event['adapter']}",
        f"Scores: impact {s['impact']} · urgency {s['urgency']} · confidence {s['confidence']}",
        f"Links: {', '.join(event.get('kb_links', [])) or '—'}",
        f"Full analysis: {summary_path or 'summary pending — run monitor.py analyze ' + event['id']}",
        "",
        f"Delivered to: {', '.join(sorted({d['user'] for d in alert['deliveries'] if d['mode'] == 'instant'})) or 'digest only'}",
    ]
    return "\n".join(lines) + "\n"


def write_outbox(outbox_dir, event, alert, summary_path=None):
    out = Path(outbox_dir) / f"{alert['created']}-{alert['id']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_instant(event, alert, summary_path), encoding="utf-8")
    return out
