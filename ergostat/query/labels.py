"""What an item is labelled by, for a filter or a group: its state, a low-cardinality field (a group relation's
field among them: a gap's ``milestone``), or its ``state_group``. A state is a column; a field, and a state group, are
read once per version of the index."""

from __future__ import annotations

import threading

from ..spec import codec

MOST_ITEMS = 20_000         # documents one kind's field is read from (its latest)
NONE = "none"
STATE_GROUP = "state_group"     # a label, not a field: an item's stage in its progress (``stage``)
KEPT_MOST = 16              # fields kept read
_KEPT: dict[tuple, dict] = {}
_LOCK = threading.Lock()


def word(v) -> str:
    """A field's value as a label (an empty text is none, as a group's progress reads it)."""
    if v is None or v == "":
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


def stage(ix, kind: str) -> dict[int, str]:
    """Each of ``kind``'s items' ``state_group`` (done, in progress, waiting, stopped; or left, summary, odd: out of
    its group's total), by rid, as its progress per group counts it (``spec/grouptally.py``); read once per version of
    the index (a member's group reads the other kinds' items too: the index's version covers them all)."""
    from ..spec.grouptally import stages
    k = ix.known(kind)

    def read():
        key = (str(ix.path), ix._meta("epoch"), ix.seq, k, STATE_GROUP)
        with _LOCK:
            got = _KEPT.get(key)
        if got is None:
            by_id = stages(ix, ix.spec, kind)
            rows = ix.db.execute("select rid, id from items where kind = ?", (k,)).fetchall()
            got = {rid: by_id.get(i, NONE) for rid, i in rows}
            with _LOCK:
                while len(_KEPT) >= KEPT_MOST:
                    _KEPT.pop(next(iter(_KEPT)))
                _KEPT[key] = got
        return got
    return ix.guard(read)


def labeller(ix, kind: str, name: str):
    """rid -> label, for ``state``, ``kind``, ``state_group`` or a field."""
    if name == "kind":
        return lambda _rid: kind
    got = states(ix, kind) if name == "state" else stage(ix, kind) if name == STATE_GROUP else field(ix, kind, name)
    return lambda rid: got.get(rid, NONE)


def allowed(ix, kind: str, where: tuple):
    """rid -> whether the item passes the filter ``where`` (``((name, values), ...)``), or None when there is none."""
    if not where:
        return None
    tests = [(labeller(ix, kind, name), set(vals)) for name, vals in where]
    return lambda rid: all(f(rid) in vals for f, vals in tests)
