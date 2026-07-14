"""Merchant identity service tests: identity.db separation from mv.db."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import RESEARCHER, VALID_IDENTITY, make_dbs  # noqa: E402

from app.db import DbError  # noqa: E402
from app.models import ValidationError  # noqa: E402


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn, self.identity_conn, self.config = make_dbs(self.tmp.name)

    def test_create_identity_happy_path(self):
        from app import identity
        row = identity.create(self.identity_conn, self.config, RESEARCHER, dict(VALID_IDENTITY), "t0")
        self.assertTrue(row["merchant_identity_id"].startswith("MID-"))
        self.assertEqual(row["consent_status"], "granted")
        self.assertIsNone(row["protected_external_reference"])

    def test_identity_lives_only_in_identity_db(self):
        from app import identity
        row = identity.create(self.identity_conn, self.config, RESEARCHER, dict(VALID_IDENTITY), "t0")
        tables_mv = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertNotIn("merchant_identity", tables_mv)
        fetched = identity.get(self.identity_conn, row["merchant_identity_id"])
        self.assertEqual(fetched["merchant_identity_id"], row["merchant_identity_id"])

    def test_identity_not_found_raises(self):
        from app import identity
        with self.assertRaises(DbError):
            identity.get(self.identity_conn, "MID-DOES-NOT-EXIST")

    def test_synthetic_only_blocks_non_synthetic_identity(self):
        from app import identity
        bad = {**VALID_IDENTITY, "data_classification": "confidential"}
        with self.assertRaises(ValidationError):
            identity.create(self.identity_conn, self.config, RESEARCHER, bad, "t0")

    def test_missing_permitted_use_rejected(self):
        from app import identity
        bad = {k: v for k, v in VALID_IDENTITY.items() if k != "permitted_use"}
        with self.assertRaises(ValidationError):
            identity.create(self.identity_conn, self.config, RESEARCHER, bad, "t0")

    def test_identity_create_is_audited_in_identity_db(self):
        from app import audit, identity
        row = identity.create(self.identity_conn, self.config, RESEARCHER, dict(VALID_IDENTITY), "t0")
        events = audit.list_for_object(self.identity_conn, "merchant_identity", row["merchant_identity_id"])
        self.assertEqual([e["action"] for e in events], ["create"])

    def test_identity_suppress_withdrawn(self):
        from app import identity
        row = identity.create(self.identity_conn, self.config, RESEARCHER, dict(VALID_IDENTITY), "t0")
        updated = identity.suppress(self.identity_conn, RESEARCHER, row["merchant_identity_id"], "withdrawn", "t1")
        self.assertEqual(updated["consent_status"], "withdrawn")
        self.assertFalse(updated["quote_permission"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
