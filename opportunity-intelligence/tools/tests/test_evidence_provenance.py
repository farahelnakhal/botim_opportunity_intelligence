"""Phase 4 — evidence provenance parsing tests.

The parser must PRESERVE source metadata that exists in the committed
records (source cell, dates, access label, excerpt) and stay honest about
what does not exist (None, never a fabricated value). Existing consumers
of load_records must keep working unchanged (backward compatibility).
"""

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from opportunity_engine import evidence  # noqa: E402

FULL_RECORD = """# Evidence Records — 2026-W01

## EV-2026-W01-001 — Complete provenance record
**Status:** active · **Created:** 2026-01-05 · **Last verified:** 2026-01-06

### What
| Field | Value |
|---|---|
| Pain category | `getting-paid/settlement-delay` |
| Exact customer wording | > "funds held for more than 2 months" — support "pathetic". |

### Source
| Field | Value |
|---|---|
| Source | trustpilot.com/review/example.com (SRC-001) |
| Date of evidence | 2025-11-20 |
| Access label | search-snippet |
| Language | en |

### Assessment
| Field | Value |
|---|---|
| Evidence confidence | Low — snippet-derived |

### Scores (1–5)
```
Evidence strength ........ 2
```

## EV-2026-W01-002 — Partial provenance (no dates, no access label)
**Status:** active

### Source
| Field | Value |
|---|---|
| Source | internal desk research |

### Scores (1–5)
```
Evidence strength ........ 3
```

## EV-2026-W01-003 — No source section at all
**Status:** needs-more-evidence

## EV-2026-W01-004 — Malformed URL in source cell
**Status:** active · **Created:** 2026-01-05 · **Last verified:** 2026-01-05

### Source
| Field | Value |
|---|---|
| Source | javascript:alert(1) and also /etc/passwd (SRC-002) |
| Date of evidence | Undated (2025 search index) |
"""

SOURCE_LOG = """# Source Log

| ID | Date added | Source (name + URL) | Type | Language | Access | Segments covered | Yield | Quality notes | Last checked |
|---|---|---|---|---|---|---|---|---|---|
| SRC-001 | 2026-01-04 | Trustpilot — Example (trustpilot.com/review/example.com) | review-store | en | search-snippet | seg-a | high | notes | 2026-01-06 |
| SRC-002 | 2026-01-04 | Suspicious source (javascript:alert(1)) | forum | en | direct | — | low | — | 2026-01-04 |
"""


class TestProvenanceParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        (base / "records").mkdir()
        (base / "records" / "2026-W01.md").write_text(FULL_RECORD, encoding="utf-8")
        (base / "source-log.md").write_text(SOURCE_LOG, encoding="utf-8")
        cls.records = evidence.load_records(base)
        cls.log = evidence.load_source_log(base)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_complete_source_metadata(self):
        r = self.records["EV-2026-W01-001"]
        self.assertEqual(r["status"], "active")
        self.assertEqual(r["created_at"], "2026-01-05")
        self.assertEqual(r["last_verified_at"], "2026-01-06")
        self.assertEqual(r["source_ids"], ["SRC-001"])
        self.assertEqual(r["source_text"], "trustpilot.com/review/example.com (SRC-001)")
        self.assertEqual(r["date_of_evidence"], "2025-11-20")
        self.assertEqual(r["publication_date"], "2025-11-20")
        self.assertEqual(r["access_label"], "search-snippet")
        self.assertEqual(r["language"], "en")

    def test_excerpt_preserved_and_quote_marker_stripped(self):
        r = self.records["EV-2026-W01-001"]
        self.assertEqual(r["excerpt"],
                         '"funds held for more than 2 months" — support "pathetic".')

    def test_partial_source_metadata_missing_dates_stay_none(self):
        r = self.records["EV-2026-W01-002"]
        self.assertEqual(r["source_text"], "internal desk research")
        self.assertEqual(r["source_ids"], [])
        self.assertIsNone(r["created_at"])
        self.assertIsNone(r["last_verified_at"])
        self.assertIsNone(r.get("date_of_evidence"))
        self.assertIsNone(r["publication_date"])
        self.assertIsNone(r.get("access_label"))
        self.assertIsNone(r.get("excerpt"))

    def test_missing_source_section_entirely(self):
        r = self.records["EV-2026-W01-003"]
        self.assertIsNone(r.get("source_text"))
        self.assertEqual(r["source_ids"], [])
        self.assertIsNone(r["publication_date"])

    def test_non_iso_date_of_evidence_yields_no_publication_date(self):
        r = self.records["EV-2026-W01-004"]
        self.assertEqual(r["date_of_evidence"], "Undated (2025 search index)")
        self.assertIsNone(r["publication_date"])

    def test_malformed_url_is_kept_raw_but_never_normalized_to_a_link(self):
        sys.path.insert(0, str(REPO_ROOT))
        from shared import source_urls
        r = self.records["EV-2026-W01-004"]
        self.assertIsNone(source_urls.first_candidate(r["source_text"]))
        self.assertIsNone(source_urls.normalize(self.log["SRC-002"]["url_text"]))

    def test_internal_evidence_has_no_url(self):
        from shared import source_urls
        r = self.records["EV-2026-W01-002"]
        self.assertIsNone(source_urls.first_candidate(r["source_text"]))

    def test_source_log_join_fields(self):
        e = self.log["SRC-001"]
        self.assertEqual(e["title"], "Trustpilot — Example")
        self.assertEqual(e["publisher"], "Trustpilot")
        self.assertEqual(e["url_text"], "trustpilot.com/review/example.com")
        self.assertEqual(e["added"], "2026-01-04")
        self.assertEqual(e["last_checked"], "2026-01-06")
        self.assertEqual(e["access"], "search-snippet")

    def test_backward_compatibility_shape(self):
        """Existing consumers rely on id/title/status/scores + check_citations."""
        r = self.records["EV-2026-W01-001"]
        self.assertEqual(r["id"], "EV-2026-W01-001")
        self.assertEqual(r["title"], "Complete provenance record")
        self.assertEqual(r["scores"]["evidence strength"], 2)
        out = evidence.check_citations(["EV-2026-W01-001", "EV-9999-W99-999", "bogus"],
                                       self.records)
        self.assertEqual(out["valid"], ["EV-2026-W01-001"])
        self.assertEqual(out["missing"], ["EV-9999-W99-999"])
        self.assertEqual(out["malformed"], ["bogus"])
        self.assertEqual(out["weak"], ["EV-2026-W01-001"])  # strength 2


class TestAgainstRealRepository(unittest.TestCase):
    """Every committed record must parse with provenance intact and no
    crash — the live KB is the backward-compatibility fixture."""

    def test_all_committed_records_parse_with_provenance(self):
        records = evidence.load_records(REPO_ROOT / "knowledge-base" / "customer-evidence")
        log = evidence.load_source_log(REPO_ROOT / "knowledge-base" / "customer-evidence")
        self.assertGreater(len(records), 0)
        self.assertGreater(len(log), 0)
        for rid, rec in records.items():
            self.assertIn("source_ids", rec, rid)
            self.assertIn("created_at", rec, rid)
            self.assertIn("last_verified_at", rec, rid)
            for sid in rec["source_ids"]:
                self.assertIn(sid, log, f"{rid} cites {sid} missing from source log")

    def test_no_local_filesystem_path_ever_becomes_a_url(self):
        sys.path.insert(0, str(REPO_ROOT))
        from shared import source_urls
        records = evidence.load_records(REPO_ROOT / "knowledge-base" / "customer-evidence")
        for rid, rec in records.items():
            url = source_urls.first_candidate(rec.get("source_text"))
            if url is not None:
                self.assertTrue(url.startswith("https://") or url.startswith("http://"), rid)
                self.assertNotIn("knowledge-base", url, rid)


if __name__ == "__main__":
    unittest.main()
