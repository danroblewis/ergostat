"""What an item is labelled by, for a filter or a group: its state, or a low-cardinality field. A state is a column;
a field is read from the documents once per version of the index."""

from __future__ import annotations

import threading

from ..spec import codec

MOST_ITEMS = 20_000         # documents one kind's field is read from (its latest)
NONE = "none"
KEPT_MOST = 16              # fields kept read
_KEPT: dict[tuple, dict] = {}
_LOCK = threading.Lock()


def word(v) -> str:
    """A field's value as a label."""
    if v is None:
        return NONE
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v) if isinstance(v, str | int | float) else "many"


def states(ix, kind: str) -> dict[int, str]:
    """Each of ``kind``'s items' state now, by rid."""
    k = ix.known(kind)
    rows = ix.guard(lambda: ix.db.execute("select rid, state from items where kind = ?", (k,)).fetchall())
    return {r: ix.name(s) or NONE for r, s in rows}


def field(ix, kind: str, name: str) -> dict[int, str]:
    """Each of ``kind``'s latest items' ``name`` as a label, by rid; read once per version of the index (an event
    dated before an item's newest can still change a field, so what changed cannot be told by its time)."""
    k = ix.known(kind)

    def read():
        key = (str(ix.path), ix._meta("epoch"), ix.seq, k, name)
        with _LOCK:
            got = _KEPT.get(key)
        if got is None:
            rows = ix.db.execute("select rid, body from items where kind = ? order by last desc limit ?",
                                 (k, MOST_ITEMS)).fetchall()
            got = {rid: word(codec.unpack(body)["f"].get(name)) for rid, body in rows}
            with _LOCK:
                while len(_KEPT) >= KEPT_MOST:
                    _KEPT.pop(next(iter(_KEPT)))
                _KEPT[key] = got
        return got
    return ix.guard(read)


def labeller(ix, kind: str, name: str):
    """rid -> label, for ``state``, ``kind`` or a field."""
    if name == "kind":
        return lambda _rid: kind
    got = states(ix, kind) if name == "state" else field(ix, kind, name)
    return lambda rid: got.get(rid, NONE)


def allowed(ix, kind: str, where: tuple):
    """rid -> whether the item passes the filter ``where`` (``((name, values), ...)``), or None when there is none."""
    if not where:
        return None
    tests = [(labeller(ix, kind, name), set(vals)) for name, vals in where]
    return lambda rid: all(f(rid) in vals for f, vals in tests)
