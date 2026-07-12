"""AI-summary validation (templates/summary.md made mechanical).

Summaries are authored by the LLM layer for important/critical events; this
module makes them schema-checked artefacts like everything else: all twelve
sections present, a parseable machine-consumable flags block, and honest
sourcing hooks. An alert may not reference a summary that doesn't validate.
"""

import json
import re
from pathlib import Path

from .significance import MonitorError

SECTIONS = (
    "Executive summary", "What changed", "Why it matters", "Impact on BOTIM",
    "Impact on AstraTech", "Opportunities created", "Risks created",
    "Recommended actions", "Confidence", "Supporting evidence", "Sources",
    "Related previous events",
)

FLAG_KEYS = ("rescore_flags", "ve_flags", "req_proposals", "evidence_candidates")
EVT_RE = re.compile(r"EVT-\d{4}-W\d{2}-\d{3}")
FLAGS_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def validate_summary_text(text, path_name="summary"):
    """Validate one summary document. Returns (event_id, flags)."""
    m = EVT_RE.search(text.splitlines()[0] if text else "")
    if not m:
        raise MonitorError(f"{path_name}: first line must reference the EVT id")
    event_id = m.group(0)

    missing = [s for s in SECTIONS if not re.search(rf"\*\*{re.escape(s)}", text)]
    if missing:
        raise MonitorError(f"{path_name}: missing mandatory sections: {', '.join(missing)}")

    fm = FLAGS_BLOCK_RE.search(text)
    if not fm:
        raise MonitorError(f"{path_name}: missing machine-consumable ```json flags block")
    try:
        flags = json.loads(fm.group(1))
    except json.JSONDecodeError as exc:
        raise MonitorError(f"{path_name}: flags block is not valid JSON: {exc}")
    for k in FLAG_KEYS:
        if k not in flags or not isinstance(flags[k], list):
            raise MonitorError(f"{path_name}: flags block needs list '{k}'")
    for f in flags["rescore_flags"]:
        for req in ("opp", "dimensions", "reason"):
            if req not in f:
                raise MonitorError(f"{path_name}: rescore flag missing '{req}'")
    for f in flags["ve_flags"]:
        if f.get("action") != "redesign-as-new":
            raise MonitorError(
                f"{path_name}: ve_flags action must be 'redesign-as-new' — "
                "thresholds are never edited (pre-commitment is inviolable)"
            )
    return event_id, flags


def load_summaries(summaries_dir):
    """Validate all summaries. Returns {event_id: {path, flags}}."""
    out = {}
    summaries_dir = Path(summaries_dir)
    if not summaries_dir.is_dir():
        return out
    for path in sorted(summaries_dir.glob("EVT-*.md")):
        event_id, flags = validate_summary_text(path.read_text(encoding="utf-8"), path.name)
        if not path.stem.startswith(event_id):
            raise MonitorError(f"{path.name}: filename does not match referenced event {event_id}")
        out[event_id] = {"path": str(path), "flags": flags}
    return out


def skeleton(event):
    """Emit a fill-me summary skeleton for an event (the analyze command)."""
    lines = [f"## {event['id']} — {event['title']}", ""]
    for s in SECTIONS:
        lines += [f"1. **{s}:** _fill (see intelligence-monitoring/frameworks/reasoning-pass.md)_", ""]
    lines += ["### Flags (machine-consumable)", "", "```json",
              json.dumps({k: [] for k in FLAG_KEYS}, indent=1), "```", ""]
    return "\n".join(lines)
