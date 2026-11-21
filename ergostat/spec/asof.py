"""The item index as it stood at a past moment (SPEC §5a, *Relations*): what the Items page's Graph and Timeline read
at a moment travelled to (``precedence.build(..., until=)``). The same reads as the index's (``items``, ``count``,
``links_from``, ``links_to``, ``left``, ``stays``), each answered as of ``until``: an event at ``until`` counts as
before it, as everywhere (``EventStore.query(until=)``, ``Index.late``)."""

from __future__ import annotations

from . import items as its
from .items import TRANSCRIPT_TYPES, Item, fold, kind_of
from .relations import links_of


class AsOf:
    """The index ``ix`` as it stood at ``until``, for one build (nothing is kept past it).

    **Per item**, while few items changed since (``items.late_cap``): each read takes the index's rows of items with
    nothing after ``until``, then reads the late set (items with an event after it) again. Each late item is folded
    from the record up to ``until`` (one with no event by then was not there: it is absent), and it replaces its rows
    and the links it holds. Rows first, the late set after: an item another process changes after the rows were read
    is in the late set by then, and its row is not used. The index's lock, held across the build, covers this
    process's threads; that order covers other processes (tests/test_relations_asof.py puts a write between the
    two). A count whose late set grew while it was read is read again.

    **Whole**, once the late set holds more than the cap: every item of the record up to ``until`` is folded
    (``items.fold_all``), and every later read is answered from that, links by each item's kind's relations; the
    index's rows are not read again. What was answered before was already as of ``until``.

    A kind's finished states (``left``) are judged from the record now, as on the page now."""

    def __init__(self, ix, events, spec, until: float):
        self.ix, self.events, self.spec, self.until = ix, events, spec, until
        self.lock = ix.lock
        self.late_ids: set[str] = set()              # every id seen late, with or without an event by ``until``
        self.folded: dict[str, Item] = {}            # those of them that were there at ``until``, folded to then
        self.whole: dict[str, Item] | None = None    # the whole mode: every item at ``until``
        self._links: dict[str, list[tuple[str, str]]] = {}
        with ix.lock:
            self.cap = its.late_cap(ix)
            self._late()

    # ---- the steps of a read

    def _between(self, op: str) -> None:
        """Between a read of the index's rows (``op``: items, links_from, links_to, count) and the late set's: nothing
        (a test puts a competing write here)."""

    def _late(self) -> bool:
        """The late set read again, and the ids new in it folded to ``until``; True when it gained one."""
        ids = set(self.ix.late(self.until, limit=self.cap + 1))
        if len(ids | self.late_ids) > self.cap:
            self.whole = {i.id: i for i in its.fold_all(self.events, self.spec, None, self.until, self.ix.transcript)}
            return False
        new = ids - self.late_ids
        skip = () if self.ix.transcript else (TRANSCRIPT_TYPES,)
        for i in sorted(new):
            evs = self.events.query(n=None, item=i, until=self.until, skip=skip)
            if evs:
                self.folded[i] = fold(i, evs, kind_of(self.spec, i), transcript=self.ix.transcript)
        self.late_ids |= new
        return bool(new)

    def _rows(self, op: str, read, again=lambda rows: False):
        """``read()`` of the index's rows, then the late set (read again when it gained an id and ``again(rows)``);
        None once the whole mode answers."""
        while self.whole is None:
            rows = read()
            self._between(op)
            if not self._late() or not again(rows):
                if self.whole is None:
                    return rows
        return None

    def _pool(self, rows) -> dict[str, Item]:
        return self.whole if rows is None else self.folded       # type: ignore[return-value]

    def _links_of(self, it: Item) -> list[tuple[str, str]]:
        if it.id not in self._links:
            self._links[it.id] = links_of(self.spec.items.get(it.kind or ""), it.fields)
        return self._links[it.id]

    # ---- the index's reads, as of ``until``

    def items(self, kind: str | None = None, states=None, n: int | None = None, ids=None, **_) -> list[Item]:
        ids = None if ids is None else set(ids)
        rows = self._rows("items", lambda: self.ix.items(kind, states, until=self.until, n=n, ids=ids),
                          lambda r: n is not None and len(r) >= n)
        got = [i for i in self._pool(rows).values() if _wanted(i, kind, states, ids)]
        got += [r for r in rows or [] if r.id not in self.late_ids]
        got.sort(key=lambda i: -i.last)
        return got if n is None else got[:n]

    def count(self, kind: str | None, states=None) -> int:
        rows = self._rows("count", lambda: self.ix.count(kind, states, until=self.until), lambda _: True)
        return (rows or 0) + sum(1 for i in self._pool(rows).values() if _wanted(i, kind, states, None))

    def links_from(self, ids) -> list[tuple[str, str, str]]:
        ids = list(ids)
        rows = self._rows("links_from", lambda: self.ix.links_from(ids))
        pool = self._pool(rows)
        out = [x for x in rows or [] if x[0] not in self.late_ids]
        return out + [(i, r, t) for i in ids if i in pool for r, t in self._links_of(pool[i])]

    def links_to(self, ids) -> list[tuple[str, str, str]]:
        want = set(ids)
        rows = self._rows("links_to", lambda: self.ix.links_to(list(want)))
        out = [x for x in rows or [] if x[0] not in self.late_ids]
        return out + [(i, r, t) for i, it in self._pool(rows).items() for r, t in self._links_of(it) if t in want]

    def left(self, kind: str) -> set[str]:
        return self.ix.left(kind)

    def stays(self, kind: str, most: int = 2000, finished=()):
        return self.ix.stays(kind, most, finished, until=self.until)


def _wanted(it: Item, kind: str | None, states, ids) -> bool:
    """Whether a folded item is one a read of the index asks for (as ``Index._where``: ``""`` is no kind, no state)."""
    return ((kind is None or (it.kind or "") == kind) and (ids is None or it.id in ids)
            and (states is None or (it.state or "") in [s or "" for s in states]))
