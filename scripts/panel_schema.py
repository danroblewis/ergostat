"""Write the panel part of schema/ergostat.schema.json from the kinds of panel the model checks
(ergostat/spec/dashboards.py: KINDS, NEEDS, PANEL_KEYS), so the schema and `ergostat check` never disagree on which
kinds there are and which keys each takes. Run after adding a kind: uv run python scripts/panel_schema.py"""

from __future__ import annotations

import json
from pathlib import Path

from ergostat.spec import dashboards as d

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "ergostat.schema.json"
TEXT = {"type": "string", "minLength": 1}
FLAG = {"type": "boolean"}
NAMES = {"oneOf": [{"type": "string"}, {"type": "array", "minItems": 1, "items": {"type": "string"}}]}
# the parameters the newer kinds take (the older ones' are in the schema already): each one's type
PARAMS = {
    "fit": FLAG, "quiet": FLAG, "address": {"type": "string", "pattern": "^/diagram"},
    "agent": {"anyOf": [{"$ref": "#/$defs/name"}, {"const": "$agent"}]},     # $agent: the page's address's (page: agent)
    "columns": {"oneOf": [{"enum": list(d.GOAL_COLUMNS)}, {"type": "array", "minItems": 1, "items": {"enum": list(d.GOAL_COLUMNS)}}]},
    "item": TEXT, "q": TEXT, "sort": TEXT, "history": TEXT, "match": TEXT, "about": {"$ref": "#/$defs/name"},
    "machine": TEXT, "remote": TEXT, "runs": FLAG, "window": FLAG,
    "from": {"type": "number", "minimum": 0}, "to": {"type": "number", "minimum": 0},
    "finished": {"enum": ["hide", "waits", "show"]}, "states": {"enum": ["all", "groups"]},
    "per_kind": {"type": "integer", "minimum": 1, "maximum": 500},
    "view": {"enum": ["dynamics", "blocks", "process"]},
    "show": {"oneOf": [{"enum": ["waiting", "off", "housekeeping", "suggestions"]},
                       {"type": "array", "minItems": 1, "items": {"enum": ["waiting", "off", "housekeeping", "suggestions"]}}]},
}


def panel(old: dict) -> dict:
    props = {**old["properties"], **PARAMS}
    props["panel"] = {"enum": list(d.KINDS)}
    missing = sorted(set().union(*d.KINDS.values(), d.PANEL_KEYS) - set(props))
    if missing:
        raise SystemExit(f"no type in the schema for: {', '.join(missing)} (add it to PARAMS)")
    rules = []
    for kind, keys in d.KINDS.items():
        then: dict = {"propertyNames": {"enum": sorted(d.PANEL_KEYS | keys, key=lambda k: (k != "panel", k))}}
        if d.NEEDS.get(kind):
            then = {"required": [d.NEEDS[kind]], **then}
        rules.append({"if": {"properties": {"panel": {"const": kind}}}, "then": then})
    return {**old, "properties": props, "allOf": rules}


def dump(v, indent: int) -> str:
    """As the file is written by hand: a value that fits on a line of 120 on one line, else one key or item a line."""
    flat = json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
    if len(flat) + indent <= 120 or not isinstance(v, dict | list) or not v:
        return flat
    pad = " " * (indent + 2)
    if isinstance(v, list):
        return "[\n" + ",\n".join(pad + dump(x, indent + 2) for x in v) + "\n" + " " * indent + "]"
    return "{\n" + ",\n".join(f"{pad}{json.dumps(k)}: {dump(x, indent + 2)}" for k, x in v.items()) + "\n" + " " * indent + "}"


def main() -> None:
    """Only the panel's own text is written again; the rest of the file stays byte for byte."""
    text = SCHEMA.read_text()
    new = panel(json.loads(text)["$defs"]["panel"])
    defs = text.index('"$defs"')
    start = text.index('"panel": {', defs)
    line = text.rfind("\n", 0, start) + 1
    depth, i = 0, text.index("{", start)
    for i in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            break
    SCHEMA.write_text(text[:start] + '"panel": ' + dump(new, start - line) + text[i + 1:])
    assert json.loads(SCHEMA.read_text())["$defs"]["panel"] == new


if __name__ == "__main__":
    main()
