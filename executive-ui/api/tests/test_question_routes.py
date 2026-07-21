"""Phase R10 / PR10b — question-set HTTP routes. Demo mode (committed OPP corpus
visible); no model configured, so generation takes the honest-gap path (empty
draft set + note) — the wiring, quota, ownership and reads are what's exercised."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from urllib.request import urlopen, Request

os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))
os.environ["QUESTION_SETS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "question-sets-routes.db")
# ensure no model is configured -> deterministic honest-gap generation
for _k in ("BOTIM_LLM_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
    os.environ.pop(_k, None)

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402


def _an_opportunity():
    cards = sorted((REPO / "knowledge-base" / "opportunity-scores").glob("*-scorecard.json"))
    return json.loads(cards[0].read_text(encoding="utf-8"))["opportunity_id"]


class QuestionRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prev_mode = os.environ.get("BOTIM_APP_MODE")
        os.environ["BOTIM_APP_MODE"] = "demo"
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        cls.opp = _an_opportunity()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        if cls._prev_mode is None:
            os.environ.pop("BOTIM_APP_MODE", None)
        else:
            os.environ["BOTIM_APP_MODE"] = cls._prev_mode

    def _send(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_generate_then_read(self):
        status, data = self._send("POST", f"/executive-api/opportunities/{self.opp}/question-sets", {})
        self.assertEqual(status, 201)
        st = data["question_set"]
        self.assertTrue(st["id"].startswith("RQSET-"))
        self.assertEqual(st["status"], "draft")
        # no model configured -> honest empty gap, never fabricated questions
        self.assertEqual(st["questions"], [])
        self.assertIn("no model configured", st["note"])

        _, listing = self._send("GET", "/executive-api/question-sets", None)
        self.assertIn(st["id"], [s["id"] for s in listing["question_sets"]])

        status, one = self._send("GET", f"/executive-api/question-sets/{st['id']}", None)
        self.assertEqual(status, 200)
        self.assertEqual(one["question_set"]["id"], st["id"])

    def test_unknown_opportunity_404(self):
        status, _ = self._send("POST", "/executive-api/opportunities/OPP-404/question-sets", {})
        self.assertEqual(status, 404)

    def test_unknown_set_404(self):
        status, _ = self._send("GET", "/executive-api/question-sets/RQSET-ffffffffffff", None)
        self.assertEqual(status, 404)


class ReviewAndHandoffRoutes(unittest.TestCase):
    """PR10c — review (approve/reject/edit), Merchant Voice hand-off, delete.
    Sets are seeded directly in the store (no model is configured, so the
    generate route yields empty drafts) to exercise the review surface."""

    @classmethod
    def setUpClass(cls):
        from shared.questions import QuestionSetStore
        cls._prev_mode = os.environ.get("BOTIM_APP_MODE")
        os.environ["BOTIM_APP_MODE"] = "demo"
        cls.store = QuestionSetStore(os.environ["QUESTION_SETS_DB_PATH"])
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        if cls._prev_mode is None:
            os.environ.pop("BOTIM_APP_MODE", None)
        else:
            os.environ["BOTIM_APP_MODE"] = cls._prev_mode

    def _seed(self):
        return self.store.create(_an_opportunity(), [{
            "text": "What do you do today when a supplier payment is late?",
            "purpose": "behaviour", "question_type": "open_text",
            "follow_up_prompts": ["How often does it happen?"],
            "linked_assumption": "ASM-OPP-001-workaround_cost",
            "signals": ["open_gap"], "source_weak_link_rank": 1}])["id"]

    def _send(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                      method=method, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_approve_then_handoff(self):
        sid = self._seed()
        # hand-off refused while still a draft
        status, _ = self._send("GET", f"/executive-api/question-sets/{sid}/handoff", None)
        self.assertEqual(status, 409)
        status, data = self._send("POST", f"/executive-api/question-sets/{sid}/review",
                                  {"action": "approve", "note": "ok"})
        self.assertEqual(status, 200)
        self.assertEqual(data["question_set"]["status"], "approved")
        status, ho = self._send("GET", f"/executive-api/question-sets/{sid}/handoff", None)
        self.assertEqual(status, 200)
        self.assertIn("Merchant Voice", ho["handoff"]["markdown"])
        self.assertIn("Proposal only", ho["handoff"]["markdown"])   # boundary stated
        self.assertEqual(ho["handoff"]["mv_guide_payload"][0]["purpose"], "behaviour")

    def test_reject(self):
        sid = self._seed()
        _, data = self._send("POST", f"/executive-api/question-sets/{sid}/review",
                             {"action": "reject"})
        self.assertEqual(data["question_set"]["status"], "rejected")

    def test_edit_that_breaks_taxonomy_is_400(self):
        sid = self._seed()
        status, data = self._send(
            "POST", f"/executive-api/question-sets/{sid}/review",
            {"action": "approve", "questions": [{"text": "Q?", "purpose": "not_a_real_purpose",
                                                 "question_type": "open_text"}]})
        self.assertEqual(status, 400)
        self.assertIn("taxonomy", data["error"])
        # the set stayed a draft (the bad edit did not persist)
        _, one = self._send("GET", f"/executive-api/question-sets/{sid}", None)
        self.assertEqual(one["question_set"]["status"], "draft")

    def test_valid_edit_persists_on_approve(self):
        sid = self._seed()
        status, data = self._send(
            "POST", f"/executive-api/question-sets/{sid}/review",
            {"action": "approve", "questions": [{
                "text": "Reworded neutral question?", "purpose": "willingness_to_pay",
                "question_type": "open_text", "linked_assumption": "ASM-OPP-001-wtp"}]})
        self.assertEqual(status, 200)
        self.assertEqual(data["question_set"]["questions"][0]["text"],
                         "Reworded neutral question?")

    def test_re_review_conflict_and_delete(self):
        sid = self._seed()
        self._send("POST", f"/executive-api/question-sets/{sid}/review", {"action": "approve"})
        status, _ = self._send("POST", f"/executive-api/question-sets/{sid}/review",
                               {"action": "reject"})
        self.assertEqual(status, 409)
        status, out = self._send("DELETE", f"/executive-api/question-sets/{sid}", None)
        self.assertEqual(status, 200)
        self.assertTrue(out["deleted"])
        status, _ = self._send("GET", f"/executive-api/question-sets/{sid}", None)
        self.assertEqual(status, 404)

    def test_bad_action_is_400(self):
        sid = self._seed()
        status, _ = self._send("POST", f"/executive-api/question-sets/{sid}/review",
                               {"action": "sideways"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
