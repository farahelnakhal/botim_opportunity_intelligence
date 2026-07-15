"""Phase 3 — process-lifecycle smoke tests for executive-ui/deploy/start.sh.

start.sh's real job is running two long-lived stdlib HTTP servers, so these
tests exercise it as a black box: launch the real start.sh with the two
server entrypoints swapped out for tiny stub scripts (via COPILOT_ENTRYPOINT /
EXECUTIVE_API_ENTRYPOINT), and assert on process liveness, exit codes, and
log lines. No real Anthropic key, no real copilot-backend/executive-ui/api
process is required — the stubs stand in for both, deterministically and
without network.
"""

import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parents[1]
START_SH = DEPLOY_DIR / "start.sh"

GOOD_SERVER = textwrap.dedent("""
    import argparse, os, signal, socket, sys, time
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("--root")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    args, _ = ap.parse_known_args()
    host = args.host or os.environ.get("COPILOT_HOST", "127.0.0.1")
    port = args.port or int(os.environ.get("COPILOT_PORT", "0"))
    Path(os.environ["STUB_PIDFILE"]).write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(1)
    while True:
        time.sleep(0.1)
    """)

NEVER_READY_SERVER = textwrap.dedent("""
    import os, signal, sys, time
    from pathlib import Path
    pidfile = os.environ["STUB_PIDFILE"]
    Path(pidfile).write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *a: sys.exit(0))
    # Deliberately never binds COPILOT_HOST:COPILOT_PORT — readiness must
    # time out rather than hang forever.
    while True:
        time.sleep(0.1)
    """)

FAIL_IMMEDIATELY = textwrap.dedent("""
    import os, sys
    from pathlib import Path
    pidfile = os.environ.get("STUB_PIDFILE")
    if pidfile:
        Path(pidfile).write_text(str(os.getpid()))
    sys.exit(7)
    """)


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


class LifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.copilot_pidfile = self.tmp / "copilot.pid"
        self.exec_pidfile = self.tmp / "exec.pid"
        self._proc = None

    def tearDown(self):
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait(timeout=5)
        if self._proc and self._proc.stdout:
            self._proc.stdout.close()

    def _write_stub(self, name, source):
        path = self.tmp / name
        path.write_text(source)
        return path

    def _free_port(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def _run(self, copilot_src, exec_src, extra_env=None, exec_pidfile=True):
        copilot_entry = self._write_stub("copilot_stub.py", copilot_src)
        exec_entry = self._write_stub("exec_stub.py", exec_src)
        env = dict(os.environ)
        env.update({
            "COPILOT_PROVIDER": "mock",
            "COPILOT_HOST": "127.0.0.1",
            "COPILOT_PORT": str(self._free_port()),
            "EXECUTIVE_API_HOST": "127.0.0.1",
            "EXECUTIVE_API_PORT": str(self._free_port()),
            "COPILOT_READINESS_TIMEOUT_SECONDS": "3",
            "COPILOT_READINESS_INTERVAL_SECONDS": "0.1",
            "COPILOT_ENTRYPOINT": str(copilot_entry),
            "EXECUTIVE_API_ENTRYPOINT": str(exec_entry),
            "STUB_PIDFILE": str(self.copilot_pidfile),
        })
        if extra_env:
            env.update(extra_env)
        # Executive stub gets its own pidfile via a distinct env var name so
        # both stubs can run in the same process without colliding.
        env["EXEC_STUB_PIDFILE"] = str(self.exec_pidfile) if exec_pidfile else ""
        self._proc = subprocess.Popen(
            ["bash", str(START_SH)],
            cwd=str(DEPLOY_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        return self._proc

    def _read_pid(self, pidfile, timeout=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pidfile.exists() and pidfile.read_text().strip():
                return int(pidfile.read_text().strip())
            time.sleep(0.05)
        return None


# The executive stub also needs to honor STUB_PIDFILE, but under a different
# variable name (EXEC_STUB_PIDFILE) so it doesn't clobber the copilot pidfile
# when both run in the same environment. Patch that into the stub sources.
GOOD_SERVER_EXEC = GOOD_SERVER.replace('os.environ["STUB_PIDFILE"]', 'os.environ["EXEC_STUB_PIDFILE"]')
FAIL_IMMEDIATELY_EXEC = FAIL_IMMEDIATELY.replace('os.environ.get("STUB_PIDFILE")', 'os.environ.get("EXEC_STUB_PIDFILE")')


class SuccessfulStartup(LifecycleTestCase):
    def test_readiness_gates_executive_api_start_and_both_stay_up(self):
        proc = self._run(GOOD_SERVER, GOOD_SERVER_EXEC)
        copilot_pid = self._read_pid(self.copilot_pidfile)
        exec_pid = self._read_pid(self.exec_pidfile)
        self.assertIsNotNone(copilot_pid, "copilot-backend stub never started")
        self.assertIsNotNone(exec_pid, "executive-api stub never started")
        self.assertTrue(_pid_alive(copilot_pid))
        self.assertTrue(_pid_alive(exec_pid))
        self.assertIsNone(proc.poll(), "start.sh exited early during steady-state run")

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        self.assertEqual(proc.returncode, 0, proc.stdout.read())
        self.assertFalse(_pid_alive(copilot_pid), "copilot-backend child survived shutdown")
        self.assertFalse(_pid_alive(exec_pid), "executive-api child survived shutdown")

    def test_executive_api_is_not_started_before_copilot_is_ready(self):
        # A never-ready copilot stub must keep the executive stub from ever
        # starting at all (no pidfile written).
        proc = self._run(NEVER_READY_SERVER, GOOD_SERVER_EXEC)
        proc.wait(timeout=10)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(self.exec_pidfile.exists(), "executive-api started before copilot readiness succeeded")


class ReadinessTimeout(LifecycleTestCase):
    def test_readiness_timeout_aborts_startup_with_nonzero_exit(self):
        proc = self._run(NEVER_READY_SERVER, GOOD_SERVER_EXEC)
        copilot_pid = self._read_pid(self.copilot_pidfile)
        self.assertIsNotNone(copilot_pid)
        proc.wait(timeout=10)
        out = proc.stdout.read()
        self.assertNotEqual(proc.returncode, 0, out)
        self.assertIn("did not become ready", out)
        self.assertFalse(_pid_alive(copilot_pid), "never-ready copilot stub was not stopped after timeout")


class ForcedCopilotFailure(LifecycleTestCase):
    def test_copilot_exiting_immediately_aborts_startup_loudly(self):
        proc = self._run(FAIL_IMMEDIATELY, GOOD_SERVER_EXEC)
        proc.wait(timeout=10)
        out = proc.stdout.read()
        self.assertNotEqual(proc.returncode, 0, out)
        self.assertFalse(self.exec_pidfile.exists(), "executive-api started despite copilot-backend failure")


class ForcedExecutiveApiFailure(LifecycleTestCase):
    def test_executive_api_exiting_immediately_stops_copilot_and_exits_nonzero(self):
        proc = self._run(GOOD_SERVER, FAIL_IMMEDIATELY_EXEC)
        copilot_pid = self._read_pid(self.copilot_pidfile)
        self.assertIsNotNone(copilot_pid, "copilot-backend stub never started")
        proc.wait(timeout=10)
        out = proc.stdout.read()
        self.assertNotEqual(proc.returncode, 0, out)
        self.assertIn("executive-ui/api exited unexpectedly", out)
        self.assertFalse(_pid_alive(copilot_pid), "copilot-backend was left running after executive-api failed")


class SignalCleanup(LifecycleTestCase):
    def _assert_clean_signal_shutdown(self, sig):
        proc = self._run(GOOD_SERVER, GOOD_SERVER_EXEC)
        copilot_pid = self._read_pid(self.copilot_pidfile)
        exec_pid = self._read_pid(self.exec_pidfile)
        self.assertIsNotNone(copilot_pid)
        self.assertIsNotNone(exec_pid)

        proc.send_signal(sig)
        proc.wait(timeout=5)
        out = proc.stdout.read()
        self.assertEqual(proc.returncode, 0, out)
        self.assertFalse(_pid_alive(copilot_pid), "copilot-backend survived signal shutdown (orphan)")
        self.assertFalse(_pid_alive(exec_pid), "executive-api survived signal shutdown (orphan)")

    def test_sigterm_stops_both_children_cleanly(self):
        self._assert_clean_signal_shutdown(signal.SIGTERM)

    def test_sigint_stops_both_children_cleanly(self):
        self._assert_clean_signal_shutdown(signal.SIGINT)


if __name__ == "__main__":
    unittest.main()
