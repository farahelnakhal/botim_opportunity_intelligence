"""Source corroboration for verified-source market sizing (Phase C2).

Pure and deterministic. Given several figures for the SAME quantity — each
already number-verified against a cited source (`shared/research/figures.py`)
and tier-tagged from the human-curated registry (`shared/research/source_tier.py`)
— decide whether the quantity is **corroborated** or only **low-confidence**.

The corroboration rule (decision-log 2026-07-20, C2 · G1/G2):

- A quantity is **`verified`** iff **≥2 INDEPENDENT T1/T2 sources agree within
  the tolerance band**. *Independent* = **distinct registrable domain**: a figure
  repeated across a primary and an aggregator is one voice, not two. **T3/T4
  sources never count toward the ≥2 T1/T2 requirement** — recorded as context
  only. This is where the Statista gap is closed at the tier layer: Statista is
  tiered **T3** in the R9a registry *precisely because it is an AGGREGATOR that
  re-publishes others' figures*, so "a primary source + Statista repeating it"
  can never look like two independent sources.
- Otherwise **`low_confidence`** — single-source, only lower-tier, disagreeing
  T1/T2, or mixed units. Never dropped, never silently upgraded: an
  uncorroborated figure is stored and shown as low-confidence, **never identical
  to a verified one**.
- **Agreement:** two values agree iff `|a-b| / max(|a|,|b|) <= tolerance`
  (default 0.10 — a deliberately tight band; genuinely disagreeing market-sizing
  figures, often 2–5× apart, can never look corroborated). The representative
  value is the **median** of the agreeing T1/T2 set (outlier-robust, conservative).

No model, no estimation, no network: this only compares numbers already
extracted-and-verified from cited sources.
"""

import os
import statistics

from .source_tier import tier_for, _hostname

DEFAULT_TOLERANCE = 0.10
T1_T2 = ("T1", "T2")

# Multi-part public suffixes so distinct government/registered entities under a
# shared suffix are NOT collapsed into one voice (sca.gov.ae and mohre.gov.ae
# are two independent regulators, not one "gov.ae"). Superset of source_tier's
# _GOV_SUFFIXES plus the common commercial multi-part suffixes in the registry.
_MULTIPART_SUFFIXES = (
    ".gov.ae", ".gov.uk", ".gov.sa", ".gov.qa", ".gov.bh", ".gov.kw",
    ".gov.om", ".govt.nz", ".gc.ca", ".co.uk", ".com.au", ".co.jp", ".org.uk",
)


def tolerance():
    """The corroboration tolerance band (relative). `C2_CORROBORATION_TOLERANCE`
    overrides the tight 0.10 default; an unparseable/negative value is ignored."""
    raw = os.environ.get("C2_CORROBORATION_TOLERANCE", "")
    try:
        val = float(raw)
        return val if val > 0 else DEFAULT_TOLERANCE
    except (TypeError, ValueError):
        return DEFAULT_TOLERANCE


def registrable_key(url_or_domain):
    """The independence key for a source: its registrable domain (eTLD+1-ish),
    so `data.worldbank.org` and `worldbank.org` are ONE voice while
    `sca.gov.ae` and `mohre.gov.ae` stay two. Deterministic; no network."""
    host = _hostname(url_or_domain)
    if not host:
        return ""
    for suffix in _MULTIPART_SUFFIXES:
        if host.endswith(suffix):
            labels = host.split(".")
            n = suffix.count(".") + 1        # keep one label before the suffix
            return ".".join(labels[-(n + 1):]) if len(labels) > n else host
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def _agree(a, b, tol):
    hi = max(abs(a), abs(b))
    if hi == 0:
        return True                          # both exactly zero
    return abs(a - b) / hi <= tol


def _median(values):
    return statistics.median(values)


def corroborate(figures, *, tol=None):
    """`figures`: list of dicts, each at least {value, source_id, url} (url may be
    a bare domain); optional `unit`, `tier` (else derived via the registry).
    Returns a verdict dict (see module docstring). Pure — never mutates inputs."""
    if tol is None:
        tol = tolerance()

    clean = []
    units = set()
    for f in figures or []:
        value = f.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        url = f.get("url") or f.get("domain") or ""
        tier = f.get("tier") or tier_for(url)
        if f.get("unit"):
            units.add(f["unit"])
        clean.append({
            "value": float(value), "source_id": f.get("source_id"),
            "url": url, "domain": registrable_key(url), "tier": tier,
            "unit": f.get("unit"),
        })

    tier_breakdown = {t: sum(1 for c in clean if c["tier"] == t) for t in ("T1", "T2", "T3", "T4")}
    unit = next(iter(units)) if len(units) == 1 else None

    # one VOICE per distinct registrable domain among T1/T2 sources (a domain
    # heard twice is still one voice); the voice value is that domain's median.
    voices = {}
    for c in clean:
        if c["tier"] in T1_T2 and c["domain"]:
            voices.setdefault(c["domain"], []).append(c)
    voice_list = sorted(
        ({"domain": d, "value": _median([c["value"] for c in cs]),
          "source_ids": [c["source_id"] for c in cs], "tier": cs[0]["tier"]}
         for d, cs in voices.items()),
        key=lambda v: v["value"])

    result = {
        "status": "low_confidence",
        "value": None,
        "unit": unit,
        "tolerance": tol,
        "independent_t1_t2_count": len(voice_list),
        "tier_breakdown": tier_breakdown,
        "supporting_source_ids": [],
        "agreeing_domains": [],
        "reason": None,
        "figures": [{"value": c["value"], "source_id": c["source_id"],
                     "domain": c["domain"], "tier": c["tier"]} for c in clean],
    }

    if len(units) > 1:
        result["reason"] = "unit_mismatch"
        return result
    if not clean:
        result["reason"] = "no_figures"
        return result

    # representative fallback for a low-confidence quantity: the median of the
    # best-tier voices we do have (T1/T2 if any, else all figures) — stored,
    # flagged, never presented as validated.
    if voice_list:
        result["value"] = _median([v["value"] for v in voice_list])
    else:
        result["value"] = _median([c["value"] for c in clean])

    if not voice_list:
        result["reason"] = "only_lower_tier_sources"
        return result
    if len(voice_list) < 2:
        result["reason"] = "single_source"
        return result

    # largest contiguous (value-sorted) run of voices whose span fits the band.
    best = (0, 0)
    for i in range(len(voice_list)):
        j = i
        while j + 1 < len(voice_list) and _agree(voice_list[i]["value"], voice_list[j + 1]["value"], tol):
            j += 1
        if (j - i) > (best[1] - best[0]):
            best = (i, j)
    i, j = best
    agreeing = voice_list[i:j + 1]
    if len(agreeing) >= 2:
        result["status"] = "verified"
        result["reason"] = "corroborated"
        result["value"] = _median([v["value"] for v in agreeing])
        result["agreeing_domains"] = [v["domain"] for v in agreeing]
        result["supporting_source_ids"] = [sid for v in agreeing for sid in v["source_ids"]]
    else:
        result["reason"] = "t1_t2_sources_disagree"
    return result
