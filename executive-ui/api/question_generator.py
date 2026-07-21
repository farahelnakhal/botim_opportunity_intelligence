"""Merchant research-question generation from an evidence-gap profile (R10, PR10b).

Orchestration layer (lives here, in executive-ui/api, per decision D1 — so
`shared/` never imports UP into `impact/` or Merchant Voice). Mirrors the
"model proposes, deterministic validation disposes" discipline of
`shared/research/extract.py` (PR3) and Merchant Voice's own extraction:

  gap profile (impact.gap_profile)  ->  bounded LLM draft (shared.llm.provider)
    ->  per-question deterministic validation  ->  persist survivors as a
        DRAFT question set (shared.questions store)

Every proposed question must survive validation or it is dropped (never
softened):
  - it targets an `assumption_id` that is an actual weak link IN THIS profile
    (an invented / unmatched id is rejected — the model cannot fabricate a link);
  - it conforms to Merchant Voice's OWN question taxonomy, checked by importing
    MV's `validate_question_input` (single source of truth — see D1 coupling
    note in the R10 decision-log);
  - bounded counts (per weak link and per set).

The LLM drafts only question *text* + picks a taxonomy purpose/type; it never
assigns severity (that is the deterministic profile's job), never approves, and
nothing here writes the knowledge base or touches Merchant Voice's storage — the
result is a proposal a human reviews (PR10c) before any question reaches a guide.
A missing / unconfigured model yields an honest empty draft with a note — never
a fabricated question.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from impact import gap_profile as _gap_profile          # noqa: E402
from shared.llm.provider import ProviderError           # noqa: E402

_MV_ROOT = REPO_ROOT / "merchant-voice"

MAX_WEAK_LINKS = 8
MAX_PER_LINK = 2
MAX_QUESTIONS = 16


def _load_mv_models():
    """Load Merchant Voice's `models` under the `mv_app` alias — identical
    mechanism to copilot-backend/app/mv_tools.py (MV's own package is named
    `app`, so it must not be imported under the bare name). Pure-code import:
    no MV DB, no HTTP, no data touched — this is the taxonomy source of truth,
    not a cross-service write."""
    if "mv_app" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "mv_app", _MV_ROOT / "app" / "__init__.py",
            submodule_search_locations=[str(_MV_ROOT / "app")])
        module = importlib.util.module_from_spec(spec)
        sys.modules["mv_app"] = module
        spec.loader.exec_module(module)
    return importlib.import_module("mv_app.models")


_mv_models = _load_mv_models()
ValidationError = _mv_models.ValidationError
PURPOSES = _mv_models.QUESTION_PURPOSES
TYPES = _mv_models.QUESTION_TYPES


_SYSTEM = (
    "You draft neutral, non-leading customer-research questions for merchant "
    "interviews. You NEVER assert findings, assume answers, or invent facts. "
    "You only propose questions that would help TEST an unproven assumption. "
    "Output ONLY a JSON object; do no arithmetic and state no conclusions."
)


def _user_prompt(weak_links):
    lines = [
        "For each evidence gap below, propose up to "
        f"{MAX_PER_LINK} merchant-facing research questions that would help test it.",
        f"Allowed `purpose` values: {', '.join(PURPOSES)}.",
        f"Allowed `question_type` values: {', '.join(TYPES)}.",
        "Questions must be neutral and non-leading. Return ONLY JSON of the form",
        '{"questions": [{"targets_assumption_id": "<one of the ids below>", '
        '"text": "...", "purpose": "<allowed>", "question_type": "<allowed>", '
        '"follow_up_prompts": ["..."]}]}.',
        "Use ONLY these assumption ids; never invent one:",
    ]
    for w in weak_links:
        lines.append(f"- {w['assumption_id']} [{w['category']}] ({', '.join(w['signals'])}): "
                     f"{w['statement'][:200]}")
    return "\n".join(lines)


def _parse_questions(content):
    """Best-effort extraction of the questions array; malformed -> [] (never an
    error). Same tolerance as shared/research/extract.py."""
    if not isinstance(content, str) or not content.strip():
        return []
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rstrip("`").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    qs = data.get("questions")
    return qs if isinstance(qs, list) else []


def generate_question_set(store, opp_id, provider, configuration, *, now,
                          owner_user_id=None, max_weak_links=MAX_WEAK_LINKS,
                          max_per_link=MAX_PER_LINK):
    """Build (and persist) a DRAFT question set for a committed opportunity.
    Raises FileNotFoundError if the opportunity has no scorecard (mapped to 404
    upstream). Returns the persisted draft set."""
    profile = _gap_profile.build_gap_profile(opp_id, now)
    weak = profile["weak_links"][:max_weak_links]
    model_name = getattr(configuration, "model", None)
    prov = {"generator": "question_generator", "model": model_name, "generated_at": now,
            "gap_profile_weak_links": [{"assumption_id": w["assumption_id"],
                                        "priority_rank": w["priority_rank"],
                                        "signals": w["signals"]} for w in weak]}

    if not weak:
        return store.create(opp_id, [], provenance=prov, owner_user_id=owner_user_id,
                            note="no open evidence gaps for this opportunity — nothing to draft")
    if provider is None:
        return store.create(opp_id, [], provenance=prov, owner_user_id=owner_user_id,
                            note="no model configured — cannot draft questions (set BOTIM_LLM_API_KEY)")

    by_asm = {w["assumption_id"]: w for w in weak}
    try:
        resp = provider.generate([{"role": "user", "content": _user_prompt(weak)}],
                                  [], _SYSTEM, configuration)
        proposed = _parse_questions(resp.content)
    except ProviderError:
        return store.create(opp_id, [], provenance=prov, owner_user_id=owner_user_id,
                            note="question-drafting model unavailable")

    accepted, rejected, per_link = [], 0, {}
    for p in proposed:
        if len(accepted) >= MAX_QUESTIONS:
            break
        if not isinstance(p, dict):
            rejected += 1
            continue
        asm = p.get("targets_assumption_id")
        w = by_asm.get(asm)
        if w is None:                       # invented / unmatched id -> reject
            rejected += 1
            continue
        if per_link.get(asm, 0) >= max_per_link:
            rejected += 1
            continue
        candidate = {
            "text": p.get("text"),
            "purpose": p.get("purpose"),
            "question_type": p.get("question_type", "open_text"),
            "follow_up_prompts": p.get("follow_up_prompts", []),
            "linked_assumption": asm,
            "linked_hypothesis": None,
        }
        try:
            _mv_models.validate_question_input(candidate, len(accepted))
        except ValidationError:             # fails MV taxonomy -> reject
            rejected += 1
            continue
        candidate["signals"] = w["signals"]
        candidate["source_weak_link_rank"] = w["priority_rank"]
        accepted.append(candidate)
        per_link[asm] = per_link.get(asm, 0) + 1

    note = None
    if not accepted:
        note = "the model proposed no questions that passed taxonomy validation"
    return store.create(opp_id, accepted, provenance=prov, rejected_count=rejected,
                        note=note, owner_user_id=owner_user_id)


# --- PR10c: reviewer-edit taxonomy validation + Merchant Voice hand-off ----- #

def validate_edited_questions(questions):
    """Re-validate a reviewer's EDITED question list against Merchant Voice's
    OWN taxonomy (the same single source of truth the generator uses) before it
    is persisted on approval — so a human edit can never smuggle a question past
    the taxonomy gate. Raises ValidationError (message names the bad index) on
    the first non-conforming question; returns None on success. Pure code — no
    MV DB/HTTP/data touched (D1 coupling note)."""
    if not isinstance(questions, list) or not questions:
        raise ValidationError("an approved question set needs a non-empty list of questions")
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise ValidationError(f"question[{i}] must be an object")
        # MV's validator checks text/purpose/question_type/follow_up_prompts/
        # linked_assumption shape; question_type defaults to open_text there.
        _mv_models.validate_question_input({
            "text": q.get("text"),
            "purpose": q.get("purpose"),
            "question_type": q.get("question_type", "open_text"),
            "follow_up_prompts": q.get("follow_up_prompts", []),
            "linked_assumption": q.get("linked_assumption"),
            "linked_hypothesis": q.get("linked_hypothesis"),
        }, i)


def render_handoff(question_set):
    """Render an APPROVED question set into a manual Merchant-Voice hand-off:
    copy-paste markdown plus a JSON payload shaped exactly like MV's
    `POST /campaigns/{id}/guides` question input. This is a PROPOSAL a human
    pastes into Merchant Voice's OWN review/approve flow — R10 never calls MV
    (D3). No merchant is contacted; nothing is written to MV here."""
    questions = question_set.get("questions") or []
    payload = [{
        "text": q.get("text"),
        "purpose": q.get("purpose"),
        "question_type": q.get("question_type", "open_text"),
        "follow_up_prompts": q.get("follow_up_prompts", []),
        "linked_assumption": q.get("linked_assumption"),
        "linked_hypothesis": q.get("linked_hypothesis"),
    } for q in questions]
    opp = question_set.get("opportunity_id", "")
    lines = [
        f"# Merchant Voice hand-off — {question_set.get('id', '')} ({opp})",
        "",
        "> **Proposal only.** These reviewer-approved, taxonomy-valid questions "
        "are a DRAFT for a human to create a Merchant Voice guide from, through "
        "Merchant Voice's own campaign/guide review+approval flow. Nothing here "
        "has been sent to Merchant Voice or to any merchant; creating the guide "
        "is a manual step you take in Merchant Voice.",
        "",
    ]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. **{q.get('text', '')}**  ")
        lines.append(f"   purpose: `{q.get('purpose')}` · type: "
                     f"`{q.get('question_type', 'open_text')}`"
                     + (f" · tests: `{q.get('linked_assumption')}`"
                        if q.get("linked_assumption") else ""))
        for fup in q.get("follow_up_prompts") or []:
            lines.append(f"   - follow-up: {fup}")
    if not questions:
        lines.append("_(no questions in this set)_")
    return {"markdown": "\n".join(lines) + "\n", "mv_guide_payload": payload}
