"""Deterministic evidence-freshness calculation (Integration Phase 4).

THE single home for freshness bands, thresholds, and the reference-date
priority order. Both the executive-ui API (executive-ui/adapter/collect.py)
and copilot-backend (copilot-backend/app/tools_registry.py) import this
module so the thresholds are never duplicated across backends, and the
frontend only ever *displays* the status the backend computed — it never
re-derives one.

This is a pure date calculation over dates already stored in the repository.
It never calls the network, never refetches a source, and never alters a
record. It is a deterministic status, not an LLM judgment.

Bands (measured in whole days from the reference date to `today`):

    fresh    age <= FRESH_MAX_DAYS  (90)
    aging    FRESH_MAX_DAYS < age <= AGING_MAX_DAYS  (180)
    stale    age > AGING_MAX_DAYS
    unknown  no usable reference date exists

Reference-date priority (first parseable value wins):

    last_verified_at > retrieved_at > publication_date
        > date_of_evidence > created_at

A record with none of those dates is honestly `unknown` — a missing date is
never replaced with an invented one.
"""

import datetime
import re

FRESH_MAX_DAYS = 90
AGING_MAX_DAYS = 180

STATUS_FRESH = "fresh"
STATUS_AGING = "aging"
STATUS_STALE = "stale"
STATUS_UNKNOWN = "unknown"

# (field, past-tense phrase used in the human-readable reason)
REFERENCE_PRIORITY = (
    ("last_verified_at", "Last verified"),
    ("retrieved_at", "Retrieved"),
    ("publication_date", "Published"),
    ("date_of_evidence", "Evidence dated"),
    ("created_at", "Record created"),
)

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def parse_iso_date(value):
    """A datetime.date from a YYYY-MM-DD(-prefixed) string, else None.

    Accepts full ISO timestamps ("2026-07-10T12:00:00Z") by using the date
    prefix. Anything non-parseable (free text like "Undated (2025-2026
    search index)", empty, or a non-string) returns None — never a guess.
    """
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str):
        return None
    m = _ISO_DATE_RE.match(value.strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def band(age_days):
    """The freshness band for a non-negative age in days."""
    if age_days <= FRESH_MAX_DAYS:
        return STATUS_FRESH
    if age_days <= AGING_MAX_DAYS:
        return STATUS_AGING
    return STATUS_STALE


def compute(dates, today=None):
    """Freshness fields for a record's stored dates.

    `dates` is a mapping that may contain any of the REFERENCE_PRIORITY
    fields (values: ISO date strings or None). Returns a dict with:

        freshness_status          fresh | aging | stale | unknown
        freshness_reference_date  ISO YYYY-MM-DD or None
        freshness_age_days        int or None
        freshness_reason          one honest sentence

    A reference date in the future (clock skew / data error) is clamped to
    age 0 rather than reported as a negative age.
    """
    today = parse_iso_date(today) or datetime.date.today()
    for field, phrase in REFERENCE_PRIORITY:
        ref = parse_iso_date((dates or {}).get(field))
        if ref is None:
            continue
        age = max((today - ref).days, 0)
        status = band(age)
        reason = f"{phrase} {age} day{'s' if age != 1 else ''} ago."
        if field != "last_verified_at":
            reason += " No verification date is available."
        if status == STATUS_STALE:
            reason += f" Older than the {AGING_MAX_DAYS}-day staleness threshold."
        return {
            "freshness_status": status,
            "freshness_reference_date": ref.isoformat(),
            "freshness_age_days": age,
            "freshness_reason": reason,
        }
    return {
        "freshness_status": STATUS_UNKNOWN,
        "freshness_reference_date": None,
        "freshness_age_days": None,
        "freshness_reason": ("No verification, retrieval, publication, or creation "
                             "date is available for this record."),
    }
