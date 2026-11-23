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

import json
import re

from ..spec.ir import Ref
from .bounds import UNTRUSTED_EVERY
from .expand import COMMAND, ERGOSTAT, FOLDER, LIB, LIBRARY, MARK, OWNER, REF, VAR, F, Given, H, hours, strip
from .expand import A as MA
from .expand import B as MB

S, L, M, D, A, NO = "one value", "values", "map of values", "data", "anything", "refused"
RUN = "a run: the owner's own command, or ergostat's program with checked arguments (R1, R2)"
SBX = "a sensor's run: on the owner's shell only as R1, R2 allow (owner_runs), else in ergostat.sandbox (runs.py)"
W = "written by the owner or a trusted template, never a library"
T ="text read or shown to an agent: no piece of it, at any depth, written by a library (R3)"


class Text(str):
    """A path refused by R3 (``untrusted-text``) rather than by the allowlist (``library-untrusted``)."""

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
    "--no-coherence", "--no-extremes", "--mirror", "--position", "--batch-kind", "--states"})
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
    "run": (SBX, "runs on the owner's shell only as R1, R2 allow; any other run, only in ergostat.sandbox"),
    "query": (T, "reads an outside source: only as the owner or a trusted template wrote every piece of it"),
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
        "final": (L, "its states no event moves it out of"), "finished": (L, "its states that count as finished"),
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
# A machine block (program, ai, person): made only when its keys are all allowed below. Every other key a machine
# block may have is refused by name: who acts and how much, what it runs, reads, is given or may do.
MACHINE_NO = {k: (NO, why) for why, ks in (
    ("who acts, on which rung, and in which mode", ("agent", "mode", "model")),
    ("how many runs, items, attempts and how much each may take", ("max", "min", "takes", "pool", "lease", "on")),
    ("a controller's law, which only the owner tunes", ("gain", "integral-time", "deadband", "resolution", "limits")),
    ("what is run, kept running or parsed from its output", ("run", "daemon", "parse", "timeout", "until")),
    ("what it may read, write and reach", ("workdir", "workspace", "read", "tools", "actions", "read-only", "network")),
    ("what it is given or judged by", ("context", "review")),
    ("the text of another type of block", ("prompt", "ask"))) for k in ks}
GOAL_UNTIL = {"goal": (S, "the setpoint it holds"), "until": (S, "a setpoint it stops at"),
              "every": (W, "its timer"), "cron": (W, "its schedule")}
MACHINE_TYPES = {
    "program": {**MACHINE_NO, **GOAL_UNTIL, "until": MACHINE_NO["until"], "timeout": (W, "how long it runs"),
                "run": (RUN, "the owner's own command, or ergostat's program")},
    "ai": {**MACHINE_NO, **GOAL_UNTIL, "prompt": (T, "what the AI session is asked (R3)")},
    "person": {**MACHINE_NO, **GOAL_UNTIL, "ask": (T, "what the person is asked (R3)")}}
REFUSED_TYPES = {"external": "stands for something acting outside", "judge": "judges and applies changes to the model"}
SOURCE = {k: (T, why) for k, why in (("type", "the kind of source"), ("url", "where it is read from"),
                                     ("token-file", "the file its token is read from"), ("tls", "its certificates"))}

ALLOWED = {"systems": SYSTEM, "items": ITEM, "parameters": PARAMETER, "auxiliaries": AUXILIARY, "stocks": STOCK,
           "flows": FLOW, "goals": GOAL, "blocks": BLOCK, "uses": USE, "sources": SOURCE}
REFUSED = {"agents": "who acts, and on which rung", "workspaces": "folders and repositories runs work in",
           "compute": "the machines runs execute on",
           "actions": "outward acts a session may ask for",
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


def owner_runs(marked: dict, tw: str) -> list[str]:
    """``section.part.sensor`` of each sensor whose ``run:`` R1 or R2 lets run on the owner's shell (an allowlist: a
    shape not read here, or a check that raises, leaves it out, and it runs sandboxed)."""
    out = []
    for section, entries in marked.items():
        for name, x in entries.items():
            got = (x.get("sensors") if x.get("sensor") is None else {"main": x["sensor"]}) if isinstance(x, dict) else None
            for n, s in (got.items() if isinstance(got, dict) else ()):
                try:
                    if isinstance(s, dict) and run_ok(s.get("run"), tw):
                        out.append(f"{section}.{strip(name)}.{strip(n)}")
                except Exception:   # noqa: S112 (lesson-3: a verdict that raises proves nothing)
                    continue
    return out


NAMED = "named"  # a template's own text that may hold its instance's name (``named``): only owner pieces are known


def fine(tt: str) -> tuple:
    """The writers whose pieces R3 lets through, by who wrote the template's own text: an allowlist."""
    return (OWNER, COMMAND) if tt == NAMED else (OWNER, COMMAND, FOLDER, ERGOSTAT)


def text_ok(v, tt: str) -> bool:
    """R3: ``ask``, ``prompt``, ``query``, a source's values: every key and value in it, at any depth, by a writer
    ``fine`` lets through. ``tt``: who wrote the template's own text: LIBRARY when that text may hold a value unmarked
    (``blind``), NAMED when it may hold the instance's name (``named``), which a held chain's library chose."""
    if isinstance(v, dict):
        return all(text_ok(k, tt) and text_ok(x, tt) for k, x in v.items())
    if isinstance(v, list):
        return all(text_ok(x, tt) for x in v)
    if isinstance(v, Given):
        return bool(v.meta) and v.meta[0] in fine(tt)
    segs = _segments(v) if isinstance(v, str) else [(None, v)]
    return segs is not None and all(m[0] in fine(tt) if m else (t == "" or tt in fine(LIBRARY)) for m, t in segs)


def _keyed(x) -> bool:
    return isinstance(x, list) and any(map(_keyed, x)) or isinstance(x, dict) and any(
        isinstance(k, str) and "${" in k or _keyed(v) for k, v in x.items())


def _texts(x) -> list:
    """The values of every ``ask``, ``prompt``, ``query`` and ``sources`` key in it, at any depth."""
    if isinstance(x, list):
        return [y for v in x for y in _texts(v)]
    return [y for k, v in x.items() for y in ([v] if k in TEXT_KEYS else _texts(v))] if isinstance(x, dict) else []


TEXT_KEYS = ("ask", "prompt", "query", "sources")


def blind(t) -> bool:
    """A template whose own text puts in a field (``${p.x}``, ``${it.name}``), an ``each:`` element or a key made
    from a value, or whose R3 text names a part (``block.x``, which rename() makes ``block.<instance>-x``): expand
    leaves those unmarked, so whose words they are can't be told and R3 reads them as a library's."""
    raw = json.dumps(t.body, default=str)
    return '"each":' in raw or any("." in m.group(1) for m in VAR.finditer(raw)) or _keyed(t.body) or \
        any(REF.search(json.dumps(x, default=str)) for x in _texts(t.body))


def named(t) -> bool:
    """A template whose text or defaults use ``${name}``, ``${here}`` or ``${folder}``. In a held chain the instance's
    name holds the library's ``uses:`` keys, and expand puts it in unmarked: in the template's own text, and in its
    defaults and nested ``with:`` values, marked as the template's (``expand.wrote``). So R3 lets through only the
    owner's pieces of its text (NAMED), and the values it gives a nested use count as a library's (uses.plan)."""
    raw = json.dumps([t.body, *(p.default for p in t.params.values())], default=str)
    return any(m.group(1) in ("name", "here", "folder") for m in VAR.finditer(raw))


def _match(spec, v, path: str, tw: str = LIBRARY, tt: str = LIBRARY) -> str | None:
    """The first refused path in ``v`` under ``spec``, or None when all of it is allowed. ``tw``: who wrote the
    template that made it (expand.author); ``tt``: who wrote its own text, for R3."""
    if spec == A:
        return None
    if spec in (RUN, W):
        return None if (run_ok if spec == RUN else writer_ok)(v, tw) else path
    if spec == T:
        return None if text_ok(v, tt) else Text(path)
    if spec == SBX:                     # text, holding no mark character outside a mark (fail closed)
        return None if isinstance(v, str) and _segments(v) is not None else path
    if isinstance(v, Given):         # a value given whole: all of it is its writer's (none known: the library's)
        tt = v.meta[0] if v.meta and v.meta[0] in fine(tt) else LIBRARY
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
            if p := _match(got[0], x, f"{path}.{k}", tw, tt):
                return p
        return None
    if spec[0] == "each":
        if not isinstance(v, dict):
            return path
        return next((p for k, x in v.items() if (p := _match(spec[1], x, f"{path}.{k}", tw, tt))), None)
    if spec[0] == "list":
        if not isinstance(v, list):
            return path
        return next((p for i, x in enumerate(v) if (p := _match(spec[1], x, f"{path}.{i}", tw, tt))), None)
    if spec[0] == "or":
        got = [_match(s, v, path, tw, tt) for s in spec[1:]]
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


def refused(section: str, name: str, entry, made: set = frozenset(), tw: str = LIBRARY, tt: str = LIBRARY) -> str | None:
    """The first path in this part a held chain may not make (``blocks.x-fetch.run``), or None; a ``Text`` when R3
    refused it. ``made``: the (section, name) of every part the held chain makes, the only parts its blocks' ``out:``
    may name. ``entry`` as expanded with its marks (expand.Made.marked), ``tw`` who wrote the template that made it
    (expand.author), ``tt`` who wrote its own text (LIBRARY when ``blind``)."""
    path = f"{section}.{name}"
    table = ALLOWED.get(section)
    if table is None:
        return section
    if section == "blocks":
        t = strip(entry.get("type")) if isinstance(entry, dict) else None
        if not isinstance(t, str) or t not in (*BLOCK_TYPES, *MACHINE_TYPES):
            return f"{path}.type"
        table = {**table, **(BLOCK_TYPES.get(t) or MACHINE_TYPES[t])}
        return _match(table, entry, path, tw, tt) or _out(entry, path, made)
    return _match(table, entry, path, tw, tt)
