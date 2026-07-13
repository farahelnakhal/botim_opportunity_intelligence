#!/usr/bin/env python3
"""Build the executive UI: collect the read-only model, render static HTML.

Usage (from repo root):
  python3 executive-ui/build.py                 # build into executive-ui/dist/
  python3 executive-ui/build.py --out DIR
  python3 executive-ui/build.py --serve [--port 8000]   # build then serve dist/

Reads real repository outputs. Writes ONLY into the output dir (default
executive-ui/dist/, gitignored). Never touches the knowledge base.
"""

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from adapter import collect  # noqa: E402
from render import (assumptions, brief, evidence, feed, opportunity,  # noqa: E402
                    overview, proposal)


def build(root=".", out=None):
    out = Path(out) if out else HERE / "dist"
    out.mkdir(parents=True, exist_ok=True)
    model = collect.build_model(root)

    pages = {
        "index.html": overview.render(model),
        "evidence.html": evidence.render(model),
        "assumptions.html": assumptions.render(model),
        "feed.html": feed.render(model),
        "proposals.html": proposal.render(model),
        "briefs.html": brief.render(model),
    }
    pages.update(opportunity.render_all(model))
    for name, html in pages.items():
        (out / name).write_text(html, encoding="utf-8")

    for asset in ("app.css", "app.js"):
        src = HERE / "static" / asset
        if src.exists():
            shutil.copyfile(src, out / asset)

    return out, model, list(pages)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    out, model, pages = build(args.root, args.out)
    print(f"built {len(pages)} pages into {out}")
    print(f"  {model.generated_note}")
    print(f"  opportunities: {', '.join(o.id for o in model.opportunities)}"
          + (f" · archived: {', '.join(o.id for o in model.archived)}" if model.archived else ""))
    if args.serve:
        import functools
        import http.server
        import socketserver
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
        print(f"serving {out} at http://localhost:{args.port} (Ctrl-C to stop)")
        with socketserver.TCPServer(("", args.port), handler) as httpd:
            httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
