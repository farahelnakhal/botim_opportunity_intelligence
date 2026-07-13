"""Append-only score-history / audit log (JSONL).

Entries are never edited or deleted. Kinds: 'applied', 'rollback', 'recovery'.
Rollback and recovery are new entries that preserve the originals.
"""

import json

from . import paths


def _read_lines():
    if not paths.SCORE_HISTORY.exists():
        return []
    out = []
    for line in paths.SCORE_HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def read_all():
    return _read_lines()


def find(history_id):
    for e in _read_lines():
        if e.get("history_id") == history_id:
            return e
    return None


def next_history_id():
    n = 0
    for e in _read_lines():
        hid = e.get("history_id", "")
        if hid.startswith("HIST-"):
            try:
                n = max(n, int(hid[5:]))
            except ValueError:
                pass
    return f"HIST-{n + 1:04d}"


def append(entry):
    """Append one entry (append-only; caller supplies a unique history_id)."""
    paths.SCORE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with paths.SCORE_HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
