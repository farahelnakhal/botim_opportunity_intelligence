"""Deterministic validation of model-proposed observations.

The model may PROPOSE observations; this module decides what may actually
be persisted. Nothing here trusts model self-assessment — confidence,
sensitivity flags, and even the model's own claimed is_direct_quote are
all re-derived or checked against the redacted source text.

Design choices (documented per the Phase 3 instruction not to silently
invent behavior):
  - Exact-substring excerpt validation only (never fuzzy) — see
    `normalize_for_match`. A fabricated or reworded excerpt is REJECTED,
    not corrected.
  - Invalid SEG/OPP/ASM links are REMOVED from the observation (not a
    rejection of the whole observation) and flagged `invalid_link_removed`;
    a missing/unknown contradiction_target is cleared and flagged
    `contradiction_target_removed`. Neither is ever silently replaced with
    an invented ID.
  - A single-response claim that reads as a cross-merchant generalization
    ("most merchants", "X percent of merchants", ...) is REJECTED outright
    — Phase 4 aggregation, not this per-response extraction step, is where
    cross-participant patterns belong.
  - Frequency/severity: if the *primary* observation_type is `frequency` or
    `severity` and the field ends up unsupported, the whole observation is
    rejected (a "frequency" observation with no frequency is meaningless).
    If frequency/severity is merely an attached attribute on a different
    observation_type, the unsupported field is cleared and flagged instead
    of rejecting the whole observation.
"""

import unicodedata

from .models import (AGGREGATE_CLAIM_PHRASES, CONFIDENCE_LEVELS, FREQUENCY_VALUE_TRIGGERS,
                     FREQUENCY_VALUES, GENERIC_INTEREST_PHRASES, OBSERVATION_TYPES,
                     SEVERITY_TRIGGER_WORDS, SEVERITY_VALUES, WTP_SUPPORT_TRIGGERS)

REJECT_REASONS = (
    "invalid_observation_type", "invalid_confidence", "missing_source_answer_id",
    "invalid_source_answer_id", "missing_source_excerpt", "unsupported_excerpt",
    "missing_normalized_statement", "single_response_aggregate_claim",
    "unsupported_frequency_observation", "unsupported_severity_observation",
    "identity_data_detected",
)


class ValidationOutcome:
    def __init__(self, accepted, observation=None, reason=None, flags=None):
        self.accepted = accepted
        self.observation = observation
        self.reason = reason
        self.flags = flags or []


def normalize_for_match(text):
    """Unicode NFC + whitespace/line-break collapsing + harmless punctuation
    spacing only — NEVER fuzzy (no edit distance, no synonym matching)."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(text.split())
    for punct in (",", ".", ";", ":", "!", "?"):
        text = text.replace(f" {punct}", punct)
    return text.strip().lower()


def _contains_any(haystack, phrases):
    haystack_norm = normalize_for_match(haystack)
    return any(phrase in haystack_norm for phrase in phrases)


def validate_observation(raw_obs, context):
    """`context` keys: answers_by_id ({answer_id: {question_id, original_answer}}),
    valid_seg_ids, valid_opp_ids, valid_asm_ids, existing_observation_ids
    (for contradiction_target — same response only), identity_strings
    (defensive leak check), quote_permission (bool)."""
    flags = []

    if not isinstance(raw_obs, dict):
        return ValidationOutcome(False, reason="invalid_provider_output")

    obs_type = raw_obs.get("observation_type")
    if obs_type not in OBSERVATION_TYPES:
        return ValidationOutcome(False, reason="invalid_observation_type")

    confidence = raw_obs.get("extraction_confidence")
    if confidence not in CONFIDENCE_LEVELS:
        return ValidationOutcome(False, reason="invalid_confidence")

    source_answer_id = raw_obs.get("source_answer_id")
    if not isinstance(source_answer_id, str) or not source_answer_id:
        return ValidationOutcome(False, reason="missing_source_answer_id")
    answer = context["answers_by_id"].get(source_answer_id)
    if answer is None:
        # covers both "unknown id" and "belongs to a different response" —
        # answers_by_id is scoped to THIS response only by the caller.
        return ValidationOutcome(False, reason="invalid_source_answer_id")

    source_excerpt = raw_obs.get("source_excerpt")
    if not isinstance(source_excerpt, str) or not source_excerpt.strip():
        return ValidationOutcome(False, reason="missing_source_excerpt")

    source_text = answer.get("original_answer") or ""
    if normalize_for_match(source_excerpt) not in normalize_for_match(source_text):
        return ValidationOutcome(False, reason="unsupported_excerpt")

    normalized_statement = raw_obs.get("normalized_statement")
    if not isinstance(normalized_statement, str) or not normalized_statement.strip():
        return ValidationOutcome(False, reason="missing_normalized_statement")

    # identity-leak defensive check (should be structurally impossible since
    # identity data is never sent to the model — checked anyway)
    text_fields = " ".join(str(raw_obs.get(f) or "") for f in (
        "source_excerpt", "normalized_statement", "follow_up_question",
        "current_workaround", "payment_rail"))
    for identity_string in context.get("identity_strings", []):
        if identity_string and identity_string in text_fields:
            return ValidationOutcome(False, reason="identity_data_detected")

    # single-response aggregate-claim guard
    if _contains_any(normalized_statement, AGGREGATE_CLAIM_PHRASES) or \
            _contains_any(source_excerpt, AGGREGATE_CLAIM_PHRASES):
        return ValidationOutcome(False, reason="single_response_aggregate_claim")

    # quote vs paraphrase
    claimed_quote = bool(raw_obs.get("is_direct_quote"))
    materially_identical = normalize_for_match(normalized_statement) == normalize_for_match(source_excerpt)
    is_direct_quote = claimed_quote and materially_identical and context.get("quote_permission", False)
    if claimed_quote and not is_direct_quote:
        flags.append("quote_downgraded")

    # WTP safeguard
    if obs_type == "willingness_to_pay_signal":
        has_support = _contains_any(source_excerpt, WTP_SUPPORT_TRIGGERS)
        is_generic_only = _contains_any(source_excerpt, GENERIC_INTEREST_PHRASES) or \
            _contains_any(normalized_statement, GENERIC_INTEREST_PHRASES)
        if not has_support:
            obs_type = "concept_reaction"
            flags.append("wtp_downgraded_generic_interest" if is_generic_only else "wtp_downgraded_unsupported")

    # frequency safeguard — the claimed value must be grounded by ITS OWN
    # trigger phrase, not just any frequency-ish word in the excerpt
    frequency = raw_obs.get("frequency")
    if frequency is not None:
        triggers = FREQUENCY_VALUE_TRIGGERS.get(frequency, ())
        if frequency not in FREQUENCY_VALUES or not _contains_any(source_excerpt, triggers):
            if obs_type == "frequency":
                return ValidationOutcome(False, reason="unsupported_frequency_observation")
            frequency = None
            flags.append("unsupported_frequency")

    # severity safeguard
    severity = raw_obs.get("severity")
    if severity is not None:
        if severity not in SEVERITY_VALUES or not _contains_any(source_excerpt, SEVERITY_TRIGGER_WORDS):
            if obs_type == "severity":
                return ValidationOutcome(False, reason="unsupported_severity_observation")
            severity = None
            flags.append("unsupported_severity")

    # link validation — remove invalid, never invent replacements
    def _filter_links(raw_ids, valid_ids):
        raw_ids = raw_ids if isinstance(raw_ids, list) else []
        kept = [i for i in raw_ids if isinstance(i, str) and i in valid_ids]
        return kept, len(kept) != len(raw_ids)

    linked_segments, seg_dropped = _filter_links(raw_obs.get("linked_segments"), context["valid_seg_ids"])
    linked_opportunities, opp_dropped = _filter_links(raw_obs.get("linked_opportunities"), context["valid_opp_ids"])
    linked_assumptions, asm_dropped = _filter_links(raw_obs.get("linked_assumptions"), context["valid_asm_ids"])
    if seg_dropped or opp_dropped or asm_dropped:
        flags.append("invalid_link_removed")

    contradiction_target = raw_obs.get("contradiction_target")
    if contradiction_target is not None:
        if contradiction_target not in context.get("existing_observation_ids", set()):
            contradiction_target = None
            flags.append("contradiction_target_removed")

    follow_up_question = raw_obs.get("follow_up_question")
    if follow_up_question is not None and not isinstance(follow_up_question, str):
        follow_up_question = None
    current_workaround = raw_obs.get("current_workaround")
    if current_workaround is not None and not isinstance(current_workaround, str):
        current_workaround = None
    payment_rail = raw_obs.get("payment_rail")
    if payment_rail is not None and not isinstance(payment_rail, str):
        payment_rail = None

    cleaned = {
        "observation_type": obs_type, "source_answer_id": source_answer_id,
        "source_excerpt": source_excerpt, "normalized_statement": normalized_statement,
        "is_direct_quote": is_direct_quote, "extraction_confidence": confidence,
        "frequency": frequency, "severity": severity, "current_workaround": current_workaround,
        "payment_rail": payment_rail, "linked_segments": linked_segments,
        "linked_opportunities": linked_opportunities, "linked_assumptions": linked_assumptions,
        "contradiction_target": contradiction_target, "follow_up_question": follow_up_question,
        "sensitivity_flags": flags,
    }
    return ValidationOutcome(True, observation=cleaned, flags=flags)


def validate_observations(raw_list, context):
    """Returns (accepted: list[dict], rejected: list[{"reason": str}])."""
    accepted, rejected = [], []
    if not isinstance(raw_list, list):
        return accepted, [{"reason": "invalid_provider_output"}]
    for raw_obs in raw_list:
        outcome = validate_observation(raw_obs, context)
        if outcome.accepted:
            accepted.append(outcome.observation)
        else:
            rejected.append({"reason": outcome.reason})
    return accepted, rejected
