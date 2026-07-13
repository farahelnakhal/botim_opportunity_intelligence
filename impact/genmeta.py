"""Generated-output metadata so Farah's UI can detect stale outputs.

Every generated JSON/Markdown read model carries: schema_version, generated_at,
source_files, source_hashes, engine identifier, generator version. `generated_at`
is injectable (pass `now`) so identical inputs regenerate byte-identically in
tests.
"""

from pathlib import Path

from . import paths

SCHEMA_VERSION = "1.0"
GENERATOR_VERSION = "1.0.0"
ENGINE_ID = "opportunity_engine.scoring"


def _rel(p):
    try:
        return str(Path(p).resolve().relative_to(paths.REPO_ROOT))
    except ValueError:
        return str(p)


def build_meta(kind, source_paths, now):
    """kind: read-model name; source_paths: files consumed; now: ISO timestamp
    string (caller supplies — never invented here)."""
    files, hashes = [], {}
    for p in source_paths:
        p = Path(p)
        rel = _rel(p)
        files.append(rel)
        hashes[rel] = paths.sha256_text(p.read_text(encoding="utf-8")) if p.exists() else None
    return {
        "kind": kind,
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "engine": ENGINE_ID,
        "generated_at": now,
        "source_files": files,
        "source_hashes": hashes,
        "is_derived": True,
        "authoritative": False,
        "note": "Generated read model — not independently editable; regenerate from authoritative sources. Never a second source of truth.",
    }


def stale(meta):
    """Return the list of source files whose current hash differs from the
    recorded hash (empty => the generated output is up to date)."""
    changed = []
    for rel, recorded in meta.get("source_hashes", {}).items():
        p = paths.REPO_ROOT / rel
        current = paths.sha256_text(p.read_text(encoding="utf-8")) if p.exists() else None
        if current != recorded:
            changed.append(rel)
    return changed
