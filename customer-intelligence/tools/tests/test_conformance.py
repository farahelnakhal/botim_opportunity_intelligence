"""Tests for the Workstream A conformance checker.

Run from repo root:
    python3 -m unittest discover customer-intelligence/tools/tests
or:
    python3 customer-intelligence/tools/tests/test_conformance.py

Synthetic-fixture tests build a throwaway knowledge base in a temp dir; the
live test runs the checker read-only against the real repository.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import conformance_check as cc  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]


def make_record(
    rid="EV-2026-W01-001",
    status="active",
    confidence="Medium — two source types",
    segment="SEG-test-segment",
    source="example.com (SRC-001)",
    duplicate="unique",
    contradictory='none found (searched: "provider fast payout")',
    axes=None,
):
    axes = axes if axes is not None else {a: 3 for a in cc.SCORE_AXES}
    score_lines = "\n".join(
        f"{axis.title() if axis != 'botim relevance' else 'BOTIM relevance'} "
        f"{'.' * 10} {v}"
        for axis, v in axes.items()
    )
    return f"""
## {rid} — Test record

**Status:** {status} · **Created:** 2026-01-01 · **Last verified:** 2026-01-01

| Field | Value |
|---|---|
| Customer segment | {segment} |
| Pain category | `getting-paid/settlement-delay` |
| Provider mentioned | TestCo |
| Exact customer wording | > "quote" |
| Source | {source} |
| Date of evidence | 2026-01-01 |
| Access label | direct |
| Language | en |
| Evidence confidence | {confidence} |
| Duplicate status | {duplicate} |
| Contradictory evidence | {contradictory} |
| Product implication | Inference: test |

```
{score_lines}
```
"""


class FixtureKB:
    """Builds a minimal valid knowledge base in a temp dir."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        kb = self.root / "knowledge-base"
        (kb / "customer-evidence" / "records").mkdir(parents=True)
        (kb / "segments").mkdir()
        (kb / "inflection-points").mkdir()
        (kb / "segments" / "SEG-test-segment.md").write_text("# stub\n")
        (kb / "inflection-points" / "IP-2026-001.md").write_text("# stub\n")
        (kb / "customer-evidence" / "source-log.md").write_text(
            "| ID | Source |\n|---|---|\n| SRC-001 | example |\n"
        )

    def write_records(self, content, name="2026-W01.md"):
        (
            self.root / "knowledge-base" / "customer-evidence" / "records" / name
        ).write_text(content)

    def cleanup(self):
        self.tmp.cleanup()


class ConformanceTests(unittest.TestCase):
    def setUp(self):
        self.kb = FixtureKB()
        self.addCleanup(self.kb.cleanup)

    def run_check(self):
        return cc.check(self.kb.root)

    def test_valid_record_passes(self):
        self.kb.write_records(make_record())
        errors, _ = self.run_check()
        self.assertEqual(errors, [])

    def test_duplicate_id_detected(self):
        self.kb.write_records(make_record() + make_record())
        errors, _ = self.run_check()
        self.assertTrue(any("duplicate ID" in e for e in errors))

    def test_invalid_confidence_detected(self):
        self.kb.write_records(make_record(confidence="Medium-High — compound"))
        errors, _ = self.run_check()
        self.assertTrue(any("evidence confidence" in e for e in errors))

    def test_confidence_nuance_after_dash_allowed(self):
        self.kb.write_records(
            make_record(confidence="Low — facts are High-certainty but pain unvoiced")
        )
        errors, _ = self.run_check()
        self.assertEqual(errors, [])

    def test_invalid_status_detected(self):
        self.kb.write_records(make_record(status="pending"))
        errors, _ = self.run_check()
        self.assertTrue(any("invalid status" in e for e in errors))

    def test_status_annotation_after_token_allowed(self):
        # mirrors downstream parser: first token wins, annotation tolerated
        self.kb.write_records(make_record(status="active (dates aging — reverify)"))
        errors, _ = self.run_check()
        self.assertEqual(errors, [])

    def test_missing_axis_detected(self):
        axes = {a: 3 for a in cc.SCORE_AXES if a != "urgency"}
        self.kb.write_records(make_record(axes=axes))
        errors, _ = self.run_check()
        self.assertTrue(any("missing score axis 'urgency'" in e for e in errors))

    def test_dangling_seg_ref_detected(self):
        self.kb.write_records(make_record(segment="SEG-does-not-exist"))
        errors, _ = self.run_check()
        self.assertTrue(any("unknown segment 'SEG-does-not-exist'" in e for e in errors))

    def test_dangling_src_ref_detected(self):
        self.kb.write_records(make_record(source="example.com (SRC-999)"))
        errors, _ = self.run_check()
        self.assertTrue(any("unknown source 'SRC-999'" in e for e in errors))

    def test_dangling_ev_ref_detected(self):
        self.kb.write_records(make_record(duplicate="duplicate-of:EV-2026-W01-099"))
        errors, _ = self.run_check()
        self.assertTrue(any("unknown evidence ref" in e for e in errors))

    def test_valid_cross_record_ev_ref_passes(self):
        first = make_record()
        second = make_record(
            rid="EV-2026-W01-002", duplicate="corroborates:EV-2026-W01-001"
        )
        self.kb.write_records(first + second)
        errors, _ = self.run_check()
        self.assertEqual(errors, [])

    def test_valid_ip_ref_passes_and_dangling_detected(self):
        ok = make_record(contradictory="tension with IP-2026-001, unresolved")
        self.kb.write_records(ok)
        errors, _ = self.run_check()
        self.assertEqual(errors, [])
        bad = make_record(contradictory="see IP-2026-099")
        self.kb.write_records(bad)
        errors, _ = self.run_check()
        self.assertTrue(any("unknown inflection ref 'IP-2026-099'" in e for e in errors))

    def test_missing_required_field_detected(self):
        record = make_record().replace("| Product implication | Inference: test |\n", "")
        self.kb.write_records(record)
        errors, _ = self.run_check()
        self.assertTrue(any("missing required field 'product implication'" in e for e in errors))

    def test_prose_ids_not_validated(self):
        # example IDs outside structured fields must not create errors
        record = make_record()
        record += "\nDocumentation prose mentioning EV-2099-W99-999 and SRC-999 and SEG-imaginary.\n"
        self.kb.write_records(record)
        errors, _ = self.run_check()
        self.assertEqual(errors, [])

    def test_segment_without_seg_token_warns_not_errors(self):
        self.kb.write_records(make_record(segment="New UAE SMEs (no profile yet)"))
        errors, warnings = self.run_check()
        self.assertEqual(errors, [])
        self.assertTrue(any("no SEG- reference" in w for w in warnings))


class LiveKnowledgeBaseTest(unittest.TestCase):
    """Read-only run against the real repository."""

    def test_live_knowledge_base_conforms(self):
        records_dir = REPO_ROOT / "knowledge-base" / "customer-evidence" / "records"
        if not records_dir.is_dir():
            self.skipTest("live knowledge base not present")
        before = {p: p.stat().st_mtime for p in REPO_ROOT.rglob("*.md")}
        errors, _ = cc.check(REPO_ROOT)
        after = {p: p.stat().st_mtime for p in REPO_ROOT.rglob("*.md")}
        self.assertEqual(before, after, "checker must not modify any file")
        self.assertEqual(errors, [], f"live knowledge base has conformance errors: {errors}")


if __name__ == "__main__":
    unittest.main()
