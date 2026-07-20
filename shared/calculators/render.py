"""Markdown rendering of a calculator envelope — the shown-working block that
embeds in chat answers and reports. Rendered strings come from the envelope's
typed steps, so display can never diverge from the computed number.
"""

from .base import LABEL_NAMES


def render_markdown(envelope):
    title = envelope.get("title") or envelope["calculator_id"]
    lines = [f"### {title} (deterministic calculation)", ""]

    # inputs with provenance
    lines.append("**Inputs**")
    lines.append("")
    lines.append("| Input | Value | Basis | Note |")
    lines.append("|---|---|---|---|")
    for name, n in envelope["normalized_inputs"].items():
        basis = LABEL_NAMES.get(n["label"], n["label"])
        note = (n.get("note") or "").replace("|", "\\|")
        lines.append(f"| {name} | {_num(n['value'])} | {basis} | {note} |")
    lines.append("")

    # shown working — one row per step
    lines.append("**Working**")
    lines.append("")
    lines.append("| Step | Formula | Substituted | Result |")
    lines.append("|---|---|---|---|")
    for s in envelope["steps"]:
        unit = f" {s['unit']}" if s.get("unit") else ""
        lines.append(
            f"| {s['output']} | {s['expression']} | {s['substituted']} | "
            f"{s['result_display']}{unit} |")
    lines.append("")

    # outputs
    lines.append("**Outputs**")
    lines.append("")
    for key, out in envelope["outputs"].items():
        unit = f" {out['unit']}" if out.get("unit") else ""
        basis = LABEL_NAMES.get(out.get("label", "A"), out.get("label", "A"))
        note = f" — {out['note']}" if out.get("note") else ""
        if out.get("value") is None:
            reason = out.get("reason", "")
            lines.append(f"- **{key}: {out['display']}** ({reason})")
        else:
            lines.append(f"- **{key}: {out['display']}{unit}** ({basis}){note}")
    lines.append("")

    if envelope.get("warnings"):
        lines.append("**Warnings**")
        lines.append("")
        for wmsg in envelope["warnings"]:
            lines.append(f"- ⚠ {wmsg}")
        lines.append("")

    for d in envelope.get("disclaimers", []):
        lines.append(f"> {d}")
    return "\n".join(lines).rstrip() + "\n"


def _num(v):
    if v is None:
        return "—"
    if float(v).is_integer() and abs(v) < 1e15:
        return f"{int(v):,}"
    return f"{v:,g}"
