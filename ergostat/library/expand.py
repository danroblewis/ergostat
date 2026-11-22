"""One ``uses:`` entry, expanded into the ordinary sections it stands for (SPEC §2a).

    uses:
      pings:                      # the instance: its parts are named pings-..., and it is a system, pings
        use: respond-to           # the template
        within: awareness         # optional: the system it is part of (else its file's defaults: system:)
        with:                     # the template's parameters
          within: 4h

In the template, ``${param}`` is a parameter's value (``${within:hours}`` a duration in hours, ``${cmd:quote}``
quoted for the shell), ``${name}`` the instance's name, ``${python}`` the Python ergostat runs on, ``${lib}`` the
programs the built-in templates run, and ``${here}`` the template's own folder (quoted for the shell; ``${folder}``
as it is, for a file's path). A whole value that is one
``${param}`` takes the parameter's value as it is (a number, a list); a key whose value comes out empty is left
out. An entry (or any map) with ``if: ${param}`` is kept only when it is set, and a value ``{if: C, value: V,
else: E}`` is V when C holds, else E (or left out); one with ``each: PARAM`` is made once
for every element of a list parameter, the element's fields as ``${as.field}`` (``as:`` names it, ``it`` by default)
with ``${as.index}``, ``${as.next}`` and ``${as.prev}`` (the next and previous element's name, or ``last:`` and
``first:`` at the ends). ``{each: PARAM, key: K, value: V}`` makes a map, and a list element ``{each: PARAM, value:
V}`` that many elements.

Every name the template defines is the instance's: ``waiting`` becomes ``pings-waiting``, and every reference to it
(``stock.waiting``, ``from: waiting``, a parameter in an equation) follows; a name that is wholly one ``${param}``
(an item kind, ``${kind}``) is taken as given; a template written ``once: true`` (used at most once a model) keeps
every name as written. What a parameter brings in (a reference to a part outside, a
command) is never renamed. Every part made is in the instance's system, and everything it says points at the
``use:`` line."""

from __future__ import annotations

import copy
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass

from ..spec.ir import NAME, SETPOINT
from ..spec.load import Problem, Where
from .templates import Param, Template, trusted

A, H, B = "\x00", "\x02", "\x01"            # A who,type,how,ok H text B: what a parameter brought in, never renamed
F = "\x03"                                  # before a run holding a field: its writer can't be told
MARK = re.compile(f"{A}([^{A}{H}{B}]*){H}([^{A}{H}{B}]*){B}")
OWNER, COMMAND, ERGOSTAT, FOLDER, LIBRARY = "o", "c", "e", "f", "l"    # who wrote a value (SPEC §2a, *Writers*)
VAR = re.compile(r"\$\{([a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)?)(?::([a-z]+))?(?:\|([^}]*))?\}")
WHOLE = re.compile(r"^\$\{([a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)?)(?::([a-z]+))?(?:\|([^}]*))?\}$")
REF = re.compile(r"(?<![\w.-])(stock|flow|goal|block|auxiliary|variable|parameter|system)\.([a-z][a-z0-9-]*)")
WORD = re.compile(r"(?<![\w.-])([a-z][a-z0-9-]*)(?![\w-]|\.[a-z])")
SECTION_OF = {"stock": "stocks", "flow": "flows", "goal": "goals", "block": "blocks", "auxiliary": "auxiliaries",
              "variable": "auxiliaries", "parameter": "parameters", "system": "systems"}
BARE = {("flows", "from"): "stocks", ("flows", "to"): "stocks", ("goals", "stock"): "stocks", ("goals", "flow"): "flows",
        ("goals", "auxiliary"): "auxiliaries", ("goals", "variable"): "auxiliaries", ("blocks", "goal"): "goals",
        ("blocks", "agent"): "agents", ("systems", "within"): "systems", ("blocks", "workspace"): "workspaces",
        ("blocks", "actions"): "actions"}
IN_SYSTEM = ("items", "parameters", "auxiliaries", "stocks", "flows", "goals", "blocks")
FALSE = {"", "false", "no", "0", "off", "none"}
USE_KEYS = {"use", "with", "within", "description"}
BUILTIN_NAMES = ("name", "python", "ergostat", "lib", "here", "folder")
MAX_DEPTH = 6


class Via(Where):
    """Where a part made by a template was asked for: the ``use:`` line, and which template made it."""

    def __init__(self, file, line: int, template: str, instance: str):
        super().__init__(file, line)
        self.template, self.instance = template, instance

    def __str__(self) -> str:
        return f"{self.file.name}:{self.line} (use {self.instance}: {self.template})"


class ExpandError(Exception):
    def __init__(self, message: str, key: str | None = None):
        super().__init__(message)
        self.key = key


@dataclass
class Given:
    """A parameter's value, whole (a number, a list): a leaf, never renamed. ``meta``: who wrote it, as in a mark."""
    value: object
    meta: tuple | None = None


PY = shlex.quote(sys.executable)
LIB = f"{PY} -m ergostat.library.run"


def builtins(name: str, t: Template) -> dict:
    return {"name": (name, None), "python": (PY, None), "ergostat": (f"{PY} -m ergostat", None),
            "lib": (LIB, None), "here": (shlex.quote(str(t.path.parent)), None), "folder": (str(t.path.parent), None)}


def author(t: Template) -> str:
    """Who wrote a template's own words: ergostat, the owner's folder, or a library."""
    return ERGOSTAT if t.builtin else FOLDER if trusted(t) else LIBRARY


def mark(meta: tuple, how: str | None, text: str) -> str:
    """``meta``: (who wrote it, its parameter's type, "1" when its text is its type's narrow form)."""
    return f"{A}{meta[0]},{meta[1]},{how or ''},{meta[2]}{H}{text}{B}"


def texts(x) -> list[str]:
    """Every text in it, keys too, and the mark of a whole value brought in."""
    if isinstance(x, Given):
        return [mark(x.meta, None, "")] if x.meta else []
    if isinstance(x, dict):
        return [y for k, v in x.items() for y in (*texts(k), *texts(v))]
    if isinstance(x, list):
        return [y for v in x for y in texts(v)]
    return [x] if isinstance(x, str) else []


def forged(x) -> bool:
    """Text holding a mark's characters: only expand makes marks, so a template or value holding one is refused."""
    return any(c in s for s in texts(x) for c in (A, H, B, F))


def wrote(tw: str, raw, walked, writers: dict) -> str:
    """Who wrote a value a template made of its own words and its parameters: a library, when the template is one's,
    any parameter in it is a library's, or it holds a field (``${it.x}``, ``${p.first}``: whose words can't be told);
    else the template's writer (SPEC §2a)."""
    refs = [m.group(1) for s in texts(raw) for m in VAR.finditer(s)]
    marks = [m.group(1) for s in texts(walked) for m in MARK.finditer(s)]
    bad = any("." in r or writers.get(r, (LIBRARY,))[0] == LIBRARY for r in refs if r in writers or r not in BUILTIN_NAMES)
    return LIBRARY if tw == LIBRARY or bad or any(m.startswith(LIBRARY) for m in marks) else tw


def strip(x):
    """The value with the marks around parameters' text taken out, and whole values unwrapped."""
    if isinstance(x, Given):
        return strip(x.value)
    if isinstance(x, str):
        return MARK.sub(lambda m: m.group(2), x).replace(A, "").replace(H, "").replace(B, "").replace(F, "")
    if isinstance(x, list):
        return [strip(v) for v in x]
    if isinstance(x, dict):
        return {strip(k): strip(v) for k, v in x.items()}
    return x


def truthy(x) -> bool:
    x = strip(x)
    if isinstance(x, str):
        for op in (" == ", " != "):
            if op in x:
                a, b = (y.strip() for y in x.split(op, 1))
                return (a == b) == (op == " == ")
    if x is None or x is False:
        return False
    if isinstance(x, str):
        return x.strip().lower() not in FALSE
    if isinstance(x, list | dict):
        return bool(x)
    return True


def hours(v) -> float:
    if isinstance(v, int | float) and not isinstance(v, bool):
        return float(v) / 3600.0
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h|d|w)?\s*", str(v))
    if not m:
        raise ExpandError(f"{v!r} is not a duration (like 0, 30s, 5m, 2h, 1d)")
    return float(m.group(1)) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[m.group(2) or "s"] / 3600.0


def _num(x: float):
    return int(x) if float(x).is_integer() else round(x, 9)


def apply(value, how: str | None, name: str = ""):
    if how == "arg":                      # --name VALUE, or nothing; a list, --name for each (a plural's s dropped)
        flag = "--" + name.rsplit(".", 1)[-1]
        if value is None or value is False or value == "" or value == []:
            return ""
        if value is True:
            return flag
        if isinstance(value, list):
            one = flag[:-1] if flag.endswith("s") else flag
            return " ".join(f"{one} {shlex.quote(str(v))}" for v in value)
        return f"{flag} {shlex.quote(str(value))}"
    if how == "quote" and value is None:
        return "''"
    if how is None or value is None:
        return value
    if how == "hours":
        return _num(hours(value))
    if how == "seconds":
        return _num(hours(value) * 3600)
    if how == "quote":
        return shlex.quote(value if isinstance(value, str) else json.dumps(value))
    if how == "json":
        return json.dumps(value)
    raise ExpandError(f"${{...:{how}}}: known: hours, seconds, quote, json, arg")


class Scope:
    """The names ``${...}`` can say: each a value, and whether it came from a parameter (marked, never renamed)."""

    def __init__(self, names: dict):
        self.names = names

    def more(self, extra: dict) -> Scope:
        return Scope({**self.names, **extra})

    def look(self, name: str):
        head, _, field = name.partition(".")
        if head not in self.names:
            raise ExpandError(f"${{{name}}}: no parameter {head!r}")
        v, marked = self.names[head]
        if field and isinstance(strip(v), list) and field in ("first", "last", "count"):
            els = [x.get("name") if isinstance(x, dict) else x for x in strip(v)]
            return (len(els) if field == "count" else (els[0] if field == "first" else els[-1]) if els else None), None
        if field:
            if not isinstance(v, dict):
                raise ExpandError(f"${{{name}}}: {head} has no fields")
            return v.get(field), None
        return v, marked

    def sub(self, s: str, marks: bool = True, key=None):
        if key == "run" and marks and any("." in m.group(1) for m in VAR.finditer(s)):
            got = self.sub(s, marks)       # a field in a run: whose words it holds can't be told (SPEC §2a)
            return F + got if isinstance(got, str) else got
        m = WHOLE.match(s)
        if m:
            v, meta = self.look(m.group(1))
            if v is None and m.group(3) is not None:
                return m.group(3)
            v = apply(strip(v), m.group(2), m.group(1))
            if v is None:
                return None
            if meta and marks:
                return mark(meta, m.group(2), v) if isinstance(v, str) else Given(v, meta)
            return v

        def one(m):
            v, meta = self.look(m.group(1))
            if v is None and m.group(3) is not None:
                return m.group(3)
            v = apply(strip(v), m.group(2), m.group(1))
            text = "" if v is None else (v if isinstance(v, str) else json.dumps(v) if isinstance(v, list | dict) else
                                         str(_num(v)) if isinstance(v, float) else str(v).lower() if isinstance(v, bool) else str(v))
            return mark(meta, m.group(2), text) if meta and marks else text
        return VAR.sub(one, s)


def elements(scope: Scope, param: str) -> list[dict]:
    v, _ = scope.look(param)
    v = strip(v)
    if v is None:
        return []
    if not isinstance(v, list):
        raise ExpandError(f"each: {param} is not a list")
    out = []
    for x in v:
        out.append(dict(x) if isinstance(x, dict) else {"name": x})
    return out


def each_scopes(scope: Scope, spec: dict) -> list[Scope]:
    els = elements(scope, str(spec["each"]))
    as_ = str(spec.get("as") or "it")
    names = [str(e.get("name")) if e.get("name") is not None else None for e in els]
    out = []
    for i, e in enumerate(els):
        var = {**e, "index": i + 1, "first": i == 0, "last": i == len(els) - 1,
               "next": names[i + 1] if i + 1 < len(els) else spec.get("last", "done"),
               "prev": names[i - 1] if i > 0 else spec.get("first")}
        out.append(scope.more({as_: (var, None)}))
    return out


DROP = object()


def walk(x, scope: Scope, key=None):
    if isinstance(x, Given):
        return x
    if isinstance(x, str):
        return scope.sub(x, key=key)
    if isinstance(x, list):
        out = []
        for el in x:
            if isinstance(el, dict) and "each" in el and "value" in el and "key" not in el:
                for sc in each_scopes(scope, el):
                    v = walk(el["value"], sc)
                    if v is not None and v is not DROP:
                        out.append(v)
                continue
            v = walk(el, scope, key)
            if v is not None and v is not DROP:
                out.append(v)
        return out
    if isinstance(x, dict):
        if "value" in x and ("if" in x) != ("unless" in x) and set(x) <= {"if", "unless", "value", "else"}:
            word = "if" if "if" in x else "unless"             # a value chosen: {if: C, value: V, else: E}
            hold = truthy(walk(x[word], scope)) == (word == "if")
            return walk(x["value"], scope, key) if hold else walk(x["else"], scope, key) if "else" in x else DROP
        if "each" in x and "key" in x and "value" in x:
            got = {}
            for sc in each_scopes(scope, x):
                k = strip(sc.sub(str(x["key"]), marks=False))
                v = walk(x["value"], sc)
                if v is not None and v is not DROP:
                    got[k] = v
            return got
        out = {}
        for k, v in x.items():
            if k == "each" and isinstance(v, dict | list):        # entries made, beside the ones written
                for g in v if isinstance(v, list) else [v]:
                    got = walk(g, scope) if isinstance(g, dict) and {"each", "key", "value"} <= set(g) else None
                    if isinstance(got, dict):
                        out.update(got)
                continue
            k2 = strip(scope.sub(k, marks=False)) if isinstance(k, str) else k
            v2 = walk(v, scope, k2)
            if v2 is None or v2 is DROP:
                continue
            out[k2] = v2
        for word, keep_if in (("if", True), ("unless", False)):
            if word in x:
                cond = out.pop(word, None)
                if truthy(cond) != keep_if:
                    return DROP
        return out
    return x


def coerce(p: Param, v):
    """A parameter's value, checked against its type; ExpandError says what is wrong."""
    if v is None:
        return None
    raw = strip(v)
    t = p.type
    if p.choices and raw not in p.choices:
        raise ExpandError(f"{p.name}: one of {', '.join(map(str, p.choices))} (not {raw!r})")
    if t in ("number", "integer"):
        try:
            n = float(raw)
        except (TypeError, ValueError):
            raise ExpandError(f"{p.name}: a number (not {raw!r})") from None
        if t == "integer" and not n.is_integer():
            raise ExpandError(f"{p.name}: a whole number (not {raw!r})")
        if p.min is not None and not n >= p.min:                    # (NaN is outside either bound)
            raise ExpandError(f"{p.name}: at least {p.min} (min: {p.min}; not {raw!r})")
        if p.max is not None and not n <= p.max:
            raise ExpandError(f"{p.name}: at most {p.max} (max: {p.max}; not {raw!r})")
        return int(n) if t == "integer" else _num(n)
    if t == "duration":
        h = hours(raw)
        if p.min is not None and not h >= p.min:
            raise ExpandError(f"{p.name}: at least {p.min * 3600:g}s (not {raw!r})")
        if p.max is not None and not h <= p.max:
            raise ExpandError(f"{p.name}: at most {p.max * 3600:g}s (not {raw!r})")
        return raw
    if t == "setpoint":
        if not SETPOINT.match(str(raw)):
            raise ExpandError(f'{p.name}: a setpoint, like "<= 20" (quoted)')
        return str(raw)
    if t == "bool":
        return truthy(raw)
    if t == "name":
        if not isinstance(raw, str) or not NAME.match(raw):
            raise ExpandError(f"{p.name}: a name: lowercase letters, digits and -, starting with a letter (not {raw!r})")
        return raw
    if t == "glob":
        if not isinstance(raw, str) or "/" not in raw:
            raise ExpandError(f"{p.name}: an id glob with a / in it, like ticket/* (not {raw!r})")
        return raw
    if t == "cron":
        from ..cron import Cron, CronError
        try:
            Cron(str(raw))
        except CronError as e:
            raise ExpandError(f"{p.name}: {e}") from None
        return str(raw)
    if t == "rung":
        if raw not in ("program", "ai", "person", "external"):
            raise ExpandError(f"{p.name}: program, ai, person or external (not {raw!r})")
        return raw
    if t == "strings":
        raw = [raw] if isinstance(raw, str) else raw
        if not isinstance(raw, list) or not all(isinstance(x, str | int | float) for x in raw):
            raise ExpandError(f"{p.name}: a list of words")
        return [str(x) for x in raw]
    if t in ("list", "names"):
        if not isinstance(raw, list):
            raise ExpandError(f"{p.name}: a list")
        if t == "names" and not all(isinstance(x, str) and NAME.match(x) for x in raw):
            raise ExpandError(f"{p.name}: a list of names")
        if t == "list":
            for x in raw:
                n = x.get("name") if isinstance(x, dict) else x
                if not isinstance(n, str) or not NAME.match(n):
                    raise ExpandError(f"{p.name}: each element a name, or a map with name: (lowercase letters, digits "
                                      f"and -), not {n!r}")
        return raw
    if t == "any":                        # as given, checked where it is used
        return raw
    if t == "map":
        if not isinstance(raw, dict):
            raise ExpandError(f"{p.name}: a map")
        return raw
    if isinstance(raw, dict | list):
        raise ExpandError(f"{p.name}: a single value, not a {'map' if isinstance(raw, dict) else 'list'}")
    if isinstance(raw, bool):
        return str(raw).lower()
    return raw if isinstance(raw, str) else str(_num(raw)) if isinstance(raw, float) else str(raw)


@dataclass
class Made:
    """What one instance expanded to."""
    sections: dict          # section → {name: plain entry}
    system: dict            # its own system's entry
    standins: list          # the parameters left to their stand-ins
    values: dict            # every parameter's value
    marked: dict = None     # section → {name: entry with its marks}, for the gate (trust.py) to judge
    writers: dict = None    # each nested use → {its with: key: who wrote the value}
    shorts: dict = None     # section → {name made: its name in the template}, for each name the instance's (belongs.py)


def params(t: Template, given: dict, scope: Scope, writers: dict | None = None):
    """Every parameter's value: given, else its default (else nothing). Also the stand-ins it runs on (each
    parameter's ``stand-in:`` says what stands in when it, and every parameter saying the same, is left out), what
    is wrong (each with the key of ``with:`` it is about), and each value's mark: who wrote it, its type, and whether
    its text is its type's narrow form. ``writers``: who wrote each given value; None for the owner's own ``with:``
    (a value whose writer is not known counts as a library's)."""
    from .trust import narrow_ok
    values: dict = {}
    metas: dict = {}
    tw = author(t)
    wrong: list[tuple[str, str | None]] = []
    for k in given:
        if k not in t.params:
            near = [n for n in t.params if n[:3] == str(k)[:3]]
            wrong.append((f"with.{k}: {t.name} has no parameter {k!r}" + (f" (did you mean {near[0]}?)" if near else
                          f" (it takes: {', '.join(t.params) or 'none'})"), k))
    forced = bool(os.environ.get("ERGOSTAT_STANDINS"))           # a trial on stand-ins: what they stand in for is left out
    for n, p in t.params.items():
        sc = scope.more({k: (v, None) for k, v in values.items()})
        try:
            if n in given and not (forced and p.standin):
                v = given[n]
                w = OWNER if writers is None else writers.get(n, LIBRARY)
                if w in (OWNER, COMMAND):          # an owner's command only while it goes on, whole, as a command
                    w = COMMAND if p.type == "command" and (writers is None or w == COMMAND) else OWNER
            elif p.has_default:
                v = walk(p.default, sc)
                w = wrote(tw, p.default, v, metas)
            elif p.required:
                wrong.append((f"with.{n}: {t.name} needs it: {p.description or p.type}", None))
                continue
            else:
                v, w = None, tw
            raw = strip(v) if v is not DROP else None
            values[n] = coerce(p, raw)
            metas[n] = (w, p.type, narrow_ok(p.type, raw))
        except ExpandError as e:
            wrong.append((f"with.{str(e) if str(e).startswith(n + ':') else n + ': ' + str(e)}", n if n in given else None))
    groups: dict[str, list[str]] = {}
    for n, p in t.params.items():
        if p.standin:
            groups.setdefault(str(p.standin), []).append(n)
    standins = [f"{' or '.join(ns)}: {what}" for what, ns in groups.items()
                if not any(x in given and not (forced and t.params[x].standin) for x in ns)]
    return values, standins, wrong, metas


def local_names(t: Template, body: dict, inst: str, scope: Scope) -> tuple[dict, dict]:
    """Each section's entries with their names made, each entry's ``each:`` unrolled: (section → [(name, entry,
    scope)]), and the renames (section → {name in the template: name made})."""
    made: dict = {}
    renames: dict = {}
    for section, entries in body.items():
        if section == "uses" or not isinstance(entries, dict):
            continue
        rows = []
        for key, entry in entries.items():
            scopes = [scope]
            if isinstance(entry, dict) and "each" in entry and "value" not in entry:
                scopes = each_scopes(scope, entry)
                entry = {k: v for k, v in entry.items() if k not in ("each", "as", "last", "first")}
            for sc in scopes:
                m = WHOLE.match(str(key))
                if m and not m.group(2) and m.group(1) in t.params:
                    name = strip(sc.look(m.group(1))[0])
                    if name is None:
                        continue
                    name = str(name)
                else:
                    bare = str(strip(sc.sub(str(key), marks=False)))
                    name = bare if t.once else f"{inst}-{bare}"
                    renames.setdefault(section, {})[bare] = name
                rows.append((name, entry, sc))
        made[section] = rows
    return made, renames


def rename(x, section: str, key: str | None, renames: dict):
    """References to the template's own names, made the instance's; what a parameter brought in is left alone."""
    if isinstance(x, Given):
        return x
    if isinstance(x, list):
        return [rename(v, section, key, renames) for v in x]
    if isinstance(x, dict):
        return {k: rename(v, section, k, renames) for k, v in x.items()}
    if not isinstance(x, str):
        return x
    target = BARE.get((section, key)) or ("systems" if key == "system" else "items" if key == "items" else None)
    if target and A not in x and x in renames.get(target, {}):
        return renames[target][x]

    def outside(text: str) -> str:
        text = REF.sub(lambda m: f"{m.group(1)}.{renames.get(SECTION_OF[m.group(1)], {}).get(m.group(2), m.group(2))}", text)
        if key == "equation":
            text = WORD.sub(lambda m: renames.get("parameters", {}).get(m.group(1), m.group(1)), text)
        return text
    parts = re.split(f"({A}[^{B}]*{B})", x)
    return "".join(p if p.startswith(A) else outside(p) for p in parts)


def expand(t: Template, inst: str, given: dict, writers: dict | None = None) -> Made:
    """The instance's sections. ExpandError (with the key of ``with:`` it is about) when it cannot be made.
    ``writers``: who wrote each value given (None: the owner, in the owner's own ``with:``)."""
    if forged(t.body) or forged([p.default for p in t.params.values()]) or forged(given):
        err = ExpandError(f"template {t.name}, or a value given to it, holds a control character only ergostat's own "
                          f"marks use")
        err.forged = True
        raise err
    scope = Scope(builtins(inst, t))
    values, standins, wrong, metas = params(t, given, scope, writers)
    if wrong:
        err = ExpandError("; ".join(w for w, _ in wrong), next((k for _, k in wrong if k), None))
        err.all = wrong
        raise err
    scope = scope.more({k: (v, metas[k]) for k, v in values.items()})
    body = copy.deepcopy(t.body)
    rows, renames = local_names(t, body, inst, scope)
    sections: dict = {}
    marked: dict = {}
    for section, entries in rows.items():
        out = sections.setdefault(section, {})
        for name, entry, sc in entries:
            got = walk(entry, sc)
            if got is DROP:
                continue
            got = rename(got if got is not None else {}, section, None, renames)
            marked.setdefault(section, {})[name] = got
            got = strip(got)
            if isinstance(got, dict) and section in IN_SYSTEM and not got.get("system"):
                got["system"] = inst
            if section == "systems" and isinstance(got, dict) and not got.get("within"):
                got["within"] = inst
            out[name] = got
    subs: dict = {}
    shorts = {s: {name: bare for bare, name in r.items()} for s, r in renames.items() if not t.once}
    for sub, entry in (body.get("uses") or {}).items():          # templates made of templates
        got = walk(entry, scope)
        if got is DROP:
            continue
        bare = str(strip(scope.sub(str(sub), marks=False)))
        name = f"{inst}-{bare}"
        shorts.setdefault("uses", {})[name] = bare
        raw, given_on = (entry.get("with") if isinstance(entry, dict) else None), got.get("with")
        subs[name] = {k: nested(k, v, raw, metas, author(t)) for k, v in given_on.items()} if isinstance(given_on, dict) else {}
        got = strip(rename(got, "uses", None, renames))
        got.setdefault("within", inst)
        sections.setdefault("uses", {})[name] = got
    return Made(sections, {"description": t.description.split("\n")[0]}, standins, values, marked, subs, shorts)


def nested(k, walked, raw, metas: dict, tw: str) -> str:
    """Who wrote a value of a nested ``with:``: wholly one ``${p}``, p's writer; else as ``wrote`` says (SPEC §2a).
    One whose text can't be found in the template counts as a library's."""
    rv = raw.get(k) if isinstance(raw, dict) else None
    m = WHOLE.match(rv) if isinstance(rv, str) else None
    if m and not m.group(2) and m.group(3) is None and m.group(1) in metas:
        return metas[m.group(1)][0]
    return LIBRARY if rv is None else wrote(tw, rv, walked, metas)


def problem(msg: str, where: Where | None, code: str, inst: str) -> Problem:
    return Problem("error", msg, where, code, f"system.{inst}")
