"""Parser and integrity checker for the product-opportunity backlog.

Reads knowledge-base/product-ideas/BACKLOG.md (template:
opportunity-intelligence/templates/opportunity-backlog.md) and enforces the
row rules in code: unique OPP ids, recognised classifications, a next action
on every live row, REQ references that exist in the evidence-request queue,
and 'reject' only in the archive.
"""

import re
from pathlib import Path

OPP_ID_RE = re.compile(r"^OPP-\d{3}$")
REQ_ID_RE = re.compile(r"^REQ-\d{3}$")
VE_REF_RE = re.compile(r"\bVE-\d{3}\b")
REQ_REF_RE = re.compile(r"\bREQ-\d{3}\b")

# classification cell must contain exactly one of these markers (case-insensitive)
CLASSIFICATIONS = ("strong", "promising", "weak", "reject", "unscored")

SECTION_HEADERS = {
    "## backlog": "backlog",
    "## evidence-request queue": "requests",
    "## archive": "archive",
}


def classification_enum(label):
    """Canonical enum for a prose classification label: FIRST enum word stated
    wins (audit D-2/AG-2) — 'Promising but unvalidated (borderline Weak)' is
    'promising'. Returns None if no enum word appears."""
    low = label.lower()
    hits = [(low.find(c), c) for c in CLASSIFICATIONS if c in low]
    return min(hits)[1] if hits else None


def _cells(line):
    """'| a | b |' -> ['a', 'b'] (None if not a table row)."""
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|") and s.count("|") >= 3):
        return None
    return [c.strip() for c in s[1:-1].split("|")]


def parse(path):
    """Parse BACKLOG.md into {'backlog': [...], 'requests': [...], 'archive': [...]}."""
    data = {"backlog": [], "requests": [], "archive": []}
    section = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        low = line.strip().lower()
        if low.startswith("## "):
            section = next(
                (name for header, name in SECTION_HEADERS.items() if low.startswith(header)),
                None,
            )
            continue
        if section is None:
            continue
        cells = _cells(line)
        if not cells or cells[0].lower() in ("id", "req id") or set(cells[0]) <= {"-", " ", ":"}:
            continue
        if section == "backlog" and len(cells) >= 8:
            data["backlog"].append({
                "id": cells[0].strip("* "),
                "proposition": cells[1],
                "segment": cells[2],
                "classification": cells[3],
                "composite": cells[4],
                "evidence_confidence": cells[5],
                "invalidation_risk": cells[6],
                "next_action": cells[7],
            })
        elif section == "requests" and len(cells) >= 5:
            data["requests"].append({
                "id": cells[0].strip("* "),
                "for": cells[1],
                "needed": cells[2],
                "why": cells[3],
                "status": cells[4],
            })
        elif section == "archive" and len(cells) >= 5:
            data["archive"].append({
                "id": cells[0].strip("* "),
                "proposition": cells[1],
                "date": cells[2],
                "reason": cells[3],
                "reopen_trigger": cells[4],
            })
    return data


def check(path):
    """Integrity-check a backlog file. Returns (data, issues)."""
    data = parse(path)
    issues = []

    if not data["backlog"] and not data["archive"]:
        issues.append("no backlog or archive rows parsed — file empty or table format changed")
        return data, issues

    seen = {}
    for section in ("backlog", "archive"):
        for row in data[section]:
            rid = row["id"]
            if not OPP_ID_RE.match(rid):
                issues.append(f"{section}: malformed id {rid!r} (expected OPP-nnn)")
                continue
            if rid in seen:
                issues.append(f"duplicate id {rid} (in {seen[rid]} and {section})")
            seen[rid] = section

    req_ids = set()
    for row in data["requests"]:
        if not REQ_ID_RE.match(row["id"]):
            issues.append(f"requests: malformed id {row['id']!r} (expected REQ-nnn)")
        elif row["id"] in req_ids:
            issues.append(f"requests: duplicate id {row['id']}")
        req_ids.add(row["id"])
        if not row["status"]:
            issues.append(f"requests: {row['id']} has no status")

    for row in data["backlog"]:
        enum = classification_enum(row["classification"])
        row["classification_enum"] = enum
        if enum is None:
            issues.append(
                f"{row['id']}: unrecognised classification {row['classification']!r}"
            )
        elif enum == "reject":
            issues.append(
                f"{row['id']}: classification 'reject' belongs in the archive, not the live backlog"
            )
        if not row["next_action"] or row["next_action"] in ("—", "-"):
            issues.append(f"{row['id']}: live backlog row has no next action")
        for ref in REQ_REF_RE.findall(row["next_action"]):
            if ref not in req_ids:
                issues.append(
                    f"{row['id']}: next action references {ref}, which is not in the evidence-request queue"
                )

    for row in data["archive"]:
        if not row["reopen_trigger"]:
            issues.append(f"archive {row['id']}: no reopen trigger recorded")

    return data, issues


def referenced_experiments(data):
    """All VE-nnn ids referenced from backlog next actions."""
    refs = set()
    for row in data["backlog"]:
        refs.update(VE_REF_RE.findall(row["next_action"]))
    return refs
