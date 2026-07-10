"""Validator for validation-experiment specs (VE-*.md).

Enforces opportunity-intelligence/templates/validation-experiment.md in code:
every experiment file must carry all mandatory fields, the hypothesis must be
falsifiable (contain a number), and success/failure thresholds must be
pre-committed numbers — an experiment without a kill threshold is a
commitment, not a test.

Expected file shape (as produced by the template):

    - **Experiment ID:** VE-001
    - **Hypothesis:** ≥40% of ...
    - **Success threshold (pre-committed):** ...
    ...

Parenthetical qualifiers in labels ("(pre-committed)") are ignored; a field's
value may continue on following indented lines (sub-bullets).
"""

import re
from pathlib import Path

FIELD_RE = re.compile(r"^-\s+\*\*(.+?):\*\*\s*(.*)$")
HEADER_RE = re.compile(r"^#{1,6}\s")
VE_ID_RE = re.compile(r"^VE-\d{3}$")

REQUIRED_FIELDS = (
    "experiment id",
    "proposition tested",
    "hypothesis",
    "target participants",
    "recruitment criteria",
    "method",
    "sample size",
    "success threshold",
    "failure threshold",
    "duration",
    "data collected",
    "decision informed",
)

MUST_CONTAIN_NUMBER = ("hypothesis", "success threshold", "failure threshold")


def _norm_label(label):
    """'Success threshold (pre-committed)' -> 'success threshold'."""
    return re.sub(r"\s*\([^)]*\)", "", label).strip().lower()


def parse_file(path):
    """Parse one VE spec. Returns dict: normalised field label -> value text."""
    fields = {}
    current = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = FIELD_RE.match(line)
        if m:
            current = _norm_label(m.group(1))
            # first occurrence wins; the result-record section may repeat labels
            if current in fields:
                current = None
                continue
            fields[current] = m.group(2).strip()
            continue
        if HEADER_RE.match(line):
            current = None
            continue
        if current is not None:
            fields[current] = (fields[current] + " " + line.strip()).strip()
    return fields


def validate_file(path):
    """Validate one VE spec file. Returns a list of issue strings (empty = ok)."""
    issues = []
    fields = parse_file(path)

    for name in REQUIRED_FIELDS:
        if name not in fields:
            issues.append(f"missing mandatory field: {name}")
        elif not fields[name]:
            issues.append(f"mandatory field is empty: {name}")

    for name in MUST_CONTAIN_NUMBER:
        value = fields.get(name, "")
        if value and not re.search(r"\d", value):
            issues.append(
                f"field '{name}' contains no number — thresholds and hypotheses "
                "must be quantified and pre-committed"
            )

    ve_id = fields.get("experiment id", "")
    if ve_id and not VE_ID_RE.match(ve_id):
        issues.append(f"experiment id {ve_id!r} does not match VE-nnn")
    stem = Path(path).name
    if ve_id and not stem.startswith(ve_id):
        issues.append(f"filename {stem!r} does not start with experiment id {ve_id!r}")

    return issues


def validate_dir(validation_dir):
    """Validate all VE-*.md files. Returns dict path -> list of issues."""
    out = {}
    root = Path(validation_dir)
    if not root.is_dir():
        return out
    for path in sorted(root.glob("VE-*.md")):
        out[str(path)] = validate_file(path)
    return out
