"""Cross-module integration tests for the combined agent.

These test the CONTRACT between Workstream A and Workstream B against the
repo's real files: A's records must be consumable by B's tooling, B's
citations must resolve into A's knowledge base, and every cross-module ID
reference must point at something that exists. If either side changes format,
these fail before main breaks.

Run: python3 -m unittest discover -s shared/tests
(or via shared/integration_check.py)
"""

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "opportunity-intelligence" / "tools"))
sys.path.insert(0, str(REPO_ROOT / "customer-intelligence" / "tools"))

import conformance_check  # noqa: E402  (Workstream A)
from opportunity_engine import backlog, evidence, journal, scoring, sync  # noqa: E402  (Workstream B)

KB = REPO_ROOT / "knowledge-base"
EV_RE = re.compile(r"\bEV-\d{4}-W\d{2}-\d{3}\b")
SEG_RE = re.compile(r"\bSEG-[a-z0-9][a-z0-9-]*\b")
IP_RE = re.compile(r"\bIP-\d{4}-\d{3}\b")


def _records():
    return evidence.load_records(KB / "customer-evidence")


class TestAToBContract(unittest.TestCase):
    """A's real records are consumable by B's parser."""

    def setUp(self):
        self.records = _records()

    def test_parser_reads_all_real_records(self):
        # A's own parser is ground truth for record count
        a_side = {}
        for path in sorted((KB / "customer-evidence" / "records").glob("*.md")):
            for rec in conformance_check.parse_records_file(path):
                a_side[rec["id"]] = rec
        self.assertGreaterEqual(len(a_side), 19)
        self.assertEqual(set(self.records), set(a_side),
                         "B's parser and A's parser disagree on which records exist")

    def test_every_record_fully_parsed_by_b(self):
        for rid, rec in self.records.items():
            self.assertIsNotNone(rec["status"], rid)
            self.assertEqual(len(rec["scores"]), 10, f"{rid}: B parsed {len(rec['scores'])}/10 axes")
            self.assertIn("evidence_confidence", rec, rid)

    def test_parsers_agree_on_scores(self):
        for path in sorted((KB / "customer-evidence" / "records").glob("*.md")):
            for a_rec in conformance_check.parse_records_file(path):
                b_rec = self.records[a_rec["id"]]
                self.assertEqual(b_rec["scores"], a_rec["scores"], a_rec["id"])

    def test_a_conformance_zero_errors(self):
        errors, _warnings = conformance_check.check(str(REPO_ROOT))
        self.assertEqual(errors, [], errors)

    def test_handoffs_section_exists_in_weekly_updates(self):
        updates = list((KB / "customer-evidence" / "weekly-updates").glob("*.md"))
        self.assertTrue(updates, "no weekly updates found")
        for path in updates:
            self.assertIn("Handoffs to Workstream B", path.read_text(encoding="utf-8"), path.name)


class TestBToAResolution(unittest.TestCase):
    """B's citations and references resolve into A's knowledge base."""

    def setUp(self):
        self.records = _records()

    def test_all_scorecard_citations_resolve(self):
        for path in sorted((KB / "opportunity-scores").glob("*.json")):
            card = json.loads(path.read_text(encoding="utf-8"))
            cited = {m for e in card["scores"].values() for m in EV_RE.findall(e.get("basis", ""))}
            missing = cited - set(self.records)
            self.assertEqual(missing, set(), f"{path.name}: citations don't resolve: {missing}")

    def test_all_ev_refs_in_b_documents_resolve(self):
        for folder in ("product-ideas", "commercial-models", "validation"):
            for path in sorted((KB / folder).glob("*.md")):
                refs = set(EV_RE.findall(path.read_text(encoding="utf-8")))
                missing = refs - set(self.records)
                self.assertEqual(missing, set(), f"{folder}/{path.name}: {missing}")

    def test_segment_refs_in_b_documents_resolve(self):
        seg_ids = {p.stem for p in (KB / "segments").glob("SEG-*.md")}
        for folder in ("product-ideas", "opportunity-scores", "validation"):
            for path in sorted(KB.glob(f"{folder}/*")):
                if path.suffix not in (".md", ".json"):
                    continue
                refs = set(SEG_RE.findall(path.read_text(encoding="utf-8")))
                missing = refs - seg_ids
                self.assertEqual(missing, set(), f"{folder}/{path.name}: unknown segments {missing}")

    def test_inflection_refs_in_b_documents_resolve(self):
        ip_ids = {p.stem for p in (KB / "inflection-points").glob("IP-*.md")}
        for path in sorted((KB / "product-ideas").glob("*.md")):
            refs = set(IP_RE.findall(path.read_text(encoding="utf-8")))
            missing = refs - ip_ids
            self.assertEqual(missing, set(), f"{path.name}: unknown inflection points {missing}")


class TestSyncBridge(unittest.TestCase):
    """The axis→dimension mapping is valid and the sync runs on real data."""

    def test_mapping_endpoints_exist(self):
        for axis, dim in sync.AXIS_TO_DIMENSION.items():
            self.assertIn(axis, evidence.SCORE_AXES, axis)
            self.assertIn(dim, scoring.DIMENSIONS, dim)
        for axis in sync.UNMAPPED_AXES:
            self.assertIn(axis, evidence.SCORE_AXES, axis)
        # every A axis is either mapped or deliberately unmapped — none forgotten
        self.assertEqual(
            set(sync.AXIS_TO_DIMENSION) | set(sync.UNMAPPED_AXES),
            set(evidence.SCORE_AXES),
        )

    def test_sync_runs_on_real_repo(self):
        reports = sync.analyse(REPO_ROOT)
        self.assertGreaterEqual(len(reports), 3)
        by_id = {r["opportunity_id"]: r for r in reports}
        self.assertIn("OPP-010", by_id)
        r = by_id["OPP-010"]
        self.assertEqual(r["unresolved"], [])
        self.assertGreaterEqual(len(r["usable"]), 5)
        # weak records must never appear as suggestion sources
        for s in r["suggestions"]:
            for rid in s["from_records"]:
                self.assertNotIn(rid, r["excluded_weak"])

    def test_sync_render(self):
        report = sync.render_markdown(sync.analyse(REPO_ROOT))
        self.assertIn("OPP-010", report)
        self.assertIn("Report-only", report)


class TestAgentDefinition(unittest.TestCase):
    """The combined agent's shared files are consistent."""

    def test_master_prompt_references_both_modules(self):
        text = (REPO_ROOT / "MASTER_PROMPT.md").read_text(encoding="utf-8")
        self.assertIn("customer-intelligence/SYSTEM_PROMPT.md", text)
        self.assertIn("opportunity-intelligence/SYSTEM_PROMPT.md", text)
        self.assertIn("shared/integration_check.py", text)

    def test_referenced_prompts_exist(self):
        for p in ("customer-intelligence/SYSTEM_PROMPT.md",
                  "opportunity-intelligence/SYSTEM_PROMPT.md",
                  "WORKSTREAMS.md", "MASTER_PROMPT.md"):
            self.assertTrue((REPO_ROOT / p).is_file(), p)

    def test_backlog_and_journal_still_valid(self):
        _, issues = backlog.check(KB / "product-ideas" / "BACKLOG.md")
        self.assertEqual(issues, [], issues)
        journal.load(KB / "product-ideas" / "decision-journal.json")  # validates

    def test_no_module_writes_in_others_folders(self):
        # structural spot-check: A's tools never import B's engine and vice versa
        a_tool = (REPO_ROOT / "customer-intelligence/tools/conformance_check.py").read_text(encoding="utf-8")
        self.assertNotIn("import opportunity_engine", a_tool)
        b_run = (REPO_ROOT / "opportunity-intelligence/tools/run.py").read_text(encoding="utf-8")
        self.assertNotIn("customer-intelligence/tools", b_run)


if __name__ == "__main__":
    unittest.main()
