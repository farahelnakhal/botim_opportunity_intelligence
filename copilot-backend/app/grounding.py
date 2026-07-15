"""Grounding: turns tool results into deterministic facts, citations,
confidence, assumptions, unknowns and next actions.

Grounding owns the facts. Scores, classifications, confidence values,
evidence roles, assumption counts and citations come from here (i.e. from the
existing engines/records) — the model synthesizes prose around them and can
never override them.
"""

ROUTE = {"evidence": "/evidence/{id}", "opportunity": "/opportunity/{id}",
         "segment": "/segment/{id}", "inflection": "/inflection/{id}",
         "experiment": "/experiment/{id}", "assumption": "/assumption/{id}",
         # Merchant Voice (Phase 5) — an approved, published finding. Never
         # authoritative Part A evidence; never an EV-typed citation.
         "merchant_finding": "/merchant-findings/{id}",
         # Integration Phase 2 — additive citation type (competitor profiles
         # surfaced by search_product_knowledge for new-opportunity analysis).
         "competitor": "/competitor/{id}"}

NO_DECISION = "No product or build decision has been made."
NOT_VALIDATION = ("A concept reaction is a reaction to a proposed concept, not independent proof that the "
                  "underlying pain, its frequency, or willingness to pay have been established.")


def _cite(cid, ctype, title, role, metadata=None):
    return {"id": cid, "type": ctype, "title": (title or "")[:160], "role": role,
            "target": {"type": "internal_route", "value": ROUTE[ctype].format(id=cid)},
            "metadata": metadata}


def _finding_metadata(f):
    return {"campaign_id": f["campaign_id"], "method": f["method"], "segment_id": f["segment_id"],
           "strength_band": f["strength_band"], "support_count": f["support_count"],
           "contradiction_count": f["contradiction_count"], "denominator": f["denominator"],
           "denominator_definition": f["denominator_definition"]}


def _finding_role(f):
    if f["finding_type"] == "contradiction":
        return "contradictory"
    if f["finding_type"] == "concept_reaction":
        return "concept_reaction"
    if f["strength_band"] in ("insufficient", "single_signal"):
        return "weak_lead"
    return "primary"


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

    def cite(self, cid, ctype, title, role, metadata=None):
        cur = self.citations.get(cid)
        rank = {"primary": 3, "contradictory": 3, "weak_lead": 2, "concept_reaction": 2,
               "contextual": 1, "excluded": 0}
        if cur is None or rank.get(role, 0) > rank.get(cur["role"], 0):
            self.citations[cid] = _cite(cid, ctype, title, role, metadata=metadata)

    def cite_research_candidate(self, c):
        """Phase R3 — an approved external-research candidate. The citation
        opens the run detail (claim -> sources -> run traceability lives
        there); metadata carries the source URLs/freshness so the UI can
        label it external without another fetch."""
        cid = c["candidate_id"]
        if cid not in self.citations:
            self.citations[cid] = {
                "id": cid, "type": "research_candidate",
                "title": (c.get("claim") or "")[:160],
                "role": "external_research",
                "target": {"type": "internal_route",
                           "value": f"/research/runs/{c['run_id']}"},
                "metadata": {"run_id": c["run_id"], "run_title": c.get("run_title"),
                             "external": True,
                             "sources": [{"url": s.get("url"), "title": s.get("title"),
                                          "published_at": s.get("published_at"),
                                          "freshness_status": s.get("freshness_status")}
                                         for s in (c.get("sources") or [])[:5]]},
            }

    def cite_merchant_finding(self, f):
        self.cite(f["finding_id"], "merchant_finding", f["approved_statement"], _finding_role(f),
                  metadata=_finding_metadata(f))
        if f["finding_type"] == "concept_reaction":
            self.warnings.append(
                f"{f['finding_id']} is a concept reaction — not independent proof of pain, frequency, "
                "or willingness to pay")
        if f["contradiction_count"] > 0:
            self.warnings.append(
                f"{f['finding_id']} has {f['contradiction_count']} contradicting observation(s) preserved "
                "— not silently dropped")

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


# citation-metadata fields exposed for evidence provenance (Phase 4).
# Deliberately bounded: no filesystem paths, no raw prompts/traces, no
# identity data — only the source/date/freshness fields the contract lists.
_EVIDENCE_META_FIELDS = (
    "source_title", "source_url", "publisher", "publication_date",
    "retrieved_at", "last_verified_at", "access_label",
    "freshness_status", "freshness_reason",
)


def _evidence_metadata(prov):
    meta = {k: prov.get(k) for k in _EVIDENCE_META_FIELDS}
    excerpt = prov.get("excerpt")
    meta["excerpt"] = excerpt[:300] if isinstance(excerpt, str) else None
    return meta


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
    # Phase 4 — deterministic freshness per cited evidence id, collected from
    # tool results only (get_evidence_record provenance / get_opportunity
    # evidence_freshness). Used for deduplicated stale warnings below.
    ev_freshness = {}

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
            for ev_id, f in (r.get("evidence_freshness") or {}).items():
                ev_freshness.setdefault(ev_id, f)
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
            prov = r.get("provenance") or {}
            pack.cite(r["ev_id"], "evidence", r["title"], role,
                      metadata=_evidence_metadata(prov) if prov else None)
            if prov:
                ev_freshness.setdefault(r["ev_id"], prov)
                pack.facts.append(
                    f"  Provenance: source {prov.get('source_title') or 'internal record (no external source)'}"
                    f", freshness {prov.get('freshness_status')} — {prov.get('freshness_reason')}")
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

        elif name == "get_external_research":
            # Phase R3 — human-approved external web-research candidates.
            # Always presented as EXTERNAL and non-authoritative; stale
            # sources are flagged deterministically (shared/freshness bands).
            cands = r.get("approved_candidates") or []
            if not cands:
                pack.facts.append("No approved external research candidates exist yet "
                                  "(run and review external research first).")
                pack.unknowns.append("no approved external-research candidates matched "
                                     "(get_external_research)")
            else:
                pack.facts.append("EXTERNAL RESEARCH — human-approved candidate claims "
                                  "from web research (external; NOT authoritative "
                                  "repository evidence; no EV id exists):")
                stale = 0
                for c in cands[:10]:
                    srcs = c.get("sources") or []
                    src_bits = []
                    for s in srcs[:4]:
                        bit = s.get("title") or s.get("domain") or s.get("url")
                        if s.get("published_at"):
                            bit += f" ({str(s['published_at'])[:10]})"
                        if s.get("freshness_status") == "stale":
                            bit += " [STALE]"
                            stale += 1
                        src_bits.append(bit)
                    pack.facts.append(f"- {c['claim']} — sources: {'; '.join(src_bits) or 'recorded'}")
                    if c.get("contradicts"):
                        pack.facts.append(f"  (recorded contradiction note: {c['contradicts']})")
                    pack.cite_research_candidate(c)
                if stale:
                    pack.warnings.append(
                        f"{stale} cited external source(s) are stale (older than the "
                        f"180-day threshold) — re-run research before relying on them.")
                pack.conf_sources["external research (candidate)"] = "low"
            pack.needs_no_decision = True

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

        elif name == "list_merchant_campaigns":
            if r["campaigns"]:
                pack.facts.append("Merchant Voice campaigns with published findings:")
                for c in r["campaigns"]:
                    pack.facts.append(f"- {c['campaign_id']} ({c['method']}): "
                                      f"{c['published_finding_count']} published finding(s)")
            else:
                pack.unknowns.append("no Merchant Voice campaigns have a published finding yet")

        elif name == "get_merchant_campaign":
            pack.facts.append(f"{r['campaign_id']} — {r['title']} ({r['method']}): "
                              f"{r['published_finding_count']} published finding(s)")

        elif name == "get_campaign_summary":
            if not r["findings_by_type"]:
                pack.unknowns.append(f"no published Merchant Voice findings for {r['campaign_id']}")
            for finding_type, entries in r["findings_by_type"].items():
                pack.facts.append(f"{r['campaign_id']} ({r['method']}) — {finding_type}:")
                for f in entries:
                    pack.facts.append(f"- {f['numerator']} of {f['denominator']} {f['denominator_definition']}: "
                                      f"{f['approved_statement']} (suggested strength: {f['strength_band']})")
                    pack.cite_merchant_finding(f)
            if r["limitations"]:
                pack.facts.append("Limitations: " + "; ".join(r["limitations"]))

        elif name in ("get_approved_merchant_findings", "get_segment_feedback",
                      "get_opportunity_merchant_feedback", "get_assumption_feedback",
                      "get_merchant_objections", "get_merchant_workarounds"):
            findings = r["findings"]
            if not findings:
                pack.unknowns.append(f"no published Merchant Voice findings matched ({name})")
            for f in findings:
                pack.facts.append(f"- {f['numerator']} of {f['denominator']} {f['denominator_definition']} "
                                  f"({f['method']}, {f['finding_type']}): {f['approved_statement']} "
                                  f"(suggested strength: {f['strength_band']}, "
                                  f"{f['contradiction_count']} contradicting)")
                pack.cite_merchant_finding(f)
                if f["limitations"]:
                    pack.facts.append(f"  Limitations: {'; '.join(f['limitations'])}")

        elif name == "compare_segment_feedback":
            for side_key in ("segment_a", "segment_b"):
                side = r[side_key]
                pack.facts.append(f"Segment {side['segment_id']} in {r['campaign_id']}:")
                for f in side["findings"]:
                    pack.facts.append(f"- {f['numerator']} of {f['denominator']} {f['denominator_definition']}: "
                                      f"{f['approved_statement']} (suggested strength: {f['strength_band']})")
                    pack.cite_merchant_finding(f)
            pack.facts.append(r["grouping_note"])

        elif name == "get_merchant_quotes":
            if r["quotes"]:
                pack.facts.append("Permission-verified merchant quotes:")
                for q in r["quotes"][:5]:
                    pack.facts.append(f'  "{q["text"]}" ({q["finding_id"]}, {q["role"]})')
            else:
                pack.unknowns.append("no permission-eligible direct quotes are currently available")

        elif name == "get_campaign_limitations":
            if r["limitations"]:
                pack.facts.append(f"Limitations recorded for {r['campaign_id']}: " + "; ".join(r["limitations"]))
            else:
                pack.facts.append(f"No limitations recorded for {r['campaign_id']}.")

    # Phase 4 — surface stale evidence honestly, once per record (never once
    # per mention). The status is deterministic metadata from stored dates
    # (shared/freshness.py); nothing here claims the source was re-checked.
    for ev_id in sorted(ev_freshness):
        f = ev_freshness[ev_id]
        if f.get("freshness_status") == "stale" and ev_id in pack.citations:
            last = f.get("last_verified_at")
            age = f.get("freshness_age_days")
            detail = (f"was last verified {age} days ago" if last and age is not None
                      else (f.get("freshness_reason") or "has no recent verification date"))
            pack.warnings.append(
                f"{ev_id} {detail} — stale evidence; re-verification is recommended "
                "before relying on it")

    if intent == "general_explanation":
        # A fixed, factual description of this system's own scoring mechanics
        # — never repository evidence, so it is safe to state as a direct
        # fact rather than something requiring a tool lookup.
        pack.facts.append(
            "How scoring works: each opportunity is scored on 17 fixed dimensions (customer pain, "
            "commercial potential, competitive position, and feasibility factors), each rated 1-5. "
            "The raw score is the sum (out of 85); the composite score is a weighted reference figure. "
            "A dimension is marked assumption-based when no supporting evidence is on file for it. "
            "If too many of the 17 factors are assumption-based, the classification is automatically "
            "capped at 'promising' regardless of the raw score, so an unvalidated idea can never be "
            "labelled 'strong'. Scores are computed by the scoring engine — never invented or "
            "adjusted by this conversation.")

    # intent-level discipline epilogues (deterministic, not model-generated)
    if intent == "challenge_hypothesis":
        pack.facts.append(
            "Hypothesis discipline: the proposition under challenge remains a hypothesis — "
            "no product has been selected on the basis of this evidence. Validation before "
            "any development is recommended.")
        pack.actions.append("Run the linked validation experiment(s) before any build decision")
        pack.needs_no_decision = True

    if intent in ("merchant_feedback", "campaign_summary", "segment_feedback", "merchant_objections",
                 "merchant_workarounds", "concept_reactions", "merchant_wtp_signals",
                 "merchant_contradictions"):
        pack.facts.append(
            "Merchant Voice discipline: findings above are approved and published research signals, "
            "not authoritative Part A evidence — Workstream A decides final evidence strength. "
            + NOT_VALIDATION)
        pack.needs_no_decision = True

    if intent == "new_opportunity_analysis":
        # No OPP record exists for this idea, so there is nothing to score —
        # deterministic scoring requires a committed scorecard's real inputs,
        # which a brand-new idea never has. We never ask the model to invent
        # one either: the response is retrieved repository context (if any)
        # plus a clearly labeled hypothesis, gaps, and a research plan.
        found_anything = any(
            name in ("search_product_knowledge",) and r.get("results")
            or name == "get_approved_merchant_findings" and r.get("findings")
            for name, r in executed
        )
        if not found_anything:
            pack.unknowns.append(
                "no related repository evidence, opportunities, segments, competitor notes, or "
                "approved Merchant Voice findings were found for this idea — treat it as a fresh, "
                "unvalidated hypothesis with no supporting internal signal yet")
        if not pack.actions:
            pack.actions.append("Run first customer interviews to test the core pain hypothesis before any build decision.")
        pack.facts.append(
            "New-opportunity discipline: this is NOT a committed opportunity — no OPP id has been "
            "assigned, no engine score has been computed (scoring requires a real, committed scorecard, "
            "which a brand-new idea does not have), and nothing has been written to the knowledge base. "
            "Everything above `search_product_knowledge` returned is a real repository record; the "
            "problem framing, target-segment hypothesis, and research plan are unvalidated hypotheses to test.")
        pack.needs_no_decision = True

    return pack
