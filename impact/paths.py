"""Repository paths, dependency imports, and hashing helpers.

Path globals are recomputed from a configurable repo root so tests can operate
on a temporary copy and never touch live knowledge-base data. Other modules
must read these as ``paths.NAME`` (not ``from .paths import NAME``) so a
``set_repo_root`` call is visible to them.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

# module-level globals, filled by _compute()
REPO_ROOT = KB = IMPACT_KB = None
PROPOSALS_DIR = TRANSACTIONS_DIR = ASSUMPTIONS_DIR = None
MONITORING_DIR = EMAIL_DIR = SCORE_HISTORY = LOCK_FILE = None
REGISTERS_DIR = BRIEFS_DIR = RESEARCH_DIR = METADATA_DIR = None


def _compute(root):
    global REPO_ROOT, KB, IMPACT_KB, PROPOSALS_DIR, TRANSACTIONS_DIR
    global ASSUMPTIONS_DIR, MONITORING_DIR, EMAIL_DIR, SCORE_HISTORY, LOCK_FILE
    global REGISTERS_DIR, BRIEFS_DIR, RESEARCH_DIR, METADATA_DIR
    REPO_ROOT = Path(root).resolve()
    KB = REPO_ROOT / "knowledge-base"
    IMPACT_KB = KB / "impact"
    PROPOSALS_DIR = IMPACT_KB / "proposals"
    TRANSACTIONS_DIR = IMPACT_KB / "transactions"
    ASSUMPTIONS_DIR = IMPACT_KB / "assumptions"
    MONITORING_DIR = IMPACT_KB / "monitoring"
    EMAIL_DIR = IMPACT_KB / "email-previews"
    SCORE_HISTORY = IMPACT_KB / "score-history.jsonl"
    LOCK_FILE = IMPACT_KB / ".lock"
    # generated read-model outputs (derived, written only with --write/--output)
    REGISTERS_DIR = IMPACT_KB / "assumption-registers"
    BRIEFS_DIR = IMPACT_KB / "briefs"
    RESEARCH_DIR = IMPACT_KB / "research-requests"
    METADATA_DIR = IMPACT_KB / "assumption-metadata"


def set_repo_root(root):
    """Point all impact data paths at another repo root (used by tests)."""
    _compute(root)


# default: the real repository (this file lives at <repo>/impact/paths.py)
_compute(os.environ.get("IMPACT_REPO_ROOT", Path(__file__).resolve().parents[1]))

# make the Part B engine importable (opportunity_engine) without changing it
_B_TOOLS = Path(__file__).resolve().parents[1] / "opportunity-intelligence" / "tools"
if str(_B_TOOLS) not in sys.path:
    sys.path.insert(0, str(_B_TOOLS))


def load_engine():
    """Return (scoring, evidence) modules from the Part B engine."""
    from opportunity_engine import scoring, evidence
    return scoring, evidence


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ensure_dirs():
    for d in (PROPOSALS_DIR, TRANSACTIONS_DIR, ASSUMPTIONS_DIR, MONITORING_DIR, EMAIL_DIR):
        d.mkdir(parents=True, exist_ok=True)
