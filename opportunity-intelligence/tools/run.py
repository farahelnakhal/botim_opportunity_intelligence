#!/usr/bin/env python3
"""CLI for the Opportunity Intelligence engine (Workstream B).

Usage (from repo root):
  python3 opportunity-intelligence/tools/run.py model   knowledge-base/commercial-models/opp-001-inputs.json
  python3 opportunity-intelligence/tools/run.py subsidy knowledge-base/commercial-models/opp-002-subsidy-inputs.json
  python3 opportunity-intelligence/tools/run.py score   knowledge-base/opportunity-scores/opp-001-scorecard.json
  python3 opportunity-intelligence/tools/run.py evidence [--dir knowledge-base/customer-evidence]
  python3 opportunity-intelligence/tools/run.py cite EV-2026-W28-001,EV-2026-W28-002 [--dir ...]

Add --write <path> to also save the report as markdown (write only into
Workstream B folders; the tool refuses Workstream A paths).
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from opportunity_engine import (  # noqa: E402
    backlog,
    commercial,
    evidence,
    experiments,
    journal,
    montecarlo,
    results,
    scoring,
    sensitivity,
    stress,
    subsidy,
    sync,
)

JOURNAL_PATH = "knowledge-base/product-ideas/decision-journal.json"

FOREIGN_DIRS = (
    "customer-intelligence",
    "knowledge-base/customer-evidence",
    "knowledge-base/competitors",
    "knowledge-base/segments",
    "knowledge-base/inflection-points",
)


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"error: file not found: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"error: {path} is not valid JSON: {exc}")


def _emit(report, write_path):
    print(report, end="")
    if write_path:
        resolved = Path(write_path).resolve()
        for fd in FOREIGN_DIRS:
            if str(resolved).replace("\\", "/").find(f"/{fd}/") != -1 or str(resolved).endswith(fd):
                sys.exit(f"error: refusing to write into Workstream A / shared path: {write_path}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(report, encoding="utf-8")
        print(f"\n[written to {write_path}]", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("model", help="compute a three-case commercial model")
    p.add_argument("inputs")
    p.add_argument("--write")

    p = sub.add_parser("subsidy", help="compute an interchange subsidy model")
    p.add_argument("inputs")
    p.add_argument("--write")

    p = sub.add_parser("score", help="validate a 17-dimension scorecard")
    p.add_argument("scorecard")
    p.add_argument("--write")

    p = sub.add_parser("evidence", help="list Workstream A evidence records (read-only)")
    p.add_argument("--dir", default="knowledge-base/customer-evidence")

    p = sub.add_parser("cite", help="check EV-id citations against loaded records")
    p.add_argument("ids", help="comma-separated EV ids")
    p.add_argument("--dir", default="knowledge-base/customer-evidence")

    p = sub.add_parser("sensitivity", help="tornado analysis: which input hurts contribution most")
    p.add_argument("inputs")
    p.add_argument("--case", default="base", choices=list(commercial.CASES))
    p.add_argument("--degrade", type=float, default=0.5, help="perturbation factor (default 0.5 = ±50%%)")
    p.add_argument("--write")

    p = sub.add_parser("verdict", help="evaluate a VE result file against its pre-committed thresholds")
    p.add_argument("result")
    p.add_argument("--write")

    p = sub.add_parser("simulate", help="Monte Carlo over the three-case model (distributions, P(loss))")
    p.add_argument("inputs")
    p.add_argument("--n", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--write")

    p = sub.add_parser("stress", help="run named adverse scenarios (credit-and-run, adverse selection, ...)")
    p.add_argument("inputs")
    p.add_argument("--case", default="base", choices=list(commercial.CASES))
    p.add_argument("--scenarios", help="optional custom scenarios JSON (same shape as the built-in library)")
    p.add_argument("--write")

    p = sub.add_parser("grid", help="two-way stress grid: contribution across two inputs' ranges")
    p.add_argument("inputs")
    p.add_argument("--x", required=True, help="input for columns (e.g. routed_share)")
    p.add_argument("--y", required=True, help="input for rows (e.g. ecl_rate_annual)")
    p.add_argument("--case", default="base", choices=list(commercial.CASES))
    p.add_argument("--steps", type=int, default=7)
    p.add_argument("--write")

    p = sub.add_parser("predict", help="log a dated, falsifiable prediction (reasoning-protocol step 4)")
    p.add_argument("statement")
    p.add_argument("--p", type=float, required=True, help="probability strictly between 0 and 1")
    p.add_argument("--resolve-by", required=True, help="YYYY-MM-DD deadline")
    p.add_argument("--links", default="", help="comma-separated ids (VE-001, OPP-001, ...)")
    p.add_argument("--journal", default=JOURNAL_PATH)

    p = sub.add_parser("resolve", help="resolve a prediction true/false (probabilities are never edited)")
    p.add_argument("id")
    p.add_argument("outcome", choices=["true", "false"])
    p.add_argument("--note", default="")
    p.add_argument("--journal", default=JOURNAL_PATH)

    p = sub.add_parser("calibration", help="Brier score + calibration buckets + open/overdue predictions")
    p.add_argument("--journal", default=JOURNAL_PATH)
    p.add_argument("--write")

    p = sub.add_parser("sync", help="compare cited Workstream A evidence against scorecard scores (report-only)")
    p.add_argument("--root", default=".")
    p.add_argument("--write")

    p = sub.add_parser("check", help="sweep the whole knowledge base: models, scorecards, citations, VE specs, results, backlog, journal")
    p.add_argument("--root", default=".", help="repo root (default: cwd)")

    args = ap.parse_args(argv)

    try:
        if args.cmd == "model":
            model = _load_json(args.inputs)
            _emit(commercial.render_markdown(model, commercial.compute_model(model)), args.write)
        elif args.cmd == "subsidy":
            model = _load_json(args.inputs)
            _emit(subsidy.render_markdown(model, subsidy.compute_model(model)), args.write)
        elif args.cmd == "score":
            card = _load_json(args.scorecard)
            ev = scoring.evaluate(card)
            _emit(scoring.render_markdown(card, ev), args.write)
            if ev["violations"]:
                sys.exit(2)
        elif args.cmd == "evidence":
            print(evidence.render_markdown(evidence.load_records(args.dir)), end="")
        elif args.cmd == "cite":
            records = evidence.load_records(args.dir)
            result = evidence.check_citations(args.ids.split(","), records)
            print(json.dumps(result, indent=2))
            if result["missing"] or result["malformed"]:
                sys.exit(2)
        elif args.cmd == "sensitivity":
            model = _load_json(args.inputs)
            baseline, rows = sensitivity.analyse(model, args.case, args.degrade)
            _emit(sensitivity.render_markdown(model, args.case, args.degrade, baseline, rows), args.write)
        elif args.cmd == "verdict":
            ev = results.evaluate(_load_json(args.result))
            _emit(results.render_markdown(ev), args.write)
        elif args.cmd == "simulate":
            model = _load_json(args.inputs)
            sim = montecarlo.simulate(model, n=args.n, seed=args.seed)
            _emit(montecarlo.render_markdown(model, sim), args.write)
        elif args.cmd == "stress":
            model = _load_json(args.inputs)
            custom = _load_json(args.scenarios) if args.scenarios else None
            baseline, rows = stress.run(model, args.case, custom)
            _emit(stress.render_markdown(model, args.case, baseline, rows), args.write)
        elif args.cmd == "grid":
            model = _load_json(args.inputs)
            xs, ys, matrix = sensitivity.grid(model, args.x, args.y, args.case, args.steps)
            _emit(sensitivity.render_grid_markdown(model, args.x, args.y, args.case, xs, ys, matrix), args.write)
        elif args.cmd == "predict":
            import datetime
            data = journal.load(args.journal)
            entry = journal.add(
                data, args.statement, args.p,
                datetime.date.today().isoformat(), args.resolve_by,
                [x.strip() for x in args.links.split(",") if x.strip()],
            )
            journal.save(data, args.journal)
            print(f"logged {entry['id']} (p={entry['p']:.0%}, resolve by {entry['resolve_by']})")
        elif args.cmd == "resolve":
            import datetime
            data = journal.load(args.journal)
            entry = journal.resolve(data, args.id, args.outcome == "true",
                                    datetime.date.today().isoformat(), args.note)
            journal.save(data, args.journal)
            print(f"{entry['id']} resolved {entry['outcome']} (was p={entry['p']:.0%})")
        elif args.cmd == "calibration":
            import datetime
            cal = journal.calibration(journal.load(args.journal),
                                      today=datetime.date.today().isoformat())
            _emit(journal.render_markdown(cal), args.write)
        elif args.cmd == "sync":
            _emit(sync.render_markdown(sync.analyse(args.root)), args.write)
        elif args.cmd == "check":
            sys.exit(run_check(Path(args.root)))
    except commercial.InputError as exc:
        sys.exit(f"input error: {exc}")


EV_CITE_RE = re.compile(r"\bEV-\d{4}-W\d{2}-\d{3}\b")


def run_check(root):
    """Sweep the knowledge base; print a report; return exit code (0 ok, 1 failures)."""
    kb = root / "knowledge-base"
    failures, notes = [], []

    def ok(msg):
        print(f"  ok    {msg}")

    def fail(msg):
        failures.append(msg)
        print(f"  FAIL  {msg}")

    print("== commercial & subsidy models ==")
    model_files = sorted((kb / "commercial-models").glob("*.json"))
    for path in model_files:
        rel = path.relative_to(root)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if path.name.endswith("-subsidy-inputs.json"):
                subsidy.compute_model(data)
            elif path.name.endswith("-inputs.json"):
                commercial.compute_model(data)
            else:
                notes.append(f"skipped unrecognised json: {rel}")
                continue
            ok(f"{rel} computes across all three cases")
        except (commercial.InputError, json.JSONDecodeError) as exc:
            fail(f"{rel}: {exc}")
    if not model_files:
        notes.append("no model input files found")

    print("== scorecards ==")
    records = evidence.load_records(kb / "customer-evidence")
    for path in sorted((kb / "opportunity-scores").glob("*.json")):
        rel = path.relative_to(root)
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
            ev = scoring.evaluate(card)
        except (commercial.InputError, json.JSONDecodeError) as exc:
            fail(f"{rel}: {exc}")
            continue
        if ev["violations"]:
            fail(f"{rel}: " + "; ".join(ev["violations"]))
        else:
            ok(f"{rel} valid (composite {ev['composite_indicative']}, {ev['assumption_count']}/17 (A))")
        cited = sorted({m for e in ev["scores"].values() for m in EV_CITE_RE.findall(e["basis"])})
        if cited:
            res = evidence.check_citations(cited, records)
            if res["missing"] or res["malformed"]:
                fail(f"{rel}: citations not found in evidence records: "
                     + ", ".join(res["missing"] + res["malformed"]))
            if res["weak"]:
                notes.append(f"{rel}: weak-evidence citations (leads, not findings): " + ", ".join(res["weak"]))
    if not records:
        notes.append("no Workstream A evidence records yet — citation checks limited to format")

    print("== validation experiments ==")
    ve_results = experiments.validate_dir(kb / "validation")
    for path, issues in ve_results.items():
        rel = Path(path).relative_to(root)
        if issues:
            fail(f"{rel}: " + "; ".join(issues))
        else:
            ok(f"{rel} has all mandatory fields, quantified thresholds")

    print("== experiment results ==")
    for path in sorted((kb / "validation").glob("*-result.json")):
        rel = path.relative_to(root)
        try:
            ev = results.evaluate(json.loads(path.read_text(encoding="utf-8")))
        except (commercial.InputError, json.JSONDecodeError) as exc:
            fail(f"{rel}: {exc}")
            continue
        ve_id = ev["experiment_id"]
        if not list((kb / "validation").glob(f"{ve_id}-*.md")):
            fail(f"{rel}: no spec file {ve_id}-*.md for this result")
            continue
        ok(f"{rel}: verdict {ev['verdict'].upper()} → {ev['action'][:60]}")
        if ev["verdict"] in ("fail", "pass"):
            notes.append(f"{rel}: conclusive verdict {ev['verdict'].upper()} — "
                         f"ensure BACKLOG.md reflects the pre-committed action")

    print("== decision journal ==")
    journal_path = kb / "product-ideas" / "decision-journal.json"
    if journal_path.exists():
        import datetime
        try:
            cal = journal.calibration(journal.load(journal_path),
                                      today=datetime.date.today().isoformat())
        except commercial.InputError as exc:
            fail(f"decision-journal.json: {exc}")
        else:
            ok(f"decision-journal.json: {cal['n_resolved']} resolved, {len(cal['open'])} open"
               + (f", Brier {cal['brier']:.3f}" if cal["brier"] is not None else ""))
            for p in cal["overdue"]:
                fail(f"decision-journal.json: {p['id']} overdue (resolve by {p['resolve_by']}) — resolve it or log why")
    else:
        notes.append("no decision journal yet")

    print("== backlog ==")
    backlog_path = kb / "product-ideas" / "BACKLOG.md"
    if backlog_path.exists():
        data, issues = backlog.check(backlog_path)
        for issue in issues:
            fail(f"BACKLOG.md: {issue}")
        if not issues:
            ok(f"BACKLOG.md: {len(data['backlog'])} live, {len(data['archive'])} archived, "
               f"{len(data['requests'])} evidence requests")
        for ve_id in sorted(backlog.referenced_experiments(data)):
            if not list((kb / "validation").glob(f"{ve_id}-*.md")):
                fail(f"BACKLOG.md references {ve_id} but no {ve_id}-*.md exists in knowledge-base/validation/")
    else:
        notes.append("no BACKLOG.md yet")

    print()
    for note in notes:
        print(f"  note  {note}")
    print(f"\n{'CHECK FAILED' if failures else 'CHECK PASSED'} — {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    main()
