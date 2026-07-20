"""Runtime persistence for user accounts and sessions (Phase R8a).

Design (see docs/decision-log.md, Phase R8a entry):

- Email + password accounts with PBKDF2-HMAC-SHA256 hashing (pure stdlib —
  no external auth provider, no new dependencies). Per-user random salt,
  600k iterations, constant-time comparison. The stored format is
  `pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>` so iterations can be
  raised later without breaking existing accounts.
- Opaque session tokens (256-bit, `secrets`) delivered as an HttpOnly
  cookie; only the SHA-256 **hash** of a token is stored, so a leaked
  database cannot be replayed as sessions.
- Enforcement is the server's job (BOTIM_AUTH_MODE) — this module only
  stores and verifies. Password reset requires email infrastructure (R6)
  and does not exist yet; that is stated, not worked around.
- Login attempts are rate-limited in-process (single-process threading
  server): after LOCKOUT_THRESHOLD consecutive failures for an email, that
  email is locked out for LOCKOUT_WINDOW_S seconds. Documented limitation:
  the counter resets on process restart.
- Storage: runtime SQLite (gitignored) at AUTH_DB_PATH, default
  `runtime/auth.db`. IDs use the USER- namespace (`USER-<12 hex>`).
"""

import datetime
import hashlib
import os
import re
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path

SCHEMA_VERSION = 2

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO / "runtime" / "auth.db"

USER_RE = re.compile(r"^USER-[0-9a-f]{12}$")
# deliberately simple: something@something.tld — real verification needs
# email infrastructure (R6); this only rejects obvious garbage
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PBKDF2_ITERATIONS = 600_000
PASSWORD_MIN = 10
PASSWORD_MAX = 200
EMAIL_MAX = 254
NAME_MAX = 120

SESSION_TTL_DAYS = 30
LOCKOUT_THRESHOLD = 8
LOCKOUT_WINDOW_S = 15 * 60


class AuthError(Exception):
    """Safe, structured auth error — `status` maps to the HTTP status; the
    message never contains hashes, tokens, SQL, or paths."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now_dt():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_password(password, iterations=PBKDF2_ITERATIONS):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, iterations, salt, expected = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     bytes.fromhex(salt), int(iterations))
        return secrets.compare_digest(digest.hex(), expected)
    except (ValueError, AttributeError):
        return False


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthStore:
    """SQLite-backed accounts + sessions. One short-lived connection per
    operation; every write is a transaction."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path
                            or os.environ.get("AUTH_DB_PATH")
                            or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._attempts = {}          # email -> (consecutive_failures, first_failure_ts)
        self._attempts_lock = threading.Lock()
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
                raise AuthError("auth database is newer than this code", status=500)
            if version < 1:
                conn.execute("""CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    created_at TEXT NOT NULL)""")
                conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL)""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user "
                             "ON sessions(user_id)")
            if version < 2:
                # Phase R8b — per-user quota accounting for expensive actions
                # (chat calls, research executions, workspace refreshes, ...).
                # One row per performed action; counted over a sliding window
                # and pruned opportunistically. Survives restarts by design.
                conn.execute("""CREATE TABLE IF NOT EXISTS quota_events (
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    at TEXT NOT NULL)""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_quota_user_action "
                             "ON quota_events(user_id, action, at)")
            conn.execute("INSERT OR REPLACE INTO meta (key, value) "
                         "VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    @staticmethod
    def _user_dict(row):
        return {"id": row["id"], "email": row["email"],
                "display_name": row["display_name"], "created_at": row["created_at"]}

    # -- accounts ------------------------------------------------------------ #

    @staticmethod
    def _normalize_email(email):
        if not isinstance(email, str) or len(email) > EMAIL_MAX \
                or not EMAIL_RE.match(email.strip()):
            raise AuthError("a valid email address is required")
        return email.strip().lower()

    def register(self, email, password, display_name=None):
        email = self._normalize_email(email)
        if not isinstance(password, str) or len(password) < PASSWORD_MIN:
            raise AuthError(f"password must be at least {PASSWORD_MIN} characters")
        if len(password) > PASSWORD_MAX:
            raise AuthError("password is too long")
        if display_name is not None:
            if not isinstance(display_name, str) or len(display_name) > NAME_MAX:
                raise AuthError("display_name must be a short string")
            display_name = display_name.strip() or None
        user_id = f"USER-{uuid.uuid4().hex[:12]}"
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, display_name, created_at) "
                    "VALUES (?,?,?,?,?)",
                    (user_id, email, hash_password(password), display_name, _iso(_now_dt())))
        except sqlite3.IntegrityError:
            raise AuthError("an account with this email already exists", status=409)
        return self.get_user(user_id)

    def get_user(self, user_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise AuthError("user not found", status=404)
        return self._user_dict(row)

    # -- login + lockout ------------------------------------------------------ #

    def _lockout_check(self, email):
        with self._attempts_lock:
            count, first_ts = self._attempts.get(email, (0, 0.0))
            now = _now_dt().timestamp()
            if now - first_ts > LOCKOUT_WINDOW_S:
                self._attempts.pop(email, None)
                return
            if count >= LOCKOUT_THRESHOLD:
                raise AuthError("too many failed sign-in attempts — try again later",
                                status=429)

    def _record_attempt(self, email, ok):
        with self._attempts_lock:
            if ok:
                self._attempts.pop(email, None)
                return
            count, first_ts = self._attempts.get(email, (0, 0.0))
            now = _now_dt().timestamp()
            if now - first_ts > LOCKOUT_WINDOW_S:
                count, first_ts = 0, now
            self._attempts[email] = (count + 1, first_ts or now)

    def login(self, email, password):
        """Verify credentials and open a session. Returns (user, raw_token).
        The failure message never reveals whether the email exists."""
        email = self._normalize_email(email)
        self._lockout_check(email)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        ok = bool(row) and verify_password(password if isinstance(password, str) else "",
                                           row["password_hash"])
        self._record_attempt(email, ok)
        if not ok:
            raise AuthError("invalid email or password", status=401)
        token = secrets.token_urlsafe(32)
        now = _now_dt()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) "
                "VALUES (?,?,?,?)",
                (_token_hash(token), row["id"], _iso(now),
                 _iso(now + datetime.timedelta(days=SESSION_TTL_DAYS))))
        return self._user_dict(row), token

    # -- sessions ------------------------------------------------------------- #

    def session_user(self, token):
        """The user for a session token, or None (unknown/expired). Expired
        sessions are deleted lazily on lookup."""
        if not isinstance(token, str) or not token:
            return None
        th = _token_hash(token)
        with self._connect() as conn:
            row = conn.execute(
                """SELECT s.expires_at, u.* FROM sessions s
                   JOIN users u ON u.id = s.user_id WHERE s.token_hash=?""",
                (th,)).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= _iso(_now_dt()):
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (th,))
                return None
        return self._user_dict(row)

    # -- per-user quotas (Phase R8b) ------------------------------------------ #

    def check_quota(self, user_id, action, limit, window_s=86400):
        """Count-then-record one action for a user. Raises AuthError 429 when
        the user already performed `limit` actions inside the window; on
        success the action is recorded and counts against future calls.
        Old rows are pruned opportunistically."""
        if not isinstance(user_id, str) or not USER_RE.match(user_id):
            raise AuthError("invalid user id")
        now = _now_dt()
        window_start = _iso(now - datetime.timedelta(seconds=window_s))
        with self._connect() as conn:
            conn.execute("DELETE FROM quota_events WHERE at < ?",
                         (_iso(now - datetime.timedelta(seconds=window_s * 2)),))
            used = conn.execute(
                "SELECT COUNT(*) AS n FROM quota_events "
                "WHERE user_id=? AND action=? AND at >= ?",
                (user_id, action, window_start)).fetchone()["n"]
            if used >= max(1, int(limit)):
                raise AuthError(
                    f"daily limit reached for {action.replace('_', ' ')} "
                    f"({limit} per day) — try again later", status=429)
            conn.execute("INSERT INTO quota_events (user_id, action, at) VALUES (?,?,?)",
                         (user_id, action, _iso(now)))
        return {"action": action, "used": used + 1, "limit": int(limit)}

    def quota_status(self, user_id, action, limit, window_s=86400):
        """Read-only quota view (used for UI indicators): how many of `action`
        the user performed inside the window, the limit, and how many remain —
        WITHOUT recording anything (unlike check_quota, which counts-and-records)."""
        if not isinstance(user_id, str) or not USER_RE.match(user_id):
            raise AuthError("invalid user id")
        now = _now_dt()
        window_start = _iso(now - datetime.timedelta(seconds=window_s))
        with self._connect() as conn:
            used = conn.execute(
                "SELECT COUNT(*) AS n FROM quota_events "
                "WHERE user_id=? AND action=? AND at >= ?",
                (user_id, action, window_start)).fetchone()["n"]
        lim = max(1, int(limit))
        return {"action": action, "used": used, "limit": lim,
                "remaining": max(0, lim - used)}

    def logout(self, token):
        if not isinstance(token, str) or not token:
            return False
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE token_hash=?",
                               (_token_hash(token),))
        return cur.rowcount > 0
