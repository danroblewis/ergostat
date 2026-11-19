"""What a remote ergostat serves of its model (SPEC §4c): the merged document the compiler sees, after includes are
read and templates expanded, redacted (no commands, prompts, queries, sources, workspaces or actions), with a
version: the first 16 hex of the SHA-256 of its canonical JSON. Parts this model itself imported from a remote
are not served: a remote of a remote is not composed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FORMAT = "ergostat-model/1"
SERVED = ("systems", "items", "parameters", "auxiliaries", "stocks", "flows", "goals", "blocks", "agents")
SENSOR_KINDS = ("items", "run", "query", "manual", "changes", "builtin")
SENSOR_KEEP = {"every", "cron", "unit", "description", "averages", "state", "entering", "leaving", "over", "measure",
               "items", "changes", "builtin", "manual"}
PART_KEEP = {
    "systems": {"description", "within", "show"},
    "items": {"id", "states", "show", "description", "system"},
    "parameters": {"value", "unit", "estimate", "table", "range", "description", "system"},
    "auxiliaries": {"unit", "driven-by", "exogenous", "equation", "description", "system"},
    "stocks": {"unit", "limit", "initial", "cumulative", "rate-unit", "description", "system"},
    "flows": {"from", "to", "unit", "rate", "driven-by", "two-way", "equation", "rate-unit", "description", "system"},
    "goals": {"stock", "flow", "auxiliary", "variable", "hold", "tolerance", "critical", "process", "description",
              "system"},
    "blocks": {"type", "in", "out", "goal", "until", "agent", "role", "every", "cron", "max", "min", "description",
               "system"},
    "agents": {"kind", "description"},
}


def plain(x):
    """The loader's maps as plain JSON values."""
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [plain(v) for v in x]
    if x is None or isinstance(x, bool | int | float | str):
        return x
    return str(x)


def sensor(raw) -> dict:
    """A sensor as served: what kind of instrument it is and how often it reads; never its command or query."""
    if not isinstance(raw, dict):
        return {"kind": "manual"}
    kind = next((k for k in SENSOR_KINDS if raw.get(k) not in (None, False)), "run")
    out = {k: plain(v) for k, v in raw.items() if k in SENSOR_KEEP}
    out["kind"] = kind
    if kind == "query":
        out.pop("query", None)
    return out


def part(section: str, raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {k: plain(v) for k, v in raw.items() if k in PART_KEEP[section]}
    if section in ("stocks", "flows", "auxiliaries"):
        sensors = dict(raw.get("sensors") or {}) if isinstance(raw.get("sensors"), dict) else {}
        if raw.get("sensor") is not None:
            sensors["main"] = raw["sensor"]
        if sensors:
            out["sensors"] = {str(n): sensor(s) for n, s in sensors.items()}
    return out


def imported(entry) -> bool:
    """A part this model took from one of its own remotes (compose.py marks where it came from)."""
    from .compose import RemoteVia
    return isinstance(getattr(entry, "where", None), RemoteVia)


def document(doc) -> dict:
    """The served model, from a loaded document (spec.load.Document)."""
    sections = {}
    for section in SERVED:
        got = {}
        for name, entry in (doc.sections.get(section) or {}).items():
            if imported(entry):
                continue
            got[str(name)] = part(section, entry)
        if section == "auxiliaries":                             # the old name, read as the new
            for name, entry in (doc.sections.get("variables") or {}).items():
                if not imported(entry):
                    got[str(name)] = part(section, entry)
        sections[section] = got
    return {"format": FORMAT, "name": doc.name, "sections": sections}


def version_of(served: dict) -> str:
    body = json.dumps({"format": served.get("format"), "sections": served.get("sections")}, sort_keys=True,
                      separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def model(path: Path) -> dict:
    """The served model of the project whose main file is ``path``, with its version."""
    from ..spec.load import load as load_doc
    doc = load_doc(path)
    served = document(doc)
    served["version"] = version_of(served)
    return served
