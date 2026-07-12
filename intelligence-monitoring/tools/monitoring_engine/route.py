"""Alert routing: tier → channels per user preferences, with fatigue budgets.

P0 delivery is an auditable file-based outbox (alerts JSONL records what
would be sent where); real email/in-app transports are deployment adapters
behind the same records.
"""

import json
from pathlib import Path

from .significance import MonitorError, TIERS

TIER_ORDER = {t: i for i, t in enumerate(TIERS)}

# tier → default channel treatment (DESIGN.md §7)
ROUTING = {
    "critical": {"instant": True, "digest": "daily"},
    "important": {"instant": False, "digest": "daily"},
    "informative": {"instant": False, "digest": "weekly"},
    "insignificant": None,  # dashboard archive only
}

PREF_REQUIRED = ("user", "channels", "min_tier", "fatigue_budget")


def load_preferences(pref_dir):
    prefs = []
    pref_dir = Path(pref_dir)
    if not pref_dir.is_dir():
        return prefs
    for path in sorted(pref_dir.glob("*.json")):
        p = json.loads(path.read_text(encoding="utf-8"))
        for f in PREF_REQUIRED:
            if f not in p:
                raise MonitorError(f"{path.name}: preference file missing '{f}'")
        for channel, t in p["min_tier"].items():
            if t not in TIERS:
                raise MonitorError(f"{path.name}: min_tier.{channel} {t!r} not in {TIERS}")
        if not isinstance(p["fatigue_budget"], int) or p["fatigue_budget"] < 1:
            raise MonitorError(f"{path.name}: fatigue_budget must be a positive integer")
        prefs.append(p)
    return prefs


def _subscribed(pref, event):
    subs = pref.get("subscriptions", {})
    ent_list = subs.get("entities", [])
    if ent_list and event["entity"] not in ent_list and not any(
            link in ent_list for link in event.get("kb_links", [])):
        return False
    return True


def route_event(event, prefs, instants_sent_today):
    """Decide deliveries for one event. Returns list of delivery dicts.

    instants_sent_today: {user: count} — the fatigue-budget ledger for the day.
    """
    treatment = ROUTING[event["tier"]]
    if treatment is None:
        return []
    deliveries = []
    for pref in prefs:
        if not _subscribed(pref, event):
            continue
        for channel, mode in pref["channels"].items():
            if mode == "off":
                continue
            if TIER_ORDER[event["tier"]] < TIER_ORDER[pref["min_tier"].get(channel, "important")]:
                continue
            if treatment["instant"] and mode == "instant":
                used = instants_sent_today.get(pref["user"], 0)
                demoted = used >= pref["fatigue_budget"] and event["tier"] != "critical"
                if not demoted:
                    instants_sent_today[pref["user"]] = used + 1
                deliveries.append({"user": pref["user"], "channel": channel,
                                   "mode": "digest" if demoted else "instant",
                                   "demoted_by_budget": demoted})
            else:
                deliveries.append({"user": pref["user"], "channel": channel,
                                   "mode": f"digest-{treatment['digest']}",
                                   "demoted_by_budget": False})
    return deliveries
