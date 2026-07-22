"""Phase H2 (PR-H2b) — PII redact-and-flag at the social-content ingestion
boundary. Offline: the social adapters are constructed directly with injected
fetch (they're gated, never live). Proves PII in a review/post body is redacted
BEFORE storage (and thus before any model exposure) via the shared floor, is
flagged on the source, is fail-closed on unredactable input, and that the
non-social (web-search) path is untouched (H2 scope = R9a social adapters)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.research import ResearchStore, execute_run  # noqa: E402
from shared.research.providers import (AppStoreReviewsProvider,  # noqa: E402
                                        MockSearchProvider)


def _appstore_fetch(content, title="Payouts are slow"):
    review = {"im:rating": {"label": "3"}, "id": {"label": "111"},
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


def _dead_page(url, timeout_s):
    raise OSError("no page")   # force excerpt to fall back to the provider snippet


def _run_social(content, title="Payouts are slow"):
    s = ResearchStore(Path(tempfile.mkdtemp()) / "research.db")
    run = s.create_run({"title": "h2b"})
    s.add_query(run["id"], {"query_text": "12345"})
    provider = AppStoreReviewsProvider(fetch_fn=_appstore_fetch(content, title), country="ae")
    execute_run(s, run["id"], provider, fetch_fn=_dead_page, sleep_fn=lambda s_: None)
    return s.get_run(run["id"], include_children=True)["sources"][0]


class SocialContentRedaction(unittest.TestCase):
    def test_email_and_phone_redacted_and_flagged(self):
        src = _run_social("Reach me at trader@example.com or +971-50-123-4567 for details.")
        self.assertIn("[REDACTED-EMAIL]", src["excerpt"])
        self.assertIn("[REDACTED-PHONE]", src["excerpt"])
        self.assertNotIn("trader@example.com", src["excerpt"])
        self.assertNotIn("971-50-123-4567", src["excerpt"])
        sig = src["quality_signals"]
        self.assertEqual(sig["pii_redaction"], "redacted")
        self.assertIn("email", sig["pii_categories"])
        self.assertIn("phone", sig["pii_categories"])

    def test_name_trigger_sets_manual_review(self):
        src = _run_social("My name is John Smith and settlement is slow.")
        self.assertIn("[REDACTED-NAME]", src["excerpt"])
        self.assertNotIn("John Smith", src["excerpt"])
        sig = src["quality_signals"]
        self.assertIn("name", sig["pii_categories"])
        self.assertTrue(sig["pii_manual_review"])

    def test_title_is_also_redacted(self):
        src = _run_social("Nothing sensitive here.", title="Email me at ceo@firm.co please")
        self.assertIn("[REDACTED-EMAIL]", src["title"])
        self.assertNotIn("ceo@firm.co", src["title"])

    def test_clean_content_is_flagged_clean_and_unchanged(self):
        src = _run_social("Settlement takes four days and it hurts cash flow.")
        self.assertEqual(src["quality_signals"]["pii_redaction"], "clean")
        self.assertIn("Settlement takes four days", src["excerpt"])   # untouched
        self.assertNotIn("pii_categories", src["quality_signals"])   # nothing to list

    def test_fail_closed_withholds_unredactable_content(self):
        # an embedded control byte makes the shared floor treat this as a
        # redaction FAILURE — content must be withheld, never passed through raw
        src = _run_social("Secret \x07 phone +971-50-123-4567 hidden in control bytes.")
        self.assertEqual(src["quality_signals"]["pii_redaction"], "failed")
        self.assertEqual(src["excerpt"], "[content withheld: PII redaction failed]")
        self.assertNotIn("971-50-123-4567", src["excerpt"])


class NonSocialPathUntouched(unittest.TestCase):
    """H2 scope is R9a's social adapters; the web-search path (pii_sensitive
    False) must be unchanged — no redaction, no flag."""

    def test_mock_provider_content_not_redacted(self):
        s = ResearchStore(Path(tempfile.mkdtemp()) / "research.db")
        run = s.create_run({"title": "web"})
        s.add_query(run["id"], {"query_text": "q"})
        provider = MockSearchProvider({"q": [
            {"url": "https://example.com/a", "title": "T",
             "snippet": "Contact analyst@example.com for the dataset."}]})
        execute_run(s, run["id"], provider, fetch_fn=_dead_page, sleep_fn=lambda s_: None)
        src = s.get_run(run["id"], include_children=True)["sources"][0]
        self.assertIn("analyst@example.com", src["excerpt"])          # verbatim, unredacted
        self.assertNotIn("pii_redaction", src["quality_signals"])     # no flag on the web path


class SharedFloorImportable(unittest.TestCase):
    def test_shared_redaction_module_works(self):
        from shared import redaction
        r = redaction.process_text("Mail: a@b.co")
        self.assertIn("[REDACTED-EMAIL]", r.redacted_text)
        self.assertIn("email", r.categories)


if __name__ == "__main__":
    unittest.main()
