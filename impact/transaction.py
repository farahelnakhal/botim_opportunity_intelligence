"""File-transaction engine: lock, manifest, backups, staging, recovery.

Guarantee (stated accurately, NOT called fully atomic across files):
  * a handled validation failure before commit -> zero target-file changes;
  * an unexpected interruption may briefly leave an intermediate state, but it
    is detected via the manifest and automatically restored from complete
    backups before any other workflow operation proceeds.

A repository-wide lock plus non-terminal manifest states serialise operations:
no apply/rollback may begin while an unresolved transaction exists.
"""

import datetime
import json
import os
from pathlib import Path

from . import history, paths
from .errors import ImpactError
from .paths import ensure_dirs, sha256_bytes

NON_TERMINAL = {"preparing", "applying", "recovering"}


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def _sanitize(path):
    return str(Path(path)).replace(os.sep, "__").lstrip("_")


def _manifest_path(txn_id):
    return paths.TRANSACTIONS_DIR / f"{txn_id}.json"


def _write_manifest(m):
    _manifest_path(m["transaction_id"]).write_text(
        json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_manifest(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- lock -----------------------------------------------------------------

def _acquire_lock(txn_id):
    ensure_dirs()
    try:
        fd = os.open(str(paths.LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ImpactError("impact lock held by another operation")
    with os.fdopen(fd, "w") as fh:
        fh.write(f"{txn_id} pid={os.getpid()} {_now()}\n")


def _release_lock():
    try:
        paths.LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


# --- recovery -------------------------------------------------------------

def find_unresolved():
    if not paths.TRANSACTIONS_DIR.exists():
        return []
    out = []
    for p in sorted(paths.TRANSACTIONS_DIR.glob("*.json")):
        try:
            m = _read_manifest(p)
        except (json.JSONDecodeError, OSError):
            continue
        if m.get("status") in NON_TERMINAL:
            out.append(m)
    return out


def _restore(m):
    """Restore every affected path from complete backups (or delete files that
    did not previously exist), verifying against manifest prior hashes."""
    backup_dir = paths.TRANSACTIONS_DIR / m["transaction_id"] / "backup"
    for path in m["affected_paths"]:
        prior_hash = m["prior_content_hashes"].get(path)
        target = Path(path)
        # discard any leftover staged temp
        tmp = target.parent / f"{target.name}.{m['transaction_id']}.tmp"
        if tmp.exists():
            tmp.unlink()
        if prior_hash is None:
            if target.exists():
                target.unlink()
            continue
        bkp = backup_dir / _sanitize(path)
        data = bkp.read_bytes()
        if sha256_bytes(data) != prior_hash:
            raise ImpactError(f"backup for {path} does not match recorded prior hash")
        target.write_bytes(data)


def recover(m):
    """Recover one unresolved transaction. Returns a short status string."""
    status = m.get("status")
    txn_id = m["transaction_id"]
    if status == "preparing":
        # no live target was replaced yet (replaces happen only in 'applying')
        for path in m["affected_paths"]:
            target = Path(path)
            tmp = target.parent / f"{target.name}.{txn_id}.tmp"
            if tmp.exists():
                tmp.unlink()
        m["status"] = "aborted"
        m["recovered_at"] = _now()
        _write_manifest(m)
        _release_lock()
        return "aborted (no target changed)"

    # applying or recovering: targets may have been replaced -> restore all
    m["status"] = "recovering"
    _write_manifest(m)
    _restore(m)
    m["status"] = "rolled-back"
    m["recovered_at"] = _now()
    _write_manifest(m)
    history.append({
        "history_id": history.next_history_id(),
        "kind": "recovery",
        "timestamp": _now(),
        "transaction_id": txn_id,
        "proposal_id": m.get("proposal_id"),
        "op_type": m.get("op_type"),
        "restored_paths": m["affected_paths"],
        "note": "interrupted transaction detected and automatically restored from backups",
    })
    _release_lock()
    return "restored from backups"


def preflight():
    """Recover any unresolved transactions. Returns list of recovered txn ids.
    Callers must refuse to begin new work when this returns a non-empty list."""
    recovered = []
    for m in find_unresolved():
        recover(m)
        recovered.append(m["transaction_id"])
    if not recovered:
        # clear a stale lock left with no unresolved manifest
        if paths.LOCK_FILE.exists():
            paths.LOCK_FILE.unlink()
    return recovered


# --- transaction ----------------------------------------------------------

class Transaction:
    def __init__(self, op_type, proposal_id, proposal_hash):
        ensure_dirs()
        self.op_type = op_type
        self.proposal_id = proposal_id
        self.proposal_hash = proposal_hash
        self.transaction_id = "TXN-" + datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        self.targets = []          # list of (abs_path_str, content_str)
        self.manifest = None
        self._locked = False

    def __enter__(self):
        _acquire_lock(self.transaction_id)
        self._locked = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._locked:
            _release_lock()
            self._locked = False
        return False

    def _backup_dir(self):
        return paths.TRANSACTIONS_DIR / self.transaction_id / "backup"

    def prepare(self, targets):
        """targets: list of (path, new_content_str). Back up existing files,
        stage temps, and record hashes in a 'preparing' manifest."""
        # content may be None -> the target is to be DELETED on commit
        self.targets = [(str(p), c) for p, c in targets]
        self._backup_dir().mkdir(parents=True, exist_ok=True)
        prior, proposed = {}, {}
        for path, content in self.targets:
            target = Path(path)
            if target.exists():
                data = target.read_bytes()
                prior[path] = sha256_bytes(data)
                (self._backup_dir() / _sanitize(path)).write_bytes(data)
            else:
                prior[path] = None
            proposed[path] = None if content is None else sha256_bytes(content.encode("utf-8"))
        self.manifest = {
            "transaction_id": self.transaction_id,
            "proposal_id": self.proposal_id,
            "proposal_hash": self.proposal_hash,
            "op_type": self.op_type,
            "created": _now(),
            "affected_paths": [p for p, _ in self.targets],
            "prior_content_hashes": prior,
            "proposed_content_hashes": proposed,
            "status": "preparing",
        }
        _write_manifest(self.manifest)
        for path, content in self.targets:
            if content is None:
                continue
            target = Path(path)
            tmp = target.parent / f"{target.name}.{self.transaction_id}.tmp"
            tmp.write_text(content, encoding="utf-8")

    def validate_staged(self, validators):
        """validators: dict path -> callable(content_str). Runs against staged
        temp contents before any live replacement. Raises on failure."""
        for path, content in self.targets:
            if content is None:
                continue
            fn = validators.get(path)
            if fn is not None:
                fn(content)  # may raise ImpactError

    def abort(self):
        for path, content in self.targets:
            if content is None:
                continue
            target = Path(path)
            tmp = target.parent / f"{target.name}.{self.transaction_id}.tmp"
            if tmp.exists():
                tmp.unlink()
        if self.manifest is not None:
            self.manifest["status"] = "aborted"
            self.manifest["aborted_at"] = _now()
            _write_manifest(self.manifest)

    def commit(self):
        """Replace (or delete) all targets, then verify each live file matches
        its proposed hash. On any post-replace mismatch, restore and raise."""
        self.manifest["status"] = "applying"
        _write_manifest(self.manifest)
        for path, content in self.targets:
            target = Path(path)
            if content is None:
                if target.exists():
                    target.unlink()
                continue
            tmp = target.parent / f"{target.name}.{self.transaction_id}.tmp"
            os.replace(str(tmp), str(target))
        # post-apply validation across ALL affected files
        for path, content in self.targets:
            target = Path(path)
            if content is None:
                if target.exists():
                    self._restore_and_mark()
                    raise ImpactError(f"post-apply: {path} should be absent; transaction restored")
                continue
            if sha256_bytes(target.read_bytes()) != self.manifest["proposed_content_hashes"][path]:
                self._restore_and_mark()
                raise ImpactError(f"post-apply hash mismatch for {path}; transaction restored")
        self.manifest["status"] = "applied"
        self.manifest["applied_at"] = _now()
        _write_manifest(self.manifest)

    def _restore_and_mark(self):
        self.manifest["status"] = "recovering"
        _write_manifest(self.manifest)
        _restore(self.manifest)
        self.manifest["status"] = "rolled-back"
        _write_manifest(self.manifest)
        history.append({
            "history_id": history.next_history_id(),
            "kind": "recovery",
            "timestamp": _now(),
            "transaction_id": self.transaction_id,
            "proposal_id": self.proposal_id,
            "op_type": self.op_type,
            "restored_paths": self.manifest["affected_paths"],
            "note": "post-apply validation failed; restored from backups",
        })
