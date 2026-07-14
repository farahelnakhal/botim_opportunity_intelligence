"""On-demand opportunity analysis for ANY market — not just the committed SME set.

A new conversation describes an opportunity in free text; this module turns it
into a structured, first-pass analysis: segment, job-to-be-done, hypothesis, a
full 17-dimension scorecard, evidence gaps, and a customer-research/validation
plan.

Honesty is enforced by construction, not by trusting the model:
  * Every dimension of a generated scorecard is marked `assumption = true` —
    there is no evidence yet — so the REAL engine (`scoring.evaluate`) caps the
    classification at "promising (unvalidated)". A generated opportunity can
    never come out "strong".
  * The engine, not the LLM, computes the composite, assumption count, and
    critical flags. The LLM proposes scores and reasoning; the single source of
    truth still scores them.
  * Nothing is written to the knowledge base. The result is ephemeral analysis.

Engine: Claude (Anthropic API) when ANTHROPIC_API_KEY is set; otherwise a
deterministic offline scaffold that produces the same shape (a frame to run the
analysis yourself), clearly labelled.
"""

import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO / "opportunity-intelligence" / "tools"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from opportunity_engine import scoring  # noqa: E402

DECISION_BANNER = "No product or build decision has been made."
DIMENSIONS = list(scoring.DIMENSIONS)

STAGES = ["Understanding the opportunity", "Searching comparable markets",
          "Mapping customer pain", "Scoring 17 dimensions", "Finding evidence gaps",
          "Drafting a validation plan", "Finished"]

# --- LLM config (the user sets these in their own environment) -------------- #
# Three ways to run, chosen automatically in this order:
#   1. Anthropic (cloud, needs a key): ANTHROPIC_API_KEY
#   2. Any OpenAI-compatible endpoint — local (Ollama, LM Studio) OR a free
#      cloud API (e.g. Groq — no card required, an OpenAI-compatible endpoint
#      at https://api.groq.com/openai/v1): set BOTIM_LLM_BASE_URL (+ API key
#      if the provider needs one).
#   3. Deterministic offline scaffold (no setup at all).
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
# Deliberately NOT reusing this session's ANTHROPIC_BASE_URL (an internal proxy):
# a self-hosted deployment should hit the public API with its own key.
BASE_URL = os.environ.get("BOTIM_ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
MODEL = os.environ.get("BOTIM_ANALYSIS_MODEL", "claude-sonnet-5")

# Any OpenAI-compatible /chat/completions endpoint — self-hosted (Ollama) or a
# free hosted provider (Groq, etc). LOCAL_KEY defaults to a placeholder that
# works for Ollama (which ignores it); set BOTIM_LLM_API_KEY for providers that
# require a real key.
LOCAL_BASE_URL = os.environ.get("BOTIM_LLM_BASE_URL", "").rstrip("/")
LOCAL_MODEL = os.environ.get("BOTIM_LLM_MODEL", "llama3.1")
LOCAL_KEY = os.environ.get("BOTIM_LLM_API_KEY", "ollama")


def provider():
    """Which engine will answer: 'claude' | 'local' | 'scaffold'."""
    if API_KEY:
        return "claude"
    if LOCAL_BASE_URL:
        return "local"
    return "scaffold"

_SYSTEM = (
    "You are a rigorous, skeptical product-opportunity analyst for BOTIM, the UAE super-app "
    "by AstraTech (messaging + payments + fintech). Given any market or product idea, produce a "
    "first-pass opportunity analysis grounded in how a real analyst would reason about customer "
    "pain, willingness to pay, distribution, credit, and defensibility.\n\n"
    "CRITICAL HONESTY RULES:\n"
    "- This is an UNVALIDATED HYPOTHESIS. Never claim demand is proven or a product is validated "
    "or selected. Frame everything as what must still be tested.\n"
    "- Do NOT invent citations, evidence IDs, statistics presented as measured, or customer quotes. "
    "Reason from plausible priors and clearly-labelled assumptions only.\n"
    "- Scores are your prior estimates to be tested, not findings.\n"
    "- Be balanced: include genuine disconfirming evidence and rejection conditions.\n\n"
    "Return STRICT JSON only (no prose, no markdown fences) with exactly these keys:\n"
    '{\n'
    '  "name": string (concise opportunity title),\n'
    '  "segment": string (specific target customer segment),\n'
    '  "jtbd": string (the job-to-be-done, one sentence),\n'
    '  "hypothesis": string (2-4 sentences: who, pain, proposed solution, why BOTIM),\n'
    '  "is_lending_product": boolean,\n'
    '  "contradictory_evidence": string (what would/does argue against this),\n'
    '  "rejection_conditions": string (what result would kill it),\n'
    '  "scores": { <each of the 17 dimension keys>: { "score": 1-5 integer, "basis": short rationale } },\n'
    '  "research_questions": [ 5-7 non-leading customer-interview questions ],\n'
    '  "evidence_gaps": [ 4-6 specific unknowns that must be validated before building ]\n'
    "}\n"
    "The 17 dimension keys are EXACTLY: " + ", ".join(DIMENSIONS) + "."
)


def _gen_id(prompt):
    h = hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()[:4].upper()
    return f"GEN-{h}"


_last_error = None  # surfaced to help the user debug their key/config


def _history_messages(prompt, history):
    """Build a role/content message list from prior turns + the new prompt."""
    msgs = []
    for h in (history or []):
        content = str(h.get("content") or h.get("text") or "").strip()
        if not content:
            continue
        msgs.append({"role": "assistant" if h.get("role") == "assistant" else "user",
                     "content": content[:4000]})
    msgs.append({"role": "user", "content": f"Analyze/refine this opportunity for BOTIM:\n\n{prompt}"})
    return msgs


def _extract_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    # tolerate leading/trailing prose from smaller local models: grab the outer {...}
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _call_anthropic(messages, timeout):
    body = json.dumps({"model": MODEL, "max_tokens": 2000, "system": _SYSTEM,
                       "messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": API_KEY,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read())
    text = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
    return _extract_json(text)


def _call_openai_compatible(messages, timeout):
    """Ollama / LM Studio / any OpenAI-compatible /chat/completions endpoint. No key needed for Ollama."""
    body = json.dumps({
        "model": LOCAL_MODEL,
        "messages": [{"role": "system", "content": _SYSTEM}] + messages,
        "temperature": 0.4,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{LOCAL_BASE_URL}/chat/completions", data=body, method="POST",
        headers={"content-type": "application/json", "authorization": f"Bearer {LOCAL_KEY}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read())
    text = payload["choices"][0]["message"]["content"]
    return _extract_json(text)


def _call_llm(prompt, history=None, timeout=90):
    """Return parsed JSON from the configured LLM, or None on any failure."""
    global _last_error
    _last_error = None
    p = provider()
    if p == "scaffold":
        return None
    messages = _history_messages(prompt, history)
    try:
        return _call_anthropic(messages, timeout) if p == "claude" else _call_openai_compatible(messages, timeout)
    except Exception as exc:
        _last_error = f"{type(exc).__name__}: {exc}"
        return None


def _scaffold(prompt):
    """Deterministic offline analysis frame — honest, obviously a starting point."""
    title = prompt.strip().rstrip(".")
    if len(title) > 80:
        title = title[:77] + "…"
    lending = bool(re.search(r"\b(credit|lend|loan|financ|working capital|bnpl|factoring)\b", prompt, re.I))
    scores = {d: {"score": 3, "basis": "Not yet assessed — assign after first customer interviews."}
              for d in DIMENSIONS}
    return {
        "name": title[:1].upper() + title[1:],
        "segment": "To be defined — narrow to a specific, reachable customer segment first.",
        "jtbd": "To be articulated from customer interviews (what job are they hiring this to do?).",
        "hypothesis": (f"Unvalidated hypothesis derived from your prompt: \"{title}\". "
                       "No evidence has been gathered yet — every dimension below is an assumption to test."),
        "is_lending_product": lending,
        "contradictory_evidence": "None gathered yet. Actively seek disconfirming evidence before proceeding.",
        "rejection_conditions": "Define a pre-committed kill threshold before running any experiment.",
        "scores": scores,
        "research_questions": [
            "Walk me through the last time you faced this problem — what did you do?",
            "What did that cost you (time, money, missed opportunities)?",
            "What have you tried to solve it, and what happened?",
            "Who else is involved in that decision?",
            "What would have to be true for you to switch to a new solution?",
        ],
        "evidence_gaps": [
            "Is the pain frequent and severe enough to drive switching?",
            "Is there observed willingness to pay, not just stated interest?",
            "Does BOTIM have a real distribution or data advantage here?",
            "What is the true competitive gap, and how long does it stay open?",
        ],
    }


def _build_opportunity(prompt, data, engine):
    # Force every dimension to assumption=true: a generated scorecard has no
    # evidence records, so the engine will cap the classification honestly.
    card_scores = {}
    for d in DIMENSIONS:
        entry = (data.get("scores") or {}).get(d) or {}
        raw = entry.get("score", 3)
        try:
            s = int(round(float(raw)))
        except (TypeError, ValueError):
            s = 3
        s = max(1, min(5, s))
        card_scores[d] = {"score": s, "assumption": True, "basis": str(entry.get("basis", ""))[:400]}

    oid = _gen_id(prompt)
    card = {"opportunity_id": oid, "name": data.get("name", prompt)[:160],
            "is_lending_product": bool(data.get("is_lending_product", True)),
            "scores": card_scores}
    ev = scoring.evaluate(card)  # SINGLE SOURCE OF TRUTH — engine scores it

    composite = ev["composite_indicative"]
    # capped at 'promising' because all 17 are assumptions; honest downgrade to 'weak' if weak.
    classification = "weak" if composite < 3.0 else "promising"
    factors = [{"key": d, "score": card_scores[d]["score"], "assumption": True,
                "basis": card_scores[d]["basis"], "evidence_ids": []} for d in DIMENSIONS]

    return {
        "id": oid,
        "name": card["name"],
        "raw_score": sum(f["score"] for f in factors),
        "raw_max": 5 * len(DIMENSIONS),
        "composite": composite,
        "classification": classification,
        "classification_label": "Promising (unvalidated)" if classification == "promising" else "Weak / needs work",
        "confidence": "low",  # nothing is validated yet
        "assumption_count": ev["assumption_count"],
        "factors": factors,
        "critical_flags": ev["critical_flags"],
        "segment": data.get("segment", "—"),
        "jtbd": data.get("jtbd", "—"),
        "hypothesis": data.get("hypothesis", "—"),
        "strongest_evidence": [],
        "contradictory_evidence": data.get("contradictory_evidence", "—"),
        "rejection_conditions": data.get("rejection_conditions", "—"),
        "validation_plan": "; ".join((data.get("research_questions") or [])[:3]) or "—",
        "score_history": [],
        "latest_change": "Generated from a new-conversation prompt (unvalidated)",
        "latest_alert": "—",
        "next_action": (data.get("research_questions") or ["Run first customer interviews."])[0],
        "profile_path": "(generated — not committed to the knowledge base)",
        "is_archived": False,
        "impact_history": [],
        "brief_envelope": None,
        "generated": True,
        "engine": engine,
    }


def analyze(prompt, root=None, history=None):  # noqa: ARG001 (root kept for signature parity)
    prompt = (prompt or "").strip()
    if not prompt:
        return {"intent": "new_analysis", "stages": STAGES, "decision_banner": DECISION_BANNER,
                "text": "Describe an opportunity or market to analyze.",
                "blocks": [{"type": "empty", "text": "Nothing to analyze yet."}],
                "generated_opportunity": None}

    data = _call_llm(prompt, history)
    engine = provider()  # 'claude' | 'local' | 'scaffold'
    if data is None:
        data = _scaffold(prompt)
        engine = "scaffold"
    opp = _build_opportunity(prompt, data, engine)

    if engine == "claude":
        engine_note = "Generated by Claude — an unvalidated first-pass hypothesis. "
    elif engine == "local":
        engine_note = f"Generated by {LOCAL_MODEL} — an unvalidated first-pass hypothesis. "
    elif provider() != "scaffold" and _last_error:
        engine_note = (f"The model call failed ({_last_error}); showing an offline scaffold instead. ")
    else:
        engine_note = "Offline scaffold (no model configured) — a frame to run the analysis yourself. "
    blocks = [
        {"type": "opportunity", "opportunity": opp},
        {"type": "scorecard", "opportunity": opp},
        {"type": "research_plan", "data": {
            "questions": data.get("research_questions", []),
            "gaps": data.get("evidence_gaps", []),
        }},
        {"type": "banner", "text": DECISION_BANNER},
    ]
    text = (f"{engine_note}I analysed “{opp['name']}” and scored all 17 dimensions "
            f"(composite {opp['composite']} — capped at “promising, unvalidated” because every "
            "dimension is an assumption with no evidence yet). Below is the scorecard and a "
            "customer-research plan to start closing the biggest gaps.")
    return {"intent": "new_analysis", "stages": STAGES, "decision_banner": DECISION_BANNER,
            "text": text, "blocks": blocks, "generated_opportunity": opp}
