"""What a template from a folder the owner did not mark trusted may make (SPEC §2a, *Libraries you did not write*).

A use is held when its template, or any template it uses at any depth, came from an untrusted ``library:`` folder.
Every part made from the first untrusted template downward (trusted and ergostat's own templates nested under it too)
is checked here, as expanded: after its parameters' values (``with:``, defaults) are put in, so a key or a value that
only appears once substituted is checked like one written out.

It is an allowlist. A section, a key, a block type or a value's shape not listed below as allowed is refused: a key
compile gains later is refused here until it is listed. ``NO`` marks the keys refused by name (each with its reason),
so that every key compile reads is classified (tests/test_library_trust.py, ``test_every_compile_key_classified``).
``inferred`` and ``formerly`` are refused everywhere: a library may not say ergostat inferred a part (invariant 11).

The shapes: ``S`` one value (text, number, true or false); ``L`` one value or a list of them; ``M`` a map of names to
one value or a list of them; ``D`` data (values, lists and maps), read by compile only as numbers or names; ``A``
anything (only under a ``uses:`` entry's ``with:``, whose values reach only the nested template's parts, which are
checked themselves). A map is a table of its own keys; ``each(T)`` a map of names to T; ``list_of(T)`` a list of T;
``one_of(...)`` any of them."""

from __future__ import annotations

from ..spec.ir import Ref

S, L, M, D, A, NO = "one value", "values", "map of values", "data", "anything", "refused"
CLAIMS = ("inferred", "formerly")       # invariant 11: a library never claims ergostat inferred a part


def each(t):
    return ("each", t)


def list_of(t):
    return ("list", t)


def one_of(*ts):
    return ("or", *ts)


COMMON = {"system": (S, "the system it is drawn in"), "description": (S, "words shown with it")}
CLAIMED = {"inferred": (NO, "says ergostat inferred it, which a library may not claim (invariant 11)"),
           "formerly": (NO, "says it is a part renamed, which carries another part's record over to it")}

SENSOR = {     # where sensors live: stocks.X.sensor(s), flows.X.sensor(s), auxiliaries.X.sensor(s)
    "items": (S, "counts items of a kind from the record ergostat already keeps; runs nothing"),
    "state": (L, "which states of the kind are counted"),
    "entering": (S, "a flow counted as items enter this state"),
    "leaving": (S, "a flow counted as items leave this state"),
    "where": (M, "which items are counted, by their fields"),
    "over": (S, "the window a count is taken over"),
    "measure": (S, "count, oldest or age of the counted items"),
    "sum": (S, "a field summed instead of a count"),
    "changes": (S, "a flow read from its stock's own readings"),
    "unit": (S, "the unit it is shown in"),
    "description": (S, "words shown with it"),
    "run": (NO, "runs a command"),
    "query": (NO, "reads an outside source over the network"),
    "daemon": (NO, "starts and keeps a process"),
    "push": (NO, "takes readings pushed from outside"),
    "parse": (NO, "only means something on a command's or query's output"),
    "every": (NO, "starts readings on a timer"),
    "cron": (NO, "starts readings on a schedule"),
    "timeout": (NO, "only means something for a command"),
    "builtin": (NO, "runs ergostat's own measure as a process of its own, on a timer"),
    "manual": (NO, "asks a person for readings"),
    "averages": (NO, "only means something on a command's, query's or person's reading"),
}
SENSORS = {"sensors": (each(SENSOR), "its sensors, by name"), "sensor": (SENSOR, "its one sensor")}
LINK = {"cause": (S, "what it follows"), "instant": (S, "the dependence is immediate"),
        "description": (S, "words shown with it"), "inferred": CLAIMED["inferred"]}
DRIVEN = {"driven-by": (one_of(L, LINK, list_of(one_of(S, LINK))), "the causes drawn into it")}
PROCESS = {"gain": (S, "the loop's process gain"), "time-constant": (S, "its time constant"),
           "dead-time": (S, "its dead time"), "integrating": (S, "an integrating process"),
           "identified": (S, "words on where the numbers came from"), "description": (S, "words shown with it")}
REL = {"kind": (L, "the kind it names"), "precedence": (S, "it orders the work"), "inverse": (S, "the reverse's name"),
       "group": (S, "it groups items"), "description": (S, "words shown with it")}
JOIN = {"children": (S, "the relation children name it by"), "all": (L, "the states all must reach"),
        "any": (L, "the states any must reach"), "to": (S, "the state it moves to")}

SYSTEM = {"description": (S, "words shown with it"), "within": (S, "the system it is drawn in"),
          "show": (L, "parts shown on its box")}
ITEM = {**COMMON, "id": (S, "which ids are this kind"), "states": (L, "its states"),
        "on": (M, "which event moves it to which state"), "show": (L, "fields shown"), "formats": (M, "how fields are shown"),
        "fold": (M, "how events' fields fold into it"), "relations": (each(one_of(L, REL)), "relations to other items"),
        "join": (one_of(JOIN, list_of(JOIN)), "a parent moved on by its children's states"),
        "about": (S, "the field naming the parts it is about; only check reads it"),
        "lease": (NO, "makes its items a work queue that blocks take and run")}
STOCK = {**COMMON, **CLAIMED, **SENSORS, "unit": (S, "its unit"), "limit": (S, "its most"), "initial": (S, "its first value"),
         "cumulative": (S, "a running total"), "rate-unit": (S, "how its rate is shown"),
         "observe": (S, "kept by the observer between readings")}
FLOW = {**COMMON, **CLAIMED, **SENSORS, **DRIVEN, "from": (S, "the stock it drains"), "to": (S, "the stock it fills"),
        "unit": (S, "its unit"), "rate": (S, "its rate"), "two-way": (S, "it runs both ways"),
        "equation": (S, "its rate as arithmetic on the model's names, read by ergostat's own parser"),
        "rate-unit": (S, "how its rate is shown")}
AUXILIARY = {**COMMON, **CLAIMED, **SENSORS, **DRIVEN, "unit": (S, "its unit"), "exogenous": (S, "set from outside the model"),
             "equation": (S, "its value as arithmetic on the model's names, read by ergostat's own parser")}
PARAMETER = {**COMMON, **CLAIMED, "value": (S, "its value"), "unit": (S, "its unit"), "estimate": (S, "the value is a guess"),
             "table": (D, "a lookup table of numbers"), "range": (L, "what it might be, for sensitivity")}
GOAL = {**COMMON, "stock": (S, "what it holds"), "flow": (S, "what it holds"), "auxiliary": (S, "what it holds"),
        "variable": (S, "what it holds (the old name)"), "hold": (S, "its setpoint"), "tolerance": (S, "its band"),
        "critical": (S, "drawn and checked as critical; runs and sends nothing"), "process": (PROCESS, "the loop's process"),
        "per": (S, "held per item or per group"),
        "owner": (NO, "names who answers for it, which only the owner says"),
        "on-stale": (NO, "changes what the engine does when its reading is stale")}
USE = {"use": (S, "the nested template, whose parts are checked here too"), "within": (S, "the system it is drawn in"),
       "description": (S, "words shown with it"),
       "with": (A, "its values reach only the nested template's parts, checked themselves once expanded")}
BLOCK = {**COMMON, "type": (S, "one of the types below; any other is refused"), "in": (one_of(L, M), "what it reads"),
         "out": (L, "the signal it writes; only to a part the held chain made itself (see OUT_TO): "
                    "another block's input commands that block, and a goal's is its setpoint"),
         "role": (S, "how it is drawn"),
         "on-stale": (NO, "changes what the engine does when an input is stale")}
BLOCK_TYPES = {      # computed by ergostat itself from its inputs: none runs, calls out, notifies or starts an action
    "onoff": {"goal": (S, "the setpoint it holds"), "until": (S, "a setpoint it stops at"),
              "min-on": (S, "least time on"), "min-off": (S, "least time off")},
    "compare": {"above": (S, "a threshold"), "below": (S, "a threshold"), "back-above": (S, "a threshold back"),
                "back-below": (S, "a threshold back")},
    "proportional": {"goal": (S, "the setpoint"), "gain": (S, "its gain"), "min": (S, "its clamp"), "max": (S, "its clamp")},
    "limit": {"min": (S, "its clamp"), "max": (S, "its clamp"), "rate": (S, "its rate limit")},
    "delay": {"delay": (S, "how long its input is held back")},
    "schedule": {"table": (D, "the value by time of day; it outputs a number and starts nothing")},
    "lookup": {"table": (D, "a table from input to output")},
    "select": {"pick": (S, "min, max or first of its inputs")},
    "expr": {"expr": (S, "arithmetic on its inputs, read by ergostat's own parser (no names but its inputs)")},
    "timer": {"after": (S, "how long its input is on before its output is; it outputs a number and starts nothing")},
    "counter": {"reset": (S, "when its count goes back to 0")},
    "alarm": {"above": (S, "a threshold"), "below": (S, "a threshold"),
              "for": (S, "how long past it before raised; raised, it outputs 1, shown on the page; it sends nothing")},
}
REFUSED_TYPES = {"program": "runs a command", "ai": "starts an AI session", "person": "asks a person to act",
                 "external": "stands for something acting outside", "judge": "judges and applies changes to the model"}

ALLOWED = {"systems": SYSTEM, "items": ITEM, "parameters": PARAMETER, "auxiliaries": AUXILIARY, "stocks": STOCK,
           "flows": FLOW, "goals": GOAL, "blocks": BLOCK, "uses": USE}
REFUSED = {"agents": "who acts, and on which rung", "workspaces": "folders and repositories runs work in",
           "actions": "outward acts a session may ask for", "sources": "outside sources read over the network",
           "claims": "commands that check claims", "contexts": "what an AI session is given to read",
           "leases": "terms of work queues", "daemons": "processes kept running", "loops": "loops declared by hand",
           "operating": "operating states, which cap or stop every block's pool",
           "variables": "the old name of auxiliaries, kept for the owner's own files"}


def _match(spec, v, path: str) -> str | None:
    """The first refused path in ``v`` under ``spec``, or None when all of it is allowed."""
    if spec == A:
        return None
    if spec == S:
        return None if v is None or isinstance(v, str | int | float | bool) else path
    if spec == L:
        return _match(S, v, path) if not isinstance(v, list) else next(
            (p for i, x in enumerate(v) if (p := _match(S, x, f"{path}.{i}"))), None)
    if spec in (M, D):
        if isinstance(v, list) and spec == D:
            return next((p for i, x in enumerate(v) if (p := _match(D, x, f"{path}.{i}"))), None)
        if not isinstance(v, dict):
            return _match(S, v, path) if spec == D else path
        for k, x in v.items():
            if not isinstance(k, str | int | float) or k in CLAIMS:
                return f"{path}.{k}"
            if p := _match(D if spec == D else L, x, f"{path}.{k}"):
                return p
        return None
    if isinstance(spec, dict):
        if v is None:
            return None
        if not isinstance(v, dict):
            return path
        for k, x in v.items():
            got = spec.get(k)
            if got is None or got[0] == NO:
                return f"{path}.{k}"
            if p := _match(got[0], x, f"{path}.{k}"):
                return p
        return None
    if spec[0] == "each":
        if not isinstance(v, dict):
            return path
        return next((p for k, x in v.items() if (p := _match(spec[1], x, f"{path}.{k}"))), None)
    if spec[0] == "list":
        if not isinstance(v, list):
            return path
        return next((p for i, x in enumerate(v) if (p := _match(spec[1], x, f"{path}.{i}"))), None)
    if spec[0] == "or":
        got = [_match(s, v, path) for s in spec[1:]]
        return None if None in got else max(got, key=len)
    return path                                     # a shape not known here: refused


OUT_TO = {"block": "blocks", "goal": "goals", "flow": "flows", "auxiliary": "auxiliaries"}


def _out(entry: dict, path: str, made: set) -> str | None:
    """A block's ``out:`` that names a part the held chain did not make (the owner's program block, which it would
    command; the owner's setpoint), or that is not a reference: refused."""
    v = entry.get("out")
    for i, x in enumerate(v if isinstance(v, list) else [] if v is None else [v]):
        r = Ref.parse(x)
        if r is None or (OUT_TO.get(r.kind), r.name) not in made:
            return f"{path}.out" + (f".{i}" if isinstance(v, list) else "")
    return None


def refused(section: str, name: str, entry, made: set = frozenset()) -> str | None:
    """The first path in this part a held chain may not make (``blocks.x-fetch.run``), or None. ``made``: the
    (section, name) of every part the held chain makes, the only parts its blocks' ``out:`` may name."""
    path = f"{section}.{name}"
    table = ALLOWED.get(section)
    if table is None:
        return section
    if section == "blocks":
        t = entry.get("type") if isinstance(entry, dict) else None
        if not isinstance(t, str) or t not in BLOCK_TYPES:
            return f"{path}.type"
        table = {**table, **BLOCK_TYPES[t]}
        return _match(table, entry, path) or _out(entry, path, made)
    return _match(table, entry, path)
