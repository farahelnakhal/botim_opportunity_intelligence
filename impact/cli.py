"""Command-line interface for the evidence-impact workflow.

Subcommands (hyphenated aliases in the task map 1:1):
  propose   -> impact-propose
  apply     -> apply-impact <proposal-id> --approver X [--confirm-segment-upgrade]
  reject    -> reject-impact <proposal-id>
  rollback  -> rollback-impact <history-id> --approver X
  recover   -> recover-impact
  email     -> impact-email <proposal-id>   (preview only; never sends)
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

from . import apply as apply_mod
from . import (brief, email, gaps, paths, proposal, research_request,
               rollback, tracker, transaction)
from .errors import ImpactError


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def _emit(content, args, default_path):
    """Read-only by default: print. Persist only with --write (canonical path)
    or --output <path>. Returns nothing."""
    if not isinstance(content, str):
        content = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    out = getattr(args, "output", None)
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        print(f"written: {p}")
    elif getattr(args, "write", False):
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(content, encoding="utf-8")
        print(f"written: {default_path}")
    else:
        print(content, end="")


def _next_proposal_id(today):
    paths.ensure_dirs()
    n = 0
    for p in paths.PROPOSALS_DIR.glob(f"PROP-{today}-*.json"):
        try:
            n = max(n, int(p.stem.rsplit("-", 1)[1]))
        except ValueError:
            pass
    return f"PROP-{today}-{n + 1:03d}"


def _cmd_propose(a):
    card = json.loads(Path(a.scorecard).read_text(encoding="utf-8"))
    descriptor = json.loads(Path(a.evidence).read_text(encoding="utf-8"))
    segment = json.loads(Path(a.segment).read_text(encoding="utf-8")) if a.segment else None
    today = a.today or datetime.date.today().isoformat()
    pid = a.id or _next_proposal_id(today)
    prop = proposal.generate(card, descriptor, segment, proposal_id=pid, today=today)
    paths.ensure_dirs()
    out = paths.PROPOSALS_DIR / f"{pid}.json"
    out.write_text(json.dumps(prop, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"proposal {pid} written ({len(prop['payload']['factor_changes'])} factor change(s), "
          f"alert {prop['payload']['score_summary']['alert_tier']})")
    print(str(out))


def _cmd_apply(a):
    r = apply_mod.apply_impact(a.proposal_id, a.approver, a.confirm_segment_upgrade)
    print(f"applied {r['proposal_id']} -> {r['history_id']} "
          f"(segment_applied={r['segment_applied']}, txn {r['transaction_id']})")


def _cmd_reject(a):
    r = apply_mod.reject_impact(a.proposal_id, a.by)
    print(f"rejected {r['proposal_id']} (no persistent target changes)")


def _cmd_rollback(a):
    r = rollback.rollback_impact(a.history_id, a.approver)
    print(f"rolled back {r['target_history_id']} -> {r['history_id']}")


def _cmd_recover(a):
    recovered = transaction.preflight()
    print("recovered: " + (", ".join(recovered) if recovered else "nothing to recover"))


def _cmd_email(a):
    prop, _ = apply_mod._load_proposal(a.proposal_id)
    seg = bool(prop["payload"]["segment_changes"]) and a.assume_segment
    text = email.render(prop, seg)
    paths.ensure_dirs()
    out = paths.EMAIL_DIR / f"{prop['proposal_id']}.md"
    out.write_text(text, encoding="utf-8")
    print(str(out))


def _cmd_brief(a):
    now = _now()
    if a.portfolio:
        views = []
        for sp in sorted((paths.KB / "opportunity-scores").glob("*-scorecard.json")):
            oid = json.loads(sp.read_text(encoding="utf-8"))["opportunity_id"]
            views.append(brief.build_view(oid, now))
        if a.format == "json":
            _emit([brief.render_json(v) for v in views], a, paths.BRIEFS_DIR / "portfolio.json")
        else:
            _emit("\n---\n".join(brief.render_terminal(v) if a.format == "terminal"
                                 else brief.render_markdown(v) for v in views),
                  a, paths.BRIEFS_DIR / "portfolio.md")
        return
    view = brief.build_view(a.opportunity, now)
    slug = a.opportunity.lower()
    if a.format == "json":
        _emit(brief.render_json(view), a, paths.BRIEFS_DIR / f"{slug}.json")
    elif a.format == "terminal":
        _emit(brief.render_terminal(view), a, paths.BRIEFS_DIR / f"{slug}.txt")
    else:
        _emit(brief.render_markdown(view), a, paths.BRIEFS_DIR / f"{slug}.md")


def _cmd_assumptions(a):
    model = tracker.build(a.opportunity, _now())
    slug = a.opportunity.lower()
    if a.format == "json":
        _emit(model, a, paths.REGISTERS_DIR / f"{slug}.json")
    else:
        _emit(tracker.render_markdown(model), a, paths.REGISTERS_DIR / f"{slug}.md")


def _cmd_gaps(a):
    rep = gaps.build_portfolio(_now())
    if a.format == "json":
        _emit(rep, a, paths.IMPACT_KB / "evidence-gaps.json")
    else:
        _emit(gaps.render_markdown(rep, top=a.top), a, paths.IMPACT_KB / "evidence-gaps.md")


def _cmd_research_request(a):
    req = research_request.generate(a.assumption, _now())
    _emit(req, a, paths.RESEARCH_DIR / f"{req['request_id']}.json")


def _add_output_flags(p):
    p.add_argument("--write", action="store_true", help="persist to the canonical derived path")
    p.add_argument("--output", help="persist to an explicit path")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="impact", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("propose")
    p.add_argument("--scorecard", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--segment")
    p.add_argument("--id")
    p.add_argument("--today")
    p.set_defaults(fn=_cmd_propose)

    p = sub.add_parser("apply")
    p.add_argument("proposal_id")
    p.add_argument("--approver", required=True)
    p.add_argument("--confirm-segment-upgrade", dest="confirm_segment_upgrade", action="store_true")
    p.set_defaults(fn=_cmd_apply)

    p = sub.add_parser("reject")
    p.add_argument("proposal_id")
    p.add_argument("--by", default="cli:local")
    p.set_defaults(fn=_cmd_reject)

    p = sub.add_parser("rollback")
    p.add_argument("history_id")
    p.add_argument("--approver", required=True)
    p.set_defaults(fn=_cmd_rollback)

    p = sub.add_parser("recover")
    p.set_defaults(fn=_cmd_recover)

    p = sub.add_parser("email")
    p.add_argument("proposal_id")
    p.add_argument("--assume-segment", dest="assume_segment", action="store_true")
    p.set_defaults(fn=_cmd_email)

    # --- reporting commands (read-only by default) ---
    p = sub.add_parser("brief", help="executive decision brief (executive-brief)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--opportunity")
    g.add_argument("--portfolio", action="store_true")
    p.add_argument("--format", choices=["md", "json", "terminal"], default="md")
    _add_output_flags(p)
    p.set_defaults(fn=_cmd_brief)

    p = sub.add_parser("assumptions", help="per-opportunity assumption register (assumptions-show)")
    p.add_argument("--opportunity", required=True)
    p.add_argument("--format", choices=["md", "json"], default="md")
    _add_output_flags(p)
    p.set_defaults(fn=_cmd_assumptions)

    p = sub.add_parser("gaps", help="portfolio evidence-gap report (evidence-gaps)")
    p.add_argument("--portfolio", action="store_true")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--top", type=int)
    _add_output_flags(p)
    p.set_defaults(fn=_cmd_gaps)

    p = sub.add_parser("research-request", help="draft Part A research request (research-request)")
    p.add_argument("--assumption", required=True)
    _add_output_flags(p)
    p.set_defaults(fn=_cmd_research_request)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except ImpactError as exc:
        sys.exit(f"impact error: {exc}")


if __name__ == "__main__":
    main()
