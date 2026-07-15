"""Tests for shared/source_urls.py — the http(s)-only source-link policy
(Phase 4). Unsafe schemes, local paths, and malformed values must never
become a clickable URL."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared import source_urls  # noqa: E402


class TestSafeUrl(unittest.TestCase):
    def test_http_and_https_accepted(self):
        self.assertEqual(source_urls.safe_url("https://trustpilot.com/review/x"),
                         "https://trustpilot.com/review/x")
        self.assertEqual(source_urls.safe_url("http://example.com"), "http://example.com")

    def test_unsafe_schemes_rejected(self):
        for bad in ("javascript:alert(1)", "data:text/html;base64,xxx",
                    "file:///etc/passwd", "vbscript:msgbox(1)", "ftp://x.com/a",
                    "JAVASCRIPT:alert(1)", "mailto:a@b.com"):
            self.assertIsNone(source_urls.safe_url(bad), bad)

    def test_local_and_malformed_rejected(self):
        for bad in ("/etc/passwd", "knowledge-base/customer-evidence/records/2026-W28.md",
                    "//evil.com/x", "https://", "https://localhost/x", "", None, 42,
                    "https://exa mple.com", "https:\\\\evil.com"):
            self.assertIsNone(source_urls.safe_url(bad), repr(bad))


class TestNormalize(unittest.TestCase):
    def test_bare_domain_path_upgraded_to_https(self):
        self.assertEqual(source_urls.normalize("trustpilot.com/review/www.telr.com"),
                         "https://trustpilot.com/review/www.telr.com")
        self.assertEqual(source_urls.normalize("news.ycombinator.com/item?id=47615145"),
                         "https://news.ycombinator.com/item?id=47615145")

    def test_absolute_url_passes_through(self):
        self.assertEqual(source_urls.normalize("https://example.com/a"), "https://example.com/a")

    def test_unsafe_absolute_url_rejected(self):
        self.assertIsNone(source_urls.normalize("javascript:alert(1)//x.com"))
        self.assertIsNone(source_urls.normalize("file:///etc/passwd"))

    def test_local_paths_and_prose_rejected(self):
        for bad in ("/etc/passwd", "./records/2026-W28.md", "~/notes.md",
                    "see the weekly file", "r/dubai", "", None):
            self.assertIsNone(source_urls.normalize(bad), repr(bad))

    def test_scheme_relative_rejected(self):
        self.assertIsNone(source_urls.normalize("//evil.com/x"))


class TestFirstCandidate(unittest.TestCase):
    def test_extracts_first_url_from_source_cell(self):
        self.assertEqual(
            source_urls.first_candidate("trustpilot.com/review/www.telr.com (SRC-001)"),
            "https://trustpilot.com/review/www.telr.com")

    def test_cell_without_url_yields_none(self):
        self.assertIsNone(source_urls.first_candidate("internal desk research (SRC-099)"))
        self.assertIsNone(source_urls.first_candidate(None))

    def test_never_extracts_a_local_path(self):
        self.assertIsNone(source_urls.first_candidate("see /etc/passwd and ./notes.md"))


if __name__ == "__main__":
    unittest.main()
