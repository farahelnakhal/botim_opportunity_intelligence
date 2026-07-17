"""Phase R8b — per-user conversation scoping. A conversation created with an
authenticated identity belongs to that user; another user's id makes it
indistinguishable from nonexistent; legacy NULL-owner conversations stay
accessible. The proxy identity header is honored only when the deployment
explicitly trusts the fronting proxy. Offline (mock provider)."""

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app.api import Api                       # noqa: E402
from app.config import Config                 # noqa: E402
from app.orchestrator import Orchestrator     # noqa: E402
from app.store import ConversationStore       # noqa: E402

ALICE = "USER-aaaaaaaaaaa1"
BOB = "USER-bbbbbbbbbbb2"


def make_orchestrator():
    cfg = Config(env={"COPILOT_PROVIDER": "mock"})
    cfg.db_path = Path(tempfile.mkdtemp()) / "conv.db"
    store = ConversationStore(cfg.db_path)
    return Orchestrator(cfg, store), store


class ConversationOwnership(unittest.TestCase):
    def test_new_conversation_is_stamped_with_its_creator(self):
        o, store = make_orchestrator()
        r = o.chat("Tell me about OPP-013", conversation_id=None, user_id=ALICE)
        conv = store.get_conversation(r["conversation_id"])
        self.assertEqual(conv["owner_user_id"], ALICE)

    def test_another_users_conversation_is_indistinguishable_from_missing(self):
        o, _ = make_orchestrator()
        r = o.chat("Tell me about OPP-013", conversation_id=None, user_id=ALICE)
        cid = r["conversation_id"]
        # Alice continues fine
        cont = o.chat("What are the risks?", conversation_id=cid, user_id=ALICE)
        self.assertNotIn("error", cont)
        # Bob gets exactly the stale-conversation error, not a permission hint
        denied = o.chat("What are the risks?", conversation_id=cid, user_id=BOB)
        self.assertEqual(denied["error"]["code"], "conversation_not_found")

    def test_legacy_unowned_conversations_stay_accessible(self):
        o, _ = make_orchestrator()
        r = o.chat("Tell me about OPP-013", conversation_id=None)   # pre-auth: no user
        cid = r["conversation_id"]
        cont = o.chat("What are the risks?", conversation_id=cid, user_id=BOB)
        self.assertNotIn("error", cont)

    def test_api_read_and_delete_respect_ownership(self):
        o, store = make_orchestrator()
        api = Api(o, store)
        r = o.chat("Tell me about OPP-013", conversation_id=None, user_id=ALICE)
        cid = r["conversation_id"]
        status, _ = api.handle("GET", f"/api/conversations/{cid}", b"", user_id=ALICE)
        self.assertEqual(status, 200)
        for method, path in (("GET", f"/api/conversations/{cid}"),
                             ("GET", f"/api/conversations/{cid}/messages"),
                             ("DELETE", f"/api/conversations/{cid}")):
            status, body = api.handle(method, path, b"", user_id=BOB)
            self.assertEqual(status, 404, (method, path))
            self.assertEqual(body["error"]["code"], "not_found")
        # Alice's conversation survived Bob's denied delete
        self.assertIsNotNone(store.get_conversation(cid))

    def test_store_migration_is_idempotent_for_existing_dbs(self):
        db = Path(tempfile.mkdtemp()) / "conv.db"
        ConversationStore(db)
        store = ConversationStore(db)   # reopen: ALTER must not re-run
        cid = store.create_conversation()
        self.assertIsNone(store.get_conversation(cid)["owner_user_id"])


class ProxyTrustFlag(unittest.TestCase):
    def test_trust_flag_defaults_off_and_parses_strictly(self):
        self.assertFalse(Config(env={"COPILOT_PROVIDER": "mock"}).trust_proxy_user)
        self.assertTrue(Config(env={"COPILOT_PROVIDER": "mock",
                                    "COPILOT_TRUST_PROXY_USER": "1"}).trust_proxy_user)
        self.assertFalse(Config(env={"COPILOT_PROVIDER": "mock",
                                     "COPILOT_TRUST_PROXY_USER": "yes"}).trust_proxy_user)


if __name__ == "__main__":
    unittest.main()
