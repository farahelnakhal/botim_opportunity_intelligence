"""Server-side PDF rendering of an executive brief (Phase P1).

Render-only, pure functions — the same discipline as `impact/brief.py` and
`impact/email.py`: input is the ALREADY-BUILT brief read model
(`serialize.brief_payload` for a committed OPP, `serialize.user_brief_payload`
for a UOPP draft); output is PDF bytes. This module **recomputes nothing,
fetches nothing, and invents nothing** — an absent field renders as the exact
honest "unavailable"/"not yet defined" note the web report uses, never a
placeholder. Preliminary / candidate / unapproved / freshness / confidence
distinctions from `Report.tsx` are preserved as visible PDF treatments (colored
labels, explicit notes) so PDF export never flattens them away.

PDF generation uses reportlab (BSD-3-Clause) — the repo's first runtime
third-party dependency, a deliberate logged decision (see docs/decision-log.md,
"P1 PDF export"). All payload text is XML-escaped before it reaches reportlab's
Paragraph parser (both a rendering-safety and a data-never-instructions
measure). Generated prose is routed through the same overclaim/bounded-statement
guard as `impact/email.py`.
"""

import io
from xml.sax.saxutils import escape as _xml_escape

# reportlab is the repo's SOLE third-party runtime dependency and is needed ONLY
# for PDF export (Phase P1). It is imported LAZILY via _require_reportlab() so
# that importing this module — and therefore `server.py` and the entire test
# suite / integration gate — succeeds on stdlib alone. A missing reportlab makes
# only PDF export unavailable (an honest ReportPdfError), never a hard failure of
# the whole API server's import path. The names below are bound on first render.
colors = TA_LEFT = A4 = ParagraphStyle = mm = None
HRFlowable = ListFlowable = ListItem = Paragraph = None
SimpleDocTemplate = Spacer = Table = TableStyle = None

# Reuse the authoritative honesty vocabulary — do not fork it.
from impact.email import BOUNDED_STATEMENTS, OVERCLAIMS


class ReportPdfError(Exception):
    """Safe render failure — message never contains payload internals."""


# Semantic colors mirroring the web report's tag classes (format.ts / index.css:
# success/accent/warning/critical/neutral). Print-friendly, theme-independent.
# Populated lazily by _require_reportlab() (values need reportlab's colors).
_SEMANTIC = {}


def _require_reportlab():
    """Import reportlab on demand, binding its names as module globals and
    populating the color palette. Idempotent. Raises ReportPdfError (never a
    bare ImportError) if the package is absent, so PDF export degrades to the
    same honest 'unavailable' contract the rest of the app uses."""
    global colors, TA_LEFT, A4, ParagraphStyle, mm
    global HRFlowable, ListFlowable, ListItem, Paragraph
    global SimpleDocTemplate, Spacer, Table, TableStyle
    if Paragraph is not None:          # already imported
        return
    try:
        from reportlab.lib import colors as _colors
        from reportlab.lib.enums import TA_LEFT as _TA_LEFT
        from reportlab.lib.pagesizes import A4 as _A4
        from reportlab.lib.styles import ParagraphStyle as _ParagraphStyle
        from reportlab.lib.units import mm as _mm
        from reportlab.platypus import (
            HRFlowable as _HRFlowable, ListFlowable as _ListFlowable,
            ListItem as _ListItem, Paragraph as _Paragraph,
            SimpleDocTemplate as _SimpleDocTemplate, Spacer as _Spacer,
            Table as _Table, TableStyle as _TableStyle)
    except ImportError as exc:
        raise ReportPdfError(
            "PDF export requires the 'reportlab' package — the repo's sole "
            "runtime dependency (Phase P1). Install it with: "
            "pip install -r requirements.txt") from exc
    colors, TA_LEFT, A4, ParagraphStyle, mm = _colors, _TA_LEFT, _A4, _ParagraphStyle, _mm
    HRFlowable, ListFlowable, ListItem, Paragraph = _HRFlowable, _ListFlowable, _ListItem, _Paragraph
    SimpleDocTemplate, Spacer, Table, TableStyle = _SimpleDocTemplate, _Spacer, _Table, _TableStyle
    _SEMANTIC.update({
        "success": colors.HexColor("#177245"),
        "accent": colors.HexColor("#1a56db"),
        "warning": colors.HexColor("#9a6b00"),
        "critical": colors.HexColor("#b3261e"),
        "neutral": colors.HexColor("#5f6368"),
        "ink": colors.HexColor("#1a1a1a"),
        "muted": colors.HexColor("#6b7280"),
        "rule": colors.HexColor("#d0d5dd"),
        "banner_bg": colors.HexColor("#fff4e5"),
    })

# classification value -> semantic color key (mirrors format.ts tagClass)
_CLASS_COLOR = {
    "strong": "success", "promising": "accent",
    "weak": "warning", "needs_validation": "warning", "needs validation": "warning",
    "reject": "critical",
    "unscored": "neutral", "unknown": "neutral",
}

# freshness_status -> (label, semantic color key). Mirrors Provenance.tsx; a
# stale record carries the alert marker the web UI shows, unknown is explicit.
_FRESHNESS = {
    "fresh": ("Fresh", "success"),
    "aging": ("Aging", "warning"),
    "stale": ("⚠ Stale", "critical"),
    "unknown": ("Freshness unknown", "neutral"),
}


def _esc(value):
    """Escape any payload value for reportlab's XML-ish Paragraph parser. None
    and the '—' sentinel are handled by callers; here we only make text safe."""
    return _xml_escape("" if value is None else str(value))


def _styles():
    base = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13,
                          textColor=_SEMANTIC["ink"], alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold",
                                 fontSize=17, leading=21),
        "sub": ParagraphStyle("sub", parent=base, fontSize=8.5, textColor=_SEMANTIC["muted"]),
        "section": ParagraphStyle("section", parent=base, fontName="Helvetica-Bold",
                                  fontSize=11, leading=15, spaceBefore=10, spaceAfter=3,
                                  textColor=_SEMANTIC["ink"]),
        "body": base,
        "muted": ParagraphStyle("mutedp", parent=base, textColor=_SEMANTIC["muted"],
                                fontName="Helvetica-Oblique"),
        "banner": ParagraphStyle("banner", parent=base, fontName="Helvetica-Bold",
                                 textColor=_SEMANTIC["warning"]),
    }


class _Doc:
    """Accumulates flowables + the visible-text log the honesty guard checks."""

    def __init__(self):
        self.story = []
        self.styles = _styles()
        self._text = []

    # -- primitives ----------------------------------------------------------
    def para(self, markup, style="body", _record=True):
        """`markup` may contain SAFE reportlab tags with pre-escaped values."""
        self.story.append(Paragraph(markup, self.styles[style]))
        if _record:
            self._text.append(markup)

    def spacer(self, h=4):
        self.story.append(Spacer(1, h))

    def section(self, label):
        self.story.append(HRFlowable(width="100%", thickness=0.4,
                                     color=_SEMANTIC["rule"], spaceBefore=8, spaceAfter=2))
        self.para(_esc(label), "section")

    def empty(self, text):
        """An honest empty/unavailable note — rendered, never omitted."""
        self.para(_esc(text), "muted")

    def bullets(self, items, empty_text):
        items = [x for x in (items or []) if isinstance(x, str) and x.strip()]
        if not items:
            self.empty(empty_text)
            return
        self.story.append(ListFlowable(
            [ListItem(Paragraph(_esc(x), self.styles["body"]), leftIndent=10) for x in items],
            bulletType="bullet", start="•", bulletColor=_SEMANTIC["muted"]))
        self._text.extend(items)

    def badge_row(self, badges):
        """badges: list of (text, semantic_color_key). Rendered as colored,
        bold inline labels — the PDF equivalent of the web tag chips."""
        parts = []
        for text, key in badges:
            if text is None:
                continue
            color = _SEMANTIC.get(key, _SEMANTIC["neutral"]).hexval()[2:]
            parts.append(f'<font color="#{color}"><b>{_esc(text)}</b></font>')
            self._text.append(str(text))
        if parts:
            self.para("&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts), "body", _record=False)

    def banner(self, text):
        """The persistent 'no decision made' banner — a bordered callout on
        every report, so the bounded statement is always visible."""
        cell = Paragraph(f'<b>{_esc(text)}</b>', self.styles["banner"])
        tbl = Table([[cell]], colWidths=[170 * mm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _SEMANTIC["banner_bg"]),
            ("BOX", (0, 0), (-1, -1), 0.5, _SEMANTIC["warning"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        self.story.append(tbl)
        self.spacer(6)
        self._text.append(text)

    def to_pdf(self, title):
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4, title=title, author="BOTIM Opportunity Intelligence",
            leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
        doc.build(self.story)
        return buf.getvalue()


def _guard(text_segments):
    """Same honesty contract as impact/email.py, applied to the whole document:
    no affirmative overclaim may appear, and the bounded 'no decision' statement
    MUST be present (it is the decision banner, rendered on every report)."""
    blob = "\n".join(text_segments).lower()
    for phrase in OVERCLAIMS:
        if phrase in blob:
            raise ReportPdfError(f"brief PDF overclaim rejected: '{phrase}'")
    if not any(b in seg for seg in text_segments for b in BOUNDED_STATEMENTS):
        raise ReportPdfError("brief PDF must include the bounded 'no decision' statement")


def _confidence_label(value):
    if value is None or str(value).strip() in ("", "—"):
        return "Unknown"
    return str(value)


def _clean(value):
    """A displayable scalar, or None when the payload has nothing (sentinel
    '—' and empty string both count as absent — never fabricated)."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s != "—" else None


def _human_factor(key):
    return str(key).replace("_", " ").strip().capitalize() if key else ""


# --------------------------------------------------------------------------- #
# Committed-opportunity brief
# --------------------------------------------------------------------------- #
def _render_committed(payload, research_candidates):
    d = _Doc()
    d.para(_esc(payload.get("title") or payload["opportunity_id"]), "title")
    d.para(f'{_esc(payload["opportunity_id"])} &nbsp;·&nbsp; generated '
           f'{_esc(payload.get("generated_at"))}', "sub", _record=False)
    d.badge_row([
        (payload.get("classification_label"),
         _CLASS_COLOR.get(str(payload.get("classification")), "neutral")),
        (f'Confidence: {_confidence_label(payload.get("confidence"))}', "neutral"),
        ("Archived" if payload.get("is_archived") else None, "critical"),
    ])
    d.spacer(6)
    d.banner(payload.get("decision_banner") or "")

    s = payload.get("score_summary") or {}
    d.section("Score summary")
    d.para(f'Raw score: <b>{_esc(s.get("raw_score") if s.get("raw_score") is not None else "—")}'
           f'</b> / {_esc(s.get("raw_max"))} &nbsp;·&nbsp; '
           f'Composite (reference): <b>{_esc(s.get("composite") if s.get("composite") is not None else "—")}</b>'
           f' &nbsp;·&nbsp; Assumption-based factors: <b>{_esc(s.get("assumption_count"))}</b>')
    flags = s.get("critical_flags") or []
    if flags:
        color = _SEMANTIC["warning"].hexval()[2:]
        d.para(f'<font color="#{color}"><b>⚠ Critical flags:</b> {_esc("; ".join(flags))}</font>')

    env = payload.get("brief_envelope") or {}
    rec = (env.get("recommended_action") or {}).get("text")
    dec = (env.get("decision_requested") or {}).get("text")
    d.section("Executive summary")
    if _clean(rec) or _clean(dec):
        if _clean(rec):
            d.para(f'<b>Recommended action:</b> {_esc(rec)}')
        if _clean(dec):
            d.para(f'<b>Decision requested:</b> {_esc(dec)}')
    else:
        d.empty("No executive brief envelope is available for this opportunity.")

    d.section("Product definition & problem framing")
    d.para(f'<b>Proposition:</b> {_esc(_clean(payload.get("hypothesis")) or "—")}')
    d.para(f'<b>Target segment:</b> {_esc(_clean(payload.get("segment")) or "—")}')
    d.para(f'<b>Job-to-be-done:</b> {_esc(_clean(payload.get("jtbd")) or "—")}')

    evidence = payload.get("evidence") or []
    d.section(f"Key evidence ({len(evidence)})")
    if not evidence:
        d.empty("This scorecard cites no evidence records — every factor is assumption-based.")
    else:
        for e in evidence:
            title = e.get("title")
            title = title if _clean(title) else "Customer-evidence record"
            label, ck = _FRESHNESS.get(e.get("freshness_status") or "unknown",
                                       _FRESHNESS["unknown"])
            fc = _SEMANTIC.get(ck).hexval()[2:]
            d.para(f'• <b>{_esc(title)}</b> &nbsp;·&nbsp; '
                   f'{_esc(_clean(e.get("source_title")) or "Internal record")} '
                   f'&nbsp;·&nbsp; strength {_esc(e.get("strength"))} '
                   f'&nbsp;·&nbsp; <font color="#{fc}"><b>{_esc(label)}</b></font>')

    contradictions = [e for e in evidence if e.get("role") == "contradictory"]
    contra_text = _clean(payload.get("contradictory_evidence"))
    d.section("Contradictions")
    if not contradictions and not contra_text:
        d.empty("No contradictory evidence is recorded. Supporting evidence is preserved regardless.")
    else:
        if contra_text:
            d.para(_esc(contra_text))
        for e in contradictions:
            d.para(f'• {_esc(_clean(e.get("title")) or e.get("ev_id"))}')

    assumptions = payload.get("assumptions") or []
    d.section(f"Assumptions ({len(assumptions)})")
    if not assumptions:
        d.empty("No tracked assumptions.")
    else:
        for a in assumptions:
            d.para(f'• {_esc(_human_factor(a.get("factor_key")))} &nbsp;·&nbsp; '
                   f'{_esc(a.get("status"))}')

    mon = payload.get("monitoring") or {}
    state = mon.get("state") or {}
    events = mon.get("events") or []
    d.section("Monitoring")
    if state:
        d.para(f'<b>Status:</b> {_esc(state.get("status"))} — {_esc(state.get("status_note"))}')
    if not events:
        d.empty("No monitoring events reference this opportunity.")
    else:
        for e in events:
            d.para(f'• {_esc(_clean(e.get("title")) or e.get("id"))} &nbsp;·&nbsp; '
                   f'{_esc(e.get("detected_at"))}')

    predictions = payload.get("predictions") or []
    d.section(f"Predictions ({len(predictions)})")
    if not predictions:
        d.empty("No logged predictions reference this opportunity.")
    else:
        for p in predictions:
            outcome = p.get("outcome")
            pill = "came true" if outcome else "did not happen" if outcome is not None else "open"
            pct = ""
            if isinstance(p.get("p"), (int, float)):
                pct = f'p={round(p["p"] * 100)}% &nbsp;·&nbsp; '
            d.para(f'• {_esc(_clean(p.get("statement")) or p.get("id"))} '
                   f'&nbsp;·&nbsp; {pct}due {_esc(p.get("resolve_by"))} '
                   f'&nbsp;·&nbsp; <i>{_esc(pill)}</i>')

    mv = payload.get("merchant_voice") or {}
    findings = mv.get("findings") or []
    d.section("Merchant Voice findings (approved)")
    if not mv.get("available") or not findings:
        d.empty(_clean(mv.get("note")) or "No approved Merchant Voice findings are available.")
    else:
        for f in findings:
            d.para(f'• {_esc(_clean(f.get("approved_statement")) or f.get("finding_id"))}')
        # the web report labels these candidate — not repository evidence
        d.empty(_clean(mv.get("note")) or "Candidate — not repository evidence.")

    d.section("Risks")
    d.bullets(payload.get("risks"), "No risks are recorded in the impact brief for this opportunity.")
    d.section("Unknowns / open questions")
    d.bullets(payload.get("unknowns"), "No open evidence gaps are recorded for this opportunity.")
    d.section("Recommended next actions")
    d.bullets(payload.get("recommended_next_actions"), "No recommended next action is recorded.")

    if _clean(payload.get("brief_markdown")):
        d.section("Committed recommendation brief")
        for line in str(payload["brief_markdown"]).splitlines():
            line = line.strip()
            if line:
                d.para(_esc(line))

    sources = payload.get("sources") or []
    d.section("Sources appendix")
    if not sources:
        d.empty("No external sources are recorded behind this opportunity's cited evidence.")
    else:
        for src in sources:
            bits = []
            if _clean(src.get("publisher")):
                bits.append(_esc(src["publisher"]))
            if _clean(src.get("retrieved_at")):
                bits.append(f'retrieved {_esc(src["retrieved_at"])}')
            if _clean(src.get("source_url")):
                bits.append(_esc(src["source_url"]))
            sub = " &nbsp;·&nbsp; ".join(bits)
            d.para(f'• <b>{_esc(_clean(src.get("source_title")) or "Internal record")}</b>'
                   + (f'<br/>{sub}' if sub else ""))

    _render_external_research(d, research_candidates)
    return d, f'{payload.get("title") or payload["opportunity_id"]} — executive brief'


def _render_external_research(d, candidates):
    """Mirrors Report.tsx: null -> unavailable, [] -> none, else labelled
    candidate rows. Candidates are always tagged 'not repository evidence'."""
    d.section("External research (candidate claims)")
    if candidates is None:
        d.empty("External research is unavailable right now.")
    elif not candidates:
        d.empty("No approved external research candidates are linked to this opportunity.")
    else:
        for c in candidates:
            n = len(c.get("source_ids") or [])
            d.para(f'• {_esc(_clean(c.get("claim")) or c.get("id"))}')
            d.empty(f'Human-approved external research (candidate — not repository evidence) '
                    f'· {n} source{"" if n == 1 else "s"} '
                    f'· run {_esc(_clean(c.get("run_title")) or c.get("run_id"))}')


# --------------------------------------------------------------------------- #
# User-opportunity draft brief
# --------------------------------------------------------------------------- #
def _render_user(payload, research_candidates):
    d = _Doc()
    d.para(_esc(payload.get("title") or payload["opportunity_id"]), "title")
    d.para(f'{_esc(payload["opportunity_id"])} &nbsp;·&nbsp; generated '
           f'{_esc(payload.get("generated_at"))} &nbsp;·&nbsp; v{_esc(payload.get("version"))}',
           "sub", _record=False)
    d.badge_row([
        (payload.get("classification_label"), "neutral"),
        ("Archived" if payload.get("is_archived") else None, "critical"),
        ("Your opportunity", "neutral"),
    ])
    d.spacer(6)
    d.banner(payload.get("decision_banner") or "")

    def text_section(label, value):
        d.section(label)
        if _clean(value):
            d.para(_esc(value))
        else:
            d.empty("Not yet defined.")

    text_section("Product definition", payload.get("product_definition"))
    text_section("Problem statement", payload.get("problem_statement"))
    text_section("Target segment", payload.get("target_segment"))
    text_section("Customer description", payload.get("customer_description"))
    text_section("Value proposition", payload.get("value_proposition"))

    d.section(f'Assumptions ({len(payload.get("assumptions") or [])})')
    d.bullets(payload.get("assumptions"), "No assumptions recorded yet.")
    d.section("Risks")
    d.bullets(payload.get("risks"), "No risks recorded yet.")
    d.section("Unknowns")
    d.bullets(payload.get("unknowns"), "No unknowns recorded yet.")
    d.section("Recommended next actions")
    d.bullets(payload.get("next_actions"), "No next actions recorded yet.")

    mon = payload.get("monitoring") or {}
    status = mon.get("status")
    mon_label = {
        "not_configured": "Monitoring is not configured for this opportunity.",
        "never_run": "Configured — awaiting monitoring run (no runner is connected yet).",
        "paused": "Monitoring configuration is paused.",
        "error": f'Monitoring error: {_clean(mon.get("last_error")) or "unknown"}',
    }.get(status, "Monitoring is active.")
    d.section("Monitoring")
    d.para(_esc(mon_label))
    if status and status != "not_configured":
        d.empty(f'Cadence (intended): {_esc(mon.get("cadence"))} · '
                f'last run {_esc(_clean(mon.get("last_run_at")) or "unavailable — never run")}')

    d.section("Evidence & scoring")
    d.empty("No engine score and no evidence citations exist for a user draft — "
            "validation has not happened yet, and nothing is fabricated.")

    _render_external_research(d, research_candidates)

    d.section("Provenance")
    prov = f'Created {_esc(payload.get("created_at"))}'
    if payload.get("created_from_analysis"):
        prov += " from a grounded copilot analysis"
    prov += f' · last updated {_esc(payload.get("updated_at"))}'
    d.empty(prov)
    return d, f'{payload.get("title") or payload["opportunity_id"]} — opportunity brief'


def _assemble(payload, research_candidates):
    """Dispatch on record_type and populate the document (flowables + the
    visible-text log). Raises ReportPdfError for a payload with no id."""
    if not isinstance(payload, dict) or not payload.get("opportunity_id"):
        raise ReportPdfError("a brief payload with an opportunity_id is required")
    if payload.get("record_type") == "user_opportunity":
        return _render_user(payload, research_candidates)
    return _render_committed(payload, research_candidates)


def visible_text(payload, research_candidates=None):
    """The human-visible text segments the PDF will contain — the SAME log the
    honesty guard runs on. Exposed so tests (and callers) can assert content
    faithfully without parsing compressed PDF byte streams. Does not run the
    guard (pure inspection); render_brief_pdf enforces it."""
    _require_reportlab()
    d, _title = _assemble(payload, research_candidates)
    return list(d._text)


def render_brief_pdf(payload, research_candidates=None):
    """Render a brief read model to PDF bytes. `payload` is the exact dict
    `serialize.brief_payload` / `serialize.user_brief_payload` returns.
    `research_candidates` mirrors the web report's separately-fetched approved
    external-research list: None = unavailable, [] = none, list = rows.
    Recomputes/invents nothing; raises ReportPdfError on a bad payload or a
    failed honesty guard."""
    _require_reportlab()
    try:
        d, title = _assemble(payload, research_candidates)
        _guard(d._text)          # honesty contract, before we emit any bytes
        return d.to_pdf(title)
    except ReportPdfError:
        raise
    except Exception as exc:  # never leak internals in the message
        raise ReportPdfError(f"failed to render brief PDF ({type(exc).__name__})")
