"""Phase R7 — document upload/list/delete over HTTP, ownership, quota, and
the workspace refresh consuming uploaded content. Offline."""

import base64
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("BOTIM_APP_MODE", "test")
os.environ.setdefault("USER_OPPORTUNITIES_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "user-opportunities.db"))
os.environ.setdefault("RESEARCH_DB_PATH", os.path.join(tempfile.mkdtemp(), "research.db"))
os.environ.setdefault("WORKSPACE_DB_PATH", os.path.join(tempfile.mkdtemp(), "workspace.db"))
os.environ.setdefault("AUTH_DB_PATH", os.path.join(tempfile.mkdtemp(), "auth.db"))
os.environ["DOCUMENTS_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "documents.db")

UI = Path(__file__).resolve().parents[2]
REPO = UI.parents[0]
for p in (str(UI), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from api import server  # noqa: E402


def b64(data):
    return base64.b64encode(data).decode()


class DocumentRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server(port=0, root=str(REPO))
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def tearDown(self):
        os.environ["BOTIM_AUTH_MODE"] = "off"

    def _req(self, method, path, payload=None, cookie=None):
        headers = {"content-type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method, headers=headers)
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read()), r.headers

    def _make_opp(self, title="Docs opportunity", cookie=None):
        _, opp, _ = self._req("POST", "/api/user-opportunities",
                              {"title": title, "status": "saved",
                               "target_segment": "regional SMEs"}, cookie=cookie)
        return opp

    def _register(self, email):
        _, data, headers = self._req("POST", "/api/auth/register",
                                     {"email": email, "password": "long-enough-pass"})
        token = headers.get("Set-Cookie").split("botim_session=")[1].split(";")[0]
        return data["user"], f"botim_session={token}"

    def test_upload_list_delete_roundtrip(self):
        opp = self._make_opp()
        status, doc, _ = self._req(
            "POST", f"/api/user-opportunities/{opp['id']}/documents",
            {"filename": "study.txt",
             "content_base64": b64(b"Payroll settlement takes 4 days on average.")})
        self.assertEqual(status, 201)
        self.assertEqual(doc["status"], "extracted")
        self.assertEqual(doc["chunk_count"], 1)
        _, listing, _ = self._req("GET",
                                  f"/api/user-opportunities/{opp['id']}/documents")
        self.assertEqual([d["id"] for d in listing["documents"]], [doc["id"]])
        _, deleted, _ = self._req("DELETE", f"/api/documents/{doc['id']}")
        self.assertTrue(deleted["deleted"])
        _, after, _ = self._req("GET",
                                f"/api/user-opportunities/{opp['id']}/documents")
        self.assertEqual(after["documents"], [])

    def test_unsupported_type_and_bad_base64_are_honest_errors(self):
        opp = self._make_opp("Bad uploads")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST", f"/api/user-opportunities/{opp['id']}/documents",
                      {"filename": "deck.pdf", "content_base64": b64(b"%PDF-1.4")})
        self.assertEqual(cm.exception.code, 415)
        self.assertIn("not supported yet", cm.exception.read().decode())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("POST", f"/api/user-opportunities/{opp['id']}/documents",
                      {"filename": "a.txt", "content_base64": "@@not-base64@@"})
        self.assertEqual(cm.exception.code, 400)

    def test_workspace_refresh_quotes_uploaded_documents(self):
        opp = self._make_opp("Docs feed the workspace")
        self._req("POST", f"/api/user-opportunities/{opp['id']}/documents",
                  {"filename": "internal-study.txt",
                   "content_base64": b64(b"Internal study: settlement takes 4 days "
                                         b"on average for regional SMEs.")})
        status, v, _ = self._req(
            "POST", f"/api/user-opportunities/{opp['id']}/workspace/refresh",
            {"question": "how slow is settlement for this segment?"})
        self.assertEqual(status, 201)
        self.assertEqual(len(v["document_evidence"]), 1)
        self.assertIn("settlement takes 4 days", v["document_evidence"][0]["excerpt"])
        self.assertEqual(v["provenance"]["document_ids"],
                         [v["document_evidence"][0]["document_id"]])

    def test_documents_are_owner_scoped_under_required_auth(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        _, gina = self._register("r7-gina@example.com")
        _, hank = self._register("r7-hank@example.com")
        opp = self._make_opp("Gina's opportunity", cookie=gina)
        _, doc, _ = self._req(
            "POST", f"/api/user-opportunities/{opp['id']}/documents",
            {"filename": "private.txt",
             "content_base64": b64(b"private growth numbers 12%")}, cookie=gina)
        self.assertEqual(doc["owner_user_id"].split("-")[0], "USER")
        # Hank cannot reach the opportunity (owned) => 404 on its documents
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("GET", f"/api/user-opportunities/{opp['id']}/documents",
                      cookie=hank)
        self.assertEqual(cm.exception.code, 404)
        # nor delete the document directly
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._req("DELETE", f"/api/documents/{doc['id']}", cookie=hank)
        self.assertEqual(cm.exception.code, 404)
        # Gina deletes fine
        _, deleted, _ = self._req("DELETE", f"/api/documents/{doc['id']}", cookie=gina)
        self.assertTrue(deleted["deleted"])

    def test_upload_quota_yields_honest_429(self):
        os.environ["BOTIM_AUTH_MODE"] = "required"
        os.environ["QUOTA_DOCUMENT_UPLOAD_PER_DAY"] = "1"
        try:
            _, ivy = self._register("r7-ivy@example.com")
            opp = self._make_opp("Ivy's opportunity", cookie=ivy)
            payload = {"filename": "a.txt", "content_base64": b64(b"some text content")}
            status, _, _ = self._req(
                "POST", f"/api/user-opportunities/{opp['id']}/documents",
                payload, cookie=ivy)
            self.assertEqual(status, 201)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self._req("POST", f"/api/user-opportunities/{opp['id']}/documents",
                          payload, cookie=ivy)
            self.assertEqual(cm.exception.code, 429)
            self.assertIn("daily limit reached", cm.exception.read().decode())
        finally:
            os.environ.pop("QUOTA_DOCUMENT_UPLOAD_PER_DAY", None)


if __name__ == "__main__":
    unittest.main()
