"""Read-only parser for Workstream A customer-evidence records.

Parses knowledge-base/customer-evidence/records/YYYY-Wnn.md files written in
the customer-intelligence/templates/customer-evidence.md format:

    ## EV-YYYY-Wnn-nnn — <title>
    **Status:** active | needs-more-evidence | superseded-by:EV-… | resolved
    ...
    | Customer segment | SEG-… |
    | Evidence confidence | High — why |
    ...
    Frequency ................ 4   (10-axis score block)

This module never writes to Workstream A folders. It exists so scorecards can
cite EV ids and have the citation mechanically checked.
"""

import re
from pathlib import Path

EV_ID_RE = re.compile(r"^EV-\d{4}-W\d{2}-\d{3}$")
HEADER_RE = re.compile(r"^##\s+(EV-\d{4}-W\d{2}-\d{3})\s*[—-]+\s*(.+?)\s*$")
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(\S+)")
# provenance dates on the status line: **Created:** 2026-07-10 · **Last verified:** 2026-07-10
CREATED_RE = re.compile(r"\*\*Created:\*\*\s*(\d{4}-\d{2}-\d{2})")
LAST_VERIFIED_RE = re.compile(r"\*\*Last verified:\*\*\s*(\d{4}-\d{2}-\d{2})")
TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$")
SCORE_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)\s*\.{2,}\s*([1-5])\s*$")
SRC_ID_RE = re.compile(r"\bSRC-\d{3}\b")
ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

SCORE_AXES = (
    "frequency",
    "severity",
    "financial cost",
    "urgency",
    "dissatisfaction",
    "workaround cost",
    "switching intent",
    "willingness to pay",
    "botim relevance",
    "evidence strength",
)

# table fields worth surfacing to Workstream B
FIELDS = {
    "customer segment": "segment",
    "pain category": "pain_category",
    "evidence confidence": "evidence_confidence",
    "current workaround": "workaround",
    "workaround cost": "workaround_cost",
    "financial impact": "financial_impact",
    "duplicate status": "duplicate_status",
    "contradictory evidence": "contradictory_evidence",
    # provenance fields (Integration Phase 4 — previously discarded)
    "source": "source_text",
    "date of evidence": "date_of_evidence",
    "access label": "access_label",
    "language": "language",
    "exact customer wording": "excerpt",
}


def parse_file(path):
    """Parse one weekly records file. Returns list of record dicts."""
    text = Path(path).read_text(encoding="utf-8")
    records = []
    current = None
    for line in text.splitlines():
        m = HEADER_RE.match(line)
        if m:
            current = {
                "id": m.group(1),
                "title": m.group(2),
                "file": str(path),
                "status": None,
                "scores": {},
                # provenance (Integration Phase 4) — None means "not recorded",
                # never a fabricated value
                "created_at": None,
                "last_verified_at": None,
            }
            records.append(current)
            continue
        if current is None:
            continue
        m = STATUS_RE.match(line.strip())
        if m and current["status"] is None:
            current["status"] = m.group(1)
            cm = CREATED_RE.search(line)
            if cm:
                current["created_at"] = cm.group(1)
            vm = LAST_VERIFIED_RE.search(line)
            if vm:
                current["last_verified_at"] = vm.group(1)
            continue
        m = TABLE_ROW_RE.match(line)
        if m:
            key = m.group(1).strip().lower()
            if key in FIELDS and FIELDS[key] not in current:
                current[FIELDS[key]] = m.group(2).strip()
            continue
        m = SCORE_LINE_RE.match(line)
        if m:
            axis = m.group(1).strip().lower()
            # template prints "Dissatisfaction"; framework calls it
            # "dissatisfaction with current solutions" — normalise to the short form
            if axis in SCORE_AXES and axis not in current["scores"]:
                current["scores"][axis] = int(m.group(2))
    for rec in records:
        _finalize_provenance(rec)
    return records


def _finalize_provenance(rec):
    """Derive structured provenance from the raw table fields, in place.

    Only ever derives from text already in the record: SRC ids referenced in
    the Source cell, a YYYY-MM-DD prefix of the date-of-evidence cell, and
    the quotation marker stripped from the excerpt. Absent data stays None.
    """
    rec["source_ids"] = SRC_ID_RE.findall(rec.get("source_text") or "")
    doe = rec.get("date_of_evidence")
    m = ISO_DATE_PREFIX_RE.match(doe.strip()) if isinstance(doe, str) else None
    rec["publication_date"] = m.group(1) if m else None
    excerpt = rec.get("excerpt")
    if isinstance(excerpt, str):
        rec["excerpt"] = excerpt.lstrip("> ").strip() or None


# --------------------------------------------------------------------------- #
# Source log (knowledge-base/customer-evidence/source-log.md) — Phase 4
# --------------------------------------------------------------------------- #
SOURCE_LOG_ID_RE = re.compile(r"^SRC-\d{3}$")
_PAREN_RE = re.compile(r"\(([^)]*)\)")


def _url_candidate_from_name(name):
    """The first parenthesized token of a source-log name that looks like a
    bare domain path ("trustpilot.com/review/x"). Raw text only — safety and
    https:// normalization are applied by shared/source_urls.py at the API
    layer, never here."""
    for group in _PAREN_RE.findall(name or ""):
        for token in re.split(r"[,;]\s*", group):
            token = token.strip()
            if token and " " not in token and "." in token.split("/")[0]:
                return token
    return None


def load_source_log(evidence_dir):
    """Parse source-log.md into {SRC-id: entry}. Read-only; {} if absent.

    Entry fields: source_id, added, title (the stored name), publisher (name
    before the first em-dash), url_text (raw parenthesized domain path or
    None), type, language, access, last_checked.
    """
    path = Path(evidence_dir) / "source-log.md"
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 10 or not SOURCE_LOG_ID_RE.match(cells[0]):
            continue
        name = cells[2]
        title = _PAREN_RE.sub("", name).strip().rstrip("—- ").strip()
        out[cells[0]] = {
            "source_id": cells[0],
            "added": cells[1] or None,
            "title": title or name,
            "publisher": (title or name).split("—")[0].strip(),
            "url_text": _url_candidate_from_name(name),
            "type": cells[3] or None,
            "language": cells[4] or None,
            "access": cells[5] or None,
            "last_checked": cells[9] or None,
        }
    return out


def load_records(evidence_dir):
    """Load all records under <evidence_dir>/records/*.md. Returns dict id -> record."""
    records_dir = Path(evidence_dir) / "records"
    out = {}
    if not records_dir.is_dir():
        return out
    for path in sorted(records_dir.glob("*.md")):
        for rec in parse_file(path):
            if rec["id"] in out:
                rec["parse_warning"] = f"duplicate id also in {out[rec['id']]['file']}"
            out[rec["id"]] = rec
    return out


def check_citations(cited_ids, records):
    """Validate a list of cited EV ids against loaded records.

    Returns dict with: valid, missing, malformed, weak (evidence strength <= 2
    or status needs-more-evidence — citable only as leads, not findings).
    """
    valid, missing, malformed, weak = [], [], [], []
    for cid in cited_ids:
        cid = cid.strip()
        if not EV_ID_RE.match(cid):
            malformed.append(cid)
            continue
        rec = records.get(cid)
        if rec is None:
            missing.append(cid)
            continue
        valid.append(cid)
        strength = rec["scores"].get("evidence strength")
        if (strength is not None and strength <= 2) or rec.get("status") == "needs-more-evidence":
            weak.append(cid)
    return {"valid": valid, "missing": missing, "malformed": malformed, "weak": weak}


def render_markdown(records):
    if not records:
        return (
            "No evidence records found. knowledge-base/customer-evidence/records/ is empty — "
            "all scorecard citations must be (A) assumptions until Workstream A lands records.\n"
        )
    lines = [
        f"# Evidence records loaded: {len(records)}",
        "",
        "| ID | Title | Status | Segment | Evidence strength | Confidence |",
        "|---|---|---|---|---|---|",
    ]
    for rec in sorted(records.values(), key=lambda r: r["id"]):
        lines.append(
            "| {id} | {title} | {status} | {seg} | {strength} | {conf} |".format(
                id=rec["id"],
                title=rec["title"],
                status=rec.get("status") or "?",
                seg=rec.get("segment", ""),
                strength=rec["scores"].get("evidence strength", "?"),
                conf=rec.get("evidence_confidence", ""),
            )
        )
    return "\n".join(lines) + "\n"
