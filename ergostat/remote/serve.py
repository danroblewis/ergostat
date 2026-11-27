"""What a remote ergostat serves of its model (SPEC §4c): the merged document the compiler sees, after includes are
read and templates expanded, redacted (no commands, prompts, queries, sources, workspaces or actions), with a
version: the first 16 hex of the SHA-256 of its canonical JSON (its format, this ergostat's instance id and its
sections). Every part carries ``via``: the instance ids it came through before reaching this ergostat, origin
first (``[]`` for this model's own; for a part imported from a remote, that remote's ``via`` for it and the
remote's instance), so a consumer composes a remote of a remote and cuts what comes back to it. A stand-in for a
part a remote no longer serves is not served."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FORMAT = "ergostat-model/1"
SERVED = ("systems", "projections", "parameters", "auxiliaries", "stocks", "flows", "goals", "blocks", "agents")
SENSOR_KINDS = ("projection", "run", "query", "manual", "changes", "builtin")
SENSOR_KEEP = {"every", "cron", "unit", "description", "averages", "state", "entering", "leaving", "over", "measure",
               "projection", "changes", "builtin", "manual"}
PART_KEEP = {
    "systems": {"description", "within", "show"},
    "projections": {"match", "states", "show", "description", "system"},
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


def via_of(entry) -> list[str] | None:
    """The chain a part came through before this ergostat (compose.py marks a remote's parts); None: a stand-in,
    never served."""
    from .compose import RemoteVia
    w = getattr(entry, "where", None)
    if not isinstance(w, RemoteVia):
        return []
    return None if w.stand_in else list(w.chain)


def box(name, entry) -> dict:
    """A remote's system box is served with the description its owner wrote, else a generic one: never the text
    naming the remote's url, which is a source (and may carry a user and password)."""
    from .compose import WHERE_TEXT, RemoteVia
    w = getattr(entry, "where", None)
    if not isinstance(w, RemoteVia) or w.chain or str(entry.get("description")) != WHERE_TEXT.format(w.url):
        return {}
    return {"description": f"remote: {name}, composed from another ergostat"}


def document(doc, instance: str) -> dict:
    """The served model, from a loaded document (spec.load.Document), as the ergostat ``instance`` serves it."""
    sections = {}
    for section in SERVED:
        got = {}
        named = list((doc.sections.get(section) or {}).items())
        if section == "auxiliaries":                             # the old name, read as the new
            named += list((doc.sections.get("variables") or {}).items())
        for name, entry in named:
            via = via_of(entry)
            if via is not None:
                got[str(name)] = {**part(section, entry), "via": via, **(box(name, entry) if section == "systems"
                                                                           else {})}
                if section == "projections" and isinstance(entry, dict) and entry.get("match") is None:
                    got[str(name)]["match"] = {"key": implied(doc, str(name), entry)}   # the host names it for the remote
        sections[section] = got
    return {"format": FORMAT, "name": doc.name, "instance": instance, "sections": sections}


def implied(doc, name: str, entry) -> str:
    """The id a projection that writes none matches here (SPEC §5a), served written out: the consumer renames it and
    puts it in a system of its own, so it could not work this out."""
    from ..spec.belongs import of
    from ..spec.compile import implied_id
    system = entry.get("system") or doc.defaults.get(("projections", name), {}).get("system")
    systems = doc.sections.get("systems") or {}
    chain: list[str] = []
    s = system
    while isinstance(s, str) and s and s not in chain:
        chain.append(s)
        s = (systems.get(s) or {}).get("within") if isinstance(systems.get(s), dict) else None
    b = of(doc.defined.get(("projections", name)))
    return implied_id(list(reversed(chain)), b.short if b is not None and b.system == system else name)


def version_of(served: dict) -> str:
    body = json.dumps({"format": served.get("format"), "instance": served.get("instance"),
                       "sections": served.get("sections")}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def model(path: Path, state: Path | None = None) -> dict:
    """The served model of the project whose main file is ``path``, with its version. Raises ``InstanceError`` when
    this ergostat's instance id cannot be read: no model is served then."""
    from ..spec.load import load as load_doc
    from ..store import state_dir
    from .instance import own
    doc = load_doc(path)
    served = document(doc, own(state or state_dir(doc.name, doc.root)))
    served["version"] = version_of(served)
    return served
