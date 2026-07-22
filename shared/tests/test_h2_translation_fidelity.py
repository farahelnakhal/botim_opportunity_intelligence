"""Phase H2 (PR-H2d) — translation-fidelity is a NO-OP right now, by design.

R9a's multi-language work is QUERYING-only (localized search terms); source
CONTENT is never translated — that is deferred to R9c. So there is no
translation step whose fidelity could be wrong. Rather than leave that as an
unproven assertion, this locks it: non-English review/post content flows through
the social adapter + runner and is stored BYTE-FOR-BYTE verbatim (untranslated).

If R9c ever adds content translation, these tests will start to matter (a
translated field would no longer equal the original) — a deliberate tripwire so
"translation fidelity" becomes real scope the moment translation is introduced,
not a silently-skipped check."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import ResearchStore, execute_run  # noqa: E402
from shared.research.providers import AppStoreReviewsProvider  # noqa: E402

# non-English, no PII — so redaction (H2b) leaves it untouched and any change
# would be a (nonexistent) translation step
ARABIC_BODY = "التسوية تستغرق أربعة أيام وهذا يضر بالتدفق النقدي."
ARABIC_TITLE = "المدفوعات بطيئة"


def _appstore_fetch(content, title):
    review = {"im:rating": {"label": "2"}, "id": {"label": "111"},
              "title": {"label": title}, "content": {"label": content},
              "updated": {"label": "2026-06-01T10:00:00-07:00"}}
    feed = {"feed": {"entry": [{"im:name": {"label": "App"}, "id": {"label": "12345"}}, review]}}
    search = {"results": [{"trackId": 12345, "trackName": "App"}]}

    def fetch(url, headers):
        if "/search?" in url:
            return json.dumps(search).encode("utf-8")
        if "customerreviews" in url:
            return json.dumps(feed).encode("utf-8")
        raise AssertionError(url)
    return fetch


class TranslationFidelityNoOp(unittest.TestCase):
    def test_adapter_returns_non_english_content_verbatim(self):
        out = AppStoreReviewsProvider(fetch_fn=_appstore_fetch(ARABIC_BODY, ARABIC_TITLE),
                                      country="ae").search("12345")
        self.assertEqual(out[0]["snippet"], ARABIC_BODY)   # not translated
        self.assertEqual(out[0]["title"], ARABIC_TITLE)

    def test_runner_stores_non_english_content_verbatim(self):
        s = ResearchStore(Path(tempfile.mkdtemp()) / "research.db")
        run = s.create_run({"title": "h2d"})
        s.add_query(run["id"], {"query_text": "12345"})
        provider = AppStoreReviewsProvider(fetch_fn=_appstore_fetch(ARABIC_BODY, ARABIC_TITLE),
                                           country="ae")
        execute_run(s, run["id"], provider,
                    fetch_fn=lambda u, t: (_ for _ in ()).throw(OSError("no page")),
                    sleep_fn=lambda _s: None)
        src = s.get_run(run["id"], include_children=True)["sources"][0]
        # stored byte-for-byte as retrieved — no translation happened anywhere
        self.assertEqual(src["excerpt"], ARABIC_BODY)
        self.assertEqual(src["title"], ARABIC_TITLE)
        # redaction ran and found nothing (no PII) — so the text is untouched
        self.assertEqual(src["quality_signals"]["pii_redaction"], "clean")


if __name__ == "__main__":
    unittest.main()
