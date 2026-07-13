"""UI-ready dataclasses. Plain data holders — no logic, no scoring.

These are what the renderers consume. Every field is populated by collect.py
from real repository data or left as an explicit "unknown" sentinel; the UI
must never invent values, so absent data is represented, not fabricated.
"""

from dataclasses import dataclass, field

UNKNOWN = "—"  # honest empty value shown in the UI

# evidence roles (how a record relates to a scorecard)
PRIMARY = "primary"
CONTEXTUAL = "contextual"
EXCLUDED = "excluded"


@dataclass
class EvidenceRef:
    ev_id: str
    resolved: bool                 # does the record actually exist?
    source_type: str = UNKNOWN     # access label (direct/search-snippet/…)
    evidence_class: str = UNKNOWN
    strength: object = UNKNOWN      # int 1-5 or UNKNOWN
    confidence: str = UNKNOWN       # High/Medium/Low
    status: str = UNKNOWN
    segment: str = UNKNOWN
    title: str = UNKNOWN
    role: str = CONTEXTUAL         # primary | contextual | excluded
    weak: bool = False             # strength<3 or needs-more-evidence → lead, not finding


@dataclass
class Factor:
    key: str
    score: int
    assumption: bool               # True => (A), assumption-based
    basis: str
    evidence_ids: list = field(default_factory=list)


@dataclass
class Assumption:
    opportunity_id: str
    factor_key: str
    text: str                      # the factor basis (the assumption statement)
    status: str                    # untested | partially-supported | supported | contradicted
    evidence_ids: list = field(default_factory=list)
    sensitivity: str = UNKNOWN     # from tornado rank if available, else UNKNOWN
    validation_method: str = UNKNOWN  # linked VE if derivable
    owner: str = UNKNOWN


@dataclass
class Opportunity:
    id: str
    name: str
    raw_score: int                 # sum of 17 factors (engine-derived)
    raw_max: int
    composite: float               # engine's indicative composite
    classification: str            # engine enum: strong/promising/weak/reject/unscored
    classification_label: str      # human phrase from backlog if present
    confidence: str                # evidence_confidence, verbatim (not reinterpreted)
    assumption_count: int
    factors: list = field(default_factory=list)          # [Factor] (all 17)
    critical_flags: list = field(default_factory=list)
    segment: str = UNKNOWN
    jtbd: str = UNKNOWN
    hypothesis: str = UNKNOWN
    strongest_evidence: list = field(default_factory=list)   # [EvidenceRef]
    contradictory_evidence: str = UNKNOWN
    rejection_conditions: str = UNKNOWN
    validation_plan: str = UNKNOWN
    score_history: list = field(default_factory=list)    # [] => no prior versions recorded
    latest_change: str = "No approved impact yet"        # honest default (no impact workflow)
    latest_alert: str = UNKNOWN
    next_action: str = UNKNOWN
    profile_path: str = UNKNOWN
    is_archived: bool = False


@dataclass
class FeedItem:
    id: str
    kind: str                      # lead | alert | rescore-suggestion | summary | prediction-resolved
    tier: str                      # monitoring tier or UNKNOWN
    title: str
    detected_at: str = UNKNOWN
    detail: str = UNKNOWN
    before_after: dict = None      # {"before": ..., "after": ...} or None


@dataclass
class Brief:
    opportunity_id: str
    exists: bool
    path: str = UNKNOWN
    body: str = UNKNOWN            # raw markdown of the recommendation doc; UI renders, doesn't reinterpret


@dataclass
class UIModel:
    opportunities: list = field(default_factory=list)
    archived: list = field(default_factory=list)
    evidence: list = field(default_factory=list)         # [EvidenceRef] all records
    assumptions: list = field(default_factory=list)      # [Assumption]
    feed: list = field(default_factory=list)             # [FeedItem]
    briefs: list = field(default_factory=list)           # [Brief]
    generated_note: str = ""                             # provenance line (commit, counts)
    decision_banner: str = "No product or build decision has been made."
