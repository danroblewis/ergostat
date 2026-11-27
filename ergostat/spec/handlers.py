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
OTHERWISE = ("merge", "ignore", "rest")
MATCH_PATHS = ("type", "key", "item", "source", "time")              # and data.a.b
POW_MOST = 1000                                                      # the largest exponent ** takes


class BadExpr(ValueError):
    """An expression that does not parse, or uses what is not allowed."""


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


HELPERS = {"pick": _pick, "omit": _omit, "rename": _rename}   # plain functions of an object, usable anywhere (a spread's)
SPREAD = "..."                         # a handler's key whose object's fields each set the item's field of that name
ARITY = {"set": (1, 1), "add": (1, 1), "min": (1, 1), "max": (1, 1), "append": (1, 2), "union": (1, 1), "remove": (1, 1),
         "merge": (1, 1), "first": (1, 1), "unset": (0, 0), "count": (0, 1), "mean": (1, 1), "variance": (1, 1),
         "stdev": (1, 1), "rms": (1, 1)}


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
            if name in BUILTINS or name in HELPERS:
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
        self.call = tree.func.id if isinstance(tree, ast.Call) and tree.func.id not in HELPERS else None   # its fold
        #                                                                                    function, at the top

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
        if not isinstance(n.value, (ast.Name, ast.Attribute, ast.Subscript)):
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
    elif isinstance(n, ast.IfExp):
        for v in (n.test, n.body, n.orelse):
            _check(v, fns, names)
    elif isinstance(n, ast.Call):
        if not isinstance(n.func, ast.Name):
            raise BadExpr("only fold functions are called, by name: add(1), append(data.reason, 20)")
        name = n.func.id
        if name in HELPERS:
            if any(isinstance(a, ast.Starred) for a in n.args) or not n.args:
                raise BadExpr(f"{name}(obj, ...): the object first, then the names")
            if n.keywords and name != "rename":
                raise BadExpr(f"{name}(): names are given as text: {name}(data, 'a', 'b')")
            if name == "rename" and (len(n.args) != 1 or any(k.arg is None for k in n.keywords)):
                raise BadExpr("rename(obj, old='new', ...): the object, then each field's new name")
            for a in (*n.args, *(k.value for k in n.keywords)):
                _check(a, fns, names)
            return
        if name not in fns:
            raise BadExpr(f"{name}() is not a fold function (built in: {', '.join(BUILTINS)}"
                          + (f"; the model's: {', '.join(sorted(set(fns) - set(BUILTINS)))}" if set(fns) - set(BUILTINS) else "")
                          + ")")
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
    if isinstance(n, ast.IfExp):
        return _ev(n.body, env) if _ev(n.test, env) else _ev(n.orelse, env)
    if isinstance(n, ast.Call):
        name = n.func.id
        args = [_ev(a, env) for a in n.args]
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

def path_of(e: dict, path: str):
    """``type``, ``key`` (or ``item``), ``source``, ``time``, ``data.a.b`` of an event: None when missing."""
    if path in ("key", "item"):
        return e.get("item")
    if path in ("type", "source", "time"):
        return e.get(path)
    if path == "data" or path.startswith("data."):
        v = e.get("data")
        for part in path.split(".")[1:]:
            if not isinstance(v, dict):
                return None
            v = v.get(part)
        return v
    return None


def match_ok(match: dict, e: dict) -> bool:
    """Whether every entry of ``match`` holds for ``e``: a value with ``*`` a glob over text, any other the value
    itself. ergostat's own events (``ergostat.*``: a lease, a snapshot) are read by the key entry alone, so they reach
    the projection whose items they are about (and none without a key entry)."""
    own = str(e.get("type") or "").startswith("ergostat.")
    if own and not any(p in match for p in ("key", "item")):
        return False
    for p, want in match.items():
        if own and p not in ("key", "item"):
            continue
        have = path_of(e, p)
        if isinstance(want, str) and any(c in want for c in "*?["):
            if not isinstance(have, str) or not fnmatch.fnmatchcase(have, want):
                return False
        elif isinstance(want, list):
            from .items import same
            if not any(same(have, w) for w in want):
                return False
        else:
            from .items import same
            if not same(have, want):
                return False
    return True


def key_of(parts: list[Value], e: dict) -> str | None:
    """The item an event belongs to: its key parts' values joined by ``/``; None when one is missing (the event is
    not one of this projection's items)."""
    env = {"data": e.get("data") if isinstance(e.get("data"), dict) else {}, "time": e.get("time"), "type": e.get("type"),
           "key": e.get("item"), "source": e.get("source")}
    out = []
    for p in parts:
        v = evaluate(p, env)
        if v is None or v == "" or isinstance(v, (dict, list)):
            return None
        out.append(str(v).lower() if isinstance(v, bool) else str(v))
    return "/".join(out)


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


def apply_event(kind, it, e: dict) -> tuple[list[tuple], str | None, str | None]:
    """One plain-data event applied to item ``it`` by projection ``kind``'s handlers: what changed
    ``(op, path, before, after, rule)``, why it was refused (and nothing changed), and the state it moves to."""
    data = e.get("data") if isinstance(e.get("data"), dict) else {}
    env = {"data": data, "time": e.get("time"), "type": e.get("type"), "key": e.get("item"), "source": e.get("source"),
           "functions": kind.functions or {}}
    fields, acc = dict(it.fields), dict(it.acc)
    own = kind.handlers.get(e.get("type") or "")
    named: set[str] = set()
    changed: dict[str, str] = {}
    to = None
    try:
        for h in (kind.handlers.get("*"), own):
            for f, v in sorted((h or {}).items(), key=lambda fv: fv[0] != SPREAD):    # a spread first: the rest after
                if f == SPREAD:
                    env["current"] = None
                    got = evaluate_strict(v, env)
                    if got is None:
                        continue
                    if not isinstance(got, dict):
                        raise PatchError(f"...: a spread takes an object, and {v.text!r} gave "
                                         f"{json.dumps(got, default=str)[:60]}")
                    for k, x in got.items():
                        named.add(k)
                        fields[k] = copy.deepcopy(x) if isinstance(x, (dict, list)) else x
                        changed[k] = "set"
                    continue
                named.add(f)
                env["current"] = (to or it.state) if f == "state" else fields.get(f)
                new, rule = value_of(kind, f, v, fields, acc, env, (kind.fold or {}).get(f) if f != "state" else None)
                if new is KEEP:
                    continue
                if f == "state":
                    if new is UNSET or new is None:
                        continue
                    if not isinstance(new, str) or (kind.states and new not in kind.states):
                        raise PatchError(f"state: {json.dumps(new, default=str)[:60]} is not one of its states "
                                         f"({', '.join(kind.states) or 'none'})")
                    to = new
                    continue
                if new is UNSET:
                    fields.pop(f, None)
                else:
                    fields[f] = new
                changed[f] = rule
        if kind.otherwise == "rest" or (kind.otherwise == "merge" and own is None):
            for f, x in data.items():
                if f in named:
                    continue
                rule = (kind.fold or {}).get(f, "replace")
                if rule == "replace":
                    fields[f] = copy.deepcopy(x) if isinstance(x, (dict, list)) else x
                else:
                    new = _by_rule(f, x, fields, acc, kind, rule)
                    if new is UNSET:
                        fields.pop(f, None)
                    else:
                        fields[f] = new
                changed[f] = rule
    except PatchError as err:
        return [], str(err), None
    except Exception as err:                         # noqa: BLE001 - a fold never stops on one event
        return [], f"{type(err).__name__}: {err}", None
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
    return done, None, to

