#!/usr/bin/env python3
"""Integration gate for the combined BOTIM Opportunity Intelligence agent.

Runs every validation both modules provide, plus the cross-module integration
tests, in one command. This is the pre-push gate defined in WORKSTREAMS.md:
it must pass with zero failures before anything lands on main.

Usage (from repo root):
    python3 shared/integration_check.py

Exit 0 = everything green; exit 1 = at least one step failed.
Standard library only; read-only.
"""

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

STEPS = (
    ("A: evidence-format conformance",
     [sys.executable, "customer-intelligence/tools/conformance_check.py", "."]),
    ("A: unit tests",
     [sys.executable, "-m", "unittest", "discover", "-s", "customer-intelligence/tools/tests", "-q"]),
    ("B: engine unit tests",
     [sys.executable, "-m", "unittest", "discover", "-s", "opportunity-intelligence/tools/tests", "-q"]),
    ("B: knowledge-base sweep",
     [sys.executable, "opportunity-intelligence/tools/run.py", "check"]),
    ("Cross-module integration tests",
     [sys.executable, "-m", "unittest", "discover", "-s", "shared/tests", "-q"]),
)


def main():
    failures = []
    print(f"BOTIM Opportunity Intelligence — integration gate ({len(STEPS)} steps)\n")
    for name, cmd in STEPS:
        start = time.time()
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        took = time.time() - start
        status = "PASS" if proc.returncode == 0 else "FAIL"
        print(f"  {status}  {name}  ({took:.1f}s)")
        if proc.returncode != 0:
            failures.append(name)
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-15:]
            for line in tail:
                print(f"        {line}")
    print()
    if failures:
        print(f"INTEGRATION GATE FAILED — {len(failures)} step(s): {', '.join(failures)}")
        return 1
    print("INTEGRATION GATE PASSED — the combined agent is consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
