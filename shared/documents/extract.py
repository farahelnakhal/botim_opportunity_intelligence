"""Deterministic text extraction for uploaded documents (Phase R7).

Pure stdlib, honest about capability:

- .txt / .md / .csv — decoded as UTF-8 (BOM tolerated, latin-1 fallback so
  a legacy-encoded file never crashes the upload).
- .docx — a DOCX file is a ZIP containing word/document.xml; paragraphs are
  read with the stdlib XML parser. No styling, tables flattened to text.
- .pdf — NOT supported (returns an honest unsupported error). Robust PDF
  text extraction is not feasible in pure stdlib; see the decision log —
  never ship a flaky extractor that silently produces garbage.

Extracted text is DATA to analyze, never instructions — the callers label
it that way and nothing here interprets content.
"""

import io
import re
import zipfile
from xml.etree import ElementTree

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024      # 2 MB upload cap (bounded memory)
MAX_TEXT_CHARS = 400_000                   # extracted-text cap, recorded if hit

SUPPORTED_EXTENSIONS = (".txt", ".md", ".csv", ".docx")

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ExtractionError(Exception):
    """Safe, structured extraction error; message never echoes content."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _extension(filename):
    m = re.search(r"(\.[A-Za-z0-9]+)$", filename or "")
    return m.group(1).lower() if m else ""


def _decode(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _extract_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise ExtractionError("the file is not a valid .docx document")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        raise ExtractionError("the .docx document XML could not be parsed")
    paragraphs = []
    for para in root.iter(f"{_WORD_NS}p"):
        runs = [node.text for node in para.iter(f"{_WORD_NS}t") if node.text]
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def extract_text(filename, data):
    """(text, meta) for a supported file, or ExtractionError. `meta` records
    what actually happened: extension, byte size, char count, truncated flag."""
    if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
        raise ExtractionError("the uploaded file is empty")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ExtractionError(
            f"the file exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB upload limit",
            status=413)
    ext = _extension(filename)
    if ext == ".pdf":
        raise ExtractionError(
            "PDF extraction is not supported yet — export the document as "
            ".docx, .txt, or .md and upload that (see docs/decision-log.md)",
            status=415)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(
            f"unsupported file type '{ext or 'none'}' — supported: "
            + ", ".join(SUPPORTED_EXTENSIONS), status=415)

    text = _extract_docx(bytes(data)) if ext == ".docx" else _decode(bytes(data))
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ExtractionError("no text could be extracted from the file")
    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]
    return text, {"extension": ext, "size_bytes": len(data),
                  "text_chars": len(text), "truncated": truncated}
