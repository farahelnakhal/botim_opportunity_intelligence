"""Shared shell + badge helpers. Badges pair a glyph with text so state is
never communicated by colour alone (WCAG / presentation requirement)."""

import html

NAV = [
    ("index.html", "Overview"),
    ("evidence.html", "Evidence"),
    ("assumptions.html", "Assumptions"),
    ("feed.html", "Intelligence Feed"),
    ("proposals.html", "Rescore Review"),
    ("briefs.html", "Executive Brief"),
]

# glyph + text; CSS adds colour as reinforcement only
CONFIDENCE_GLYPH = {"high": "●●●", "medium": "●●○", "low": "●○○", "—": "○○○"}
STATUS_GLYPH = {
    "strong": "★ Strong opportunity",
    "promising": "◆ Promising — unvalidated",
    "weak": "▽ Weak",
    "reject": "✕ Rejected",
    "unscored": "· Unscored",
}
ASSUMPTION_STATUS_GLYPH = {
    "untested": "○ Untested",
    "partially-supported": "◑ Partially supported",
    "supported": "● Supported",
    "contradicted": "✕ Contradicted",
}


def esc(x):
    return html.escape(str(x), quote=True)


def confidence_badge(conf):
    key = str(conf).split(" ")[0].lower()
    glyph = CONFIDENCE_GLYPH.get(key, "○○○")
    return f'<span class="badge conf conf-{esc(key)}" title="evidence confidence">{glyph} {esc(str(conf).split(" ")[0].title())}</span>'


def status_badge(classification):
    key = str(classification).lower()
    label = STATUS_GLYPH.get(key, f"· {esc(classification)}")
    return f'<span class="badge status status-{esc(key)}">{esc(label)}</span>'


def assumption_badge(status):
    label = ASSUMPTION_STATUS_GLYPH.get(status, esc(status))
    return f'<span class="badge astatus a-{esc(status)}">{esc(label)}</span>'


def evidence_role_badge(ref):
    if ref.weak:
        return '<span class="badge ev-weak" title="strength &lt;3 or needs-more-evidence">▽ weak — lead, not finding</span>'
    role = ref.role
    glyph = {"primary": "◆ primary", "contextual": "○ contextual", "excluded": "✕ excluded"}.get(role, role)
    return f'<span class="badge ev-{esc(role)}">{esc(glyph)}</span>'


def page(title, active_href, body, model_note=""):
    nav = "".join(
        f'<a class="{"active" if href == active_href else ""}" href="{href}">{esc(label)}</a>'
        for href, label in NAV)
    note = f'<div class="provenance">{esc(model_note)}</div>' if model_note else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · BOTIM Product Discovery Copilot</title>
<link rel="stylesheet" href="app.css">
</head><body>
<header class="topbar">
  <div class="brand">BOTIM <span>Product Discovery Copilot</span></div>
  <nav class="tabs">{nav}</nav>
</header>
<div class="decision-banner" role="note">No product or build decision has been made. Scores are evidence-weighted hypotheses, not validations.</div>
<main class="wrap">
<h1>{esc(title)}</h1>
{body}
</main>
<footer class="foot">{note}<span>Read-only view · numbers are engine-computed, not recalculated here.</span></footer>
<script src="app.js" defer></script>
</body></html>
"""


def empty_state(message):
    return f'<div class="empty" role="status">{esc(message)}</div>'
