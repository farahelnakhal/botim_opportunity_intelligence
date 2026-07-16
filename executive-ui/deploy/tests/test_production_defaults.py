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

    def test_normal_mode_with_mock_provider_warns_loudly(self):
        out = self._prelude_output({})  # no key, no explicit provider, no mode
        self.assertIn("WARNING", out)
        self.assertIn("MOCK", out)
        self.assertIn("ANTHROPIC_API_KEY", out)

    def test_demo_mode_with_mock_provider_does_not_warn(self):
        out = self._prelude_output({"BOTIM_APP_MODE": "demo"})
        self.assertNotIn("WARNING", out)

    def test_normal_mode_with_live_provider_does_not_warn(self):
        out = self._prelude_output({"ANTHROPIC_API_KEY": "x"})
        self.assertNotIn("WARNING", out)
        # and the key value itself is never echoed
        self.assertNotIn('"x"', out)


if __name__ == "__main__":
    unittest.main()
