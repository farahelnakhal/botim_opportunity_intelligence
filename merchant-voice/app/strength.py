"""Deterministic, descriptive evidence-strength bands.

The model never assigns strength — this is a pure function over counts and
context flags, always computed by this service, never by the extraction
provider. It intentionally never uses "market validated" or any wording
that implies a claim has been proven — every band describes *how much
independent signal exists*, not whether the underlying idea is correct.

Inputs considered (each transparently — see the returned `factors` dict):
  - included_participant_count: distinct, non-suppressed, consent-valid
    participants contributing SUPPORTING observations
  - support_count / contradiction_count: counts of linked observations by role
  - segment_consistent / method_consistent: whether all supporting
    observations share one segment and one campaign method (Phase 4 scopes
    every candidate to a single campaign, so method is consistent by
    construction — the flag exists for defense in depth and forward
    compatibility)
  - sampling_limited: caller-supplied flag for "notable limitations" (e.g.
    a very small or skewed sample) that should hold a count-3+ result at
    emerging_pattern rather than repeated_pattern

NOT folded into the deterministic band (left as transparent, separately
visible fields instead of being compressed into one number):
  - evidence directness (is_direct_quote) — visible per-observation
  - observed behavior vs. stated preference — visible via observation_type
  - question neutrality — a guide-authoring concern, out of scope here
  - concept-test status — enforced separately as a hard gate in
    app/candidates.py (CONCEPT_TEST_ALLOWED_FINDING_TYPES), not blended
    into the strength label
  - source suppression — already reflected because suppressed observations
    are excluded from the counts THIS function receives in the first place
"""

from .models import STRENGTH_BANDS


def compute_strength_band(included_participant_count, support_count, contradiction_count,
                          segment_consistent=True, method_consistent=True, sampling_limited=False):
    factors = {
        "included_participant_count": included_participant_count, "support_count": support_count,
        "contradiction_count": contradiction_count, "segment_consistent": segment_consistent,
        "method_consistent": method_consistent, "sampling_limited": sampling_limited,
    }

    if support_count <= 0 or included_participant_count <= 0:
        band = "insufficient"
    elif contradiction_count >= support_count:
        # contradictions dominate or directly undermine the proposed statement
        band = "contradicted"
    elif contradiction_count > 0:
        # meaningful support AND contradiction coexist, without one dominating
        band = "mixed_pattern"
    elif included_participant_count == 1:
        band = "single_signal"
    elif included_participant_count >= 3 and segment_consistent and method_consistent and not sampling_limited:
        # repeated support across independent participants, same segment,
        # compatible method, contradictions don't dominate — still NOT
        # "validated": that word is deliberately never used anywhere here
        band = "repeated_pattern"
    else:
        # >= 2 independent supporting participants but limited sample,
        # inconsistent segment/method, or other notable limitations
        band = "emerging_pattern"

    assert band in STRENGTH_BANDS
    return band, factors
