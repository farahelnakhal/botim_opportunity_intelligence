"""Runtime persistence for versioned analysis workspaces (Phase R5, PR4).

Design (see docs/decision-log.md, 2026-07-16 "Versioned preliminary analysis
workspace per saved chat"):

- Versions are APPEND-ONLY: a refresh creates a new version; existing
  versions are never mutated after they finish. Readers take the latest
  `complete` version, so a concurrent build can never corrupt what chat is
  reading.
- A version records WHAT the chain produced (kb_evidence, claim_ids,
  preliminary_score, gaps) and per-version provenance (question, trigger,
  research run id, models/providers involved). Claims themselves — and their
  human review state — live in the research store (`RCAND-`); approvals
  attach to claims, never to versions, so an approval survives a refresh.
- Lifecycle: running -> complete | failed. `failed` requires an honest
  reason; `complete` must not carry one. Terminal states are immutable.
- Everything here is machine-generated PRELIMINARY analysis: never
  authoritative knowledge, never written to knowledge-base/.
- Storage: runtime SQLite (gitignored) at WORKSPACE_DB_PATH, default
  `runtime/workspace.db`. IDs use the AWV-/WSUB- namespaces (`AWV-<12 hex>`),
  which cannot collide with any other namespace in the system (RRUN-/RSRC-/
  UOPP-/MCFG-/DOC-/USER-/CALC-/…).
- Retention: prune keeps the newest N versions per opportunity (default
  10). Approved claims are unaffected by pruning — they live in the
  research store.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import uuid
import datetime
from pathlib import Path

SCHEMA_VERSION = 5

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO / "runtime" / "workspace.db"

AWV_RE = re.compile(r"^AWV-[0-9a-f]{12}$")
# recipient rows in the R6 monitoring subscription (see below)
WSUB_RE = re.compile(r"^WSUB-[0-9a-f]{12}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# a workspace belongs to a user opportunity (UOPP-) or, in principle, a
# committed one (OPP-nnn) — nothing else
OPP_REF_RE = re.compile(r"^(OPP-\d{3}|UOPP-[0-9a-f]{12})$")

STATUSES = ("running", "complete", "failed")
# the concrete trigger set locked in the decision log — an ordinary chat
# message is deliberately NOT a trigger (follow-ups reuse the latest version)
TRIGGERS = ("first_analysis", "manual_refresh", "meaningful_change",
            "stale", "monitoring")

QUESTION_MAX = 4000
ERROR_MAX = 1000
EMAIL_MAX = 254
DEFAULT_KEEP = 10
DEFAULT_STALE_HOURS = 24

# R6 scheduled-monitoring cadence (per chat). The floor is configurable so an
# operator can loosen/tighten the minimum re-run interval; the ceiling is a
# fixed 30 days. Default 6h sits in the roadmap's 4–6h target band.
DEFAULT_CADENCE_HOURS = 6
MAX_CADENCE_HOURS = 720
OUTCOME_MAX = 200
# R6 double-opt-in: a recipient's confirmation link expires after this many
# hours (R8a's 30-day session TTL is far too long for a confirm link; 48h is
# the sane default, overridable). An expired link is refused; resend issues
# a fresh one.
DEFAULT_CONFIRM_TTL_HOURS = 48
# distinct honest reasons a subscription is dormant (not eligible to run/email),
# stored in `last_outcome` so support can tell them apart from run outcomes and
# from each other. Kept separate from the tick's run outcomes (built/failed/
# skipped_*) so the two never collide.
DORMANCY_REASONS = ("dormant_no_recipients", "dormant_pending_confirmation",
                    "dormant_all_unsubscribed")

_JSON_LIST_FIELDS = ("kb_evidence", "claim_ids", "gaps", "document_evidence")
_JSON_DICT_FIELDS = ("preliminary_score", "provenance")


def _min_cadence_hours():
    try:
        return max(1, int(os.environ.get("MONITORING_MIN_CADENCE_HOURS", 4)))
    except ValueError:
        return 4


def _default_cadence_hours():
    try:
        return int(os.environ.get("MONITORING_DEFAULT_CADENCE_HOURS",
                                  DEFAULT_CADENCE_HOURS))
    except ValueError:
        return DEFAULT_CADENCE_HOURS


def _confirm_ttl_hours():
    try:
        return max(1, int(os.environ.get("MONITORING_CONFIRM_TTL_HOURS",
                                         DEFAULT_CONFIRM_TTL_HOURS)))
    except ValueError:
        return DEFAULT_CONFIRM_TTL_HOURS


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sign_unsubscribe_token(recipient_id, key):
    """Deterministic, stateless unsubscribe token (RFC 8058-style):
    "<recipient_id>.<base64url(HMAC-SHA256(key, recipient_id))>". Stable across
    every email, nothing stored per row. Returns None when no key is
    configured (so the caller can honestly decline to send a link)."""
    if not (isinstance(recipient_id, str) and recipient_id and key):
        return None
    sig = hmac.new(key.encode("utf-8"), recipient_id.encode("utf-8"),
                   hashlib.sha256).digest()
    return f"{recipient_id}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def verify_unsubscribe_token(token, key):
    """Recompute and constant-time-compare a signed unsubscribe token. Returns
    the recipient id when valid, else None. Rotating the key silently
    invalidates every previously-issued token (documented tradeoff)."""
    if not (isinstance(token, str) and key and "." in token):
        return None
    recipient_id = token.rpartition(".")[0]
    expected = sign_unsubscribe_token(recipient_id, key)
    if expected is None:
        return None
    return recipient_id if hmac.compare_digest(token, expected) else None


def _shift_hours(iso, hours):
    dt = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ") \
        .replace(tzinfo=datetime.timezone.utc)
    return (dt + datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


class WorkspaceStoreError(Exception):
    """Safe, structured store error — `status` maps to the HTTP status; the
    message never contains SQL or paths."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id():
    return f"AWV-{uuid.uuid4().hex[:12]}"


def _validate_opp_ref(opportunity_id):
    if not isinstance(opportunity_id, str) or not OPP_REF_RE.match(opportunity_id):
        raise WorkspaceStoreError("invalid opportunity reference "
                                  "(expected OPP-nnn or UOPP-<12 hex>)")
    return opportunity_id


def _validate_awv_id(version_id):
    if not isinstance(version_id, str) or not AWV_RE.match(version_id):
        raise WorkspaceStoreError("invalid workspace version id")
    return version_id


class WorkspaceStore:
    """SQLite-backed store. One short-lived connection per operation (safe
    under the threading HTTP server); every write is a transaction."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path
                            or os.environ.get("WORKSPACE_DB_PATH")
                            or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            version = int(row["value"]) if row else 0
            if version > SCHEMA_VERSION:
                raise WorkspaceStoreError("workspace database is newer than this code",
                                          status=500)
            if version < 1:
                conn.execute("""CREATE TABLE IF NOT EXISTS workspace_versions (
                    id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','complete','failed')),
                    trigger TEXT NOT NULL
                        CHECK (trigger IN ('first_analysis','manual_refresh',
                                           'meaningful_change','stale','monitoring')),
                    question TEXT,
                    error TEXT,
                    research_run_id TEXT,
                    kb_evidence TEXT NOT NULL DEFAULT '[]',
                    claim_ids TEXT NOT NULL DEFAULT '[]',
                    preliminary_score TEXT,
                    gaps TEXT NOT NULL DEFAULT '[]',
                    provenance TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE (opportunity_id, version))""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_awv_opp "
                             "ON workspace_versions(opportunity_id, version)")
            if version < 2:
                # Phase R7 — verbatim excerpts from the user's uploaded
                # documents that grounded this version (snapshot: kept even
                # if the document is later deleted). Idempotent PRAGMA guard.
                existing = {row["name"] for row in
                            conn.execute("PRAGMA table_info(workspace_versions)")}
                if "document_evidence" not in existing:
                    conn.execute("ALTER TABLE workspace_versions "
                                 "ADD COLUMN document_evidence TEXT NOT NULL DEFAULT '[]'")
            if version < 3:
                # Phase R6 — scheduled-monitoring subscriptions. One parent row
                # per chat holds the cadence + scheduling state; a child table
                # holds N recipients so teammates can be added later with NO
                # schema migration. Every recipient is a signed-in account
                # (recipient_user_id = USER- id); the recipient email is a
                # snapshot of that account's registered address at opt-in time
                # (R8a stores it at sign-up but does not confirm it). Only the
                # SHA-256 hash of each unsubscribe token is stored (never the
                # token), matching the auth store's session-token discipline.
                conn.execute("""CREATE TABLE IF NOT EXISTS workspace_subscriptions (
                    opportunity_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    cadence_hours INTEGER NOT NULL DEFAULT 6,
                    last_run_at TEXT,
                    next_run_at TEXT,
                    last_notified_version INTEGER,
                    last_outcome TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL)""")
                conn.execute("""CREATE TABLE IF NOT EXISTS workspace_subscription_recipients (
                    id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL
                        REFERENCES workspace_subscriptions(opportunity_id) ON DELETE CASCADE,
                    recipient_user_id TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    unsubscribe_token_hash TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    opted_in_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (opportunity_id, recipient_user_id))""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_wsub_recip_opp "
                             "ON workspace_subscription_recipients(opportunity_id)")
                # the token-hash column is dropped in v5; guard the index on its
                # existence so replaying migrations after v5 (schema stamped back)
                # never references a dropped column
                recip_cols = {row["name"] for row in conn.execute(
                    "PRAGMA table_info(workspace_subscription_recipients)")}
                if "unsubscribe_token_hash" in recip_cols:
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_wsub_recip_token "
                                 "ON workspace_subscription_recipients(unsubscribe_token_hash)")
            if version < 4:
                # Phase R6 double-opt-in: a recipient is not eligible to receive
                # mail until it CONFIRMS control of the address via a tokened
                # link. New/re-opted rows start confirmed=0; the tick and the
                # send path treat unconfirmed exactly like disabled. Only the
                # SHA-256 hash of the confirm token is stored (same discipline
                # as session + unsubscribe tokens). Idempotent PRAGMA guard.
                existing = {row["name"] for row in conn.execute(
                    "PRAGMA table_info(workspace_subscription_recipients)")}
                if "confirmed" not in existing:
                    conn.execute("ALTER TABLE workspace_subscription_recipients "
                                 "ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0")
                if "confirm_token_hash" not in existing:
                    conn.execute("ALTER TABLE workspace_subscription_recipients "
                                 "ADD COLUMN confirm_token_hash TEXT")
                if "confirm_expires_at" not in existing:
                    conn.execute("ALTER TABLE workspace_subscription_recipients "
                                 "ADD COLUMN confirm_expires_at TEXT")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_wsub_recip_confirm "
                             "ON workspace_subscription_recipients(confirm_token_hash)")
            if version < 5:
                # Phase R6 PR6c — unsubscribe links are now deterministic signed
                # tokens (HMAC over recipient_id), so the per-row random-token
                # hash is obsolete. Drop it + its index (SQLite >= 3.35 supports
                # DROP COLUMN; Python 3.11 bundles a newer SQLite). Idempotent.
                existing = {row["name"] for row in conn.execute(
                    "PRAGMA table_info(workspace_subscription_recipients)")}
                if "unsubscribe_token_hash" in existing:
                    conn.execute("DROP INDEX IF EXISTS idx_wsub_recip_token")
                    conn.execute("ALTER TABLE workspace_subscription_recipients "
                                 "DROP COLUMN unsubscribe_token_hash")
            conn.execute("INSERT OR REPLACE INTO meta (key, value) "
                         "VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    # -- serialization ------------------------------------------------------ #

    @staticmethod
    def _dict(row):
        d = dict(row)
        for key in _JSON_LIST_FIELDS:
            d[key] = json.loads(d.get(key) or "[]")
        for key in _JSON_DICT_FIELDS:
            d[key] = json.loads(d[key]) if d.get(key) else None
        return d

    # -- lifecycle ----------------------------------------------------------- #

    def create_version(self, opportunity_id, trigger, question=None):
        """Open a new `running` version. Version numbers increment per
        opportunity inside the same transaction (append-only concurrency:
        two simultaneous builds get distinct version numbers; readers only
        ever see `complete` versions)."""
        _validate_opp_ref(opportunity_id)
        if trigger not in TRIGGERS:
            raise WorkspaceStoreError(f"trigger must be one of {list(TRIGGERS)}")
        if question is not None:
            if not isinstance(question, str):
                raise WorkspaceStoreError("'question' must be a string")
            if len(question) > QUESTION_MAX:
                raise WorkspaceStoreError(f"'question' exceeds the {QUESTION_MAX}-character limit")
            question = question.strip() or None
        version_id = _new_id()
        now = _now()
        with self._connect() as conn:
            # retry once on a concurrent (opportunity_id, version) collision
            for attempt in (1, 2):
                row = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) AS v FROM workspace_versions "
                    "WHERE opportunity_id=?", (opportunity_id,)).fetchone()
                try:
                    conn.execute(
                        """INSERT INTO workspace_versions
                           (id, opportunity_id, version, status, trigger, question, created_at)
                           VALUES (?,?,?,'running',?,?,?)""",
                        (version_id, opportunity_id, row["v"] + 1, trigger, question, now))
                    break
                except sqlite3.IntegrityError:
                    if attempt == 2:
                        raise WorkspaceStoreError(
                            "could not allocate a workspace version (concurrent builds)",
                            status=409)
        return self.get_version(version_id)

    def _terminal_guard(self, conn, version_id):
        row = conn.execute("SELECT status FROM workspace_versions WHERE id=?",
                           (version_id,)).fetchone()
        if row is None:
            raise WorkspaceStoreError("workspace version not found", status=404)
        if row["status"] != "running":
            raise WorkspaceStoreError(
                f"version is already terminal ({row['status']}) — versions are immutable",
                status=409)

    def complete_version(self, version_id, *, kb_evidence=None, claim_ids=None,
                         preliminary_score=None, gaps=None, provenance=None,
                         research_run_id=None, document_evidence=None):
        """Finish a running version as `complete` with the chain's outputs.
        Empty outputs are honest (they show up as gaps), never invented."""
        _validate_awv_id(version_id)
        for name, value in (("kb_evidence", kb_evidence), ("claim_ids", claim_ids),
                            ("gaps", gaps), ("document_evidence", document_evidence)):
            if value is not None and not isinstance(value, list):
                raise WorkspaceStoreError(f"'{name}' must be a list")
        for name, value in (("preliminary_score", preliminary_score),
                            ("provenance", provenance)):
            if value is not None and not isinstance(value, dict):
                raise WorkspaceStoreError(f"'{name}' must be an object")
        with self._connect() as conn:
            self._terminal_guard(conn, version_id)
            conn.execute(
                """UPDATE workspace_versions SET status='complete', error=NULL,
                   kb_evidence=?, claim_ids=?, preliminary_score=?, gaps=?,
                   provenance=?, research_run_id=?, document_evidence=?,
                   completed_at=? WHERE id=?""",
                (json.dumps(kb_evidence or []), json.dumps(claim_ids or []),
                 json.dumps(preliminary_score) if preliminary_score else None,
                 json.dumps(gaps or []),
                 json.dumps(provenance) if provenance else None,
                 research_run_id, json.dumps(document_evidence or []),
                 _now(), version_id))
        return self.get_version(version_id)

    def fail_version(self, version_id, error):
        """Finish a running version as `failed` with a mandatory reason."""
        _validate_awv_id(version_id)
        if not isinstance(error, str) or not error.strip():
            raise WorkspaceStoreError("a failed version requires an honest reason")
        with self._connect() as conn:
            self._terminal_guard(conn, version_id)
            conn.execute(
                "UPDATE workspace_versions SET status='failed', error=?, completed_at=? "
                "WHERE id=?", (error.strip()[:ERROR_MAX], _now(), version_id))
        return self.get_version(version_id)

    # -- reads --------------------------------------------------------------- #

    def get_version(self, version_id):
        _validate_awv_id(version_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM workspace_versions WHERE id=?",
                               (version_id,)).fetchone()
        if row is None:
            raise WorkspaceStoreError("workspace version not found", status=404)
        return self._dict(row)

    def latest(self, opportunity_id, status="complete"):
        """The newest version with the given status (readers want 'complete').
        None when no such version exists — an honest empty state."""
        _validate_opp_ref(opportunity_id)
        if status not in STATUSES:
            raise WorkspaceStoreError(f"status must be one of {list(STATUSES)}")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_versions WHERE opportunity_id=? AND status=? "
                "ORDER BY version DESC LIMIT 1", (opportunity_id, status)).fetchone()
        return self._dict(row) if row else None

    def list_versions(self, opportunity_id, limit=50):
        """Version summaries (no bulky JSON payloads), newest first."""
        _validate_opp_ref(opportunity_id)
        limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, opportunity_id, version, status, trigger, question,
                          error, research_run_id, created_at, completed_at
                   FROM workspace_versions WHERE opportunity_id=?
                   ORDER BY version DESC LIMIT ?""", (opportunity_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def is_stale(self, version, stale_hours=None):
        """Deterministic staleness from the version's completion time.
        Threshold from WORKSPACE_STALE_HOURS (default 24h). A version with no
        completion time is honestly treated as stale (it never finished)."""
        if stale_hours is None:
            try:
                stale_hours = int(os.environ.get("WORKSPACE_STALE_HOURS",
                                                 DEFAULT_STALE_HOURS))
            except ValueError:
                stale_hours = DEFAULT_STALE_HOURS
        completed = version.get("completed_at")
        if not completed:
            return True
        try:
            done = datetime.datetime.strptime(completed, "%Y-%m-%dT%H:%M:%SZ") \
                .replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            return True
        age = datetime.datetime.now(datetime.timezone.utc) - done
        return age.total_seconds() > stale_hours * 3600

    # -- retention ------------------------------------------------------------ #

    def prune(self, opportunity_id, keep=DEFAULT_KEEP):
        """Delete all but the newest `keep` versions for an opportunity.
        Claims (and their approvals) live in the research store and are
        untouched. Returns the number of versions removed."""
        _validate_opp_ref(opportunity_id)
        keep = max(1, int(keep))
        with self._connect() as conn:
            cur = conn.execute(
                """DELETE FROM workspace_versions WHERE opportunity_id=? AND id NOT IN
                   (SELECT id FROM workspace_versions WHERE opportunity_id=?
                    ORDER BY version DESC LIMIT ?)""",
                (opportunity_id, opportunity_id, keep))
        return cur.rowcount

    # -- R6 scheduled-monitoring subscriptions -------------------------------- #

    def _validate_cadence(self, cadence_hours):
        if cadence_hours is None:
            return _default_cadence_hours()
        if isinstance(cadence_hours, bool) or not isinstance(cadence_hours, int):
            raise WorkspaceStoreError("cadence_hours must be an integer number of hours")
        lo, hi = _min_cadence_hours(), MAX_CADENCE_HOURS
        if cadence_hours < lo or cadence_hours > hi:
            raise WorkspaceStoreError(
                f"cadence_hours must be between {lo} and {hi}")
        return cadence_hours

    def subscribe(self, opportunity_id, owner_user_id, recipient_user_id,
                  recipient_email, cadence_hours=None):
        """Opt one signed-in account in as a recipient for this chat, creating
        the subscription if needed. DOUBLE OPT-IN: a new recipient — or one
        whose email changed, or one not yet confirmed — is stored UNCONFIRMED
        with a fresh, hashed, expiring confirmation token, and is NOT eligible
        for mail until it confirms. An already-confirmed recipient re-opting in
        with the same address stays confirmed (no re-confirmation). Idempotent
        per (opportunity, recipient). Returns {'recipient_id', 'confirm_token'
        (None when already confirmed — nothing to send), 'confirmed',
        'confirm_expires_at'} — the confirm token is returned once; only its
        hash is stored. Unsubscribe links are minted at SEND time from the
        recipient id + signing key (deterministic, nothing stored per row)."""
        _validate_opp_ref(opportunity_id)
        if not (isinstance(owner_user_id, str) and owner_user_id):
            raise WorkspaceStoreError("a monitoring subscription requires an owner user id")
        if not (isinstance(recipient_user_id, str) and recipient_user_id):
            raise WorkspaceStoreError("a recipient user id is required")
        email = (recipient_email or "").strip() if isinstance(recipient_email, str) else ""
        if not email or len(email) > EMAIL_MAX or not EMAIL_RE.match(email):
            raise WorkspaceStoreError("a valid recipient account email is required")
        cadence = self._validate_cadence(cadence_hours)
        now = _now()
        with self._connect() as conn:
            existing_sub = conn.execute(
                "SELECT opportunity_id FROM workspace_subscriptions WHERE opportunity_id=?",
                (opportunity_id,)).fetchone()
            if existing_sub is None:
                # parent starts DISABLED — it only becomes eligible once a
                # recipient confirms (recompute below). next_run_at is seeded so
                # scheduling begins once eligibility is reached.
                conn.execute(
                    """INSERT INTO workspace_subscriptions
                       (opportunity_id, owner_user_id, enabled, cadence_hours,
                        next_run_at, created_at, updated_at)
                       VALUES (?,?,0,?,?,?,?)""",
                    (opportunity_id, owner_user_id, cadence,
                     _shift_hours(now, cadence), now, now))
            else:
                conn.execute(
                    """UPDATE workspace_subscriptions
                       SET cadence_hours=?, next_run_at=COALESCE(next_run_at, ?),
                           updated_at=? WHERE opportunity_id=?""",
                    (cadence, _shift_hours(now, cadence), now, opportunity_id))
            existing_rec = conn.execute(
                "SELECT id, recipient_email, confirmed FROM workspace_subscription_recipients "
                "WHERE opportunity_id=? AND recipient_user_id=?",
                (opportunity_id, recipient_user_id)).fetchone()
            already_confirmed = bool(existing_rec and existing_rec["confirmed"]
                                     and existing_rec["recipient_email"] == email)
            confirm_token = confirm_hash = confirm_expires = None
            if not already_confirmed:
                confirm_token = secrets.token_urlsafe(32)
                confirm_hash = _hash_token(confirm_token)
                confirm_expires = _shift_hours(now, _confirm_ttl_hours())
            confirmed_val = 1 if already_confirmed else 0
            if existing_rec:
                rec_id = existing_rec["id"]
                conn.execute(
                    """UPDATE workspace_subscription_recipients
                       SET recipient_email=?, enabled=1, confirmed=?,
                           confirm_token_hash=?, confirm_expires_at=?,
                           updated_at=? WHERE id=?""",
                    (email, confirmed_val, confirm_hash, confirm_expires, now, rec_id))
            else:
                rec_id = _new_wsub_id()
                conn.execute(
                    """INSERT INTO workspace_subscription_recipients
                       (id, opportunity_id, recipient_user_id, recipient_email,
                        enabled, confirmed, confirm_token_hash,
                        confirm_expires_at, opted_in_at, updated_at)
                       VALUES (?,?,?,?,1,?,?,?,?,?)""",
                    (rec_id, opportunity_id, recipient_user_id, email,
                     confirmed_val, confirm_hash, confirm_expires, now, now))
            self._recompute_subscription_enabled(conn, opportunity_id, now)
        return {"recipient_id": rec_id, "confirm_token": confirm_token,
                "confirmed": bool(confirmed_val), "confirm_expires_at": confirm_expires}

    def confirm_recipient(self, token):
        """Confirm a recipient via its tokened, login-free link. Validates the
        token and its expiry, marks the recipient confirmed, and clears the
        token (single-use). An expired link is a 410; an unknown/used one a 404
        — never a silent success. Recomputes the parent's eligibility."""
        if not isinstance(token, str) or not token:
            raise WorkspaceStoreError("a confirmation token is required", status=400)
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, opportunity_id, recipient_email, confirm_expires_at "
                "FROM workspace_subscription_recipients WHERE confirm_token_hash=?",
                (_hash_token(token),)).fetchone()
            if row is None:
                raise WorkspaceStoreError("unknown or already-used confirmation link",
                                          status=404)
            if row["confirm_expires_at"] and row["confirm_expires_at"] < now:
                raise WorkspaceStoreError("this confirmation link has expired — opt in "
                                          "again to get a fresh one", status=410)
            conn.execute(
                """UPDATE workspace_subscription_recipients
                   SET confirmed=1, confirm_token_hash=NULL, confirm_expires_at=NULL,
                       enabled=1, updated_at=? WHERE id=?""", (now, row["id"]))
            self._recompute_subscription_enabled(conn, row["opportunity_id"], now)
        return {"opportunity_id": row["opportunity_id"],
                "recipient_email": row["recipient_email"], "confirmed": True}

    def get_subscription(self, opportunity_id):
        """The subscription with its recipient list, or None. Token hashes are
        NEVER included; each recipient reports confirmed / pending_confirmation."""
        _validate_opp_ref(opportunity_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_subscriptions WHERE opportunity_id=?",
                (opportunity_id,)).fetchone()
            if row is None:
                return None
            recs = conn.execute(
                """SELECT id, recipient_user_id, recipient_email, enabled, confirmed,
                          opted_in_at
                   FROM workspace_subscription_recipients WHERE opportunity_id=?
                   ORDER BY opted_in_at, id""", (opportunity_id,)).fetchall()
        sub = dict(row)
        sub["enabled"] = bool(sub["enabled"])
        sub["recipients"] = [{"id": r["id"],
                              "recipient_user_id": r["recipient_user_id"],
                              "recipient_email": r["recipient_email"],
                              "enabled": bool(r["enabled"]),
                              "confirmed": bool(r["confirmed"]),
                              "pending_confirmation": bool(r["enabled"] and not r["confirmed"]),
                              "opted_in_at": r["opted_in_at"]} for r in recs]
        return sub

    def eligible_recipients(self, opportunity_id):
        """Recipients eligible to receive mail (enabled AND confirmed), as
        {'id', 'recipient_email'} — the send path signs each id into an
        unsubscribe link. Excludes unconfirmed and unsubscribed recipients."""
        _validate_opp_ref(opportunity_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, recipient_email FROM workspace_subscription_recipients "
                "WHERE opportunity_id=? AND enabled=1 AND confirmed=1 ORDER BY id",
                (opportunity_id,)).fetchall()
        return [{"id": r["id"], "recipient_email": r["recipient_email"]} for r in rows]

    def version_by_number(self, opportunity_id, version_number):
        """The full version dict for a given (opportunity, version number), or
        None if it no longer exists (e.g. pruned). Used to resolve the diff
        baseline recorded in last_notified_version."""
        _validate_opp_ref(opportunity_id)
        if not isinstance(version_number, int):
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_versions WHERE opportunity_id=? AND version=?",
                (opportunity_id, version_number)).fetchone()
        return self._dict(row) if row else None

    def _recompute_subscription_enabled(self, conn, opportunity_id, now):
        """Parent.enabled reflects whether ANY recipient is ELIGIBLE for mail —
        enabled AND confirmed. An unconfirmed recipient counts as disabled, so a
        chat with only unconfirmed recipients is not scheduled and sends nothing
        (the double-opt-in guarantee, enforced at the persistence layer).

        When the subscription becomes INELIGIBLE, record a distinct honest
        dormancy reason in `last_outcome` so 'why did nobody get an update?' is
        answerable at a glance (pending confirmation vs everyone unsubscribed vs
        no recipients at all) rather than an ambiguous blank. When it becomes
        eligible, clear a stale dormancy marker but never clobber a real run
        outcome."""
        counts = conn.execute(
            """SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN enabled=1 AND confirmed=1 THEN 1 ELSE 0 END) AS eligible,
                 SUM(CASE WHEN enabled=1 AND confirmed=0 THEN 1 ELSE 0 END) AS pending
               FROM workspace_subscription_recipients WHERE opportunity_id=?""",
            (opportunity_id,)).fetchone()
        eligible = counts["eligible"] or 0
        if eligible:
            # eligible again: drop a lingering dormancy marker, keep run outcomes
            conn.execute(
                "UPDATE workspace_subscriptions SET enabled=1, "
                "last_outcome=CASE WHEN last_outcome IN "
                f"({','.join('?' * len(DORMANCY_REASONS))}) THEN NULL ELSE last_outcome END, "
                "updated_at=? WHERE opportunity_id=?",
                (*DORMANCY_REASONS, now, opportunity_id))
        else:
            if not counts["total"]:
                reason = "dormant_no_recipients"
            elif counts["pending"]:
                reason = "dormant_pending_confirmation"
            else:
                reason = "dormant_all_unsubscribed"
            conn.execute("UPDATE workspace_subscriptions SET enabled=0, "
                         "last_outcome=?, updated_at=? WHERE opportunity_id=?",
                         (reason, now, opportunity_id))
        return eligible

    def unsubscribe_recipient(self, opportunity_id, recipient_user_id):
        """Opt a signed-in recipient out of their own subscription. When no
        eligible recipient remains, the subscription is disabled (unscheduled)."""
        _validate_opp_ref(opportunity_id)
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE workspace_subscription_recipients SET enabled=0, updated_at=? "
                "WHERE opportunity_id=? AND recipient_user_id=? AND enabled=1",
                (now, opportunity_id, recipient_user_id))
            changed = cur.rowcount
            eligible = self._recompute_subscription_enabled(conn, opportunity_id, now)
        return {"opportunity_id": opportunity_id, "recipient_user_id": recipient_user_id,
                "unsubscribed": bool(changed), "active_recipients": eligible}

    def unsubscribe_by_token(self, token, signing_key):
        """Tokened, login-free unsubscribe (the link in a monitoring email).
        The token is a deterministic HMAC signature over the recipient id
        (see sign_unsubscribe_token); it is verified by recomputation — nothing
        is looked up by a stored secret. Disables exactly that recipient."""
        recipient_id = verify_unsubscribe_token(token, signing_key)
        if recipient_id is None:
            raise WorkspaceStoreError("unknown or expired unsubscribe link", status=404)
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, opportunity_id, recipient_email "
                "FROM workspace_subscription_recipients WHERE id=?",
                (recipient_id,)).fetchone()
            if row is None:
                raise WorkspaceStoreError("unknown or expired unsubscribe link", status=404)
            conn.execute("UPDATE workspace_subscription_recipients SET enabled=0, "
                         "updated_at=? WHERE id=?", (now, row["id"]))
            self._recompute_subscription_enabled(conn, row["opportunity_id"], now)
        return {"opportunity_id": row["opportunity_id"],
                "recipient_email": row["recipient_email"], "unsubscribed": True}

    def count_enabled_subscriptions(self, owner_user_id):
        """How many enabled subscriptions this user owns — the multiplier the
        R6 quota uses so a multi-chat user is not silently capped mid-day."""
        if not (isinstance(owner_user_id, str) and owner_user_id):
            return 0
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM workspace_subscriptions "
                "WHERE owner_user_id=? AND enabled=1", (owner_user_id,)).fetchone()
        return row["n"]

    # -- R6 scheduled-monitoring tick (scheduler-facing) ---------------------- #

    # A subscription is only schedulable if it has a live CONFIRMED recipient.
    # We check that with an EXISTS on the recipient table directly (not just the
    # denormalized parent.enabled flag) so the double-opt-in gate is enforced by
    # the query itself and can't drift if some future path forgets to recompute.
    _HAS_CONFIRMED_RECIPIENT = (
        "EXISTS (SELECT 1 FROM workspace_subscription_recipients r "
        "WHERE r.opportunity_id = workspace_subscriptions.opportunity_id "
        "AND r.enabled=1 AND r.confirmed=1)")

    def due_subscriptions(self, limit=25):
        """Enabled subscriptions with a confirmed recipient whose next_run_at
        has arrived (or is unset), oldest-due first. Read-only: the tick must
        still claim_due() each one before running it — the claim is the
        idempotency lock, not this read. A chat with zero confirmed recipients
        is never even selected here (query-level double-opt-in enforcement)."""
        now = _now()
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT opportunity_id, owner_user_id, cadence_hours, next_run_at,
                           last_notified_version
                   FROM workspace_subscriptions
                   WHERE enabled=1 AND (next_run_at IS NULL OR next_run_at <= ?)
                         AND {self._HAS_CONFIRMED_RECIPIENT}
                   ORDER BY (next_run_at IS NULL) DESC, next_run_at ASC LIMIT ?""",
                (now, limit)).fetchall()
        return [dict(r) for r in rows]

    def claim_due(self, opportunity_id):
        """Atomically claim a due subscription and advance next_run_at by one
        cadence. Returns the claimed subscription, or None when it is no longer
        enabled/due — a concurrent or double-fired tick already took it. This
        conditional advance IS the at-least-once idempotency guard: the second
        writer's UPDATE re-checks due-ness against the just-advanced value and
        matches zero rows."""
        _validate_opp_ref(opportunity_id)
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                f"""SELECT owner_user_id, cadence_hours, last_notified_version
                   FROM workspace_subscriptions
                   WHERE opportunity_id=? AND enabled=1
                         AND (next_run_at IS NULL OR next_run_at <= ?)
                         AND {self._HAS_CONFIRMED_RECIPIENT}""",
                (opportunity_id, now)).fetchone()
            if row is None:
                return None
            cur = conn.execute(
                f"""UPDATE workspace_subscriptions SET next_run_at=?, updated_at=?
                   WHERE opportunity_id=? AND enabled=1
                         AND (next_run_at IS NULL OR next_run_at <= ?)
                         AND {self._HAS_CONFIRMED_RECIPIENT}""",
                (_shift_hours(now, row["cadence_hours"]), now, opportunity_id, now))
            if cur.rowcount != 1:
                return None
        return {"opportunity_id": opportunity_id, "owner_user_id": row["owner_user_id"],
                "cadence_hours": row["cadence_hours"],
                "last_notified_version": row["last_notified_version"]}

    def record_run_result(self, opportunity_id, outcome, ran_at=None,
                          last_notified_version=None):
        """Record a scheduled run's honest outcome on the subscription.
        `last_run_at` advances ONLY when a build actually ran (`ran_at` given) —
        a skipped or never-attempted run is never presented as having run."""
        _validate_opp_ref(opportunity_id)
        now = _now()
        sets, params = ["last_outcome=?", "updated_at=?"], [str(outcome)[:OUTCOME_MAX], now]
        if ran_at is not None:
            sets.append("last_run_at=?")
            params.append(ran_at)
        if last_notified_version is not None:
            sets.append("last_notified_version=?")
            params.append(int(last_notified_version))
        params.append(opportunity_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE workspace_subscriptions SET {', '.join(sets)} "
                         "WHERE opportunity_id=?", params)
        return self.get_subscription(opportunity_id)


def _new_wsub_id():
    return f"WSUB-{uuid.uuid4().hex[:12]}"


def compare_versions(older, newer):
    """Deterministic version diff — the seed for R6 change notifications.
    Pure data comparison: composite delta from the stored engine outputs and
    claim/gap set differences. Nothing is interpreted or scored here."""
    def _composite(v):
        score = v.get("preliminary_score") or {}
        return score.get("composite")

    old_claims = set(older.get("claim_ids") or [])
    new_claims = set(newer.get("claim_ids") or [])
    old_gaps = set(older.get("gaps") or [])
    new_gaps = set(newer.get("gaps") or [])
    old_c, new_c = _composite(older), _composite(newer)
    return {
        "older_id": older.get("id"), "newer_id": newer.get("id"),
        "composite_before": old_c, "composite_after": new_c,
        "composite_delta": (round(new_c - old_c, 2)
                            if isinstance(old_c, (int, float)) and isinstance(new_c, (int, float))
                            else None),
        "new_claim_ids": sorted(new_claims - old_claims),
        "removed_claim_ids": sorted(old_claims - new_claims),
        "new_gaps": sorted(new_gaps - old_gaps),
        "resolved_gaps": sorted(old_gaps - new_gaps),
    }
