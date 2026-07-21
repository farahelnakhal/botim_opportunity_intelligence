"""Phase P1 (PR-P1a) — server-side executive-brief PDF renderer. Offline, pure.

Content is asserted via `visible_text()` (the exact human-visible segment log
the renderer emits) so we verify fidelity without parsing compressed PDF byte
streams; `render_brief_pdf()` is separately asserted to produce a valid PDF and
to enforce the honesty guard."""

import sys
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import report_pdf  # noqa: E402


def committed(**overrides):
    payload = {
        "opportunity_id": "OPP-010", "title": "SME corporate cards",
        "generated_at": "2026-07-21T09:00:00Z",
        "classification": "promising", "classification_label": "Promising — worth validating",
        "is_archived": False, "segment": "UAE SMEs", "jtbd": "control spend",
        "hypothesis": "SMEs will adopt a controlled corporate card", "confidence": "",
        "score_summary": {"raw_score": 12, "raw_max": 20, "composite": 0.6,
                          "assumption_count": 4, "critical_flags": ["unproven willingness to pay"]},
        "brief_envelope": {"recommended_action": {"text": "Run 10 merchant interviews"},
                           "decision_requested": {"text": "Fund a discovery sprint"}},
        "brief_markdown": None,
        "evidence": [
            {"ev_id": "EV-001", "title": "UAE SME count report", "source_title": "Statista",
             "strength": "medium", "role": "supporting", "freshness_status": "stale"},
            {"ev_id": "EV-002", "title": "Contradicting fee study", "source_title": "GulfNews",
             "strength": "low", "role": "contradictory", "freshness_status": "aging"},
        ],
        "contradictory_evidence": "Some SMEs report satisfaction with bank transfers",
        "assumptions": [{"opportunity_id": "OPP-010", "factor_key": "willingness_to_pay",
                         "status": "untested"}],
        "predictions": [{"id": "PRED-1", "statement": "20% adopt within a year",
                         "p": 0.2, "resolve_by": "2027-01-01", "outcome": None}],
        "monitoring": {"state": {"status": "active", "status_note": "3 events in the last 30 days"},
                       "events": [{"id": "MEVT-1", "title": "New competitor launched",
                                   "detected_at": "2026-07-10"}]},
        "merchant_voice": {"available": False, "findings": [],
                           "note": "No approved Merchant Voice findings are available."},
        "risks": ["Regulatory licensing is unconfirmed"],
        "unknowns": ["Is the credit need real?"],
        "recommended_next_actions": ["Interview 10 merchants"],
        "sources": [{"source_title": "SME report", "publisher": "Statista",
                     "source_url": "https://example.com/r", "retrieved_at": "2026-06-01",
                     "access_label": "public", "evidence_ids": ["EV-001"]}],
        "decision_banner": "No product or build decision has been made.",
    }
    payload.update(overrides)
    return payload


def user(**overrides):
    payload = {
        "record_type": "user_opportunity", "opportunity_id": "UOPP-0123456789ab",
        "title": "My draft idea", "generated_at": "2026-07-21T09:00:00Z", "version": 2,
        "status": "draft", "is_archived": False,
        "classification": "unscored", "classification_label": "Draft — unvalidated, not scored",
        "product_definition": "A thing", "problem_statement": None, "target_segment": None,
        "customer_description": None, "value_proposition": None,
        "assumptions": ["They will pay"], "risks": [], "unknowns": [], "next_actions": [],
        "monitoring": {"status": "never_run", "cadence": "weekly", "last_run_at": None},
        "source_conversation_id": None, "created_from_analysis": True,
        "created_at": "2026-07-20T08:00:00Z", "updated_at": "2026-07-20T09:00:00Z",
        "decision_banner": "No product or build decision has been made.",
    }
    payload.update(overrides)
    return payload


def joined(payload, rc=None):
    return "\n".join(report_pdf.visible_text(payload, rc))


class CommittedContent(unittest.TestCase):
    def test_core_fields_and_banner_present(self):
        t = joined(committed())
        self.assertIn("SME corporate cards", t)
        self.assertIn("Promising — worth validating", t)              # classification label
        self.assertIn("No product or build decision has been made.", t)  # bounded banner
        self.assertIn("Interview 10 merchants", t)

    def test_confidence_empty_renders_unknown(self):
        self.assertIn("Confidence: Unknown", joined(committed(confidence="")))
        self.assertIn("Confidence: high", joined(committed(confidence="high")))

    def test_freshness_distinctions_preserved(self):
        t = joined(committed())
        self.assertIn("⚠ Stale", t)          # stale carries the alert marker
        self.assertIn("Aging", t)
        # an unknown-freshness source is labelled explicitly, never blank
        t2 = joined(committed(evidence=[{"ev_id": "EV-9", "title": "x", "source_title": "y",
                                         "strength": "low", "role": "supporting",
                                         "freshness_status": None}]))
        self.assertIn("Freshness unknown", t2)

    def test_critical_flags_and_archived_badge(self):
        self.assertIn("⚠ Critical flags:", joined(committed()))
        self.assertIn("Archived", joined(committed(is_archived=True)))

    def test_empty_sections_render_honest_notes_never_omitted(self):
        t = joined(committed(evidence=[], assumptions=[], predictions=[], risks=[],
                             unknowns=[], sources=[], recommended_next_actions=[],
                             brief_envelope=None, contradictory_evidence="—"))
        self.assertIn("cites no evidence records", t)
        self.assertIn("No tracked assumptions.", t)
        self.assertIn("No executive brief envelope is available", t)
        self.assertIn("No contradictory evidence is recorded", t)
        self.assertIn("No logged predictions reference this opportunity.", t)


class UserContent(unittest.TestCase):
    def test_not_yet_defined_and_no_fabrication_note(self):
        t = joined(user())
        self.assertIn("Not yet defined.", t)                 # empty text fields
        self.assertIn("nothing is fabricated", t)            # evidence/scoring honesty note
        self.assertIn("Your opportunity", t)
        self.assertIn("Draft — unvalidated, not scored", t)

    def test_monitoring_never_run_label(self):
        self.assertIn("awaiting monitoring run", joined(user()))


class ExternalResearchDistinction(unittest.TestCase):
    def test_none_unavailable_empty_and_candidate_label(self):
        self.assertIn("External research is unavailable right now.",
                      joined(committed(), rc=None))
        self.assertIn("No approved external research candidates",
                      joined(committed(), rc=[]))
        t = joined(committed(), rc=[{"id": "RCAND-1", "claim": "SMEs want faster settlement",
                                     "source_ids": ["RSRC-1", "RSRC-2"], "run_title": "run A"}])
        self.assertIn("SMEs want faster settlement", t)
        self.assertIn("candidate — not repository evidence", t)


class PdfBytesAndGuard(unittest.TestCase):
    def test_render_produces_valid_pdf(self):
        for payload in (committed(), user()):
            pdf = report_pdf.render_brief_pdf(payload)
            self.assertIsInstance(pdf, bytes)
            self.assertTrue(pdf.startswith(b"%PDF-"), "missing PDF header")
            self.assertIn(b"%%EOF", pdf)
            self.assertGreater(len(pdf), 800)

    def test_overclaim_is_rejected(self):
        bad = committed(brief_envelope={"recommended_action":
                                        {"text": "the product is validated and ready to launch"}})
        with self.assertRaises(report_pdf.ReportPdfError) as cm:
            report_pdf.render_brief_pdf(bad)
        self.assertIn("overclaim", str(cm.exception).lower())

    def test_bad_payload_rejected(self):
        with self.assertRaises(report_pdf.ReportPdfError):
            report_pdf.render_brief_pdf({"title": "no id"})

    def test_untrusted_markup_is_escaped_not_executed(self):
        # a title containing XML-ish chars must not break reportlab parsing
        pdf = report_pdf.render_brief_pdf(committed(title="A <b>bold</b> & risky <title>"))
        self.assertTrue(pdf.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
