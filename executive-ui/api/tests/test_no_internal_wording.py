"""Regression guard: user-visible engine output must never contain internal
QA/developer-only language (e.g. "as pre-committed in the test case").

This scans the *serialized* payloads the frontend actually renders (not the
raw knowledge-base source, and not `*/test-cases/*` or `*/tests/*`, which are
legitimately internal), plus the bundled offline-seed snapshot the React app
falls back to. A regenerated snapshot must not silently reintroduce the phrase.
"""

import json
import re
import sys
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[2]        # executive-ui/
REPO = UI.parents[0]
for p in (str(UI),):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import serialize  # noqa: E402

# Phrases that must never leak into content a normal user sees. Deliberately
# narrow — do not add generic words like "test" that legitimately describe
# real experiments/concept tests.
BANNED_PHRASES = [
    "as pre-committed in the test case",
    "test case",
    "fixme",
    "debug only",
    "developer note:",
]


def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)


def _find_banned(strings):
    hits = []
    for s in strings:
        low = s.lower()
        for phrase in BANNED_PHRASES:
            if phrase in low:
                hits.append((phrase, s[:160]))
    return hits


class TestNoInternalWordingInApiOutput(unittest.TestCase):
    def test_overview_payload_clean(self):
        payload = serialize.build_payload(str(REPO))
        hits = _find_banned(_walk_strings(payload))
        self.assertEqual(hits, [], f"internal wording leaked into /api/overview: {hits}")

    def test_experiments_payload_clean(self):
        payload = serialize.experiments_payload(str(REPO))
        hits = _find_banned(_walk_strings(payload))
        self.assertEqual(hits, [], f"internal wording leaked into /api/experiments: {hits}")

    def test_monitoring_payload_clean(self):
        payload = serialize.monitoring_payload(str(REPO))
        hits = _find_banned(_walk_strings(payload))
        self.assertEqual(hits, [], f"internal wording leaked into /api/monitoring: {hits}")

    def test_journal_payload_clean(self):
        payload = serialize.journal_payload(str(REPO))
        hits = _find_banned(_walk_strings(payload))
        self.assertEqual(hits, [], f"internal wording leaked into /api/journal: {hits}")


class TestNoInternalWordingInBundledSeed(unittest.TestCase):
    """The React app's offline fallback (web/src/seed.json) is real user-visible
    content, not test source — it must stay in sync with the same guarantee."""

    def test_seed_json_clean(self):
        seed_path = UI / "web" / "src" / "seed.json"
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        hits = _find_banned(_walk_strings(data))
        self.assertEqual(hits, [], f"internal wording leaked into web/src/seed.json: {hits}")


if __name__ == "__main__":
    unittest.main()
