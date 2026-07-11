#!/usr/bin/env python3
"""Read-only conformance checker for Workstream A's knowledge base.

Validates that live evidence records honour the format Workstream B's parser
(opportunity-intelligence/tools/opportunity_engine/evidence.py) consumes, plus
Workstream A's own rules:

  - unique EV IDs across all records files
  - Evidence confidence starts with High | Medium | Low
  - Status leading token in the allowed set (annotation after it is fine,
    matching the downstream parser's first-token behaviour)
  - all ten score axes present, values 1-5
  - EV / SRC / SEG / IP references resolve, checked ONLY in structured fields
    (Customer segment, Source, Duplicate status, Contradictory evidence) of
    live records - never in documentation, templates, or prose, to avoid
    false positives on example IDs
  - required template fields present in every record

Standard library only. Never writes. Exit 0 = pass, 1 = errors found.

Usage:
    python3 customer-intelligence/tools/conformance_check.py [repo_root]
"""

import re
import sys
from pathlib import Path

HEADER_RE = re.compile(r"^##\s+(EV-\d{4}-W\d{2}-\d{3})\s*[—-]+\s*(.+?)\s*$")
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(\S+)")
TABLE_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$")
SCORE_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)\s*\.{2,}\s*([1-5])\s*$")

EV_REF_RE = re.compile(r"\bEV-\d{4}-W\d{2}-\d{3}\b")
SRC_REF_RE = re.compile(r"\bSRC-\d{3}\b")
SEG_REF_RE = re.compile(r"\bSEG-[a-z0-9][a-z0-9-]*\b")
IP_REF_RE = re.compile(r"\bIP-\d{4}-\d{3}\b")
SRC_LOG_ID_RE = re.compile(r"^\|\s*(SRC-\d{3})\s*\|")

# the leading whitespace-delimited token must be exactly the enum value, so
# compound values like "Medium-High" fail while "Medium — nuance" passes
CONFIDENCE_RE = re.compile(r"^(High|Medium|Low)(?=$|\s)")
# leading token must match one of these; trailing annotation is tolerated,
# mirroring the downstream parser which takes the first token only
STATUS_TOKENS_RE = re.compile(r"^(active|needs-more-evidence|resolved|superseded-by:EV-\d{4}-W\d{2}-\d{3})$")

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

REQUIRED_FIELDS = (
    "customer segment",
    "pain category",
    "provider mentioned",
    "exact customer wording",
    "source",
    "date of evidence",
    "access label",
    "language",
    "evidence confidence",
    "duplicate status",
    "contradictory evidence",
    "product implication",
)

# structured fields in which ID references are validated (user rule: never
# validate refs found in prose/docs - only these cells of live records)
REF_FIELDS = {
    "customer segment": ("SEG",),
    "source": ("SRC",),
    "duplicate status": ("EV",),
    "contradictory evidence": ("EV", "IP"),
}


def parse_records_file(path):
    """Parse one records file into a list of record dicts. Read-only."""
    records = []
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HEADER_RE.match(line)
        if m:
            current = {
                "id": m.group(1),
                "file": str(path),
                "status": None,
                "fields": {},
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
            if key not in current["fields"]:
                current["fields"][key] = m.group(2).strip()
            continue
        m = SCORE_LINE_RE.match(line)
        if m:
            axis = m.group(1).strip().lower()
            if axis in SCORE_AXES and axis not in current["scores"]:
                current["scores"][axis] = int(m.group(2))
    return records


def load_source_ids(source_log):
    ids = set()
    if source_log.is_file():
        for line in source_log.read_text(encoding="utf-8").splitlines():
            m = SRC_LOG_ID_RE.match(line)
            if m:
                ids.add(m.group(1))
    return ids


def check(repo_root):
    """Run all checks. Returns (errors, warnings) lists of strings."""
    root = Path(repo_root)
    kb = root / "knowledge-base"
    records_dir = kb / "customer-evidence" / "records"
    errors, warnings = [], []

    seg_ids = {p.stem for p in (kb / "segments").glob("SEG-*.md")}
    ip_ids = {p.stem for p in (kb / "inflection-points").glob("IP-*.md")}
    src_ids = load_source_ids(kb / "customer-evidence" / "source-log.md")

    all_records = {}
    for path in sorted(records_dir.glob("*.md")) if records_dir.is_dir() else []:
        for rec in parse_records_file(path):
            if rec["id"] in all_records:
                errors.append(
                    f"{rec['id']}: duplicate ID (also in {all_records[rec['id']]['file']})"
                )
            else:
                all_records[rec["id"]] = rec

    if not all_records:
        warnings.append(f"no evidence records found under {records_dir}")

    ev_ids = set(all_records)

    for rec in all_records.values():
        rid = rec["id"]

        # status
        if rec["status"] is None:
            errors.append(f"{rid}: missing **Status:** line")
        elif not STATUS_TOKENS_RE.match(rec["status"]):
            errors.append(f"{rid}: invalid status leading token '{rec['status']}'")

        # required fields
        for field in REQUIRED_FIELDS:
            if field not in rec["fields"]:
                errors.append(f"{rid}: missing required field '{field}'")

        # confidence enum
        conf = rec["fields"].get("evidence confidence")
        if conf is not None and not CONFIDENCE_RE.match(conf):
            errors.append(
                f"{rid}: evidence confidence must start with High/Medium/Low, got '{conf[:40]}'"
            )

        # score axes
        for axis in SCORE_AXES:
            if axis not in rec["scores"]:
                errors.append(f"{rid}: missing score axis '{axis}'")

        # references, structured fields only
        for field, kinds in REF_FIELDS.items():
            value = rec["fields"].get(field, "")
            if "SEG" in kinds:
                found_seg = SEG_REF_RE.findall(value)
                for seg in found_seg:
                    if seg not in seg_ids:
                        errors.append(f"{rid}: unknown segment '{seg}' in '{field}'")
                if field == "customer segment" and not found_seg:
                    warnings.append(
                        f"{rid}: customer segment has no SEG- reference ('{value[:50]}')"
                    )
            if "SRC" in kinds:
                for src in SRC_REF_RE.findall(value):
                    if src not in src_ids:
                        errors.append(f"{rid}: unknown source '{src}' in '{field}'")
            if "EV" in kinds:
                for ev in EV_REF_RE.findall(value):
                    if ev != rid and ev not in ev_ids:
                        errors.append(f"{rid}: unknown evidence ref '{ev}' in '{field}'")
            if "IP" in kinds:
                for ip in IP_REF_RE.findall(value):
                    if ip not in ip_ids:
                        errors.append(f"{rid}: unknown inflection ref '{ip}' in '{field}'")

    return errors, warnings


def main(argv):
    repo_root = argv[1] if len(argv) > 1 else "."
    errors, warnings = check(repo_root)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\nconformance: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
