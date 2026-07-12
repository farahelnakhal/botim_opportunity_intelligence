"""Adapter framework + the manual-intake adapter (first working adapter).

External observations enter through adapters (adapters/README.md contract).
The `manual-intake` adapter reads observation JSON files dropped into
knowledge-base/monitoring/intake/ — the lawful transport for observations
collected by a human or by the LLM layer's own research (which is exactly how
external monitoring works before automated fetchers land in P1). Processed
files move to intake/processed/ so the queue is idempotent.

Intake observation file schema (one JSON object per file):
{
  "entity": "ENT-wio",               // must exist in entities.json
  "signal_type": "pricing_change",   // free snake_case for external signals
  "title": "Wio same-day settlement fee cut to 0.5%",
  "scores": {impact,urgency,confidence,relevance,novelty},   // REQUIRED: no
      // defaults for external signals — the collector must score, and the
      // confidence ceiling of the source class applies (adapters/README.md)
  "facts": [{"claim": "...", "quote": "...", "source_url": "...",
             "access_label": "direct|search-snippet|...", "fetched": "YYYY-MM-DD"}],
  "kb_links": [], "details": {}, "score_note": "why these scores",
  "evidence_candidate": true|false   // if true, a candidate stub is filed for A
}
"""

import json
import re
from pathlib import Path

from . import events as ev_mod
from .significance import MonitorError, validate_scores

SIGNAL_RE = re.compile(r"^[a-z][a-z0-9_]+$")
REQUIRED = ("entity", "signal_type", "title", "scores", "facts")


def _validate_observation(o, name, entity_ids):
    for f in REQUIRED:
        if f not in o:
            raise MonitorError(f"{name}: intake observation missing '{f}'")
    if o["entity"] not in entity_ids:
        raise MonitorError(f"{name}: unknown entity {o['entity']!r} — register it in entities.json first")
    if not SIGNAL_RE.match(o["signal_type"]):
        raise MonitorError(f"{name}: signal_type must be snake_case")
    validate_scores(o["scores"])
    if not o["facts"]:
        raise MonitorError(f"{name}: at least one sourced fact required")
    for fact in o["facts"]:
        for f in ("claim", "source_url", "access_label", "fetched"):
            if not fact.get(f):
                raise MonitorError(f"{name}: fact missing '{f}' — provenance is mandatory")


def process_intake(mon_dir, existing_events, week, detected_at, entity_ids):
    """Read intake/*.json → validated events; move processed files.

    Returns (new_events, candidate_stubs) where candidate_stubs are
    (filename, markdown) pairs for evidence-candidates/.
    """
    intake = Path(mon_dir) / "intake"
    if not intake.is_dir():
        return [], []
    created, stubs = [], []
    pool = list(existing_events)
    for path in sorted(intake.glob("*.json")):
        o = json.loads(path.read_text(encoding="utf-8"))
        _validate_observation(o, path.name, entity_ids)
        e, is_new = ev_mod.make_event(
            pool, entity=o["entity"], detected_at=detected_at, adapter="manual-intake",
            signal_type=o["signal_type"], title=o["title"], scores=o["scores"],
            week=week, details=o.get("details", {}), kb_links=o.get("kb_links", []),
            score_note=o.get("score_note", ""),
        )
        if is_new:
            e["facts"] = o["facts"]
            created.append(e)
            pool.append(e)
            if o.get("evidence_candidate"):
                stubs.append((f"{e['id']}-candidate.md", _candidate_md(e, o)))
        processed = intake / "processed"
        processed.mkdir(exist_ok=True)
        path.rename(processed / path.name)
    return created, stubs


def _candidate_md(event, obs):
    lines = [f"# Evidence candidate — from {event['id']}", "",
             f"**Entity:** {obs['entity']} · **Signal:** {obs['signal_type']} · "
             f"**Detected:** {event['detected_at']} via manual-intake", "",
             f"**Claim:** {event['title']}", "", "## Facts (provenance)", ""]
    for f in obs["facts"]:
        lines.append(f"- {f['claim']} — {f['source_url']} ({f['access_label']}, fetched {f['fetched']})"
                     + (f' · quote: "{f["quote"]}"' if f.get("quote") else ""))
    lines += ["", "*For Workstream A review: promote to an EV record under your rules, "
                  "or reject with a one-line reason appended here. Workstream C never writes EV records.*"]
    return "\n".join(lines) + "\n"
