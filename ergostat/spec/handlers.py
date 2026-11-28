"""A projection's handlers (SPEC §5a): what each event does to the item it belongs to.

Events are facts; a projection's handlers say, per event type and per field, how that event changes its item, as an
event-sourced projection does. A handler's value is one small expression (a YAML number, boolean or null is a constant
on its own): the event's parts (``data``, ``time``, ``type``, ``key``, ``source``), the field's value now
(``current``), quoted text, numbers, ``true``/``false``/``null``, arithmetic, comparisons, ``and``/``or``/``not``,
``a if c else b``, and calls to the fold functions (the built-ins below and the model's own ``functions:``). It is
parsed with ``ast`` and walked against an allow-list: nothing else is ever run. Text is quoted inside it:
``set('planned')``; a bare word that is none of the names is an error.

A fold function is called ``f(current, *args)`` and returns the field's new value. The built-ins given a null value
change nothing (an aggregate skips it, as ``append``, ``add``, ``union``... do); ``set`` sets whatever it is given,
``unset()`` takes the field out. An expression with no fold function is ``set`` of its value (``data.reason`` is
``set(data.reason)``).

The whole event applies or none of it: a fold function that raises, a type error, a ``state`` not among the
projection's states refuses the event for that item (kept on the record, shown in the item's refused)."""

from __future__ import annotations

import ast
import copy
import fnmatch
import hashlib
import inspect
import json
import operator
import types
from pathlib import Path

from .changes import AGGREGATES, PatchError, _num, _order, aggregate, merged, rule_ops
from .jsonpatch import apply, pointer

NAMES = ("data", "time", "type", "key", "source", "current")          # what an expression may name
CONSTS = {"true": True, "false": False, "null": None, "True": True, "False": False, "None": None}
POW_MOST = 1000                                                      # the largest exponent ** takes


class BadExpr(ValueError):
    """An expression that does not parse, or uses what is not allowed (``code``: the check's code)."""

    def __init__(self, msg: str, code: str = "bad-expression"):
        super().__init__(msg)
        self.code = code


class _Keep:
    def __repr__(self):
        return "KEEP"


class _Unset:
    def __repr__(self):
        return "UNSET"


KEEP, UNSET = _Keep(), _Unset()        # a fold function's answer: no change; the field taken out


# ---- the built-in fold functions: f(current, *args) -> the new value (KEEP: no change)

def _set(cur, x):
    return x


def _add(cur, x):
    if x is None:
        return KEEP
    if not _num(x) or (cur is not None and not _num(cur)):
        raise PatchError(f"add needs numbers ({json.dumps(cur, default=str)[:60]} + {json.dumps(x, default=str)[:60]})")
    return (cur or 0) + x


def _minmax(name, pick):
    def f(cur, x):
        if x is None:
            return KEEP
        if cur is None:
            return x
        if not ((_num(cur) and _num(x)) or (isinstance(cur, str) and isinstance(x, str))):
            raise PatchError(f"{name} compares numbers with numbers, or text with text")
        return pick(cur, x)
    f.__name__ = name
    return f


def _append(cur, x, n=None):
    if x is None:
        return KEEP
    if cur is not None and not isinstance(cur, list):
        raise PatchError(f"append needs a list, and it holds {type(cur).__name__}")
    if n is not None and (type(n) is not int or n < 1):
        raise PatchError(f"append keeps the last N values: a whole number of 1 or more, not {n!r}")
    out = list(cur or []) + (list(x) if isinstance(x, list) else [x])
    return out[-n:] if n is not None else out


def _union(cur, x):
    if x is None:
        return KEEP
    if cur is not None and not isinstance(cur, list):
        raise PatchError(f"union needs a list, and it holds {type(cur).__name__}")
    members = {json.dumps(v, sort_keys=True, default=str): v for v in [*(cur or []), *(x if isinstance(x, list) else [x])]}
    return sorted(members.values(), key=_order)


def _remove(cur, x):
    if x is None or cur is None:
        return KEEP
    if not isinstance(cur, list):
        raise PatchError(f"remove needs a list, and it holds {type(cur).__name__}")
    gone = {json.dumps(v, sort_keys=True, default=str) for v in (x if isinstance(x, list) else [x])}
    return [v for v in cur if json.dumps(v, sort_keys=True, default=str) not in gone]


def _merge(cur, x):
    if x is None:
        return KEEP
    if cur is not None and not isinstance(cur, dict):
        raise PatchError(f"merge needs an object, and it holds {type(cur).__name__}")
    if not isinstance(x, dict):
        raise PatchError(f"merge needs an object to merge in, not {type(x).__name__}")
    return merged(cur or {}, x)


def _first(cur, x):
    return x if cur is None and x is not None else KEEP


def _unset(cur):
    return UNSET


def _aggregate(name):            # stands for an aggregate in the table (its running state is kept by ``value_of``)
    def f(cur, x=True):
        raise AssertionError(name)
    f.__name__ = name
    return f


BUILTINS = {"set": _set, "add": _add, "min": _minmax("min", min), "max": _minmax("max", max), "append": _append,
            "union": _union, "remove": _remove, "merge": _merge, "first": _first, "unset": _unset,
            **{a: _aggregate(a) for a in AGGREGATES}}
def _obj(name, obj):
    if obj is not None and not isinstance(obj, dict):
        raise PatchError(f"{name} takes an object, not {type(obj).__name__}")
    return obj or {}


def _pick(obj, *names):
    o = _obj("pick", obj)
    return {k: copy.deepcopy(o[k]) for k in names if k in o} if obj is not None else None


def _omit(obj, *names):
    o = _obj("omit", obj)
    return {k: copy.deepcopy(v) for k, v in o.items() if k not in names} if obj is not None else None


def _rename(obj, **names):
    o = _obj("rename", obj)
    return {names.get(k, k): copy.deepcopy(v) for k, v in o.items()} if obj is not None else None


def _glob(x, pattern):
    return isinstance(x, str) and isinstance(pattern, str) and fnmatch.fnmatchcase(x, pattern)


def strings(v, out: list | None = None, depth: int = 0) -> list:
    """Every text value in ``v``, nested (an object's values, a list's members; never an object's names)."""
    out = [] if out is None else out
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, dict) and depth < 64:
        for x in v.values():
            strings(x, out, depth + 1)
    elif isinstance(v, list) and depth < 64:
        for x in v:
            strings(x, out, depth + 1)
    return out


def _has(where, text) -> bool:
    """``has(TEXT)``: some text value of the event (its type, key, source or data, nested) contains TEXT, whatever
    the case; ``has(VALUE, TEXT)``: some text in VALUE does."""
    if not isinstance(text, str):
        return False
    t = text.lower()
    return any(t in s.lower() for s in strings(where))


def event_texts(env: dict) -> list:
    """The text values ``has(TEXT)`` searches: the event's type, key, source and data's."""
    return strings([env.get("type"), env.get("key"), env.get("source"), env.get("data")])


class Each(list):
    """``each(LIST, 'field')`` in a key: the values that name the objects one event applies to (one event, several)."""


def _each(lst, field=None):
    if lst is None:
        return Each()
    lst = lst if isinstance(lst, list) else [lst]
    return Each([x.get(field) if isinstance(x, dict) else None for x in lst] if field is not None else lst)


def _pairs(obj, k="key", v="value"):
    """A list of {key, value} objects as one object (AWS's tags: ``pairs(data.tagSet.items, 'key', 'value')``)."""
    if obj is None:
        return None
    if not isinstance(obj, list):
        raise PatchError(f"pairs takes a list, not {type(obj).__name__}")
    return {str(x.get(k)): copy.deepcopy(x.get(v)) for x in obj if isinstance(x, dict) and x.get(k) is not None}


def _int(x):
    """``int(x)``: a whole number from a number or its text (``'42'``, ``'4.0'``); null for anything else."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        f = float(x.strip()) if isinstance(x, str) else float(x) if isinstance(x, (int, float)) else None
    except ValueError:
        return None
    return int(f) if f is not None and f == f and abs(f) != float("inf") else None


def _float(x):
    """``float(x)``: a number from a number or its text; null for anything else."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        f = float(x.strip()) if isinstance(x, str) else float(x) if isinstance(x, (int, float)) else None
    except ValueError:
        return None
    return f if f is not None and f == f and abs(f) != float("inf") else None


def _str(x):
    """``str(x)``: text (a number as written, true/false, an object or list as JSON); null stays null."""
    if x is None or isinstance(x, str):
        return x
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (dict, list)):
        return json.dumps(x, separators=(",", ":"), sort_keys=True, default=str)
    return str(x)


def _json(x):
    """``json(x)``: JSON text parsed (an Azure ``properties.responseBody``, a GCP ``requestJson``); an object or list as
    it is; null for anything that is not JSON."""
    if isinstance(x, (dict, list)):
        return x
    if not isinstance(x, str):
        return None
    try:
        return json.loads(x)
    except (ValueError, RecursionError):
        return None


def _case(name):
    def f(x):
        return getattr(x, name)() if isinstance(x, str) else None
    f.__name__ = name
    return f


HELPERS = {"pick": _pick, "omit": _omit, "rename": _rename, "glob": _glob, "pairs": _pairs,   # plain functions,
           "int": _int, "float": _float, "str": _str, "json": _json,                       # usable anywhere
           "lower": _case("lower"), "upper": _case("upper")}                               # (a spread's too)
ONE_ARG = ("int", "float", "str", "json", "lower", "upper")       # the helpers of one value
SPREAD = "..."                         # a handler's key whose object's fields each set the item's field of that name
ARITY = {"set": (1, 1), "add": (1, 1), "min": (1, 1), "max": (1, 1), "append": (1, 2), "union": (1, 1), "remove": (1, 1),
         "merge": (1, 1), "first": (1, 1), "unset": (0, 0), "count": (0, 1), "mean": (1, 1), "variance": (1, 1),
         "stdev": (1, 1), "rms": (1, 1), "each": (1, 2)}
METHODS = ("startswith", "endswith", "lower", "upper", "strip", "split", "replace", "get")   # called on a value


# ---- the model's own functions

def load_functions(root: Path, paths, err) -> tuple[dict, str]:
    """``functions: [file.py, ...]`` (relative to the model's folder): each file's top-level ``def`` by name, and a hash
    of the files' text (the item index's cache key holds it, so a change folds again). ``err(msg)`` for a file that
    does not load, a name a built-in has, a name two files define. The model's own code, run in ergostat's process as a
    sensor's command is the owner's."""
    out: dict = {}
    h = hashlib.sha1()
    for p in paths:
        f = (Path(root) / str(p))
        try:
            text = f.read_text()
        except OSError as e:
            err(f"functions: {p}: cannot be read ({e.strerror or e})")
            continue
        h.update(str(p).encode() + b"\0" + text.encode() + b"\0")
        mod = types.ModuleType(f"ergostat_functions_{f.stem}")
        mod.__file__ = str(f)
        try:
            exec(compile(text, str(f), "exec"), mod.__dict__)           # noqa: S102 - the owner's own code
        except Exception as e:                                          # noqa: BLE001 - said, never raised
            err(f"functions: {p} does not load: {type(e).__name__}: {e}")
            continue
        for name, fn in vars(mod).items():
            if name.startswith("_") or not inspect.isfunction(fn) or fn.__module__ != mod.__name__:
                continue
            if name in BUILTINS or name in HELPERS or name == "has":
                err(f"functions: {p}: {name} is a built-in fold function ({', '.join(BUILTINS)}); name it something else")
                continue
            if name in out:
                err(f"functions: {name} is defined in two files")
                continue
            out[name] = fn
    return out, h.hexdigest()[:16]


def _arity_ok(name: str, fn, n: int) -> str | None:
    if name in ARITY:
        lo, hi = ARITY[name]
        return None if lo <= n <= hi else f"{name} takes {lo if lo == hi else f'{lo} to {hi}'} argument" + \
            ("s" if hi != 1 else "") + f", not {n}"
    try:
        inspect.signature(fn).bind(None, *([None] * n))
    except TypeError:
        return f"{name}{inspect.signature(fn)}: is called as {name}(current, ...), and {n} argument" + \
            ("s do" if n != 1 else " does") + " not fit it"
    except ValueError:
        return None
    return None


# ---- expressions

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UN = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
        ast.GtE: operator.ge, ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}


class Value:
    """A handler's value, compiled: a literal, or an expression (``tree``)."""

    __slots__ = ("text", "literal", "tree", "call")

    def __init__(self, text, literal=None, tree=None):
        self.text, self.literal, self.tree = text, literal, tree
        self.call = tree.func.id if isinstance(tree, ast.Call) and isinstance(tree.func, ast.Name) and \
            tree.func.id not in HELPERS and tree.func.id not in ("each", "has") else None   # its fold function, at the top

    def __repr__(self):
        return f"Value({self.text!r})"


def compile_value(raw, functions: dict | None = None, names=NAMES) -> Value:
    """A handler's value (or a key part): text is an expression; any other YAML value (a number, a boolean, null, a
    list, a map) a constant. BadExpr for an expression that does not parse or uses what is not allowed."""
    if not isinstance(raw, str):
        return Value(raw, literal=copy.deepcopy(raw))
    src = raw.strip()
    try:
        tree = ast.parse(src, mode="eval").body
    except SyntaxError as e:
        raise BadExpr(f"{raw!r} does not parse: {e.msg} (text is quoted: set('{raw}'))") from None
    fns = {**BUILTINS, **(functions or {})}
    _check(tree, fns, names, top=True)
    return Value(raw, tree=tree)


def _check(n, fns: dict, names, top: bool = False) -> None:
    if isinstance(n, ast.Constant):
        if not (n.value is None or isinstance(n.value, (str, int, float, bool))):
            raise BadExpr(f"{type(n.value).__name__} literals are not allowed")
    elif isinstance(n, ast.Name):
        if n.id not in names and n.id not in CONSTS:
            raise BadExpr(f"{n.id} is not a name: write set('{n.id}') for the text (the names: {', '.join(names)})")
    elif isinstance(n, ast.Attribute):
        if n.attr.startswith("_"):
            raise BadExpr(f".{n.attr}: a name starting with _ is not allowed")
        if not isinstance(n.value, (ast.Name, ast.Attribute, ast.Subscript)) and not (
                isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id in HELPERS):
            raise BadExpr(f".{n.attr}: dotted access reads into the event's parts (data.detail.state), nothing else")
        _check(n.value, fns, names)
    elif isinstance(n, ast.Subscript):
        if isinstance(n.slice, ast.Slice):
            raise BadExpr("slices are not allowed")
        _check(n.value, fns, names)
        _check(n.slice, fns, names)
    elif isinstance(n, ast.BinOp):
        if type(n.op) not in _BIN:
            raise BadExpr(f"the operator {type(n.op).__name__} is not allowed (+ - * / // % **)")
        _check(n.left, fns, names)
        _check(n.right, fns, names)
    elif isinstance(n, ast.UnaryOp):
        if type(n.op) not in _UN:
            raise BadExpr(f"the operator {type(n.op).__name__} is not allowed")
        _check(n.operand, fns, names)
    elif isinstance(n, ast.BoolOp):
        for v in n.values:
            _check(v, fns, names)
    elif isinstance(n, ast.Compare):
        if any(type(o) not in _CMP for o in n.ops):
            raise BadExpr("comparisons are == != < <= > >= in, not in")
        for v in (n.left, *n.comparators):
            _check(v, fns, names)
    elif isinstance(n, (ast.List, ast.Tuple)):
        if len(n.elts) > 1000:
            raise BadExpr("a list of at most 1000 values")
        for v in n.elts:
            _check(v, fns, names)
    elif isinstance(n, ast.IfExp):
        for v in (n.test, n.body, n.orelse):
            _check(v, fns, names)
    elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
        if n.func.attr not in METHODS or n.keywords or any(isinstance(a, ast.Starred) for a in n.args):
            raise BadExpr(f".{n.func.attr}(): the methods a value has are {', '.join(METHODS)}")
        _check(n.func.value, fns, names)
        for a in n.args:
            _check(a, fns, names)
    elif isinstance(n, ast.Call):
        if not isinstance(n.func, ast.Name):
            raise BadExpr("only fold functions are called, by name: add(1), append(data.reason, 20)")
        name = n.func.id
        if name == "has":
            if n.keywords or not 1 <= len(n.args) <= 2 or any(isinstance(a, ast.Starred) for a in n.args):
                raise BadExpr("has('text'): some text of the event contains it (has(VALUE, 'text'): some text in VALUE)")
            for a in n.args:
                _check(a, fns, names)
            return
        if name in HELPERS:
            if any(isinstance(a, ast.Starred) for a in n.args) or not n.args:
                raise BadExpr(f"{name}(obj, ...): the object first, then the names")
            if n.keywords and name != "rename":
                raise BadExpr(f"{name}(): names are given as text: {name}(data, 'a', 'b')")
            if name == "rename" and (len(n.args) != 1 or any(k.arg is None for k in n.keywords)):
                raise BadExpr("rename(obj, old='new', ...): the object, then each field's new name")
            if name in ONE_ARG and len(n.args) != 1:
                raise BadExpr(f"{name}(x) takes one value")
            for a in (*n.args, *(k.value for k in n.keywords)):
                _check(a, fns, names)
            return
        if name not in fns:
            raise BadExpr(f"{name}() is not a fold function (built in: {', '.join(BUILTINS)}"
                          + (f"; the model's: {', '.join(sorted(set(fns) - set(BUILTINS) - {'each'}))}"
                             if set(fns) - set(BUILTINS) - {"each"} else "")
                          + ("; each() is for a key" if name == "each" else "") + ")", "unknown-function")
        if n.keywords or any(isinstance(a, ast.Starred) for a in n.args):
            raise BadExpr(f"{name}(): arguments are given in order, without names or *")
        if name in AGGREGATES and not top:
            raise BadExpr(f"{name}() keeps a running state of the field: it is the whole expression, not part of one")
        bad = _arity_ok(name, fns[name], len(n.args))
        if bad:
            raise BadExpr(bad)
        for a in n.args:
            _check(a, fns, names)
    else:
        raise BadExpr(f"{type(n).__name__} is not allowed in an expression")


def _ev(n, env: dict):
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.Name):
        return CONSTS[n.id] if n.id in CONSTS else env.get(n.id)
    if isinstance(n, ast.Attribute):
        v = _ev(n.value, env)
        return v.get(n.attr) if isinstance(v, dict) else None
    if isinstance(n, ast.Subscript):
        v, i = _ev(n.value, env), _ev(n.slice, env)
        if isinstance(v, dict):
            return v.get(i) if isinstance(i, (str, int, float, bool)) or i is None else None
        if isinstance(v, (list, str)) and type(i) is int:
            return v[i] if -len(v) <= i < len(v) else None
        return None
    if isinstance(n, ast.BinOp):
        a, b = _ev(n.left, env), _ev(n.right, env)
        if isinstance(n.op, ast.Pow) and _num(b) and abs(b) > POW_MOST:
            raise PatchError(f"** takes exponents up to {POW_MOST}")
        if isinstance(n.op, ast.Mult) and (isinstance(a, (str, list)) or isinstance(b, (str, list))):
            m = b if isinstance(a, (str, list)) else a
            if _num(m) and m * len(a if isinstance(a, (str, list)) else b) > 1_000_000:
                raise PatchError("a repeated text or list of over a million is not made")
        return _BIN[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp):
        return _UN[type(n.op)](_ev(n.operand, env))
    if isinstance(n, ast.BoolOp):
        if isinstance(n.op, ast.And):
            v = True
            for x in n.values:
                v = _ev(x, env)
                if not v:
                    return v
            return v
        v = False
        for x in n.values:
            v = _ev(x, env)
            if v:
                return v
        return v
    if isinstance(n, ast.Compare):
        left = _ev(n.left, env)
        for o, c in zip(n.ops, n.comparators, strict=True):
            right = _ev(c, env)
            if not _CMP[type(o)](left, right):
                return False
            left = right
        return True
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_ev(x, env) for x in n.elts]
    if isinstance(n, ast.IfExp):
        return _ev(n.body, env) if _ev(n.test, env) else _ev(n.orelse, env)
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
        obj = _ev(n.func.value, env)
        args = [_ev(a, env) for a in n.args]
        m = n.func.attr
        try:
            if m == "get":
                return obj.get(*args) if isinstance(obj, dict) else None
            return getattr(obj, m)(*args) if isinstance(obj, str) else None
        except (TypeError, ValueError, AttributeError):
            return None
    if isinstance(n, ast.Call):
        name = n.func.id
        args = [_ev(a, env) for a in n.args]
        if name == "each":
            return _each(*args)
        if name == "has":
            return _has(event_texts(env), args[0]) if len(args) == 1 else _has(args[0], args[1])
        if name in HELPERS:
            return HELPERS[name](*args, **{k.arg: _ev(k.value, env) for k in n.keywords})
        fn = BUILTINS.get(name) or env["functions"][name]
        cur = env.get("current")
        try:
            got = fn(cur if name in BUILTINS or not isinstance(cur, (dict, list)) else copy.deepcopy(cur), *args)
            #      (the built-ins make what they return anew, never changing what they are given)
        except PatchError:
            raise
        except Exception as e:                       # noqa: BLE001 - the event is refused with why
            raise PatchError(f"{name}: {type(e).__name__}: {e}") from None
        if got is KEEP:
            return cur if "current" in env else None
        return got
    raise PatchError(f"{type(n).__name__} is not allowed")         # (never: compile_value checked it)


def evaluate_strict(v: Value, env: dict):
    """A value as a handler gives it (an error refuses the event)."""
    return copy.deepcopy(v.literal) if v.tree is None else _ev(v.tree, env)


def evaluate(v: Value, env: dict):
    """A key part's or a match's value: the literal, or the expression's."""
    if v.tree is None:
        return copy.deepcopy(v.literal)
    try:
        return _ev(v.tree, env)
    except PatchError:
        return None
    except Exception:                                # noqa: BLE001 - a key that cannot be read is no key
        return None


# ---- events: what a projection reads, and the item each belongs to
def env_of(e: dict, kind=None) -> dict:
    """The names an expression reads of event ``e``: ``data``, ``time`` (the event's own time when the projection
    names it, ``time:``; else the recorded time), ``type``, ``key`` (its item), ``source``."""
    data = e.get("data") if isinstance(e.get("data"), dict) else {}
    return {"data": data, "time": own_time(kind, e, data), "type": e.get("type"), "key": e.get("item"),
            "source": e.get("source")}


def own_time(kind, e: dict, data: dict | None = None) -> float:
    """The event's time by the projection's ``time:`` (an expression of it, as seconds or ISO 8601 text), else the
    recorded time."""
    v = getattr(kind, "own_time", None) if kind is not None else None
    if v is None:
        return e.get("time")
    from .fields import seconds
    got = seconds(evaluate(v, {"data": data if data is not None else (e.get("data") or {}), "time": e.get("time"),
                                "type": e.get("type"), "key": e.get("item"), "source": e.get("source")}))
    return got if got is not None else e.get("time")


def keys_from(parts: list[Value], env: dict) -> list[str]:
    """The objects an event applies to: its key parts' values joined by ``/`` (``each(...)`` in a part: one for each
    of its values); none when a part is missing (the event is not one of this projection's objects)."""
    outs = [[]]
    for p in parts:
        v = evaluate(p, env)
        vals = list(v) if isinstance(v, Each) else [v]
        got = []
        for x in vals:
            if x is None or x == "" or isinstance(x, (dict, list)):
                continue
            got.append(str(x).lower() if isinstance(x, bool) else str(x))
        if not got:
            return []
        outs = [o + [g] for o in outs for g in dict.fromkeys(got)]
        if len(outs) > 1000:
            outs = outs[:1000]
    return ["/".join(o) for o in outs]


def _key_text(x) -> str:
    return str(x).lower() if isinstance(x, bool) else str(x)


def key_values(parts: list[Value], env: dict, id: str) -> list | None:
    """The key parts' values that name object ``id`` (``each(...)`` in a part: the one of its values that does), as
    the event gives them: what the key's fields are set to for that object. None when no combination names it."""
    outs = [[]]
    for p in parts:
        v = evaluate(p, env)
        vals = [x for x in (list(v) if isinstance(v, Each) else [v])
                if not (x is None or x == "" or isinstance(x, (dict, list)))]
        if not vals:
            return None
        outs = [o + [g] for o in outs for g in vals][:1000]
    return next((o for o in outs if "/".join(_key_text(x) for x in o) == id), None)


def key_of(parts: list[Value], e: dict) -> str | None:
    """The first object an event belongs to (``keys_from``); None when it belongs to none."""
    got = keys_from(parts, env_of(e))
    return got[0] if got else None


# ---- folding one event

def value_of(kind, f: str, v: Value, fields: dict, acc: dict, env: dict, implicit_rule: str | None):
    """The field's new value (KEEP: unchanged, UNSET: taken out) and the rule that made it."""
    if v.tree is None:
        new = copy.deepcopy(v.literal)
        return (_by_rule(f, new, fields, acc, kind, implicit_rule) if implicit_rule else new), (implicit_rule or "set")
    if v.call in AGGREGATES:
        args = [_ev(a, env) for a in v.tree.args]
        x = args[0] if args else True
        if x is None:
            return KEEP, v.call
        ops, st = aggregate(fields, f, x, v.call, acc)
        if st is not None:
            acc[f] = st
        return (ops[-1]["value"] if ops else KEEP), v.call
    got = _ev(v.tree, env)
    if v.call is None:
        if implicit_rule:
            return _by_rule(f, copy.deepcopy(got), fields, acc, kind, implicit_rule), implicit_rule
        return (copy.deepcopy(got) if isinstance(got, (dict, list)) else got), "set"
    if got is UNSET:
        return UNSET, v.call
    if v.call in BUILTINS and got is env.get("current") and v.call != "set":
        return KEEP, v.call
    if v.call in BUILTINS and v.call != "set":
        return got, v.call
    return (copy.deepcopy(got) if isinstance(got, (dict, list)) else got), v.call


def _by_rule(f: str, x, fields: dict, acc: dict, kind, rule: str):
    """A plain value folded by the projection's own rule for the field (a relation's, a pipeline's stages)."""
    tmp = {f: copy.deepcopy(fields[f])} if f in fields else {}
    apply(tmp, rule_ops(tmp, f, x, rule, (kind.bounds or {}).get(f), acc))
    return tmp[f] if f in tmp else UNSET


SEEN = "~seen"           # acc's key: the latest events' digests (an event delivered twice counts once)
TIMES = "~t"             # acc's key: each field's event time, as last written (the fold is by event time)
SEEN_MOST = 256          # the latest events an object remembers, to know one delivered twice
LATEST_WINS = ("set", "replace", "unset", None)   # newest by event time wins (unset too)


def _digest(e: dict) -> str:
    return hashlib.sha1(json.dumps([e.get("type"), e.get("data")], sort_keys=True, default=str).encode()).hexdigest()[:16]


def apply_event(kind, it, e: dict) -> tuple[list[tuple], str | None, str | None, str | None]:
    """One plain-data event applied to object ``it`` by projection ``kind``: the first kind of event whose ``when:``
    holds takes it, and its entry's values fold into their fields. What changed ``(op, path, before, after, rule)``,
    why it was refused (and nothing changed), the state it moves to, and the kind of event that took it (None: none
    did, the remainder). The fold is by event time: a value folded by replace (or a state) older than the field's is
    not taken, a ``first`` older than the field's replaces it; an event the object saw already (the same type and data
    whole) changes nothing."""
    data = e.get("data") if isinstance(e.get("data"), dict) else {}
    ek = kind.kind_of(e)
    if ek is None:
        return [], None, None, None
    acc = dict(it.acc)
    if getattr(kind, "own_time", None) is not None:  # events that carry their own time: the same type and data whole
        h = _digest(e)                               # is the same event, delivered twice (without it, a value set,
        seen = list(acc.get(SEEN) or [])             # cleared and set again is three events, not a repeat)
        if h in seen:
            return [], None, None, ek.name
        acc[SEEN] = (seen + [h])[-SEEN_MOST:]
    env = {**env_of(e, kind), "functions": kind.functions or {}}
    t_own = (env["time"] if isinstance(env["time"], (int, float)) else e.get("time")) \
        if getattr(kind, "own_time", None) is not None else None     # by event time when it names one; else in order
    times = dict(acc.get(TIMES) or {})
    declared = getattr(kind, "declared", None) or {}
    keyed = {}                                       # the key's fields: the values that name this object
    if getattr(kind, "key", None) and ek.key and isinstance(getattr(it, "id", None), str):
        vals = key_values(ek.key, env, it.id)
        if vals is not None:
            keyed = dict(zip(kind.key, vals, strict=True))
    fields = dict(it.fields)
    changed: dict[str, str] = {}
    to = None
    try:
        for f, v in sorted(ek.fields.items(), key=lambda fv: fv[0] != SPREAD):    # a spread first: the rest after
            if f == SPREAD:
                env["current"] = None
                got = evaluate_strict(v, env)
                if got is None:
                    continue
                if not isinstance(got, dict):
                    raise PatchError(f"...: a spread takes an object, and {v.text!r} gave "
                                     f"{json.dumps(got, default=str)[:60]}")
                for k, x in got.items():
                    if k in ek.fields or k == "state" and kind.states:
                        continue                     # the entry's own value for it wins
                    d = declared.get(k)
                    rule = (kind.fold or {}).get(k)
                    if d is not None and d.fold in (kind.functions or {}):     # folded by the model's own function
                        new = kind.functions[d.fold](copy.deepcopy(fields.get(k)), x)
                        if new is KEEP:
                            continue
                    elif rule and rule not in ("replace", "first"):          # folded by its declared rule
                        if x is None:
                            continue
                        new = _by_rule(k, x, fields, acc, kind, rule)
                    else:
                        older = t_own is not None and k in times and t_own < times[k]
                        if rule == "first" and k in fields and not older or rule != "first" and older:
                            continue
                        new = copy.deepcopy(x) if isinstance(x, (dict, list)) else x
                        times[k] = t_own
                    if d is not None and new is not UNSET and not d.type.fits(new):
                        raise PatchError(f"{k}: {json.dumps(new, default=str)[:60]} is not {d.type}")
                    if new is UNSET:
                        fields.pop(k, None)
                    else:
                        fields[k] = new
                    changed[k] = rule or "set"
                continue
            latest = v.call in LATEST_WINS
            first = v.call == "first"
            older = t_own is not None and f in times and t_own < times[f]
            if latest and older:                     # an older value than the field's: newest by event time wins
                continue
            env["current"] = (to or it.state) if f == "state" else (None if first and older else fields.get(f))
            if f in keyed:
                new, rule = keyed[f], "set"
            else:
                new, rule = value_of(kind, f, v, fields, acc, env, (kind.fold or {}).get(f) if f != "state" else None)
            if new is KEEP:
                continue
            if latest or first:
                times[f] = t_own
            if f == "state":
                if new is UNSET or new is None:
                    continue
                if not isinstance(new, str) or (kind.states and new not in kind.states):
                    raise PatchError(f"state: {json.dumps(new, default=str)[:60]} is not one of its states "
                                     f"({', '.join(kind.states) or 'none'})")
                to = new
                continue
            d = declared.get(f)
            if d is not None and new is not UNSET and not d.type.fits(new):
                raise PatchError(f"{f}: {json.dumps(new, default=str)[:60]} is not {d.type}")
            if new is UNSET:
                fields.pop(f, None)
            else:
                fields[f] = new
            changed[f] = rule
    except PatchError as err:
        return [], str(err), None, ek.name
    except Exception as err:                         # noqa: BLE001 - a fold never stops on one event
        return [], f"{type(err).__name__}: {err}", None, ek.name
    if times:
        acc[TIMES] = times
    done = []
    for f, rule in changed.items():
        had, before = f in it.fields, it.fields.get(f)
        if f not in fields:
            if had:
                done.append(("remove", pointer(f), before, None, rule))
        elif not had:
            done.append(("add", pointer(f), None, fields[f], rule))
        elif not (type(before) is type(fields[f]) and before == fields[f]):
            done.append(("replace", pointer(f), before, fields[f], rule))
    if done:
        for _, p, _, _, _ in done:
            f = p[1:].replace("~1", "/").replace("~0", "~")
            if f in fields:
                it.fields[f] = fields[f]
            else:
                it.fields.pop(f, None)
    it.acc.clear()
    it.acc.update(acc)
    return done, None, to, ek.name


def key_glob(tree) -> str | None:
    """The id glob a query reads by, when it reads by its key's prefix alone (``key.startswith('ticket/')``,
    ``glob(key, 'ticket/*')``); None for any other query."""
    if not isinstance(tree, ast.Call) or len(tree.args) not in (1, 2):
        return None
    f, a = tree.func, tree.args
    if isinstance(f, ast.Attribute) and f.attr == "startswith" and isinstance(f.value, ast.Name) and f.value.id == "key" \
            and len(a) == 1 and isinstance(a[0], ast.Constant) and isinstance(a[0].value, str):
        return a[0].value.replace("[", "[[]").replace("*", "[*]").replace("?", "[?]") + "*"
    if isinstance(f, ast.Name) and f.id == "glob" and len(a) == 2 and isinstance(a[0], ast.Name) and a[0].id == "key" \
            and isinstance(a[1], ast.Constant) and isinstance(a[1].value, str):
        return a[1].value
    return None


def one_literal(v: Value):
    """The constant a value gives, when it is one: ``'done'``, ``set('done')``, ``first('x')`` (None: an expression)."""
    if v.tree is None:
        return v.literal if isinstance(v.literal, str) else None
    t = v.tree
    if isinstance(t, ast.Constant) and isinstance(t.value, str):
        return t.value
    if isinstance(t, ast.Call) and isinstance(t.func, ast.Name) and t.func.id in ("set", "first") and len(t.args) == 1 \
            and isinstance(t.args[0], ast.Constant) and isinstance(t.args[0].value, str):
        return t.args[0].value
    return None


def when_type(tree) -> str | None:
    """The one event type a ``when:`` takes, when it says one (``type == 'ticket.done'``, alone or first of an
    ``and``); None otherwise."""
    if isinstance(tree, ast.BoolOp) and isinstance(tree.op, ast.And):
        return next((t for t in (when_type(v) for v in tree.values) if t), None)
    if isinstance(tree, ast.Compare) and len(tree.ops) == 1 and isinstance(tree.ops[0], ast.Eq):
        a, b = tree.left, tree.comparators[0]
        for x, y in ((a, b), (b, a)):
            if isinstance(x, ast.Name) and x.id == "type" and isinstance(y, ast.Constant) and isinstance(y.value, str):
                return y.value
    return None
