"""Read-only Merchant Voice tools for the Product Discovery Copilot.

Every function here calls ONLY app.published_query (Merchant Voice's own
read-only, Copilot-facing query layer) against a connection opened
STRICTLY READ-ONLY (SQLite URI mode=ro) — a real write attempt raises
sqlite3.OperationalError, not just a convention. This module never opens
identity.db, never performs a write, and never returns unreviewed/
rejected/suppressed/needs_revalidation content, draft proposals, or
researcher-only review notes — those guarantees live in
merchant-voice/app/published_query.py itself; this is a thin, read-only
caller.

Merchant Voice's own `app` package is loaded here under the distinct
module name "mv_app" (never the bare name "app") — copilot-backend's own
code is ALSO an `app` package, so importing merchant-voice's package under
its natural name would either fail or silently alias to the wrong
package. See _load_mv_app().
"""

import datetime
import importlib.util
import re
import sqlite3
import sys

from .config import REPO_ROOT

_MV_ROOT = REPO_ROOT / "merchant-voice"

CAMPAIGN_RE = re.compile(r"^MVC-[A-Za-z0-9-]{1,40}$")
FINDING_RE = re.compile(r"^MEF-[A-Za-z0-9-]{1,40}$")
SEG_RE = re.compile(r"^SEG-[a-z0-9][a-z0-9-]{0,60}$")
OPP_RE = re.compile(r"^OPP-\d{3}$")
ASM_RE = re.compile(r"^ASM-OPP-\d{3}-[a-z0-9_]{1,40}$")


class ToolError(Exception):
    def __init__(self, message, not_found=False):
        super().__init__(message)
        self.not_found = not_found


def _load_mv_app():
    if "mv_app" in sys.modules:
        return sys.modules["mv_app"]
    spec = importlib.util.spec_from_file_location(
        "mv_app", _MV_ROOT / "app" / "__init__.py",
        submodule_search_locations=[str(_MV_ROOT / "app")])
    module = importlib.util.module_from_spec(spec)
    sys.modules["mv_app"] = module
    spec.loader.exec_module(module)
    return module


_load_mv_app()
published_query = importlib.import_module("mv_app.published_query")
mv_db_module = importlib.import_module("mv_app.db")
mv_models = importlib.import_module("mv_app.models")

FINDING_TYPES = mv_models.OBSERVATION_TYPES


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def _validate(pattern, value, kind):
    if not isinstance(value, str) or not pattern.match(value):
        raise ToolError(f"invalid {kind} id: {value!r}")
    return value


def _conn(config):
    """A genuinely read-only SQLite connection — a write attempt through it
    raises sqlite3.OperationalError, not merely a documented convention.
    Returns None if mv.db does not exist yet (Merchant Voice never run)."""
    if not config.mv_db_path.exists():
        return None
    return sqlite3.connect(f"file:{config.mv_db_path}?mode=ro", uri=True)


def _empty_reason():
    return "no Merchant Voice research data is available yet"


# --- tools --------------------------------------------------------------------

def list_merchant_campaigns(config):
    conn = _conn(config)
    if conn is None:
        return {"campaigns": []}
    return {"campaigns": published_query.list_campaigns(conn)}


def get_merchant_campaign(config, campaign_id):
    _validate(CAMPAIGN_RE, campaign_id, "campaign")
    conn = _conn(config)
    if conn is None:
        raise ToolError(_empty_reason(), not_found=True)
    try:
        return published_query.get_campaign(conn, campaign_id)
    except mv_db_module.DbError:
        raise ToolError(f"{campaign_id} not found or has no published findings", not_found=True)


def get_campaign_summary(config, campaign_id):
    _validate(CAMPAIGN_RE, campaign_id, "campaign")
    conn = _conn(config)
    if conn is None:
        raise ToolError(_empty_reason(), not_found=True)
    try:
        return published_query.get_campaign_summary(conn, campaign_id)
    except mv_db_module.DbError:
        raise ToolError(f"{campaign_id} not found", not_found=True)


def get_approved_merchant_findings(config, campaign_id=None, finding_type=None):
    if campaign_id is not None:
        _validate(CAMPAIGN_RE, campaign_id, "campaign")
    if finding_type is not None and finding_type not in FINDING_TYPES:
        raise ToolError(f"finding_type must be one of {FINDING_TYPES}")
    conn = _conn(config)
    if conn is None:
        return {"findings": []}
    return {"findings": published_query.list_findings(conn, campaign_id=campaign_id, finding_type=finding_type)}


def get_segment_feedback(config, segment_id):
    _validate(SEG_RE, segment_id, "segment")
    conn = _conn(config)
    if conn is None:
        return {"findings": []}
    return {"findings": published_query.list_findings(conn, segment_id=segment_id)}


def get_opportunity_merchant_feedback(config, opportunity_id):
    _validate(OPP_RE, opportunity_id, "opportunity")
    conn = _conn(config)
    if conn is None:
        return {"findings": []}
    return {"findings": published_query.list_findings(conn, opportunity_id=opportunity_id)}


def get_assumption_feedback(config, assumption_id):
    _validate(ASM_RE, assumption_id, "assumption")
    conn = _conn(config)
    if conn is None:
        return {"findings": []}
    return {"findings": published_query.list_findings(conn, assumption_id=assumption_id)}


def get_merchant_objections(config, campaign_id=None):
    return get_approved_merchant_findings(config, campaign_id=campaign_id, finding_type="objection")


def get_merchant_workarounds(config, campaign_id=None):
    return get_approved_merchant_findings(config, campaign_id=campaign_id, finding_type="workaround")


def get_merchant_quotes(config, campaign_id=None, finding_id=None):
    if campaign_id is not None:
        _validate(CAMPAIGN_RE, campaign_id, "campaign")
    if finding_id is not None:
        _validate(FINDING_RE, finding_id, "finding")
    conn = _conn(config)
    if conn is None:
        return {"quotes": []}
    try:
        return {"quotes": published_query.get_merchant_quotes(conn, _now(), campaign_id=campaign_id,
                                                              finding_id=finding_id)}
    except mv_db_module.DbError:
        raise ToolError(f"{finding_id} not found", not_found=True)


def compare_segment_feedback(config, campaign_id, segment_a, segment_b):
    _validate(CAMPAIGN_RE, campaign_id, "campaign")
    _validate(SEG_RE, segment_a, "segment"); _validate(SEG_RE, segment_b, "segment")
    conn = _conn(config)
    if conn is None:
        raise ToolError(_empty_reason(), not_found=True)
    return published_query.compare_segment_feedback(conn, campaign_id, segment_a, segment_b)


def get_campaign_limitations(config, campaign_id):
    _validate(CAMPAIGN_RE, campaign_id, "campaign")
    conn = _conn(config)
    if conn is None:
        return {"campaign_id": campaign_id, "limitations": []}
    return published_query.get_campaign_limitations(conn, campaign_id)


# --- registry ------------------------------------------------------------------

def _schema(props, required):
    return {"type": "object", "properties": props, "required": required}


_ID = {"type": "string"}

REGISTRY = {
    "list_merchant_campaigns": (list_merchant_campaigns, _schema({}, []),
                                "List Merchant Voice campaigns with at least one published finding"),
    "get_merchant_campaign": (get_merchant_campaign, _schema({"campaign_id": _ID}, ["campaign_id"]),
                             "Campaign metadata (published-finding-bearing campaigns only)"),
    "get_campaign_summary": (get_campaign_summary, _schema({"campaign_id": _ID}, ["campaign_id"]),
                            "Published findings for a campaign, grouped by finding type, with limitations"),
    "get_approved_merchant_findings": (
        get_approved_merchant_findings,
        _schema({"campaign_id": _ID, "finding_type": _ID}, []),
        "Approved+published findings, optionally filtered by campaign and/or finding type "
        "(pain, objection, workaround, willingness_to_pay_signal, concept_reaction, contradiction, ...)"),
    "get_segment_feedback": (get_segment_feedback, _schema({"segment_id": _ID}, ["segment_id"]),
                            "Published findings for one merchant segment"),
    "get_opportunity_merchant_feedback": (
        get_opportunity_merchant_feedback, _schema({"opportunity_id": _ID}, ["opportunity_id"]),
        "Published findings linked to one opportunity"),
    "get_assumption_feedback": (get_assumption_feedback, _schema({"assumption_id": _ID}, ["assumption_id"]),
                               "Published findings linked to one assumption"),
    "get_merchant_objections": (get_merchant_objections, _schema({"campaign_id": _ID}, []),
                               "Published objection findings"),
    "get_merchant_workarounds": (get_merchant_workarounds, _schema({"campaign_id": _ID}, []),
                                "Published workaround findings"),
    "get_merchant_quotes": (get_merchant_quotes, _schema({"campaign_id": _ID, "finding_id": _ID}, []),
                           "Direct-quote observations still permission/consent/retention-eligible, linked to "
                           "a published finding"),
    "compare_segment_feedback": (
        compare_segment_feedback,
        _schema({"campaign_id": _ID, "segment_a": _ID, "segment_b": _ID},
               ["campaign_id", "segment_a", "segment_b"]),
        "Side-by-side published findings for two segments in one campaign — never pooled"),
    "get_campaign_limitations": (get_campaign_limitations, _schema({"campaign_id": _ID}, ["campaign_id"]),
                                "Limitations recorded across a campaign's published findings"),
}


def tool_specs():
    return [{"name": name, "description": desc, "input_schema": schema}
            for name, (_, schema, desc) in REGISTRY.items()]


def call_tool(config, name, arguments):
    if name not in REGISTRY:
        raise ToolError(f"tool {name!r} is not in the allowlist")
    fn, schema, _ = REGISTRY[name]
    args = arguments or {}
    unknown = set(args) - set(schema["properties"])
    if unknown:
        raise ToolError(f"unknown arguments: {sorted(unknown)}")
    missing = [k for k in schema["required"] if k not in args]
    if missing:
        raise ToolError(f"missing arguments: {missing}")
    return fn(config, **args)
