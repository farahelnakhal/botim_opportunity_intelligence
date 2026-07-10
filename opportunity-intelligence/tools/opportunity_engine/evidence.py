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
TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$")
SCORE_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)\s*\.{2,}\s*([1-5])\s*$")

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
            }
            records.append(current)
            continue
        if current is None:
            continue
        m = STATUS_RE.match(line.strip())
        if m and current["status"] is None:
            current["status"] = m.group(1)
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
    return records


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
