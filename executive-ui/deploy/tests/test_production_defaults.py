"""PR1 (production cleanup) — the deploy image must default to the clean
NORMAL mode (demo is an explicit opt-in build arg), and a normal-mode
deployment on the mock provider must warn loudly, never silently."""

import re
import subprocess
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
DOCKERFILE = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
START_SH = DEPLOY / "start.sh"


class DockerfileDefaults(unittest.TestCase):
    def test_app_mode_defaults_to_normal_not_demo(self):
        self.assertIn("ARG APP_MODE=normal", DOCKERFILE)
        # demo must never be hardcoded as the runtime or build-time mode
        self.assertNotRegex(DOCKERFILE, r"BOTIM_APP_MODE=demo\b")
        self.assertNotRegex(DOCKERFILE, r"VITE_APP_MODE=demo\b")

    def test_mode_envs_follow_the_build_arg(self):
        self.assertRegex(DOCKERFILE, r"VITE_APP_MODE=\$APP_MODE")
        self.assertRegex(DOCKERFILE, r"BOTIM_APP_MODE=\$APP_MODE")

    def test_runtime_databases_live_on_the_writable_volume(self):
        # research runs must persist across container restarts like user
        # opportunities do — never inside the ephemeral image layer
        self.assertIn("USER_OPPORTUNITIES_DB_PATH=/data/runtime/", DOCKERFILE)
        self.assertIn("RESEARCH_DB_PATH=/data/runtime/", DOCKERFILE)


class MockProviderWarning(unittest.TestCase):
    """Run only start.sh's configuration prelude (everything before the first
    service starts) and inspect its output — no servers are launched."""

    def _prelude_output(self, env_pairs):
        script = START_SH.read_text(encoding="utf-8")
        cut = script.index('log "starting copilot-backend')
        prelude = script[:cut] + "\nexit 0\n"
        return subprocess.run(
            ["bash", "-c", prelude], capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", **dict(env_pairs)},
        ).stdout

    def test_normal_mode_with_no_key_errors_loudly_and_never_defaults_to_mock(self):
        out = self._prelude_output({})  # no key, no explicit provider, no mode
        self.assertIn("ERROR", out)
        self.assertIn("BOTIM_LLM_API_KEY", out)
        # mock is NOT silently selected — runtime mode is 'unconfigured'
        self.assertNotIn("COPILOT_PROVIDER=mock", out)
        self.assertNotIn("deterministic mock responder", out)

    def test_demo_mode_with_no_key_defaults_to_mock_without_error(self):
        out = self._prelude_output({"BOTIM_APP_MODE": "demo"})
        self.assertIn("deterministic mock responder", out)
        self.assertNotIn("ERROR", out)
        self.assertNotIn("WARNING", out)

    def test_normal_mode_with_explicit_mock_warns_loudly(self):
        out = self._prelude_output({"BOTIM_LLM_PROVIDER": "mock"})
        self.assertIn("WARNING", out)
        self.assertIn("MOCK", out)
        self.assertIn("BOTIM_LLM_API_KEY", out)

    def test_normal_mode_with_canonical_key_is_silent(self):
        out = self._prelude_output({"BOTIM_LLM_API_KEY": "k-secret-value"})
        self.assertNotIn("WARNING", out)
        self.assertNotIn("ERROR", out)
        self.assertNotIn("k-secret-value", out)  # key never echoed

    def test_alias_keys_also_count_as_configured(self):
        for var in ("ANTHROPIC_API_KEY", "GROQ_API_KEY"):
            out = self._prelude_output({var: "k-alias-value"})
            self.assertNotIn("ERROR", out, var)
            self.assertNotIn("k-alias-value", out, var)


if __name__ == "__main__":
    unittest.main()
