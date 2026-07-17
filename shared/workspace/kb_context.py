"""Bounded, read-only KB context retrieval for workspace builds (PR4).

Finds committed customer-evidence records related to an opportunity/question
by deterministic keyword overlap — the same discipline as the copilot's
search_product_knowledge: real records only, a transparent match score, no
model involvement, no fabrication. The knowledge base is read via the
existing opportunity_engine.evidence parser and never written.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_TOOLS = REPO / "opportunity-intelligence" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

MAX_RESULTS = 8
_WORD = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS = frozenset(
    "the and for with that this from are was were has have had not you your "
    "our their its can will would should could about into over under between "
    "what which when where how why who whom does doing done".split())

# record fields worth matching against (parsed by opportunity_engine.evidence)
_MATCH_FIELDS = ("title", "segment", "pain_category", "workaround",
                 "financial_impact", "excerpt")


def _tokens(text):
    return {w for w in _WORD.findall((text or "").lower())} - _STOPWORDS


def load_kb_records(kb_dir=None):
    """Default records loader — committed customer-evidence records.
    Injectable in tests and in deployments without the KB checkout."""
    from opportunity_engine import evidence
    directory = Path(kb_dir) if kb_dir else REPO / "knowledge-base" / "customer-evidence"
    return evidence.load_records(directory)


def search_kb_context(query_text, records=None, max_results=MAX_RESULTS):
    """[{id, title, segment, evidence_confidence, status, match}] — records
    ranked by keyword overlap with the query text. An empty result is an
    honest 'no related internal evidence' outcome, never padded."""
    if records is None:
        records = load_kb_records()
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    scored = []
    for ev_id, rec in records.items():
        record_tokens = set()
        for field in _MATCH_FIELDS:
            record_tokens |= _tokens(rec.get(field))
        overlap = len(query_tokens & record_tokens)
        if overlap:
            scored.append((overlap, ev_id, rec))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"id": ev_id, "title": rec.get("title", ""),
             "segment": rec.get("segment"), "status": rec.get("status"),
             "evidence_confidence": rec.get("evidence_confidence"),
             "match": overlap}
            for overlap, ev_id, rec in scored[:max(1, int(max_results))]]
