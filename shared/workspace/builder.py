"""Workspace build orchestrator (Phase R5, PR4) — the full analysis chain.

One build = one new workspace version running the chain the platform already
has, composed end to end:

  1. KB context   — related committed evidence records (kb_context.py;
                    deterministic keyword overlap, read-only).
  2. Research     — a bounded external research run (shared/research
                    runner) from queries derived ONLY from the opportunity's
                    own fields + the question. No search provider ⇒ the step
                    is skipped with an honest gap, never fabricated.
  3. Extraction   — PR3 claim extraction over the run's recorded sources
                    (model proposes, deterministic validation disposes);
                    accepted claims land `pending_review` in the research
                    store. No model ⇒ honest gap.
  4. Scoring      — a synthetic ALL-ASSUMPTION scorecard evaluated by the
                    REAL engine (opportunity_engine.scoring.evaluate), the
                    same pattern as generate.py: because every dimension is
                    an assumption, the engine itself caps the result at
                    "promising" — a workspace build can never come out
                    validated or "strong". Labelled preliminary.

The chain runs only on explicit triggers (store.TRIGGERS); ordinary chat
follow-ups read the latest complete version instead. Honest partial
outcomes: a missing provider or an empty result is recorded as a gap on a
COMPLETE version — the version fails only when the build itself breaks.
"""

import sys
from pathlib import Path

from .kb_context import search_kb_context
from .store import DEFAULT_KEEP, TRIGGERS, WorkspaceStoreError

REPO = Path(__file__).resolve().parents[2]
_TOOLS = REPO / "opportunity-intelligence" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

MAX_QUERIES = 8
PRELIMINARY_BASIS = ("preliminary default — not yet assessed; assign after "
                     "reviewing the workspace's evidence and claims")


def build_queries(opportunity, question=None, max_queries=MAX_QUERIES):
    """Deterministic, bounded research queries from the opportunity's OWN
    fields (+ the user's question). No market, product, or segment is ever
    hardcoded here — a workspace build works for any opportunity profile."""
    title = (opportunity.get("title") or "").strip()
    segment = (opportunity.get("target_segment") or "").strip()
    problem = (opportunity.get("problem_statement") or "").strip()
    queries = []
    if question and question.strip():
        queries.append(("question", question.strip()[:400]))
    if title:
        queries.append(("market size", f"{title} market size statistics"))
        queries.append(("competitors", f"{title} competitors providers comparison"))
    if title and segment:
        queries.append(("customer need", f"{segment} {title} pain points problems"))
    elif problem:
        queries.append(("customer need", problem[:200]))
    if title:
        queries.append(("regulation", f"{title} regulation licensing requirements"))
    return queries[:max(1, int(max_queries))]


def _preliminary_score(opportunity_id, kb_hits, accepted_claims):
    """Synthetic all-assumption scorecard through the REAL scoring engine.
    Every dimension is an explicit assumption (score 3, no evidence mapped),
    so the engine's own assumption cap applies — the classification can
    never exceed 'promising'. The counts of real inputs found by this build
    travel alongside for the reader; they never inflate the score."""
    from opportunity_engine import scoring

    card = {"opportunity_id": "OPP-000" if not opportunity_id.startswith("OPP-") else opportunity_id,
            "scores": {d: {"score": 3, "assumption": True, "basis": PRELIMINARY_BASIS}
                       for d in scoring.DIMENSIONS}}
    ev = scoring.evaluate(card)  # SINGLE SOURCE OF TRUTH — the engine scores it
    return {
        "preliminary": True,
        "engine": "opportunity_engine.scoring",
        "composite": ev["composite_indicative"],
        "assumption_count": ev["assumption_count"],
        "assumption_capped": ev["assumption_capped"],
        "max_classification": ev["max_classification"],
        "classification": "promising (preliminary, unvalidated)",
        "confidence": "low",
        "basis_note": ("all 17 dimensions are assumption-based defaults in this "
                       "workspace version — the engine caps the classification; "
                       "scores change only through the human impact workflow"),
        "inputs_found": {"kb_evidence_records": kb_hits,
                         "accepted_candidate_claims": accepted_claims},
    }


def build_workspace(ws_store, research_store, opportunity, *, trigger,
                    question=None, search_provider=None, llm_provider=None,
                    llm_config=None, kb_records=None, execute_run_fn=None,
                    keep=DEFAULT_KEEP):
    """Run the full chain and return the finished workspace version dict.

    `opportunity` is the saved opportunity dict (needs at least `id` and
    `title`). Providers are INJECTED by the caller (routes resolve them from
    the environment; tests inject stubs) — a missing provider produces an
    honest gap, never a fabricated step. Unexpected build errors finish the
    version as `failed` with the reason and re-raise."""
    if trigger not in TRIGGERS:
        raise WorkspaceStoreError(f"trigger must be one of {list(TRIGGERS)}")
    opp_id = opportunity.get("id") or ""
    version = ws_store.create_version(opp_id, trigger, question=question)

    gaps, claim_ids, run_id = [], [], None
    extraction_model = None
    try:
        # 1. KB context — related committed evidence (read-only)
        kb_matches = search_kb_context(
            " ".join(p for p in (question, opportunity.get("title"),
                                 opportunity.get("target_segment"),
                                 opportunity.get("problem_statement")) if p),
            records=kb_records)
        if not kb_matches:
            gaps.append("no related internal evidence records matched — this "
                        "analysis has no committed KB support yet")

        # 2. External research — bounded run, or an honest gap
        queries = build_queries(opportunity, question)
        if search_provider is None:
            gaps.append("external research skipped: no search provider configured "
                        "(set RESEARCH_SEARCH_PROVIDER)")
        elif not queries:
            gaps.append("external research skipped: the opportunity has no title "
                        "or fields to derive queries from")
        else:
            from shared.research.runner import execute_run as default_execute
            execute = execute_run_fn or default_execute
            run = research_store.create_run({
                "title": f"Workspace analysis: {opportunity.get('title', opp_id)}"[:200],
                "objective": "analysis workspace build",
                "opportunity_ref": opp_id or None,
                "profile": "workspace",
            })
            for objective, query_text in queries:
                research_store.add_query(run["id"], {"objective": objective,
                                                     "query_text": query_text[:4000]})
            finished = execute(research_store, run["id"], search_provider)
            run_id = finished["id"]
            if finished["status"] == "failed":
                gaps.append(f"external research failed: {finished['error']}")
            elif finished["status"] == "partial":
                gaps.append(f"external research was partial: {finished['error']}")

            # 3. Claim extraction (PR3) — only over a run that found sources
            if finished["status"] in ("complete", "partial"):
                if llm_provider is None:
                    gaps.append("claim extraction skipped: no model provider "
                                "configured (set BOTIM_LLM_API_KEY) — sources were "
                                "recorded but no candidate claims were proposed")
                else:
                    from shared.research.extract import extract_claims
                    summary = extract_claims(research_store, run_id,
                                             llm_provider, llm_config)
                    claim_ids = summary.get("candidate_ids", [])
                    extraction_model = getattr(llm_config, "model", None)
                    if summary.get("note"):
                        gaps.append(f"claim extraction: {summary['note']}")
                    elif not claim_ids and summary.get("proposed"):
                        gaps.append("no proposed claims survived deterministic "
                                    "source verification")
                    elif not claim_ids:
                        gaps.append("the extraction model proposed no claims "
                                    "from the recorded sources")

        # 4. Preliminary score through the real engine
        score = _preliminary_score(opp_id, len(kb_matches), len(claim_ids))

        provenance = {
            "question": question, "trigger": trigger,
            "queries": [q for _, q in queries],
            "kb_record_ids": [m["id"] for m in kb_matches],
            "research_run_id": run_id,
            "search_provider": type(search_provider).__name__ if search_provider else None,
            "extraction_model": extraction_model,
            "builder": "shared.workspace.builder/v1",
        }
        finished_version = ws_store.complete_version(
            version["id"], kb_evidence=kb_matches, claim_ids=claim_ids,
            preliminary_score=score, gaps=gaps, provenance=provenance,
            research_run_id=run_id)
        ws_store.prune(opp_id, keep=keep)
        return finished_version
    except Exception as exc:
        ws_store.fail_version(version["id"],
                              f"workspace build error: {type(exc).__name__}: {exc}")
        raise
