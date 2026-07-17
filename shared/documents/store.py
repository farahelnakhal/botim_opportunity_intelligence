"""Runtime persistence for uploaded documents and their chunks (Phase R7).

- Documents are user-private input: runtime SQLite at DOCUMENTS_DB_PATH
  (default `runtime/documents.db`, gitignored), never the knowledge base.
- A document belongs to an opportunity (OPP-/UOPP-) and, under required-auth
  mode, to its uploader (owner_user_id; NULL = legacy shared, same policy as
  every other store).
- Extracted text lives as ordered chunks so retrieval can quote a bounded,
  traceable excerpt (document id + chunk sequence) instead of a whole file.
- Deletion is REAL: deleting a document removes its row and every chunk.
  Workspace versions that quoted it keep their recorded excerpts (a snapshot
  is a snapshot) but the source document is gone.
- IDs use the DOC- namespace (`DOC-<12 hex>`).
"""

import datetime
import os
import re
import sqlite3
import uuid
from pathlib import Path

SCHEMA_VERSION = 1

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO / "runtime" / "documents.db"

DOC_RE = re.compile(r"^DOC-[0-9a-f]{12}$")
OPP_REF_RE = re.compile(r"^(OPP-\d{3}|UOPP-[0-9a-f]{12})$")

FILENAME_MAX = 200
STATUSES = ("extracted", "failed")


class DocumentStoreError(Exception):
    """Safe, structured store error — `status` maps to the HTTP status; the
    message never contains SQL, paths, or file content."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DocumentStore:
    """SQLite-backed store. One short-lived connection per operation; every
    write is a transaction."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path
                            or os.environ.get("DOCUMENTS_DB_PATH")
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
                raise DocumentStoreError("documents database is newer than this code",
                                         status=500)
            if version < 1:
                conn.execute("""CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    owner_user_id TEXT,
                    filename TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    text_chars INTEGER NOT NULL,
                    truncated INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('extracted','failed')),
                    error TEXT,
                    created_at TEXT NOT NULL)""")
                conn.execute("""CREATE TABLE IF NOT EXISTS document_chunks (
                    document_id TEXT NOT NULL
                        REFERENCES documents(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    PRIMARY KEY (document_id, seq))""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_opp "
                             "ON documents(opportunity_id)")
            conn.execute("INSERT OR REPLACE INTO meta (key, value) "
                         "VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))

    @staticmethod
    def _doc_dict(row):
        d = dict(row)
        d["truncated"] = bool(d["truncated"])
        return d

    # -- writes --------------------------------------------------------------- #

    def add_document(self, opportunity_id, filename, meta, chunks,
                     owner_user_id=None):
        """Persist an EXTRACTED document with its ordered chunks. Extraction
        happens before this call (extract.py); a failed extraction is never
        stored — the upload fails honestly instead."""
        if not OPP_REF_RE.match(str(opportunity_id or "")):
            raise DocumentStoreError("invalid opportunity reference")
        if not isinstance(filename, str) or not filename.strip():
            raise DocumentStoreError("'filename' is required")
        if len(filename) > FILENAME_MAX:
            raise DocumentStoreError(f"'filename' exceeds {FILENAME_MAX} characters")
        if not chunks:
            raise DocumentStoreError("the document produced no text chunks")
        doc_id = f"DOC-{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO documents
                   (id, opportunity_id, owner_user_id, filename, extension,
                    size_bytes, text_chars, truncated, chunk_count, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,'extracted',?)""",
                (doc_id, opportunity_id, owner_user_id, filename.strip(),
                 meta.get("extension", ""), int(meta.get("size_bytes", 0)),
                 int(meta.get("text_chars", 0)), int(bool(meta.get("truncated"))),
                 len(chunks), _now()))
            conn.executemany(
                "INSERT INTO document_chunks (document_id, seq, text) VALUES (?,?,?)",
                [(doc_id, i, text) for i, text in enumerate(chunks)])
        return self.get_document(doc_id)

    def delete_document(self, doc_id):
        """Permanent deletion of the document AND all its chunks."""
        self.get_document(doc_id)  # 404 for unknown
        with self._connect() as conn:
            conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        return {"deleted": True, "id": doc_id}

    # -- reads ---------------------------------------------------------------- #

    def get_document(self, doc_id):
        if not isinstance(doc_id, str) or not DOC_RE.match(doc_id):
            raise DocumentStoreError("invalid document id")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if row is None:
            raise DocumentStoreError("document not found", status=404)
        return self._doc_dict(row)

    def list_documents(self, opportunity_id, visible_to=None):
        """Documents for an opportunity, newest first. `visible_to` (a USER-
        id) applies the standard ownership filter: own rows + legacy NULL."""
        if not OPP_REF_RE.match(str(opportunity_id or "")):
            raise DocumentStoreError("invalid opportunity reference")
        clauses, params = ["opportunity_id=?"], [opportunity_id]
        if visible_to is not None:
            clauses.append("(owner_user_id IS NULL OR owner_user_id=?)")
            params.append(visible_to)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM documents WHERE {' AND '.join(clauses)} "
                "ORDER BY created_at DESC, id", params).fetchall()
        return [self._doc_dict(r) for r in rows]

    def get_chunks(self, doc_id):
        self.get_document(doc_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, text FROM document_chunks WHERE document_id=? ORDER BY seq",
                (doc_id,)).fetchall()
        return [(r["seq"], r["text"]) for r in rows]

    def chunks_for_opportunity(self, opportunity_id, visible_to=None):
        """[(document, seq, text)] across the opportunity's extracted
        documents — the retrieval corpus for a workspace build."""
        out = []
        for doc in self.list_documents(opportunity_id, visible_to=visible_to):
            if doc["status"] != "extracted":
                continue
            for seq, text in self.get_chunks(doc["id"]):
                out.append((doc, seq, text))
        return out
