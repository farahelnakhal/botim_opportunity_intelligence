"""Input validation and injection/state-change refusal.

The backend has no state-changing tools at all; these checks exist so the
response is a clear, product-focused refusal rather than a confusing attempt.
"""

import re

# state-changing / exfiltration requests -> refuse (never attempt)
_FORBIDDEN = [
    (re.compile(r"\b(ignore|disregard|forget) (all )?(prior|previous|your) (instructions|rules|prompt)", re.I),
     "instruction-override attempt"),
    (re.compile(r"\b(reveal|show|print|expose).{0,30}(system prompt|hidden prompt|instructions|api.?key|secret|token)", re.I),
     "prompt/secret disclosure request"),
    (re.compile(r"\b(change|set|update|modify|edit|overwrite|rewrite).{0,40}(score(card)?s?|evidence|segment|confidence|assumption|record)\b", re.I),
     "state-changing request"),
    (re.compile(r"\b(apply|approve|rollback|roll back).{0,30}(impact|proposal|transaction)", re.I),
     "impact-workflow mutation request"),
    (re.compile(r"\b(send|email|e-mail).{0,30}(email|digest|message|report) to\b", re.I),
     "email-sending request"),
    (re.compile(r"\b(run|execute|eval).{0,30}(shell|bash|command|python|code|script)\b", re.I),
     "code/shell execution request"),
    (re.compile(r"(\.\./|/etc/|/home/|~\/|\bopen the file\b|\bread (the )?file\b|\bcat \b)", re.I),
     "filesystem-access request"),
]

REFUSAL = (
    "That action isn't available through this copilot. I'm a **read-only** product-discovery "
    "assistant: I can explain opportunities, evidence, assumptions, gaps and next validation "
    "steps, and generate *draft* research requests or briefs — but I can't modify records, "
    "scores or state, apply or approve proposals, send emails, run code, read arbitrary files, "
    "or share internal prompts or keys. Changes go through the human-approved impact workflow. "
    "Happy to help with a product-discovery question instead."
)

OUT_OF_SCOPE = (
    "This copilot is intended for product-discovery questions — segments, customer pain, "
    "evidence, assumptions, opportunities and what to validate next — rather than code, "
    "files or implementation details. Try asking about an opportunity (e.g. OPP-013), a "
    "segment, the evidence for a problem, or what to research next."
)


def detect_forbidden(text):
    """Return the reason string if the message asks for a forbidden action."""
    for pattern, reason in _FORBIDDEN:
        if pattern.search(text):
            return reason
    return None


def validate_message(message, max_chars):
    if not isinstance(message, str) or not message.strip():
        return "message must be a non-empty string"
    if len(message) > max_chars:
        return f"message exceeds the {max_chars}-character limit"
    return None
