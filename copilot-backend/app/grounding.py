"""Grounding: turns tool results into deterministic facts, citations,
confidence, assumptions, unknowns and next actions.

Grounding owns the facts. Scores, classifications, confidence values,
evidence roles, assumption counts and citations come from here (i.e. from the
existing engines/records) — the model synthesizes prose around them and can
never override them.
"""

ROUTE = {"evidence": "/evidence/{id}", "opportunity": "/opportunity/{id}",
         "segment": "/segment/{id}", "inflection": "/inflection/{id}",
         "experiment": "/experiment/{id}", "assumption": "/assumption/{id}"}

NO_DECISION = "No product or build decision has been made."


def _cite(cid, ctype, title, role):
    return {"id": cid, "type": ctype, "title": (title or "")[:160], "role": role,
            "target": {"type": "internal_route", "value": ROUTE[ctype].format(id=cid)}}


class Pack:
    def __init__(self):
        self.facts = []
        self.citations = {}
        self.assumptions = []
        self.unknowns = []
        self.actions = []
        self.warnings = []
        self.conf_sources = {}   # label -> level
        self.needs_no_decision = False
        self.draft = None

    def cite(self, cid, ctype, title, role):
        cur = self.citations.get(cid)
        rank = {"primary": 3, "contradictory": 3, "weak_lead": 2, "contextual": 1, "excluded": 0}
        if cur is None or rank.get(role, 0) > rank.get(cur["role"], 0):
            self.citations[cid] = _cite(cid, ctype, title, role)

    def confidence(self):
        levels = {v for v in self.conf_sources.values() if v}
        if not levels:
            return {"level": "low", "basis": "no graded internal evidence was involved in this answer"}
        level = levels.pop() if len(levels) == 1 else "mixed"
        basis = "; ".join(f"{k}: {v}" for k, v in self.conf_sources.items())
        return {"level": level, "basis": basis}


def _conf_token(text):
    tok = (text or "").split("—")[0].strip().lower()
    return tok if tok in ("high", "medium", "low") else None


def _ev_titles(pack, tools):
    """Titles for evidence ids cited by opportunity views, via the records the
    tools already loaded (never re-parsed here)."""
    for name, result in tools:
        if name == "get_evidence_record":
            yield result["ev_id"], result.get("title", "")


def build(intent, executed, ids):
    """executed: list of (tool_name, result_dict) in execution order."""
    pack = Pack()
    ev_titles = dict(_ev_titles(pack, executed))

    for name, r in executed:
        if name == "list_opportunities":
            pack.facts.append("Portfolio (engine values):")
            for o in r["opportunities"]:
                pack.facts.append(
                    f"- {o['opportunity_id']} {o['name']}: raw {o['raw_score']}, composite "
                    f"{o['composite_score']}, {o['assumption_count']} assumption-based factors"
                    + (" (classification capped at 'promising')" if o["capped"] else "")
                    + f", classification {o['classification']}")
                pack.cite(o["opportunity_id"], "opportunity", o["name"], "contextual")
                pack.conf_sources.setdefault(f"{o['opportunity_id']} assessment",
                                             o.get("evidence_confidence"))
                if o["classification"] in ("promising", None):
                    pack.needs_no_decision = True

        elif name == "compare_opportunities":
            for side in ("a", "b"):
                o = r[side]
                pack.facts.append(
                    f"- {o['opportunity_id']} {o['name']}: raw {o['raw_score']}, composite "
                    f"{o['composite_score']}, {o['assumption_count']} assumptions"
                    + (" (capped)" if o["capped"] else "") + f", {o['classification']}")
                pack.cite(o["opportunity_id"], "opportunity", o["name"], "primary")
                pack.conf_sources[f"{o['opportunity_id']} assessment"] = o.get("evidence_confidence")
                if o["classification"] in ("promising", None):
                    pack.needs_no_decision = True

        elif name == "get_opportunity":
            s = r["score"]
            cap_note = (f" — classification capped at 'promising' because {s['assumption_count']} of 17 "
                        f"factors are assumption-based (cap is {s['assumption_cap']})" if s["capped"] else "")
            pack.facts += [
                f"{r['opportunity_id']} — {r['name']}",
                f"Raw score {s['raw_score']}, composite {s['composite_score']}, "
                f"classification {s['classification']}{cap_note}.",
                f"Unresolved assumptions: {r['assumptions']['unresolved']} of {r['assumptions']['total']}.",
            ]
            if s.get("critical_flags"):
                pack.facts.append("Critical flags: " + "; ".join(s["critical_flags"]) + ".")
            cust = r.get("customer") or {}
            if cust.get("segment_id"):
                pack.facts.append(
                    f"Customer segment: {cust['segment_id']} ({cust.get('segment_title') or ''}) — "
                    f"segment confidence {cust.get('segment_confidence')}.")
                pack.cite(cust["segment_id"], "segment", cust.get("segment_title"), "contextual")
                pack.conf_sources["segment confidence"] = (cust.get("segment_confidence") or "").lower() or None
            if cust.get("job_to_be_done"):
                pack.facts.append(f"Job-to-be-done: {cust['job_to_be_done']}")
            if r["supporting_primary"]:
                pack.facts.append("Primary supporting evidence (behavioural, not weak): "
                                  + ", ".join(r["supporting_primary"]) + ".")
            for ev in r["supporting_primary"]:
                pack.cite(ev, "evidence", ev_titles.get(ev, ""), "primary")
            if r["supporting_leads"]:
                pack.facts.append("Weak leads (context only, NOT primary support): "
                                  + ", ".join(r["supporting_leads"]) + ".")
                for ev in r["supporting_leads"]:
                    pack.cite(ev, "evidence", ev_titles.get(ev, ""), "weak_lead")
            if r["contradicting"]:
                pack.facts.append("Contradictory evidence (preserved): " + ", ".join(r["contradicting"]) + ".")
                for ev in r["contradicting"]:
                    pack.cite(ev, "evidence", ev_titles.get(ev, ""), "contradictory")
            else:
                pack.facts.append("No contradicting evidence is recorded in the register; "
                                  "negative signals appear in the critical flags and risks.")
            for risk in r.get("risks", []):
                pack.facts.append(f"Risk: {risk}.")
            nv = r.get("next_validation") or {}
            if nv.get("text"):
                pack.facts.append(f"Next validation: {nv['text']}")
                pack.actions.append(nv["text"])
                if nv.get("ve"):
                    pack.cite(nv["ve"], "experiment", "validation experiment", "contextual")
            for ip, title in (r.get("inflection_points") or {}).items():
                pack.cite(ip, "inflection", title, "contextual")
            conf = (r.get("confidence") or {}).get("opportunity_assessment", {})
            pack.conf_sources[f"{r['opportunity_id']} assessment"] = conf.get("value")
            pack.cite(r["opportunity_id"], "opportunity", r["name"], "primary")
            if s["classification"] in ("promising", None):
                pack.needs_no_decision = True

        elif name in ("get_assumption_register", "get_opportunity_assumptions"):
            counts = r["counts"]
            pack.facts.append(
                f"Assumptions for {r['opportunity_id']}: {counts['total_assumptions']} tracked, "
                f"{counts['unresolved']} unresolved, {counts['no_supporting_evidence']} with no "
                f"supporting evidence, {counts['contradicted']} contradicted.")
            for a in r["assumptions"]:
                status = a["status"]
                line = (f"- {a['assumption_id']} [{a.get('category', '')}] status={status}, "
                        f"importance={a.get('decision_importance', '')}")
                if a.get("supporting_ev"):
                    line += ", supporting: " + ", ".join(a["supporting_ev"])
                if a.get("contradicting_ev"):
                    line += ", CONTRADICTED by: " + ", ".join(a["contradicting_ev"])
                    for ev in a["contradicting_ev"]:
                        pack.cite(ev, "evidence", ev_titles.get(ev, ""), "contradictory")
                pack.facts.append(line)
                if status in ("untested", "partially_supported"):
                    pack.assumptions.append(f"{a['assumption_id']}: {status}")
                pack.cite(a["assumption_id"], "assumption", a.get("category", ""), "contextual")

        elif name == "get_evidence_record":
            role = "weak_lead" if r["is_weak_lead"] else "primary"
            conf = _conf_token(r.get("evidence_confidence"))
            pack.facts.append(
                f"{r['ev_id']} — {r['title']} (status {r['status']}, confidence "
                f"{r.get('evidence_confidence', '')[:90]}"
                + (", WEAK LEAD — not primary support)" if r["is_weak_lead"] else ")"))
            if r.get("contradictory_evidence"):
                pack.facts.append(f"  Contradiction field: {r['contradictory_evidence'][:200]}")
            pack.cite(r["ev_id"], "evidence", r["title"], role)
            pack.conf_sources[r["ev_id"]] = conf
            if r["is_weak_lead"]:
                pack.warnings.append(f"{r['ev_id']} is a weak lead and was not used as primary support")

        elif name == "get_evidence_gaps":
            pack.facts.append("Top evidence gaps (heuristic priority — reasons shown):")
            for g in r["gaps"][:5]:
                pack.facts.append(f"- P{g['priority_rank']} [{g['priority_band']}] "
                                  f"{g['opportunity_id']}: {g['question']} (why: {'; '.join(g['reasons'][:3])})")
                pack.cite(g["assumption_id"], "assumption", g["statement"], "contextual")
            pack.unknowns += [f"{g['opportunity_id']}: {g['question']}" for g in r["gaps"][:5]]

        elif name == "get_segment":
            pack.facts.append(f"{r['segment_id']} — {r['title']} (confidence {r['confidence']}). "
                              f"Job-to-be-done: {r.get('job_to_be_done') or 'see profile'}")
            pack.cite(r["segment_id"], "segment", r["title"], "primary")
            pack.conf_sources["segment confidence"] = (r.get("confidence") or "").lower() or None

        elif name == "get_inflection_point":
            pack.facts.append(f"{r['ip_id']} — {r['title']} (status {r['status']}).")
            pack.cite(r["ip_id"], "inflection", r["title"], "contextual")

        elif name == "get_competitor_evidence":
            pack.facts.append(f"Competitor {r['competitor']}: {r['title']}"
                              + (f" — gaps: {r['gaps']}" if r.get("gaps") else ""))

        elif name == "get_validation_experiment":
            m = "; ".join(f"{x['name']} (pass {x['success']['op']}{x['success']['value']}, "
                          f"fail {x['failure']['op']}{x['failure']['value']})"
                          for x in r["metrics"] if x.get("success") and x.get("failure"))
            pack.facts.append(f"{r['ve_id']} validates {r['proposition']}: {m}.")
            pack.cite(r["ve_id"], "experiment", f"validates {r['proposition']}", "primary")

        elif name in ("get_executive_brief", "generate_executive_brief"):
            md = r.get("markdown") or r.get("draft", {}).get("markdown", "")
            pack.facts.append(md.strip())
            if name == "generate_executive_brief":
                pack.draft = r
            brief_json = r.get("json") or {}
            opp = brief_json.get("opportunity", {})
            if opp.get("opportunity_id"):
                pack.cite(opp["opportunity_id"], "opportunity", opp.get("name", ""), "primary")
                conf = (brief_json.get("confidence") or {}).get("opportunity_assessment", {})
                pack.conf_sources[f"{opp['opportunity_id']} assessment"] = conf.get("value")
                unresolved = (brief_json.get("assumptions") or {}).get("unresolved")
                if unresolved:
                    pack.assumptions.append(f"{unresolved} scorecard assumptions remain unresolved")
                for act in [ (brief_json.get("recommended_action") or {}).get("text") ]:
                    if act:
                        pack.actions.append(act)
            pack.needs_no_decision = True

        elif name == "get_recent_changes":
            if not r["changes"]:
                pack.facts.append("No recorded changes in score history or monitoring yet.")
            else:
                pack.facts.append("Recent changes (score history + monitoring):")
                for c in r["changes"][-10:]:
                    label = " [simulated fixture]" if c.get("simulated_fixture") else ""
                    pack.facts.append(f"- {c.get('timestamp', '?')} {c.get('source')}: "
                                      f"{c.get('summary', '')}{label}")

        elif name == "get_score_history":
            if r["entries"]:
                for e in r["entries"][-5:]:
                    pack.facts.append(f"- {e.get('timestamp')}: {e.get('kind')} {e.get('explanation', '')}")
            else:
                pack.facts.append(f"No score-history entries for {r['opportunity_id']}.")

        elif name == "search_product_knowledge":
            if r["results"]:
                pack.facts.append("Related records found:")
                for hit in r["results"][:6]:
                    pack.facts.append(f"- {hit['id']} ({hit['type']}): {hit['title'][:100]}")
                    ctype = hit["type"] if hit["type"] in ROUTE else "evidence"
                    pack.cite(hit["id"], ctype, hit["title"], "contextual")
            else:
                pack.unknowns.append(f"no internal records matched: {r['query'][:80]}")

        elif name == "generate_research_request_draft":
            d = r["draft"]
            pack.draft = r
            pack.facts.append(
                f"Draft research request {d['request_id']} (status: draft, ephemeral — "
                f"not added to any backlog): {d['question']} Required evidence: {d['required_evidence']}")
            pack.actions.append(f"Review draft research request {d['request_id']} with Part A")

        elif name == "generate_impact_proposal_draft":
            pack.draft = r
            s = r["draft"]["payload"]["score_summary"]
            pack.facts.append(
                f"Draft impact proposal (ephemeral, not persisted, not appliable from chat): raw "
                f"{s['raw_score_prev']}→{s['raw_score_new']}/85. A human must run the real impact workflow.")
            pack.warnings.append("impact-proposal draft is ephemeral; nothing was written or applied")

    # intent-level discipline epilogues (deterministic, not model-generated)
    if intent == "challenge_hypothesis":
        pack.facts.append(
            "Hypothesis discipline: the proposition under challenge remains a hypothesis — "
            "no product has been selected on the basis of this evidence. Validation before "
            "any development is recommended.")
        pack.actions.append("Run the linked validation experiment(s) before any build decision")
        pack.needs_no_decision = True

    return pack
