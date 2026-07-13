"""Extraction orchestration: eligibility -> prompt -> provider call ->
deterministic validation -> persistence as pending_review observations.

The provider is the SAME canonical shared.llm.provider abstraction used
everywhere else in the repository (no second provider abstraction). The
provider call itself never happens inside a SQLite transaction — an
extraction_runs row is created and committed first (status='in_progress'),
the network call happens with no write lock held, and results are
persisted in a second, fast transaction.

The model may only PROPOSE observations. It never sets review_status
(always 'pending_review' on creation here) and it cannot mark anything
approved, create a finding, or touch Part A/B/impact/assumption state —
none of that exists in this module at all.
"""

import hashlib
import json
import uuid

from . import audit, guides
from .auth import require_any_role
from .db import DbError, dumps, loads
from .eligibility import ExtractionError, check_eligibility
from .extraction_prompt import TOOL_NAME, build_messages, build_tools, get_system_prompt
from .extraction_validate import validate_observations
from .models import EXTRACTION_RUN_ID_RE, OBSERVATION_ID_RE, ValidationError
from shared.llm.provider import ProviderError, make_provider


def compute_source_hash(response_id, eligible_answers):
    payload = {
        "response_id": response_id,
        "answers": sorted((a["answer_id"], a["original_answer"]) for a in eligible_answers),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _parse_raw_observations(model_response):
    if model_response.tool_calls:
        for call in model_response.tool_calls:
            if call.get("name") == TOOL_NAME:
                args = call.get("arguments") or {}
                observations = args.get("observations")
                if isinstance(observations, list):
                    return observations
        raise ExtractionError("model did not return the expected tool call", code="invalid_provider_output")
    content = model_response.content or ""
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        raise ExtractionError("model output was not valid JSON", code="invalid_provider_output")
    if isinstance(parsed, dict) and isinstance(parsed.get("observations"), list):
        return parsed["observations"]
    if isinstance(parsed, list):
        return parsed
    raise ExtractionError("model output did not match the expected shape", code="invalid_provider_output")


def _observation_row_to_dict(row):
    (observation_id, response_id, campaign_id, participant_id, source_answer_id, observation_type,
     normalized_statement, source_excerpt, is_direct_quote, extraction_confidence, frequency, severity,
     current_workaround, payment_rail, linked_segments, linked_opportunities, linked_assumptions,
     contradiction_target, follow_up_question, sensitivity_flags, review_status, workflow_status,
     superseded_by_run_id, created_by, created_at, updated_at, model_provider, model_name,
     extraction_run_id, source_hash) = row
    return {
        "observation_id": observation_id, "response_id": response_id, "campaign_id": campaign_id,
        "participant_id": participant_id, "source_answer_id": source_answer_id,
        "observation_type": observation_type, "normalized_statement": normalized_statement,
        "source_excerpt": source_excerpt, "is_direct_quote": bool(is_direct_quote),
        "extraction_confidence": extraction_confidence, "frequency": frequency, "severity": severity,
        "current_workaround": current_workaround, "payment_rail": payment_rail,
        "linked_segments": loads(linked_segments), "linked_opportunities": loads(linked_opportunities),
        "linked_assumptions": loads(linked_assumptions), "contradiction_target": contradiction_target,
        "follow_up_question": follow_up_question, "sensitivity_flags": loads(sensitivity_flags),
        "review_status": review_status, "workflow_status": workflow_status,
        "superseded_by_run_id": superseded_by_run_id, "created_by": created_by, "created_at": created_at,
        "updated_at": updated_at, "model_provider": model_provider, "model_name": model_name,
        "extraction_run_id": extraction_run_id, "source_hash": source_hash,
    }


OBSERVATION_COLUMNS = (
    "observation_id, response_id, campaign_id, participant_id, source_answer_id, observation_type, "
    "normalized_statement, source_excerpt, is_direct_quote, extraction_confidence, frequency, severity, "
    "current_workaround, payment_rail, linked_segments_json, linked_opportunities_json, "
    "linked_assumptions_json, contradiction_target, follow_up_question, sensitivity_flags_json, "
    "review_status, workflow_status, superseded_by_run_id, created_by, created_at, updated_at, "
    "model_provider, model_name, extraction_run_id, source_hash")


def get_observation(conn, observation_id):
    row = conn.execute(f"SELECT {OBSERVATION_COLUMNS} FROM observations WHERE observation_id=?",
                       (observation_id,)).fetchone()
    if row is None:
        raise DbError(f"observation not found: {observation_id}")
    return _observation_row_to_dict(row)


def list_observations_for_response(conn, response_id, include_superseded=False):
    query = f"SELECT {OBSERVATION_COLUMNS} FROM observations WHERE response_id=?"
    if not include_superseded:
        query += " AND workflow_status != 'superseded'"
    query += " ORDER BY created_at"
    rows = conn.execute(query, (response_id,)).fetchall()
    return [_observation_row_to_dict(r) for r in rows]


def _run_row_to_dict(row):
    (extraction_run_id, response_id, provider, model, started_at, completed_at, status,
     input_source_hash, proposed_count, accepted_count, rejected_count, safe_error_code, actor_id) = row
    return {
        "extraction_run_id": extraction_run_id, "response_id": response_id, "provider": provider,
        "model": model, "started_at": started_at, "completed_at": completed_at, "status": status,
        "input_source_hash": input_source_hash, "proposed_count": proposed_count,
        "accepted_count": accepted_count, "rejected_count": rejected_count,
        "safe_error_code": safe_error_code, "actor_id": actor_id,
    }


RUN_COLUMNS = ("extraction_run_id, response_id, provider, model, started_at, completed_at, status, "
              "input_source_hash, proposed_count, accepted_count, rejected_count, safe_error_code, actor_id")


def get_run(conn, extraction_run_id):
    row = conn.execute(f"SELECT {RUN_COLUMNS} FROM extraction_runs WHERE extraction_run_id=?",
                       (extraction_run_id,)).fetchone()
    if row is None:
        raise DbError(f"extraction run not found: {extraction_run_id}")
    return _run_row_to_dict(row)


def list_runs_for_response(conn, response_id):
    rows = conn.execute(f"SELECT {RUN_COLUMNS} FROM extraction_runs WHERE response_id=? ORDER BY started_at",
                        (response_id,)).fetchall()
    return [_run_row_to_dict(r) for r in rows]


def _reusable_run(conn, response_id, source_hash):
    row = conn.execute(
        f"SELECT {RUN_COLUMNS} FROM extraction_runs WHERE response_id=? AND input_source_hash=? "
        "AND status='completed' ORDER BY started_at DESC LIMIT 1", (response_id, source_hash)).fetchone()
    return _run_row_to_dict(row) if row else None


def run_extraction(conn, config, principal, response_id, now, rerun=False):
    require_any_role(principal, ("researcher", "reviewer", "admin"))

    try:
        response, participant, campaign, eligible_answers = check_eligibility(conn, response_id, now)
    except ExtractionError as exc:
        with conn:
            audit.record(conn, principal["label"], principal["role"], "extraction_denied", "response",
                        response_id, now, safe_diff={"error_code": exc.code})
        raise

    in_progress = conn.execute(
        "SELECT 1 FROM extraction_runs WHERE response_id=? AND status='in_progress'", (response_id,)).fetchone()
    if in_progress:
        raise ExtractionError("an extraction run is already in progress for this response",
                              code="duplicate_extraction")

    source_hash = compute_source_hash(response_id, eligible_answers)

    with conn:
        audit.record(conn, principal["label"], principal["role"], "extraction_requested", "response",
                    response_id, now, safe_diff={"rerun": bool(rerun), "source_hash": source_hash})

    if not rerun:
        existing = _reusable_run(conn, response_id, source_hash)
        if existing is not None:
            observations = list_observations_for_response(conn, response_id)
            return existing, observations

    extraction_run_id = "MER-" + uuid.uuid4().hex[:12]
    if not EXTRACTION_RUN_ID_RE.match(extraction_run_id):
        raise ValidationError(f"invalid extraction_run_id: {extraction_run_id!r}")

    superseded_count = 0
    with conn:
        conn.execute(
            "INSERT INTO extraction_runs (extraction_run_id, response_id, provider, model, started_at, "
            "completed_at, status, input_source_hash, proposed_count, accepted_count, rejected_count, "
            "safe_error_code, actor_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (extraction_run_id, response_id, config.provider, config.model, now, None, "in_progress",
             source_hash, None, None, None, None, principal["label"]))
        if rerun:
            prior = conn.execute(
                "SELECT observation_id FROM observations WHERE response_id=? AND workflow_status='active' "
                "AND review_status='pending_review'", (response_id,)).fetchall()
            superseded_count = len(prior)
            if prior:
                conn.execute(
                    "UPDATE observations SET workflow_status='superseded', superseded_by_run_id=?, updated_at=? "
                    "WHERE response_id=? AND workflow_status='active' AND review_status='pending_review'",
                    (extraction_run_id, now, response_id))
            audit.record(conn, principal["label"], principal["role"], "supersession", "response", response_id,
                        now, safe_diff={"extraction_run_id": extraction_run_id, "superseded_count": superseded_count})

    guide = guides.get(conn, response["guide_id"])
    guide_questions_by_id = {q["question_id"]: q["text"] for q in guide["questions"]}
    messages = build_messages(campaign, eligible_answers, guide_questions_by_id)
    tools = build_tools()
    system_prompt = get_system_prompt()

    def _fail(code, message):
        with conn:
            conn.execute("UPDATE extraction_runs SET completed_at=?, status='failed', safe_error_code=? "
                        "WHERE extraction_run_id=?", (now, code, extraction_run_id))
            audit.record(conn, principal["label"], principal["role"], "extraction_completed", "response",
                        response_id, now, safe_diff={"extraction_run_id": extraction_run_id, "status": "failed",
                                                     "error_code": code})
        raise ExtractionError(message, code=code)

    provider = make_provider(config)
    try:
        model_response = provider.generate(messages, tools, system_prompt, config)
    except ProviderError as exc:
        _fail("provider_timeout" if exc.timeout else "provider_error", str(exc))
        return  # unreachable; _fail always raises

    try:
        raw_observations = _parse_raw_observations(model_response)
    except ExtractionError as exc:
        _fail(exc.code, str(exc))
        return  # unreachable

    existing_observation_ids = {
        o["observation_id"] for o in list_observations_for_response(conn, response_id, include_superseded=True)}
    context = {
        "answers_by_id": {a["answer_id"]: a for a in eligible_answers},
        "valid_seg_ids": set(campaign.get("target_segments", [])),
        "valid_opp_ids": set(campaign.get("linked_opportunities", [])),
        "valid_asm_ids": set(campaign.get("linked_assumptions", [])),
        "existing_observation_ids": existing_observation_ids,
        "identity_strings": [participant["participant_id"], participant["merchant_identity_id"]],
        "quote_permission": bool(participant["quote_permission"]),
    }
    accepted, rejected = validate_observations(raw_observations, context)

    created = []
    with conn:
        for obs in accepted:
            observation_id = "MVO-" + uuid.uuid4().hex[:10]
            if not OBSERVATION_ID_RE.match(observation_id):
                raise ValidationError(f"invalid observation_id: {observation_id!r}")
            row = {
                "observation_id": observation_id, "response_id": response_id, "campaign_id": campaign["campaign_id"],
                "participant_id": participant["participant_id"], **obs,
                "review_status": "pending_review", "workflow_status": "active", "superseded_by_run_id": None,
                "created_by": principal["label"], "created_at": now, "updated_at": now,
                "model_provider": config.provider, "model_name": config.model,
                "extraction_run_id": extraction_run_id, "source_hash": source_hash,
            }
            conn.execute(
                f"INSERT INTO observations ({OBSERVATION_COLUMNS}) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["observation_id"], row["response_id"], row["campaign_id"], row["participant_id"],
                 row["source_answer_id"], row["observation_type"], row["normalized_statement"],
                 row["source_excerpt"], int(row["is_direct_quote"]), row["extraction_confidence"],
                 row["frequency"], row["severity"], row["current_workaround"], row["payment_rail"],
                 dumps(row["linked_segments"]), dumps(row["linked_opportunities"]),
                 dumps(row["linked_assumptions"]), row["contradiction_target"], row["follow_up_question"],
                 dumps(row["sensitivity_flags"]), row["review_status"], row["workflow_status"],
                 row["superseded_by_run_id"], row["created_by"], row["created_at"], row["updated_at"],
                 row["model_provider"], row["model_name"], row["extraction_run_id"], row["source_hash"]))
            created.append(observation_id)
            existing_observation_ids.add(observation_id)

        conn.execute(
            "UPDATE extraction_runs SET completed_at=?, status='completed', proposed_count=?, "
            "accepted_count=?, rejected_count=? WHERE extraction_run_id=?",
            (now, len(raw_observations), len(accepted), len(rejected), extraction_run_id))
        audit.record(conn, principal["label"], principal["role"], "extraction_completed", "response",
                    response_id, now, safe_diff={
                        "extraction_run_id": extraction_run_id, "status": "completed",
                        "proposed_count": len(raw_observations), "accepted_count": len(accepted),
                        "rejected_count": len(rejected)})

    return get_run(conn, extraction_run_id), [get_observation(conn, oid) for oid in created]
