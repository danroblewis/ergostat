"""An event's changeset, applied to an item's document (SPEC §5a). Every event changes its item in
one of three ways, which it chooses:

- ``patch``: a JSON Patch (RFC 6902), applied in order (``jsonpatch``);
- ``set``: the whole document at once: a patch that removes every field and adds the new
  document's back, so it takes the one path and shows in history as a full replacement;
- ``data`` (what blocks and scripts emit): each key folded by its kind's rule for it (``fold:``),
  turned into patch operations, so it takes the same path too. With no rule, a key replaces
  its field.

A changeset is applied whole or not at all: a ``test`` that fails, a path not there, a ``sum`` of
something that is not a number refuses the whole event, with why, and leaves the document as it
was. Refusal is a fact of the fold (the record keeps the event), shown in the item's history."""

from __future__ import annotations

import json

from .jsonpatch import PatchError, apply, pointer

RULES = ("replace", "append", "sum", "min", "max", "union", "merge", "first")
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


def rule_ops(doc: dict, key: str, value, rule: str) -> list[dict]:
    """The patch operations that fold ``value`` into field ``key`` by ``rule``."""
    path, has = pointer(key), key in doc
    cur = doc.get(key)
    if rule == "replace":
        return [{"op": "add", "path": path, "value": value}]
    if rule == "first":
        return [] if has else [{"op": "add", "path": path, "value": value}]
    if rule == "append":
        if has and not isinstance(cur, list):
            raise PatchError(f"{key}: append needs a list, and it holds {type(cur).__name__}")
        new = value if isinstance(value, list) else [value]
        return ([] if has else [{"op": "add", "path": path, "value": []}]) + \
            [{"op": "add", "path": path + "/-", "value": x} for x in new]
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
    raise PatchError(f"{key}: no fold rule {rule!r}")


def form_of(e: dict) -> str:
    return "patch" if e.get("patch") is not None else "set" if e.get("set") is not None else "data"


def ops_of(doc: dict, e: dict, rules: dict[str, str]) -> list[dict]:
    """The event's changeset, as patch operations against ``doc``."""
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
        ops += rule_ops(doc, k, v, rules.get(k, "replace"))
    return ops


def fold_event(doc: dict, e: dict, rules: dict[str, str]) -> tuple[list[tuple], str | None]:
    """Apply one event to ``doc``: what changed, or why it was refused (and nothing changed)."""
    try:
        ops = ops_of(doc, e, rules)
    except PatchError as err:
        return [], str(err)
    if not ops:
        return [], None
    try:
        return apply(doc, ops), None
    except PatchError as err:
        return [], str(err)
    except Exception as err:          # noqa: BLE001 - a fold never stops on one event
        return [], f"{type(err).__name__}: {err}"
