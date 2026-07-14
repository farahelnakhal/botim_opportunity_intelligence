"""Read-only Merchant Voice tools tests: registered read-only, arg
validation, no arbitrary paths, and query-layer guarantees (only approved
+published data surfaces, no identity fields, segment/method distinction
preserved) as seen through the Copilot's own tool-calling surface.

Builds its own tiny synthetic mv.db fixture directly against merchant
voice's app package (loaded under the alias "mv_app" by app.mv_tools —
see that module's docstring for why the alias is required) rather than
importing merchant-voice/tests/fixtures.py, which would collide with this
process's own "app" package (copilot-backend's).
"""

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app import mv_tools, tools_registry  # noqa: E402  (import triggers mv_app alias load)

db_mod = importlib.import_module("mv_app.db")
campaigns_mod = importlib.import_module("mv_app.campaigns")
guides_mod = importlib.import_module("mv_app.guides")
identity_mod = importlib.import_module("mv_app.identity")
participants_mod = importlib.import_module("mv_app.participants")
responses_mod = importlib.import_module("mv_app.responses")
extraction_mod = importlib.import_module("mv_app.extraction")
observation_review_mod = importlib.import_module("mv_app.observation_review")
candidates_mod = importlib.import_module("mv_app.candidates")
findings_mod = importlib.import_module("mv_app.findings")
mv_config_mod = importlib.import_module("mv_app.config")
provider_mod = importlib.import_module("shared.llm.provider")

RESEARCHER = {"role": "researcher", "label": "researcher-1"}
REVIEWER = {"role": "reviewer", "label": "reviewer-1"}


class _StubProvider(provider_mod.ConversationModel):
    def __init__(self, answer_id, observation_type="pain"):
        self.answer_id = answer_id
        self.observation_type = observation_type

    def generate(self, messages, tools, system_prompt, configuration):
        return provider_mod.ModelResponse(content=json.dumps({"observations": [{
            "observation_type": self.observation_type, "source_answer_id": self.answer_id,
            "source_excerpt": "Suppliers cancel late payments every week",
            "normalized_statement": "Supplier payments are cancelled weekly.",
            "is_direct_quote": False, "extraction_confidence": "high"}]}))


def _build_fixture_mv_db(tmp_dir, linked_opportunities=("OPP-013",), segment_id=None, publish=True):
    """Campaign -> guide -> participant -> response -> extracted+approved
    observation -> candidate -> finding, optionally published. Returns
    (mv_db_path, campaign_id, finding_id_or_None)."""
    mv_conn = db_mod.connect_mv(Path(tmp_dir) / "mv.db")
    identity_conn = db_mod.connect_identity(Path(tmp_dir) / "identity.db")
    mv_config = mv_config_mod.Config(env={"MV_TOKENS": "a:t:admin",
                                          "MV_TRANSCRIPT_DIR": str(Path(tmp_dir) / "transcripts")})
    n = [0]

    def clock():
        n[0] += 1
        return f"2026-01-01T00:00:{n[0]:02d}Z"

    camp = campaigns_mod.create(mv_conn, mv_config, RESEARCHER, {
        "title": "MVC-TEST-COPILOT", "objective": "copilot smoke", "method": "interview",
        "linked_opportunities": list(linked_opportunities), "data_classification": "synthetic"}, clock())
    guide = guides_mod.create(mv_conn, RESEARCHER, camp["campaign_id"],
                              [{"text": "What is your biggest pain?", "purpose": "problem"}], clock())
    guides_mod.approve(mv_conn, mv_config, REVIEWER, guide["guide_id"], clock())
    campaigns_mod.transition(mv_conn, REVIEWER, camp["campaign_id"], "approved", clock())
    campaigns_mod.transition(mv_conn, RESEARCHER, camp["campaign_id"], "active", clock())
    idrow = identity_mod.create(identity_conn, mv_config, RESEARCHER, {
        "consent_status": "granted", "permitted_use": "internal_research_only", "quote_permission": True,
        "ai_processing_permission": True, "data_classification": "synthetic"}, clock())
    participant = participants_mod.create(mv_conn, identity_conn, mv_config, RESEARCHER, {
        "campaign_id": camp["campaign_id"], "merchant_identity_id": idrow["merchant_identity_id"],
        "segment_id": segment_id, "consent_status": "granted", "permitted_use": "internal_research_only",
        "quote_permission": True, "ai_processing_permission": True, "data_classification": "synthetic"}, clock())
    qid = guide["questions"][0]["question_id"]
    response = responses_mod.create(mv_conn, mv_config, RESEARCHER, {
        "campaign_id": camp["campaign_id"], "participant_id": participant["participant_id"],
        "guide_id": guide["guide_id"], "method": "interview",
        "answers": [{"question_id": qid, "answer": "Suppliers cancel late payments every week."}]}, clock())
    answer_id = response["answers"][0]["answer_id"]

    original_provider = extraction_mod.make_provider
    extraction_mod.make_provider = lambda cfg: _StubProvider(answer_id)
    try:
        _run, obs_list = extraction_mod.run_extraction(mv_conn, mv_config, RESEARCHER,
                                                        response["response_id"], clock())
    finally:
        extraction_mod.make_provider = original_provider
    obs = obs_list[0]
    observation_review_mod.approve(mv_conn, mv_config, REVIEWER, obs["observation_id"], clock())
    candidate = candidates_mod.create(mv_conn, RESEARCHER, mv_config, {
        "campaign_id": camp["campaign_id"], "finding_type": "pain",
        "statement": "Suppliers cancel late payments.", "proposed_evidence_role": "supporting",
        "linked_opportunities": list(linked_opportunities),
        "observations": [{"observation_id": obs["observation_id"], "role": "supporting"}]}, clock())
    candidates_mod.submit(mv_conn, RESEARCHER, candidate["candidate_id"], clock())
    _approved, finding = candidates_mod.approve(mv_conn, mv_config, REVIEWER, candidate["candidate_id"], clock())
    finding_id = None
    if publish:
        findings_mod.publish(mv_conn, REVIEWER, finding["finding_id"], clock())
        finding_id = finding["finding_id"]
    mv_conn.close()
    identity_conn.close()
    return Path(tmp_dir) / "mv.db", camp["campaign_id"], finding_id


class MvToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._original_path = tools_registry.MV_CONFIG.mv_db_path
        self.addCleanup(setattr, tools_registry.MV_CONFIG, "mv_db_path", self._original_path)

    def test_tools_registered_read_only(self):
        for name in ("list_merchant_campaigns", "get_merchant_campaign", "get_campaign_summary",
                    "get_approved_merchant_findings", "get_segment_feedback",
                    "get_opportunity_merchant_feedback", "get_assumption_feedback",
                    "get_merchant_objections", "get_merchant_workarounds", "get_merchant_quotes",
                    "compare_segment_feedback", "get_campaign_limitations"):
            self.assertIn(name, tools_registry.REGISTRY)
        source = Path(mv_tools.__file__).read_text(encoding="utf-8")
        self.assertIn("mode=ro", source)

    def test_no_writes_possible_through_readonly_connection(self):
        import sqlite3
        db_path, _cid, _fid = _build_fixture_mv_db(self.tmp.name)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("DELETE FROM campaigns")

    def test_tool_args_validated(self):
        with self.assertRaises(tools_registry.ToolError):
            tools_registry.call_tool("get_merchant_campaign", {"campaign_id": "not-a-real-id"})
        with self.assertRaises(tools_registry.ToolError):
            tools_registry.call_tool("get_approved_merchant_findings", {"finding_type": "not_a_type"})
        with self.assertRaises(tools_registry.ToolError):
            tools_registry.call_tool("get_merchant_campaign", {"unknown_arg": "x"})

    def test_no_arbitrary_path_accepted(self):
        import inspect
        for fn_name in ("get_merchant_campaign", "get_campaign_summary"):
            sig = inspect.signature(getattr(mv_tools, fn_name))
            self.assertNotIn("path", sig.parameters)
            self.assertNotIn("db_path", sig.parameters)

    def test_no_data_yet_returns_empty_not_a_crash(self):
        tools_registry.MV_CONFIG.mv_db_path = Path(self.tmp.name) / "does-not-exist.db"
        result = tools_registry.call_tool("list_merchant_campaigns", {})
        self.assertEqual(result, {"campaigns": []})

    def test_published_finding_surfaces_via_tools(self):
        db_path, cid, fid = _build_fixture_mv_db(self.tmp.name)
        tools_registry.MV_CONFIG.mv_db_path = db_path
        result = tools_registry.call_tool("get_campaign_summary", {"campaign_id": cid})
        self.assertEqual(result["published_finding_count"], 1)
        self.assertIn("pain", result["findings_by_type"])

    def test_unpublished_finding_does_not_surface(self):
        db_path, cid, fid = _build_fixture_mv_db(self.tmp.name, publish=False)
        tools_registry.MV_CONFIG.mv_db_path = db_path
        result = tools_registry.call_tool("get_approved_merchant_findings", {"campaign_id": cid})
        self.assertEqual(result["findings"], [])

    def test_opportunity_linked_finding_surfaces(self):
        db_path, cid, fid = _build_fixture_mv_db(self.tmp.name, linked_opportunities=["OPP-013"])
        tools_registry.MV_CONFIG.mv_db_path = db_path
        result = tools_registry.call_tool("get_opportunity_merchant_feedback", {"opportunity_id": "OPP-013"})
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(result["findings"][0]["finding_id"], fid)

    def test_segment_feedback_filters_correctly(self):
        db_path, cid, fid = _build_fixture_mv_db(self.tmp.name, segment_id="SEG-alpha")
        tools_registry.MV_CONFIG.mv_db_path = db_path
        result = tools_registry.call_tool("get_segment_feedback", {"segment_id": "SEG-alpha"})
        self.assertEqual(len(result["findings"]), 1)
        self.assertEqual(tools_registry.call_tool("get_segment_feedback", {"segment_id": "SEG-beta"})["findings"], [])

    def test_finding_response_has_no_identity_fields(self):
        db_path, cid, fid = _build_fixture_mv_db(self.tmp.name)
        tools_registry.MV_CONFIG.mv_db_path = db_path
        result = tools_registry.call_tool("get_approved_merchant_findings", {"campaign_id": cid})
        blob = json.dumps(result)
        self.assertNotIn("MID-", blob)  # merchant_identity_id prefix
        self.assertNotIn("MVP-", blob)  # participant_id prefix


if __name__ == "__main__":
    unittest.main(verbosity=2)
