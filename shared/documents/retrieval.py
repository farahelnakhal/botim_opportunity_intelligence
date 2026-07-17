"""Chunking + deterministic lexical retrieval over document text (Phase R7).

The "scoped RAG" seam for unstructured documents (decision-log: hybrid
retrieval — structured records go through tools/IDs, documents through
chunk retrieval). Retrieval here is TRANSPARENT keyword-overlap scoring —
the same discipline as kb_context / search_product_knowledge: every result
carries its match score, results are reproducible offline, and nothing is
generated. Vector embeddings can replace the scorer behind this same
function signature later without touching callers.
"""

import re

CHUNK_TARGET_CHARS = 1200
CHUNK_MAX_CHARS = 2000
MAX_RESULTS = 6

_WORD = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS = frozenset(
    "the and for with that this from are was were has have had not you your "
    "our their its can will would should could about into over under between "
    "what which when where how why who whom does doing done all any each".split())


def _tokens(text):
    return {w for w in _WORD.findall((text or "").lower())} - _STOPWORDS


def chunk_text(text):
    """Split extracted text into bounded chunks on paragraph boundaries
    (hard-split only when a single paragraph exceeds the max). Deterministic:
    same text, same chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        while len(para) > CHUNK_MAX_CHARS:          # oversize paragraph: hard split
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:CHUNK_MAX_CHARS])
            para = para[CHUNK_MAX_CHARS:].strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > CHUNK_TARGET_CHARS:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


def search_chunks(query_text, chunks, max_results=MAX_RESULTS):
    """[(score, index, chunk_text)] ranked by keyword overlap with the query.
    `chunks` is a list of (index, text) pairs or plain strings. Empty result
    = honestly nothing matched; never padded."""
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    scored = []
    for i, chunk in enumerate(chunks):
        idx, text = chunk if isinstance(chunk, tuple) else (i, chunk)
        overlap = len(query_tokens & _tokens(text))
        if overlap:
            scored.append((overlap, idx, text))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[:max(1, int(max_results))]
