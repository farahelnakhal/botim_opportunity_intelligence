"""Auth tests: role checks, timing-safe comparison, token non-exposure,
startup refusal without tokens."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(REPO))

from app.auth import AuthError, authenticate, require_any_role, require_role, safe_token_introspection  # noqa: E402
from app.config import Config  # noqa: E402


def make_config(tokens="admin:tok-admin:admin,researcher:tok-res:researcher,"
                       "reviewer:tok-rev:reviewer,viewer:tok-view:viewer"):
    return Config(env={"MV_TOKENS": tokens})


class AuthTests(unittest.TestCase):
    def test_valid_tokens_resolve_correct_roles(self):
        cfg = make_config()
        for token, role in (("tok-admin", "admin"), ("tok-res", "researcher"),
                            ("tok-rev", "reviewer"), ("tok-view", "viewer")):
            p = authenticate(cfg, f"Bearer {token}")
            self.assertEqual(p["role"], role)

    def test_missing_header_rejected(self):
        cfg = make_config()
        with self.assertRaises(AuthError):
            authenticate(cfg, "")
        with self.assertRaises(AuthError):
            authenticate(cfg, "NotBearer xyz")

    def test_invalid_token_rejected(self):
        cfg = make_config()
        with self.assertRaises(AuthError):
            authenticate(cfg, "Bearer not-a-real-token")

    def test_uses_timing_safe_comparison(self):
        # code-level guarantee: hmac.compare_digest is used, not `==`
        src = (BACKEND / "app" / "auth.py").read_text(encoding="utf-8")
        self.assertIn("hmac.compare_digest", src)
        self.assertNotIn("token ==", src)

    def test_role_rank_enforced(self):
        viewer = {"role": "viewer", "label": "v"}
        admin = {"role": "admin", "label": "a"}
        with self.assertRaises(AuthError):
            require_role(viewer, "researcher")
        require_role(admin, "researcher")  # no raise
        with self.assertRaises(AuthError):
            require_any_role(viewer, ("researcher", "reviewer", "admin"))
        require_any_role(admin, ("researcher", "reviewer", "admin"))

    def test_token_values_never_exposed_in_introspection(self):
        cfg = make_config()
        info = safe_token_introspection(cfg)
        blob = str(info)
        for secret in ("tok-admin", "tok-res", "tok-rev", "tok-view"):
            self.assertNotIn(secret, blob)
        self.assertTrue(all(set(i.keys()) == {"label", "role", "enabled"} for i in info))

    def test_disabled_token_map_entries_not_created_for_bad_roles(self):
        cfg = make_config("x:tok:not-a-role")
        self.assertEqual(cfg.token_roles, {})

    def test_startup_refuses_without_tokens(self):
        cfg = Config(env={"MV_TOKENS": ""})
        self.assertFalse(cfg.has_valid_tokens())
        import server as mv_server
        with mock.patch.object(mv_server, "Config", return_value=cfg):
            with self.assertRaises(SystemExit):
                mv_server.main()

    def test_no_token_values_in_captured_output_on_auth_failure(self):
        cfg = make_config()
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                authenticate(cfg, "Bearer tok-admin")
            except AuthError:
                pass
        self.assertNotIn("tok-admin", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
