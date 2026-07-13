"""Read-only bridge to the Evidence-Impact Workflow (`impact/`).

The impact module is the authoritative source for assumption status/sensitivity/
validation-method/owner, executive briefs, score history, and proposals — data
the UI previously could only approximate. This bridge consumes it read-only and
degrades gracefully: any failure (impact absent, empty data, unexpected shape)
returns an empty result so the adapter falls back to its scorecard-derived view
and the UI never breaks. It never writes; `impact.apply`/`rollback` are never
imported here.

`now` is a fixed timestamp so builds and tests are deterministic.
"""

from pathlib import Path

NOW = "2026-07-13T00:00:00Z"


def _impact(root):
    """Import the impact package and point it at `root`. None if unavailable."""
    import sys
    r = str(Path(root).resolve())
    if r not in sys.path:
        sys.path.insert(0, r)
    try:
        from impact import brief, gaps, history, paths, proposal, tracker, uicontract  # noqa: F401
        paths.set_repo_root(root)
        return {"brief": brief, "gaps": gaps, "history": history, "paths": paths,
                "tracker": tracker, "uicontract": uicontract, "proposal": proposal}
    except Exception:
        return None


def available(root):
    return _impact(root) is not None


def assumptions_by_opp(root, opp_ids, now=NOW):
    """{opp_id: [tracker assumption dicts]} — authoritative status/sensitivity/
    validation-method/owner. {} if impact unavailable."""
    imp = _impact(root)
    if not imp:
        return {}
    out = {}
    for oid in opp_ids:
        try:
            model = imp["tracker"].build(oid, now)
            out[oid] = model.get("assumptions", [])
        except Exception:
            continue
    return out


def brief_envelopes(root, opp_ids, now=NOW):
    """{opp_id: uicontract envelope dict}. Skips opps whose brief can't build."""
    imp = _impact(root)
    if not imp:
        return {}
    out = {}
    for oid in opp_ids:
        try:
            view = imp["brief"].build_view(oid, now)
            out[oid] = imp["uicontract"].envelope(view)
        except Exception:
            continue
    return out


def history_by_opp(root):
    """{opp_id: [history entries newest-first]}. {} if unavailable/empty."""
    imp = _impact(root)
    if not imp:
        return {}
    try:
        entries = imp["history"].read_all()
    except Exception:
        return {}
    out = {}
    for e in entries:
        out.setdefault(e.get("opportunity_id"), []).append(e)
    for oid in out:
        out[oid] = list(reversed(out[oid]))
    return out


def proposals(root):
    """Pending/handled impact proposals from knowledge-base/impact/proposals/.
    [] if none. Read-only file listing; no approval action is ever taken."""
    imp = _impact(root)
    if not imp:
        return []
    import json
    pdir = imp["paths"].PROPOSALS_DIR
    out = []
    if pdir and Path(pdir).is_dir():
        for p in sorted(Path(pdir).glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            s = d.get("payload", {}).get("score_summary", {})
            out.append({
                "id": d.get("proposal_id", p.stem),
                "opportunity_id": s.get("opportunity_id", "—"),
                "score_before": s.get("raw_score_prev", "—"),
                "score_after": s.get("raw_score_new", "—"),
                "status": d.get("status", "pending"),
            })
    return out
