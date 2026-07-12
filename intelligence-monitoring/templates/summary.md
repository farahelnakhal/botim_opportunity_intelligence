# Template — AI Summary (per important/critical event)

File: `knowledge-base/monitoring/summaries/EVT-YYYY-Wnn-nnn.md`. All twelve fields mandatory; every claim sourced; confidence uses Workstream A's vocabulary. Produced by the LLM layer, schema-checked before an alert may reference it. The reasoning pass (`frameworks/reasoning-pass.md`) must be answered in §"Flags".

---

## EVT-… — <title>

1. **Executive summary** (≤2 sentences)
2. **What changed** (facts only, quoted/sourced)
3. **Why it matters**
4. **Impact on BOTIM**
5. **Impact on AstraTech**
6. **Opportunities created** (backlog-candidate proposals, if any)
7. **Risks created** (mapped to named stress scenarios where possible)
8. **Recommended actions** (each mapped to a mechanism: rescore OPP-…, review VE-…, open REQ-…, exec brief; or an explicit "no action")
9. **Confidence:** High/Medium/Low — why; never above the weakest load-bearing source
10. **Supporting evidence:** EV-/IP-/SRC- ids; unpromoted candidates marked "unverified — pending Workstream A review"
11. **Sources:** URLs + access labels + fetch dates
12. **Related previous events:** EVT-/thread ids

### Flags (machine-consumable)

```json
{"rescore_flags": [{"opp": "OPP-…", "dimensions": ["…"], "reason": "…"}],
 "ve_flags": [{"ve": "VE-…", "action": "redesign-as-new", "reason": "…"}],
 "req_proposals": [], "evidence_candidates": []}
```
