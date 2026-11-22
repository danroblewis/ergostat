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

import re

from ..spec.ir import Ref
from .bounds import UNTRUSTED_EVERY
from .expand import COMMAND, ERGOSTAT, LIB, LIBRARY, MARK, F, Given, H, hours, strip
from .expand import A as MA
from .expand import B as MB

S, L, M, D, A, NO = "one value", "values", "map of values", "data", "anything", "refused"
RUN = "a run: the owner's own command, or ergostat's program with checked arguments (R1, R2)"
W = "written by the owner or a trusted template, never a library"

# R2: the only text not ergostat's own that may land in a built-in ``${lib} `` run slot, by its parameter's type.
# fullmatch, so no trailing newline or space is let through (``NAME.match`` and ``hours`` would let them).
NARROW = {"name": re.compile(r"[a-z][a-z0-9-]{0,63}"),
          "duration": re.compile(r"[0-9]{1,9}(\.[0-9]{1,6})?(ms|s|m|h|d|w)?"),
          "number": re.compile(r"-?[0-9]{1,15}(\.[0-9]{1,9})?"),
          "integer": re.compile(r"-?[0-9]{1,15}(\.[0-9]{1,9})?"),
          "bool": re.compile(r"true|false")}
# Every option of ``ergostat.library.run``'s programs, in exactly one of these (tests/test_library_provenance.py).
# Data: a name, a count or a time the program reads as data, never runs; a value not ergostat's own may follow one.
LIB_DATA_FLAGS = frozenset({
    "--name", "--kind", "--state", "--done", "--failed", "--stuck", "--flow", "--pinged-flow", "--gave-up-flow",
    "--every", "--limit", "--stand-in", "--answer-after", "--window", "--id-field", "--event", "--event-field",
    "--cursor-field", "--path", "--field", "--changes", "--title", "--cron", "--fail", "--say", "--rise", "--cut",
    "--no-coherence", "--no-extremes", "--mirror", "--position"})
# Never: what is run (a command, a renderer), read from outside (a URL, headers naming the environment), where files
# are written or removed, and the limits on processes, calls, money and time.
LIB_EXEC_FLAGS = frozenset({
    "--run", "--render", "--command", "--url", "--header", "--folder", "--keep", "--timeout", "--max", "--tries",
    "--most", "--daily", "--budget", "--rounds", "--model", "--review", "--when"})
# A rate or a count a library may set is bounded (lesson-4): seconds for times, else the number. ``--every``'s floor
# is the one every untrusted part has (bounds.py), so there is one rule for how often a library's text is read.
LIB_BOUNDS = {"--every": (UNTRUSTED_EVERY, 31_536_000), "--limit": (0, 100), "--stand-in": (0, 3600), "--window": (60, 604_800),
              "--answer-after": (0, 31_536_000), "--fail": (0, 1), "--rise": (0, 1), "--cut": (0, 1)}
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
    "run": (RUN, "runs only the owner's own command, or ergostat's program with checked arguments"),
    "query": (NO, "reads an outside source over the network"),
    "daemon": (NO, "starts and keeps a process"),
    "push": (NO, "takes readings pushed from outside"),
    "parse": (NO, "only means something on a command's or query's output"),
    "every": (W, "starts readings on a timer: only as the owner or a trusted template wrote it"),
    "cron": (W, "starts readings on a schedule: only as the owner or a trusted template wrote it"),
    "timeout": (W, "how long a command runs: only as the owner or a trusted template wrote it"),
    "builtin": (NO, "runs ergostat's own measure as a process of its own, on a timer"),
    "manual": (NO, "asks a person for readings"),
    "averages": (W, "the window a command's readings are averaged over: only as the owner or a trusted template wrote it"),
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
# A program block: refused by type, but for one whose keys are all here and whose run is allowed (R1).
PROGRAM = {"goal": (S, "the setpoint it holds"), "run": (RUN, "the owner's own command, or ergostat's program"),
           "every": (W, "its timer"), "cron": (W, "its schedule"), "timeout": (W, "how long it runs")}
REFUSED_TYPES = {"program": "runs a command, other than the owner's own or ergostat's program with checked arguments",
                 "ai":"starts an AI session", "person": "asks a person to act",
                 "external": "stands for something acting outside", "judge": "judges and applies changes to the model"}

ALLOWED = {"systems": SYSTEM, "items": ITEM, "parameters": PARAMETER, "auxiliaries": AUXILIARY, "stocks": STOCK,
           "flows": FLOW, "goals": GOAL, "blocks": BLOCK, "uses": USE}
REFUSED = {"agents": "who acts, and on which rung", "workspaces": "folders and repositories runs work in",
           "actions": "outward acts a session may ask for", "sources": "outside sources read over the network",
           "claims": "commands that check claims", "contexts": "what an AI session is given to read",
           "leases": "terms of work queues", "daemons": "processes kept running", "loops": "loops declared by hand",
           "variables": "the old name of auxiliaries, kept for the owner's own files"}


def narrow_ok(ty: str, raw) -> str:
    """"1" when a value's own text (before ``:seconds``, ``:hours``) fully matches its narrow type's pattern."""
    text = ("true" if raw else "false") if isinstance(raw, bool) else raw if isinstance(raw, str) else \
        str(raw) if isinstance(raw, int | float) else None
    return "1" if ty in NARROW and text is not None and NARROW[ty].fullmatch(text) else "0"


def _segments(s: str) -> list | None:
    """The text as (None, text written in the template) and (meta, text brought in), alternating, the first and the
    last the template's (perhaps empty); None when it holds a mark character outside a mark (fail closed)."""
    out, at = [], 0
    for m in MARK.finditer(s):
        meta = m.group(1).split(",")
        if len(meta) != 4:
            return None
        out += [(None, s[at:m.start()]), (meta, m.group(2))]
        at = m.end()
    out.append((None, s[at:]))
    return None if any(c in t for meta, t in out if meta is None for c in (MA, H, MB, F)) else out


def _value_ok(meta: list, before: str, text: str, after: str) -> bool:
    """R2: a value not ergostat's own, in a built-in ``${lib} `` slot: of a narrow type, its own text and the text
    that lands fully matching its pattern, directly after a flag of LIB_DATA_FLAGS, within that flag's bounds."""
    _, ty, how, ok = meta
    if ty not in NARROW or ok != "1" or after[:1] not in ("", " ") or before[-1:] not in ("", " "):
        return False
    if how == "arg":                              # --flag VALUE, or a bool's bare --flag
        flag, _, val = text.partition(" ")
        if ty == "bool":
            return flag in LIB_DATA_FLAGS and val == ""
    else:
        m = re.search(r"(?:^| )(--[a-z][a-z0-9-]*) $", before)
        flag, val = (m.group(1) if m else None), text
        if how not in ("", "seconds", "hours"):
            return False
    if flag not in LIB_DATA_FLAGS or not NARROW[ty].fullmatch(val):
        return False
    if flag in LIB_BOUNDS:
        lo, hi = LIB_BOUNDS[flag]
        n = hours(val) * 3600 if ty == "duration" and how in ("", "arg") else float(val) * (3600 if how == "hours" else 1)
        return lo <= n <= hi
    return True


def run_ok(v, tw: str) -> bool:
    """R1 and R2 (SPEC §2a): a ``run`` a held chain may make. ``tw``: who wrote the template it is in."""
    segs = _segments(v) if isinstance(v, str) else None
    if segs is None:
        return False
    marks = [(i, m, t) for i, (m, t) in enumerate(segs) if m is not None]
    if len(marks) == 1 and segs[0][1] == segs[2][1] == "" and marks[0][1][0] == COMMAND and marks[0][1][2] == "":
        return True                                   # (a) the owner's own command, whole
    if tw != ERGOSTAT:
        return False                                  # a library's or an owner folder's own words around it
    lib = segs[0][1].startswith(LIB + " ")
    for i, meta, text in marks:
        if text == "" or meta[0] == ERGOSTAT or (meta[0] == COMMAND and meta[2] in ("quote", "arg")):
            continue                                  # (b) ergostat's own, or the owner's command quoted
        if not (lib and _value_ok(meta, segs[i - 1][1], text, segs[i + 1][1])):
            return False                              # (c) else only a narrow value, as an argument
    return True


def writer_ok(v, tw: str) -> bool:
    """``every``, ``cron``, ``timeout``, ``averages``: written by the owner or a trusted template, never a library."""
    if isinstance(v, Given):
        return bool(v.meta) and v.meta[0] != LIBRARY
    if not isinstance(v, str):
        return tw != LIBRARY
    segs = _segments(v)
    return segs is not None and all(m[0] != LIBRARY if m else (t == "" or tw != LIBRARY) for m, t in segs)


def _match(spec, v, path: str, tw: str = LIBRARY) -> str | None:
    """The first refused path in ``v`` under ``spec``, or None when all of it is allowed. ``tw``: who wrote the
    template that made it (expand.author)."""
    if spec == A:
        return None
    if spec in (RUN, W):
        return None if (run_ok if spec == RUN else writer_ok)(v, tw) else path
    v = v.value if isinstance(v, Given) else v
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
            if p := _match(got[0], x, f"{path}.{k}", tw):
                return p
        return None
    if spec[0] == "each":
        if not isinstance(v, dict):
            return path
        return next((p for k, x in v.items() if (p := _match(spec[1], x, f"{path}.{k}", tw))), None)
    if spec[0] == "list":
        if not isinstance(v, list):
            return path
        return next((p for i, x in enumerate(v) if (p := _match(spec[1], x, f"{path}.{i}", tw))), None)
    if spec[0] == "or":
        got = [_match(s, v, path, tw) for s in spec[1:]]
        return None if None in got else max(got, key=len)
    return path                                     # a shape not known here: refused


OUT_TO = {"block": "blocks", "goal": "goals", "flow": "flows", "auxiliary": "auxiliaries"}


def _out(entry: dict, path: str, made: set) -> str | None:
    """A block's ``out:`` that names a part the held chain did not make (the owner's program block, which it would
    command; the owner's setpoint), or that is not a reference: refused."""
    v = entry.get("out")
    v = strip(v)
    for i, x in enumerate(v if isinstance(v, list) else [] if v is None else [v]):
        r = Ref.parse(x)
        if r is None or (OUT_TO.get(r.kind), r.name) not in made:
            return f"{path}.out" + (f".{i}" if isinstance(v, list) else "")
    return None


def refused(section: str, name: str, entry, made: set = frozenset(), tw: str = LIBRARY) -> str | None:
    """The first path in this part a held chain may not make (``blocks.x-fetch.run``), or None. ``made``: the
    (section, name) of every part the held chain makes, the only parts its blocks' ``out:`` may name. ``entry`` as
    expanded with its marks (expand.Made.marked), ``tw`` who wrote the template that made it (expand.author)."""
    path = f"{section}.{name}"
    table = ALLOWED.get(section)
    if table is None:
        return section
    if section == "blocks":
        t = strip(entry.get("type")) if isinstance(entry, dict) else None
        if not isinstance(t, str) or t not in (*BLOCK_TYPES, "program"):
            return f"{path}.type"
        table = {**table, **(PROGRAM if t == "program" else BLOCK_TYPES[t])}
        return _match(table, entry, path, tw) or _out(entry, path, made)
    return _match(table, entry, path, tw)
