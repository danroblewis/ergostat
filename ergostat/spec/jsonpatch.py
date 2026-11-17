"""JSON Patch (RFC 6902) over JSON Pointers (RFC 6901), written here (the standard library only at
runtime): ``add``, ``remove``, ``replace``, ``move``, ``copy`` and ``test``, ``/-`` to append to an
array. A patch is applied whole or not at all: an operation that fails (a ``test`` that does not
hold, a path that is not there, an operation that is not one) undoes the ones before it and raises
``PatchError`` with why. The document is changed in place, with an undo log, so a long document
(a session's conversation) is never copied for each change; each value put in is a copy of its
own, so nothing the document holds is shared with the event that said it.

``apply`` returns what changed, in order: ``(op, path, before, after)`` with each path resolved
(``/messages/-`` as ``/messages/7``), ``before`` and ``after`` the values there (None for absent)."""

from __future__ import annotations

import copy
import json

OPS = ("add", "remove", "replace", "move", "copy", "test")
_ABSENT = object()


class PatchError(Exception):
    pass


def escape(key: str) -> str:
    return str(key).replace("~", "~0").replace("/", "~1")


def pointer(*keys) -> str:
    return "".join("/" + escape(k) for k in keys)


def parse(path) -> list[str]:
    """A JSON Pointer's reference tokens: ``""`` is the whole document."""
    if not isinstance(path, str):
        raise PatchError(f"{path!r}: a path is a JSON Pointer string")
    if path == "":
        return []
    if not path.startswith("/"):
        raise PatchError(f"{path!r}: a JSON Pointer starts with /")
    out = []
    for t in path[1:].split("/"):
        if "~" in t and any(t[i] == "~" and t[i + 1:i + 2] not in ("0", "1") for i in range(len(t))):
            raise PatchError(f"{path!r}: ~ is escaped as ~0 (and / as ~1)")
        out.append(t.replace("~1", "/").replace("~0", "~"))
    return out


def equal(a, b) -> bool:
    """JSON equality: a boolean is not a number, 1 equals 1.0, objects ignore key order."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b, strict=True))
    return type(a) is type(b) and a == b


def _index(tok: str, n: int, path: str, adding: bool) -> int:
    if tok == "-" and adding:
        return n
    if not tok.isdigit() or (len(tok) > 1 and tok[0] == "0"):
        raise PatchError(f"{path}: {tok!r} is not an array index")
    i = int(tok)
    if i > n or (i == n and not adding):
        raise PatchError(f"{path}: index {i} is past the end of the array (length {n})")
    return i


def _parent(doc, toks: list[str], path: str):
    cur = doc
    for k, t in enumerate(toks[:-1]):
        if isinstance(cur, dict):
            if t not in cur:
                raise PatchError(f"{path}: {pointer(*toks[:k + 1])} is not there")
            cur = cur[t]
        elif isinstance(cur, list):
            cur = cur[_index(t, len(cur), path, False)]
        else:
            raise PatchError(f"{path}: {pointer(*toks[:k])} is not an object or an array")
    return cur


def get(doc, path: str):
    """The value at ``path``; ``PatchError`` when it is not there."""
    toks = parse(path)
    if not toks:
        return doc
    par, last = _parent(doc, toks, path), toks[-1]
    if isinstance(par, dict):
        if last not in par:
            raise PatchError(f"{path}: not there")
        return par[last]
    if isinstance(par, list):
        return par[_index(last, len(par), path, False)]
    raise PatchError(f"{path}: its parent is not an object or an array")


class _Doc:
    """The document being patched, and how to undo what was done to it."""

    def __init__(self, doc: dict):
        self.doc, self.undo, self.changes = doc, [], []

    def add(self, path: str, value, op: str = "add", record: bool = True) -> None:
        toks = parse(path)
        said, value = value, copy.deepcopy(value)          # the document holds its own copy; history, what was said
        if not toks:
            if not isinstance(value, dict):
                raise PatchError("the whole document is an object: it cannot be replaced by " + type(value).__name__)
            was = dict(self.doc)
            self.doc.clear()
            self.doc.update(value)
            self.undo.append(lambda: (self.doc.clear(), self.doc.update(was)))
            if record:
                self.changes.append((op, "", was, said))
            return
        par, last = _parent(self.doc, toks, path), toks[-1]
        if isinstance(par, dict):
            had = par.get(last, _ABSENT)
            par[last] = value
            self.undo.append(lambda: par.pop(last) if had is _ABSENT else par.__setitem__(last, had))
            if record:
                self.changes.append(("replace" if had is not _ABSENT and op == "add" else op, pointer(*toks),
                                     None if had is _ABSENT else had, said))
        elif isinstance(par, list):
            i = _index(last, len(par), path, True)
            par.insert(i, value)
            self.undo.append(lambda: par.pop(i))
            if record:
                self.changes.append((op, pointer(*toks[:-1], i), None, said))
        else:
            raise PatchError(f"{path}: its parent is not an object or an array")

    def remove(self, path: str, op: str = "remove", record: bool = True):
        toks = parse(path)
        if not toks:
            raise PatchError("the whole document cannot be removed")
        par, last = _parent(self.doc, toks, path), toks[-1]
        if isinstance(par, dict):
            if last not in par:
                raise PatchError(f"{path}: not there")
            was = par.pop(last)
            self.undo.append(lambda: par.__setitem__(last, was))
            at = pointer(*toks)
        elif isinstance(par, list):
            i = _index(last, len(par), path, False)
            was = par.pop(i)
            self.undo.append(lambda: par.insert(i, was))
            at = pointer(*toks[:-1], i)
        else:
            raise PatchError(f"{path}: its parent is not an object or an array")
        if record:
            self.changes.append((op, at, was, None))
        return was

    def replace(self, path: str, value) -> None:
        toks = parse(path)
        if not toks:
            self.add(path, value, "replace")
            return
        get(self.doc, path)                              # it must be there
        par, last = _parent(self.doc, toks, path), toks[-1]
        if isinstance(par, list):
            i = _index(last, len(par), path, False)
            was = par[i]
            par[i] = copy.deepcopy(value)
            self.undo.append(lambda: par.__setitem__(i, was))
            self.changes.append(("replace", pointer(*toks[:-1], i), was, value))
        else:
            self.add(path, value, "replace")

    def rollback(self) -> None:
        for u in reversed(self.undo):
            u()


def _need(o: dict, key: str, i: int):
    if key not in o:
        raise PatchError(f"operation {i}: {o.get('op')} needs {key!r}")
    return o[key]


def apply(doc: dict, ops) -> list[tuple]:
    """Apply ``ops`` to ``doc`` in place, all or none. Returns the changes made, in order."""
    if not isinstance(ops, list):
        raise PatchError("a patch is a list of operations")
    d = _Doc(doc)
    try:
        for i, o in enumerate(ops):
            if not isinstance(o, dict):
                raise PatchError(f"operation {i}: an object with op and path")
            op, path = o.get("op"), _need(o, "path", i)
            if op == "add":
                d.add(path, _need(o, "value", i))
            elif op == "remove":
                d.remove(path)
            elif op == "replace":
                d.replace(path, _need(o, "value", i))
            elif op == "move":
                src = _need(o, "from", i)
                if src == path:
                    continue
                if path.startswith(src + "/"):
                    raise PatchError(f"operation {i}: cannot move {src} into its own child {path}")
                d.add(path, d.remove(src, "move"), "move")     # what was removed is out of the document: a copy goes in
            elif op == "copy":
                d.add(path, copy.deepcopy(get(doc, _need(o, "from", i))), "copy")
            elif op == "test":
                want = _need(o, "value", i)
                have = get(doc, path)
                if not equal(have, want):
                    raise PatchError(f"test {path}: is {json.dumps(have, default=str)[:200]}, "
                                     f"not {json.dumps(want, default=str)[:200]}")
            else:
                raise PatchError(f"operation {i}: {op!r} is not an operation ({', '.join(OPS)})")
    except PatchError:
        d.rollback()
        raise
    except (TypeError, ValueError, RecursionError) as e:            # a value JSON cannot hold, a cycle
        d.rollback()
        raise PatchError(f"{type(e).__name__}: {e}") from None
    return d.changes
