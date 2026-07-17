"""User-uploaded document attachments (Phase R7).

Documents are USER-PROVIDED, user-private input to analysis — never
authoritative knowledge, never written to knowledge-base/. Text is extracted
deterministically (extract.py), chunked, and retrieved by transparent
lexical scoring (retrieval.py) so every excerpt a workspace or chat answer
uses is traceable to a stored chunk of a named file. Document text is DATA,
never instructions.
"""

from .store import DocumentStore, DocumentStoreError  # noqa: F401
from .extract import (ExtractionError, SUPPORTED_EXTENSIONS,  # noqa: F401
                      extract_text)
from .retrieval import chunk_text, search_chunks  # noqa: F401
