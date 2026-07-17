"""Conversation orchestration.

user message -> validation/refusal -> follow-up ID resolution -> deterministic
intent + tool plan -> bounded model/tool loop -> grounded response assembly.

Grounding owns the facts; the model writes prose only. The wording guard
validates unsafe wording and falls back to the deterministic grounded text
(with a warning) — it never alters authoritative numbers or classifications.
"""

from . import grounding, intents, security
from .provider import MockProvider, ProviderError, make_provider
from .system_prompt import SYSTEM_PROMPT
from .tools_registry import REGISTRY, ToolError, call_tool, tool_specs
from .wordguard import check_wording


import re as _re

_UOPP_RE = _re.compile(r"^UOPP-[0-9a-f]{12}$")
_UO_TEXT_FIELDS = ("title", "product_definition", "problem_statement",
                   "target_segment", "customer_description", "value_proposition")
_UO_LIST_FIELDS = ("assumptions", "risks", "unknowns", "next_actions")
_UO_TEXT_MAX = 2000
_UO_LIST_MAX = 20


def _sanitize_user_opportunity(raw):
    """Bounded, allowlisted copy of a user-opportunity context object
    (Phase 6). Anything malformed is dropped entirely — never partially
    trusted. These are USER-PROVIDED fields, kept clearly separate from
    repository evidence in the grounding below."""
    if not isinstance(raw, dict):
        return None
    uid = raw.get("id")
    if not isinstance(uid, str) or not _UOPP_RE.match(uid):
        return None
    out = {"id": uid}
    for key in _UO_TEXT_FIELDS:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()[:_UO_TEXT_MAX]
    for key in _UO_LIST_FIELDS:
        value = raw.get(key)
        if isinstance(value, list):
            items = [str(x).strip()[:500] for x in value[:_UO_LIST_MAX]
                     if isinstance(x, str) and x.strip()]
            if items:
                out[key] = items
    return out


def _user_opportunity_facts(uo):
    """Deterministic grounding lines for a user opportunity draft — labelled
    user-provided so the model never presents them as repository evidence."""
    if not uo:
        return []
    lines = [f"USER-PROVIDED OPPORTUNITY DRAFT {uo['id']} (fields entered by the user; "
             "unvalidated hypotheses — NOT repository evidence, NOT scored):"]
    labels = {"title": "Title", "product_definition": "Product definition",
              "problem_statement": "Problem statement", "target_segment": "Target segment",
              "customer_description": "Customer description",
              "value_proposition": "Value proposition", "assumptions": "Stated assumptions",
              "risks": "Stated risks", "unknowns": "Stated unknowns",
              "next_actions": "Planned next actions"}
    for key in _UO_TEXT_FIELDS:
        if uo.get(key):
            lines.append(f"- {labels[key]}: {uo[key]}")
    for key in _UO_LIST_FIELDS:
        if uo.get(key):
            lines.append(f"- {labels[key]}: " + "; ".join(uo[key]))
    return lines


def _resolve_context(message_ids, request_context, stored_context):
    """Explicit IDs in the newest message always win over remembered context."""
    ctx = dict(stored_context or {})
    if request_context:
        for key in ("opportunity_id", "segment_id"):
            if request_context.get(key):
                ctx[key] = request_context[key]
        # Phase 6 — a saved user opportunity passed as conversation context
        uo = _sanitize_user_opportunity(request_context.get("user_opportunity"))
        if uo:
            ctx["user_opportunity"] = uo
    if message_ids["opportunities"]:
        ctx["opportunity_id"] = message_ids["opportunities"][0]
    if message_ids["segments"]:
        ctx["segment_id"] = message_ids["segments"][0]
    return ctx


class Orchestrator:
    def __init__(self, config, store, provider=None):
        self.config = config
        self.store = store
        self.provider = provider or make_provider(config)

    # -- public entrypoint ---------------------------------------------------

    def chat(self, message, conversation_id=None, request_context=None):
        err = security.validate_message(message, self.config.max_message_chars)
        if err:
            return {"error": {"code": "message_too_long" if "limit" in err else "invalid_request",
                              "message": err, "retryable": False}}

        is_new_conversation = conversation_id is None
        if conversation_id:
            conv = self.store.get_conversation(conversation_id)
            if conv is None:
                # Phase 3 — a distinct code from generic "not_found" so the
                # frontend can safely auto-recover (drop the stale id, retry
                # once as a fresh conversation) without guessing from a bare
                # 404 that might mean something else entirely.
                return {"error": {"code": "conversation_not_found",
                                  "message": "the conversation no longer exists", "retryable": False}}
            stored_context = conv["context"]
        else:
            conversation_id = self.store.create_conversation()
            stored_context = {}

        self.store.add_message(conversation_id, "user", message)
        trace = []

        forbidden = security.detect_forbidden(message)
        if forbidden:
            answer = security.REFUSAL
            mid = self.store.add_message(conversation_id, "assistant", answer)
            return self._response(conversation_id, mid, answer, "analysis",
                                  {"level": "high", "basis": "policy refusal — no data accessed"},
                                  [], [], [], [],
                                  [f"request refused: {forbidden}; no state was read or changed"],
                                  trace, None)

        ids = intents.extract_ids(message)
        ctx = _resolve_context(ids, request_context, stored_context)
        if not ids["opportunities"] and ctx.get("opportunity_id"):
            ids["opportunities"] = [ctx["opportunity_id"]]
        if not ids["segments"] and ctx.get("segment_id"):
            ids["segments"] = [ctx["segment_id"]]

        if intents.is_out_of_scope(message):
            answer = security.OUT_OF_SCOPE
            mid = self.store.add_message(conversation_id, "assistant", answer)
            return self._response(conversation_id, mid, answer, "analysis",
                                  {"level": "high", "basis": "scope redirect — no data accessed"},
                                  [], [], [], [], [], trace, None)

        has_selected_context = bool(ctx.get("opportunity_id") or ctx.get("segment_id")
                                    or ctx.get("user_opportunity"))
        intent = intents.classify(message, ids, is_new_conversation=is_new_conversation,
                                  has_selected_context=has_selected_context)

        # A bare greeting/help word has nothing to ground an answer in — reply
        # deterministically and never create a new-product analysis or an
        # opportunity stub for it (Phase 3).
        if intent == "clarification_needed":
            answer = intents.CLARIFICATION
            mid = self.store.add_message(conversation_id, "assistant", answer)
            self.store.update_context(conversation_id, ctx)
            return self._response(conversation_id, mid, answer, "clarification",
                                  {"level": "high", "basis": "no product-discovery content to ground"},
                                  [], [], [], [], [], trace, None)

        plan = intents.tool_plan(intent, ids, message)

        # Phase R5/PR4 — when a saved user opportunity is in play (selected as
        # context or referenced by UOPP id), READ its latest preliminary
        # analysis workspace. Reading never triggers a build: the chain runs
        # only on the explicit workspace-refresh triggers, so an ordinary
        # follow-up question reuses the stored version.
        workspace_ref = ((ids.get("user_opportunities") or [None])[0]
                         or (ctx.get("user_opportunity") or {}).get("id"))
        if workspace_ref:
            plan.insert(0, ("get_analysis_workspace", {"opportunity_ref": workspace_ref}))

        executed, seen, not_found = [], set(), []
        for name, args in plan:
            key = (name, tuple(sorted(args.items())))
            if key in seen:
                continue
            seen.add(key)
            try:
                executed.append((name, call_tool(name, args)))
                trace.append(f"ran {name}" + (f" for {list(args.values())[0]}" if args else ""))
            except ToolError as exc:
                (not_found if exc.not_found else trace).append(
                    str(exc) if exc.not_found else f"{name} rejected: input validation")

        # Phase 6 — a saved user opportunity in context contributes clearly
        # labelled USER-PROVIDED facts, always kept apart from repository
        # evidence and never written back to the persisted record from here.
        user_facts = _user_opportunity_facts(ctx.get("user_opportunity"))

        # bounded model loop: the model may request extra allowlisted tools
        pack = grounding.build(intent, executed, ids)
        facts_block = "\n".join(user_facts + pack.facts) \
            if (user_facts or pack.facts) else "(no grounded facts found)"
        messages = self._history_messages(conversation_id)
        messages.append({"role": "user", "content":
                         f"Question: {message}\n\nGROUNDING FACTS:\n{facts_block}"})

        prose, iterations = None, 0
        while iterations < self.config.max_tool_iterations:
            iterations += 1
            try:
                resp = self.provider.generate(messages, tool_specs(), SYSTEM_PROMPT, self.config)
            except ProviderError as exc:
                code = "provider_timeout" if exc.timeout else "provider_error"
                return {"error": {"code": code, "message": "the model provider was unavailable",
                                  "retryable": exc.retryable}}
            if resp.stop_reason != "tool_use" or not resp.tool_calls:
                prose = resp.content
                break
            tool_msgs = []
            for call in resp.tool_calls:
                key = (call["name"], tuple(sorted((call.get("arguments") or {}).items())))
                if key in seen or call["name"] not in REGISTRY:
                    tool_msgs.append(f"[{call['name']}: skipped (duplicate or not allowlisted)]")
                    continue
                seen.add(key)
                try:
                    result = call_tool(call["name"], call.get("arguments") or {})
                    executed.append((call["name"], result))
                    trace.append(f"ran {call['name']} (model-requested)")
                    tool_msgs.append(f"[{call['name']}: ok]")
                except ToolError as exc:
                    if exc.not_found:
                        not_found.append(str(exc))
                    tool_msgs.append(f"[{call['name']}: {exc}]")
            pack = grounding.build(intent, executed, ids)
            facts_block = "\n".join(user_facts + pack.facts) \
                if (user_facts or pack.facts) else "(no grounded facts found)"
            messages.append({"role": "user", "content":
                             "Tool results incorporated.\n\nGROUNDING FACTS:\n" + facts_block})
        if prose is None:
            prose = facts_block  # iteration cap reached: deterministic grounded fallback

        for nf in not_found:
            pack.unknowns.append(f"not found in the knowledge base: {nf}")
        if user_facts:
            pack.assumptions.insert(0, (
                f"{ctx['user_opportunity']['id']}: draft fields are user-provided "
                "hypotheses, not validated repository evidence"))
        if not executed and not not_found and intent == "unknown_or_unsupported":
            prose = security.OUT_OF_SCOPE

        answer, warnings = self._assemble(prose, pack, facts_block)
        answer = answer[: self.config.max_response_chars]
        citations = list(pack.citations.values())
        mid = self.store.add_message(conversation_id, "assistant", answer,
                                     cited_ids=[c["id"] for c in citations])
        self.store.update_context(conversation_id, ctx)
        return self._response(conversation_id, mid, answer, intents.ANSWER_TYPE[intent],
                              pack.confidence(), citations, pack.assumptions[:10],
                              pack.unknowns[:10], pack.actions[:6],
                              pack.warnings + warnings, trace, pack.draft)

    # -- helpers ---------------------------------------------------------------

    def _history_messages(self, conversation_id):
        history = self.store.get_messages(conversation_id, limit=self.config.max_history)
        msgs = [{"role": m["role"], "content": m["content"]}
                for m in history[:-1]]  # exclude the just-stored user message
        return msgs[-self.config.max_history:]

    def _assemble(self, prose, pack, facts_block):
        warnings = []
        verdict = check_wording(prose)
        if verdict is not None:
            warnings.append(f"model wording rejected ({verdict}); deterministic grounded text used")
            prose = facts_block
        if pack.needs_no_decision and grounding.NO_DECISION not in prose:
            prose = prose.rstrip() + "\n\n" + grounding.NO_DECISION
        # PR2 (baseline synthesis) — the old "## Evidence used" id-list
        # appendix is gone: citations travel as structured objects in the
        # response and the frontend renders them as chips/drawers. Appending
        # a raw id dump to every answer was part of the record-dump feel.
        return prose, warnings

    def _runtime_mode(self):
        # Phase 3 — lets the frontend disclose deterministic demo synthesis
        # rather than looking identical to live model output. Never exposes
        # whether a key is configured, the provider class name, or anything
        # beyond this one fixed two-value label.
        return "deterministic_demo" if isinstance(self.provider, MockProvider) else "live_model"

    def _response(self, conversation_id, message_id, answer, answer_type, confidence,
                  citations, assumptions, unknowns, actions, warnings, trace, draft):
        resp = {"schema_version": "1.0", "conversation_id": conversation_id,
                "message_id": message_id, "answer_markdown": answer,
                "answer_type": answer_type, "confidence": confidence,
                "citations": citations, "assumptions": assumptions,
                "unknowns": unknowns, "recommended_next_actions": actions,
                "warnings": warnings, "runtime_mode": self._runtime_mode(),
                "safe_tool_trace": trace if self.config.debug_trace else []}
        if draft is not None:
            resp["draft"] = draft
        return resp
