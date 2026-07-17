"""Phase R7 — document extraction, chunking, retrieval, store, and the
workspace-builder integration. Offline; a real minimal .docx is built
in-test with the stdlib zip writer."""

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from shared.documents import (DocumentStore, DocumentStoreError,  # noqa: E402
                              ExtractionError, chunk_text, extract_text,
                              search_chunks)
from shared.documents.extract import MAX_DOCUMENT_BYTES  # noqa: E402
from shared.research import ResearchStore  # noqa: E402
from shared.workspace import WorkspaceStore, build_workspace  # noqa: E402


def make_docx(paragraphs):
    """A minimal but genuine .docx (zip + word/document.xml)."""
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?><w:document {ns}><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
        z.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


class Extraction(unittest.TestCase):
    def test_plain_text_and_markdown_roundtrip(self):
        text, meta = extract_text("notes.txt", "Settlement takes 4 days.\n".encode())
        self.assertEqual(text, "Settlement takes 4 days.")
        self.assertEqual(meta["extension"], ".txt")
        self.assertFalse(meta["truncated"])
        text, _ = extract_text("brief.md", b"# Heading\n\nBody paragraph.")
        self.assertIn("Body paragraph.", text)

    def test_docx_paragraphs_are_extracted(self):
        data = make_docx(["First paragraph about payroll.",
                          "Second paragraph: settlement takes 4 days."])
        text, meta = extract_text("report.docx", data)
        self.assertIn("First paragraph about payroll.", text)
        self.assertIn("settlement takes 4 days", text)
        self.assertEqual(meta["extension"], ".docx")

    def test_pdf_is_an_honest_unsupported_error(self):
        with self.assertRaises(ExtractionError) as cm:
            extract_text("deck.pdf", b"%PDF-1.4 ...")
        self.assertEqual(cm.exception.status, 415)
        self.assertIn("not supported yet", str(cm.exception))

    def test_unknown_type_empty_and_oversize_rejected(self):
        with self.assertRaises(ExtractionError):
            extract_text("image.png", b"\x89PNG")
        with self.assertRaises(ExtractionError):
            extract_text("empty.txt", b"")
        with self.assertRaises(ExtractionError) as cm:
            extract_text("big.txt", b"x" * (MAX_DOCUMENT_BYTES + 1))
        self.assertEqual(cm.exception.status, 413)

    def test_corrupt_docx_is_a_clear_error_not_a_crash(self):
        with self.assertRaises(ExtractionError) as cm:
            extract_text("broken.docx", b"not a zip at all")
        self.assertIn("not a valid .docx", str(cm.exception))

    def test_legacy_encoding_never_crashes(self):
        text, _ = extract_text("legacy.txt", "café à 5".encode("latin-1"))
        self.assertTrue(text)   # decoded via fallback, never an exception


class ChunkingAndRetrieval(unittest.TestCase):
    def test_chunks_split_on_paragraphs_and_are_bounded(self):
        text = "\n\n".join(f"Paragraph {i} " + "word " * 100 for i in range(6))
        chunks = chunk_text(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 2000 for c in chunks))
        # deterministic: same input, same chunks
        self.assertEqual(chunks, chunk_text(text))

    def test_search_ranks_by_keyword_overlap_and_is_honest_when_empty(self):
        chunks = ["Payroll settlement takes four days on average.",
                  "The office cafeteria menu changed."]
        hits = search_chunks("how slow is payroll settlement?", chunks)
        self.assertEqual(hits[0][2], chunks[0])
        self.assertEqual(search_chunks("zebra quantum", chunks), [])
        self.assertEqual(search_chunks("", chunks), [])


class StoreLifecycle(unittest.TestCase):
    def setUp(self):
        self.store = DocumentStore(Path(tempfile.mkdtemp()) / "documents.db")

    def _add(self, opp="UOPP-aaaaaaaaaaa1", owner=None, filename="a.txt"):
        text, meta = extract_text(filename, b"Settlement takes 4 days on average.")
        return self.store.add_document(opp, filename, meta, chunk_text(text),
                                       owner_user_id=owner)

    def test_add_list_get_chunks(self):
        doc = self._add()
        self.assertTrue(doc["id"].startswith("DOC-"))
        self.assertEqual(doc["status"], "extracted")
        self.assertEqual(doc["chunk_count"], 1)
        listing = self.store.list_documents("UOPP-aaaaaaaaaaa1")
        self.assertEqual([d["id"] for d in listing], [doc["id"]])
        self.assertIn("4 days", self.store.get_chunks(doc["id"])[0][1])

    def test_deletion_removes_document_and_chunks(self):
        import sqlite3
        doc = self._add()
        self.store.delete_document(doc["id"])
        with self.assertRaises(DocumentStoreError):
            self.store.get_document(doc["id"])
        with sqlite3.connect(self.store.db_path) as conn:
            left = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
        self.assertEqual(left, 0)   # a real deletion path, not a soft flag

    def test_ownership_filter_matches_platform_policy(self):
        mine = self._add(owner="USER-aaaaaaaaaaa1", filename="mine.txt")
        self._add(owner="USER-bbbbbbbbbbb2", filename="theirs.txt")
        legacy = self._add(owner=None, filename="legacy.txt")
        visible = self.store.list_documents("UOPP-aaaaaaaaaaa1",
                                            visible_to="USER-aaaaaaaaaaa1")
        self.assertEqual({d["id"] for d in visible}, {mine["id"], legacy["id"]})


class BuilderIntegration(unittest.TestCase):
    def test_workspace_build_quotes_matching_document_excerpts(self):
        tmp = Path(tempfile.mkdtemp())
        ws, rs = WorkspaceStore(tmp / "w.db"), ResearchStore(tmp / "r.db")
        docs = DocumentStore(tmp / "d.db")
        opp = {"id": "UOPP-aaaaaaaaaaa1", "title": "Cross-border payroll tool",
               "target_segment": "regional SMEs"}
        text, meta = extract_text("internal-study.txt",
                                  b"Internal study: payroll settlement takes 4 days "
                                  b"on average for regional SMEs.")
        docs.add_document(opp["id"], "internal-study.txt", meta, chunk_text(text))
        v = build_workspace(ws, rs, opp, trigger="first_analysis",
                            question="how slow is payroll settlement?",
                            kb_records={}, document_store=docs)
        self.assertEqual(v["status"], "complete")
        self.assertEqual(len(v["document_evidence"]), 1)
        d = v["document_evidence"][0]
        self.assertEqual(d["filename"], "internal-study.txt")
        self.assertIn("settlement takes 4 days", d["excerpt"])
        self.assertEqual(v["provenance"]["document_ids"], [d["document_id"]])

    def test_no_documents_is_an_honest_gap(self):
        tmp = Path(tempfile.mkdtemp())
        ws, rs = WorkspaceStore(tmp / "w.db"), ResearchStore(tmp / "r.db")
        docs = DocumentStore(tmp / "d.db")
        v = build_workspace(ws, rs, {"id": "UOPP-aaaaaaaaaaa1", "title": "T"},
                            trigger="first_analysis", kb_records={},
                            document_store=docs)
        self.assertIn("no uploaded documents are attached",
                      " | ".join(v["gaps"]))
        self.assertEqual(v["document_evidence"], [])

    def test_workspace_v2_migration_is_idempotent(self):
        import sqlite3
        db = Path(tempfile.mkdtemp()) / "w.db"
        WorkspaceStore(db)
        with sqlite3.connect(db) as conn:  # stamp back without dropping columns
            conn.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
        ws = WorkspaceStore(db)            # must not crash on duplicate ALTER
        v = ws.create_version("UOPP-aaaaaaaaaaa1", "first_analysis")
        v = ws.complete_version(v["id"], document_evidence=[{"document_id": "DOC-x"}])
        self.assertEqual(v["document_evidence"][0]["document_id"], "DOC-x")


if __name__ == "__main__":
    unittest.main()
