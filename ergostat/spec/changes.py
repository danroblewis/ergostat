"""An event's changeset, applied to an item's document (SPEC §5a). Every event changes its item in
one of three ways, which it chooses:

- ``patch``: a JSON Patch (RFC 6902), applied in order (``jsonpatch``);
- ``set``: the whole document at once: a patch that removes every field and adds the new
  document's back, so it takes the one path and shows in history as a full replacement;
- ``data`` (what blocks and scripts emit): each key folded by its projection's rule for it (``fold:``),
  turned into patch operations (a key with no rule replaces its field: an ``add`` at its
  path, made directly, as the operation would, since it cannot fail).

A changeset is applied whole or not at all: a ``test`` that fails, a path not there, a ``sum`` of
something that is not a number refuses the whole event, with why, and leaves the document as it
was. Refusal is a fact of the fold (the record keeps the event), shown in the item's history.

The aggregates (``count``, ``mean``, ``variance``, ``stdev``, ``rms``) show a plain number in their field and keep
what they need to go on exactly (the count, the running mean and Welford's sum of squared deviations, or the mean
of the squares) in the item's running state (``acc``: field -> state, beside its fields, kept wherever its fold is
kept: the item index, a snapshot's ``rollup.acc``), so a fold is the same however it was reached. The state holds
the value it last gave (``v``): a field a ``patch`` or ``set`` changed since starts its aggregate over."""

from __future__ import annotations

import copy
import json
import math

from .jsonpatch import PatchError, apply, pointer

RULES = ("replace", "append", "sum", "min", "max", "union", "merge", "first", "relation",
         "count", "mean", "variance", "stdev", "rms")
AGGREGATES = ("count", "mean", "variance", "stdev", "rms")   # a number shown, a running state kept (``acc``)
BOUNDED = ("append",)                                          # the rules that take a bound: ``{append: 20}``
RELATION_KEYS = ("set", "add", "remove")
FORMS = ("data", "patch", "set")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _order(v):
    """How a union's members sort: numbers, then strings, then anything else by its JSON."""
    if _num(v):
        return (0, v, "")
    if isinstance(v, str):
        return (1, 0, v)
    return (2, 0, json.dumps(v, sort_keys=True, default=str))


def merged(a, b):
    """``b`` merged into ``a``, deeply: objects key by key; anything else, ``b``'s value."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = merged(a[k], v) if k in a else v
        return out
    return b


def _same(a, b) -> bool:
    return type(a) is type(b) and a == b


def aggregate(doc: dict, key: str, value, rule: str, acc: dict | None) -> tuple[list[dict], dict | None]:
    """An aggregate's operations on field ``key`` and its running state after them (None: the state is unchanged).
    ``null`` is no value: nothing changes. ``count`` counts any other value (its state is its field); the rest take
    finite numbers (a boolean is not one), anything else refused as ``sum`` refuses it. The state (``acc[key]``) goes on
    only while the field still holds the value it gave; else (a patch or a set changed it, or another rule made it)
    the aggregate starts over from this value."""
    path, has = pointer(key), key in doc
    cur = doc.get(key)
    if value is None:
        return [], None
    if rule == "count":
        if has and cur is not None and not (type(cur) is int and cur >= 0):
            raise PatchError(f"{key}: count needs a count to add to, and it holds {json.dumps(cur, default=str)[:60]}")
        return [{"op": "add", "path": path, "value": (cur or 0) + 1}], None
    if not _num(value) or not math.isfinite(value):
        raise PatchError(f"{key}: {rule} takes finite numbers, not {json.dumps(value, default=str)[:60]}")
    s = (acc or {}).get(key)
    if not (isinstance(s, dict) and s.get("rule") == rule and has and _same(cur, s.get("v"))):
        s = {"rule": rule, "n": 0, "ms": 0.0} if rule == "rms" else {"rule": rule, "n": 0, "mean": 0.0, "m2": 0.0}
    n, x = s["n"] + 1, float(value)
    if rule == "rms":                                   # the mean of the squares, kept as a running mean
        ms = s["ms"] + (x * x - s["ms"]) / n
        new = {"rule": rule, "n": n, "ms": ms, "v": math.sqrt(ms)}
    else:                                               # Welford: the mean, and the sum of squared deviations from it
        d = x - s["mean"]
        mean = s["mean"] + d / n
        m2 = max(0.0, s["m2"] + d * (x - mean))
        var = m2 / (n - 1) if n > 1 else None          # the sample variance (n - 1): none until two values
        v = mean if rule == "mean" else var if rule == "variance" else (math.sqrt(var) if var is not None else None)
        new = {"rule": rule, "n": n, "mean": mean, "m2": m2, "v": v}
    ops = [] if has and _same(cur, new["v"]) else [{"op": "add", "path": path, "value": new["v"]}]
    return ops, new


def rule_ops(doc: dict, key: str, value, rule: str, bound: int | None = None, acc: dict | None = None) -> list[dict]:
    """The patch operations that fold ``value`` into field ``key`` by ``rule`` (``bound``: append's most values kept;
    ``acc``: the item's running state, read here, for an aggregate)."""
    if rule in AGGREGATES:
        return aggregate(doc, key, value, rule, acc)[0]
    path, has = pointer(key), key in doc
    cur = doc.get(key)
    if rule == "replace":                          # the same value again is no change (the event is still on the record)
        return [] if has and type(cur) is type(value) and cur == value else [{"op": "add", "path": path, "value": value}]
    if rule == "first":
        return [] if has else [{"op": "add", "path": path, "value": value}]
    if rule == "append":
        if has and not isinstance(cur, list):
            raise PatchError(f"{key}: append needs a list, and it holds {type(cur).__name__}")
        new = value if isinstance(value, list) else [value]
        if bound is not None and len(new) > bound:      # only the last ``bound`` of them could stay
            new = new[-bound:]
        over = max(0, len(cur if has else []) + len(new) - bound) if bound is not None else 0
        return ([] if has else [{"op": "add", "path": path, "value": []}]) + \
            [{"op": "add", "path": path + "/-", "value": x} for x in new] + \
            [{"op": "remove", "path": path + "/0"}] * over
    if rule == "sum":
        if not _num(value) or (has and cur is not None and not _num(cur)):
            raise PatchError(f"{key}: sum needs numbers ({json.dumps(cur, default=str)[:60]} + {json.dumps(value, default=str)[:60]})")
        return [{"op": "add", "path": path, "value": (cur or 0) + value}]
    if rule in ("min", "max"):
        if value is None:
            return []
        if has and cur is not None:
            if not ((_num(cur) and _num(value)) or (isinstance(cur, str) and isinstance(value, str))):
                raise PatchError(f"{key}: {rule} compares numbers with numbers, or text with text")
            if (value >= cur) if rule == "min" else (value <= cur):
                return []
        return [{"op": "add", "path": path, "value": value}]
    if rule == "union":
        if has and cur is not None and not isinstance(cur, list):
            raise PatchError(f"{key}: union needs a list, and it holds {type(cur).__name__}")
        members = {json.dumps(x, sort_keys=True, default=str): x for x in [*(cur or []), *(value if isinstance(value, list) else [value])]}
        new = sorted(members.values(), key=_order)
        return [] if has and new == cur else [{"op": "add", "path": path, "value": new}]
    if rule == "merge":
        if has and cur is not None and not isinstance(cur, dict):
            raise PatchError(f"{key}: merge needs an object, and it holds {type(cur).__name__}")
        if not isinstance(value, dict):
            raise PatchError(f"{key}: merge needs an object to merge in, not {type(value).__name__}")
        return [{"op": "add", "path": path, "value": merged(cur or {}, value)}]
    if rule == "relation":
        return _relation_ops(key, path, has, cur, value)
    raise PatchError(f"{key}: no fold rule {rule!r}")


def _ids(key: str, v) -> list[str]:
    got = v if isinstance(v, list) else [v]
    if not all(isinstance(x, str) and x for x in got):
        raise PatchError(f"{key}: a relation names items by their ids (text), not {json.dumps(v, default=str)[:60]}")
    return got


def _relation_ops(key: str, path: str, has: bool, cur, value) -> list[dict]:
    """A relation (SPEC §5a): a set of item ids. An id or a list of them is added; ``{"add": ..., "remove": ...,
    "set": ...}`` says it outright (``set`` first: the whole set, as a collector mirroring another system's links
    says it; then ``add``, then ``remove``)."""
    if has and cur is not None and not isinstance(cur, list):
        raise PatchError(f"{key}: a relation is a list of ids, and it holds {type(cur).__name__}")
    members = list(_ids(key, cur)) if cur else []        # (a patch or a set may have put anything there)
    if isinstance(value, dict):
        bad = [k for k in value if k not in RELATION_KEYS]
        if bad or not value:
            raise PatchError(f"{key}: a relation's change is ids, or an object of {', '.join(RELATION_KEYS)} ({', '.join(bad)})")
        if "set" in value:
            members = _ids(key, value["set"]) if value["set"] not in (None, []) else []
        if value.get("add") not in (None, []):
            members += _ids(key, value["add"])
        if value.get("remove") not in (None, []):
            gone = set(_ids(key, value["remove"]))
            members = [x for x in members if x not in gone]
    elif value is not None:
        members += _ids(key, value)
    new = sorted(set(members))
    return [] if (has and new == cur) or (not has and not new) else [{"op": "add", "path": path, "value": new}]


def form_of(e: dict) -> str:
    return "patch" if e.get("patch") is not None else "set" if e.get("set") is not None else "data"


def ops_of(doc: dict, e: dict, rules: dict[str, str], bounds: dict[str, int] | None = None,
           acc: dict | None = None) -> list[dict]:
    """The event's changeset, as patch operations against ``doc`` (``acc`` read, never changed: ``fold_event`` keeps
    an aggregate's state)."""
    form = form_of(e)
    if form == "patch":
        return e["patch"]
    if form == "set":
        new = e["set"]
        if not isinstance(new, dict):
            raise PatchError("set: the whole document, an object")
        return [{"op": "remove", "path": pointer(k)} for k in doc] + [{"op": "add", "path": pointer(k), "value": v}
                                                                       for k, v in new.items()]
    ops: list[dict] = []
    for k, v in (e.get("data") or {}).items():
        ops += rule_ops(doc, k, v, rules.get(k, "replace"), (bounds or {}).get(k), acc)
    return ops


def _plain(doc: dict, data: dict, rules: dict[str, str], bounds: dict[str, int] | None = None,
           acc: dict | None = None) -> list[tuple]:
    """Plain data, the usual case, folded straight in: the same changes the patch operations would
    make (a key replaced is an ``add`` at its path), without their undo log. Every key's operations
    are worked out first, so a key that cannot fold refuses the event before anything changes (an
    aggregate's running state too: kept in ``acc`` only once the event folds)."""
    staged = [(k, v, rules.get(k, "replace")) for k, v in data.items()]
    ops, states = {}, {}
    for k, v, r in staged:
        if r in AGGREGATES:
            ops[k], st = aggregate(doc, k, v, r, acc)
            if st is not None:
                states[k] = st
        elif r != "replace":
            ops[k] = rule_ops(doc, k, v, r, (bounds or {}).get(k))
    if acc is not None:
        acc.update(states)
    out = []
    for k, v, r in staged:
        if r != "replace":
            out += apply(doc, ops[k])
            continue
        had = k in doc
        if had and type(doc[k]) is type(v) and doc[k] == v:    # the same value again: no change
            continue
        out.append(("replace" if had else "add", pointer(k), doc.get(k) if had else None, v))
        doc[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
    return out


def fold_event(doc: dict, e: dict, rules: dict[str, str], bounds: dict[str, int] | None = None,
               acc: dict | None = None) -> tuple[list[tuple], str | None]:
    """Apply one event to ``doc``: what changed, or why it was refused (and nothing changed). ``bounds``: the most
    values an ``append`` keeps, by field; ``acc``: the item's running state for its aggregates, kept up here."""
    if form_of(e) == "data":
        try:
            return _plain(doc, e.get("data") or {}, rules, bounds, acc), None
        except PatchError as err:
            return [], str(err)
    try:
        ops = ops_of(doc, e, rules)
    except PatchError as err:
        return [], str(err)
    if not ops:
        return [], None
    try:
        done = apply(doc, ops)
        for k in [k for k, st in (acc or {}).items() if k not in doc or not _same(doc[k], st.get("v"))]:
            del acc[k]                                  # changed by a patch or a set: its aggregate starts over
        return done, None
    except PatchError as err:
        return [], str(err)
    except Exception as err:          # noqa: BLE001 - a fold never stops on one event
        return [], f"{type(err).__name__}: {err}"
