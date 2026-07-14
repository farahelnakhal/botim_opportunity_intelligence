"""Deterministic intent router for the assistant.

The front-end presents a single chat box; the user never picks a "module". This
router maps a natural-language prompt to the read-only data the answer needs and
returns a structured plan: a set of progress *stages* (for the streamed
long-running-task feel) plus the *blocks* (typed cards) to render.

It is intentionally rule-based and transparent — no LLM, no hidden state, no
fabrication. When it cannot map a prompt confidently it says so and offers the
overview, rather than inventing an answer. It performs NO writes and computes NO
scores; every block is built from `serialize.py` outputs (engine truth).
"""

import re

from . import serialize as S

OPP_RE = re.compile(r"\bOPP-?(\d{1,3})\b", re.IGNORECASE)


def _opp_id_in(text):
    m = OPP_RE.search(text or "")
    return f"OPP-{int(m.group(1)):03d}" if m else None


def _find_opp(payload, oid):
    for o in payload["opportunities"] + payload["archived"]:
        if o["id"] == oid:
            return o
    return None


def _match_opp_by_words(payload, text):
    """Loose match on opportunity name words (e.g. 'importer', 'settlement')."""
    t = (text or "").lower()
    best = None
    for o in payload["opportunities"]:
        name = (o.get("name") or "").lower()
        words = [w for w in re.split(r"\W+", name) if len(w) > 4]
        if any(w in t for w in words):
            best = o
            break
    return best


STAGE_SETS = {
    "opportunity": ["Finding evidence", "Scoring opportunity", "Assembling scorecard",
                    "Preparing summary", "Finished"],
    "portfolio": ["Loading portfolio", "Ranking opportunities", "Checking evidence strength",
                  "Preparing summary", "Finished"],
    "commercial": ["Loading model inputs", "Running scenarios", "Computing break-even",
                   "Preparing commercial model", "Finished"],
    "experiments": ["Loading experiment specs", "Checking pre-committed thresholds",
                    "Reading results", "Finished"],
    "monitoring": ["Scanning signals", "Ranking by tier", "Preparing alerts", "Finished"],
    "journal": ["Loading predictions", "Computing calibration", "Scoring Brier", "Finished"],
    "brief": ["Gathering evidence", "Scoring opportunity", "Running assumptions check",
              "Generating commercial model", "Preparing executive summary", "Finished"],
    "generic": ["Understanding request", "Searching knowledge base", "Preparing answer", "Finished"],
}


def route(message, root=None):
    """Return {stages, blocks, intent, text}. Pure read; safe to call anytime."""
    text = (message or "").strip()
    low = text.lower()
    payload = S.build_payload(root)
    oid = _opp_id_in(text) or (_match_opp_by_words(payload, text) or {}).get("id")

    def wrap(intent, blocks, note):
        return {
            "intent": intent,
            "stages": STAGE_SETS.get(intent, STAGE_SETS["generic"]),
            "text": note,
            "blocks": blocks,
            "decision_banner": payload["meta"]["decision_banner"],
        }

    # --- executive brief / recommendation --------------------------------- #
    if any(k in low for k in ("brief", "recommend", "executive summary", "should we build",
                              "decision", "go / no")) :
        target = _find_opp(payload, oid) if oid else (payload["opportunities"][0]
                                                      if payload["opportunities"] else None)
        blocks = []
        if target:
            blocks.append({"type": "executive_summary", "opportunity": target})
            if target.get("brief_envelope"):
                blocks.append({"type": "brief_envelope", "data": target["brief_envelope"]})
            comm = S.commercial_payload(target["id"], root)
            if comm:
                blocks.append({"type": "commercial_model", "data": comm})
        blocks.append({"type": "banner", "text": payload["meta"]["decision_banner"]})
        return wrap("brief", blocks,
                    "Here is the current executive read. It states a decision *requested*, not a "
                    "decision made — no product has been validated or selected.")

    # --- commercial model -------------------------------------------------- #
    if any(k in low for k in ("commercial", "revenue", "cost", "break-even", "breakeven",
                              "roi", "unit economics", "margin", "contribution")):
        target_id = oid or (payload["opportunities"][0]["id"] if payload["opportunities"] else None)
        comm = S.commercial_payload(target_id, root) if target_id else None
        if comm:
            return wrap("commercial", [{"type": "commercial_model", "data": comm}],
                        f"Illustrative unit economics for {comm['name']} across downside / base / "
                        "upside. Planning scenarios, not a forecast.")
        return wrap("commercial", [{"type": "empty", "text": "No committed commercial model for that opportunity yet."}],
                    "No commercial model inputs are committed for that opportunity.")

    # --- experiments / validation ----------------------------------------- #
    if any(k in low for k in ("experiment", "validation", "test", "hypothesis", " ve-", "ve-0")):
        exps = S.experiments_payload(root)
        if oid:
            exps = [e for e in exps if oid.lower() in (e.get("linked_opportunity") or "").lower()] or exps
        return wrap("experiments", [{"type": "experiment", "data": e} for e in exps],
                    f"{len(exps)} validation experiment(s). Each has a pre-committed success and kill "
                    "threshold set before the run.")

    # --- monitoring / alerts ---------------------------------------------- #
    if any(k in low for k in ("monitor", "alert", "signal", "news", "competitor", "watch",
                              "what changed", "whats new", "what's new")):
        mon = S.monitoring_payload(root)
        blocks = [{"type": "monitoring_alert", "data": a} for a in mon["alerts"][:12]]
        if not blocks:
            blocks = [{"type": "feed_item", "data": f} for f in payload["feed"][:12]]
        return wrap("monitoring", blocks or [{"type": "empty", "text": "No monitoring events."}],
                    f"{len(mon['events'])} signals this period, {len(mon['alerts'])} raised as alerts. "
                    "Higher-tier alerts are shown first.")

    # --- decision journal / calibration ----------------------------------- #
    if any(k in low for k in ("journal", "calibration", "brier", "prediction", "forecast track")):
        j = S.journal_payload(root)
        blocks = [{"type": "calibration", "data": j["calibration"]}]
        blocks += [{"type": "decision_journal", "data": p} for p in j["predictions"]]
        return wrap("journal", blocks,
                    "Decision journal with calibration. Brier score is computed over resolved, "
                    "non-excluded predictions only.")

    # --- a specific opportunity ------------------------------------------- #
    if oid:
        target = _find_opp(payload, oid)
        if target:
            blocks = [{"type": "opportunity", "opportunity": target},
                      {"type": "scorecard", "opportunity": target}]
            ev = [e for e in payload["evidence"]
                  if e["ev_id"] in {r["ev_id"] for r in target.get("strongest_evidence", [])}]
            blocks += [{"type": "evidence", "data": e} for e in ev[:4]]
            return wrap("opportunity", blocks,
                        f"{target['name']}. All 17 scoring dimensions are shown below; the "
                        "composite is reference only.")

    # --- portfolio / everything ------------------------------------------- #
    if any(k in low for k in ("portfolio", "opportunit", "rank", "top", "all", "overview",
                              "pipeline", "what do we have")):
        blocks = [{"type": "opportunity", "opportunity": o} for o in payload["opportunities"]]
        blocks.append({"type": "banner", "text": payload["meta"]["decision_banner"]})
        return wrap("portfolio", blocks,
                    f"{len(payload['opportunities'])} live opportunities ranked by raw score, plus "
                    f"{len(payload['archived'])} archived. None has been selected for build.")

    # --- fallback: honest, offers the overview ---------------------------- #
    blocks = [{"type": "opportunity", "opportunity": o} for o in payload["opportunities"][:3]]
    blocks.append({"type": "banner", "text": payload["meta"]["decision_banner"]})
    return wrap("generic", blocks,
                "I route questions to the opportunity, evidence, commercial, experiment, monitoring "
                "and decision-journal models. Here is the top of the portfolio — ask about a specific "
                "opportunity (e.g. OPP-010), its commercial model, experiments, or what changed.")
