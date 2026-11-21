"""What the dispatcher looks at, kept as the record grows (docs/proposals/scale.md, #5): of each kind of the model's
own, the items a block may take (in a state some block takes from) and the items held under a lease (in any state),
read from the item index once and then only for the items an event since was about. The dispatcher's look and the
watchdog's pass read these instead of every item of every kind, every second, for every block.

The record stays the truth: a new model (another set of kinds or of states taken), a record that went back or was
rolled up (its generation), or a record with no item index on disk, and the items are read whole again (or, without
an index, every look reads them as before)."""

from __future__ import annotations

from ..spec import items as its
from ..spec.itemindex import index_for
from ..spec.items import TRANSCRIPT_TYPES
from .fold import held


class Ready:
    def __init__(self):
        self.key = None                    # what the items were chosen by: the kinds and the states taken from
        self.spec = None                   # the model they were chosen for
        self.ix = None
        self.gen = None
        self.seq = -1
        self.items: dict[str, dict[str, its.Item]] = {}   # kind → id → the item (its fold, without its moves)

    @staticmethod
    def wanted(spec, kinds: list[str], blocks: list) -> dict[str, frozenset[str]]:
        """Kind → the states some block takes its items from."""
        out: dict[str, set[str]] = {k: set() for k in kinds}
        for b in blocks:
            out.setdefault(b.takes.kind, set()).update(b.takes.at)
        return {k: frozenset(v) for k, v in out.items()}

    def keep(self, it, want: dict) -> bool:
        return it.kind in want and (it.state in want[it.kind] or held(it.fields) is not None)

    def follow(self, events, spec, kinds, blocks):
        """Brought up to date with the record; returns the item index (None: there is none, read every item).
        ``kinds`` and ``blocks``: the kinds watched and the blocks that take items, asked for only of a new model."""
        last, gen = events.last_seq(), events.generation() if hasattr(events, "generation") else None
        if spec is self.spec and self.ix is not None and (last, gen) == (self.seq, self.gen):
            return self.ix                                  # nothing new
        want = self.wanted(spec, kinds(), blocks()) if spec is not self.spec or self.key is None else self.want
        key = tuple(sorted(want.items()))
        ix = index_for(events, spec, False)                 # (caught up to ``last`` at least)
        if ix is None:
            self.key = self.spec = self.ix = None
            return None
        with ix.lock:
            if key != self.key or gen != self.gen or ix is not self.ix:     # (another index: kinds that fold otherwise)
                self.items = {k: {} for k in want}
                for k in want:
                    if k in spec.items:
                        for it in ix.items(k, moves=False):
                            if self.keep(it, want):
                                self.items[k][it.id] = it
            elif last != self.seq:
                ids = {e["item"] for e in events.of_items(None, after_seq=self.seq, skip=(TRANSCRIPT_TYPES,))
                       if e["seq"] <= last}
                for k in self.items.values():
                    for i in ids:
                        k.pop(i, None)
                for it in ix.items(None, ids=ids, moves=False) if ids else []:
                    if self.keep(it, want):
                        self.items[it.kind][it.id] = it
            self.key, self.gen, self.seq, self.spec, self.ix, self.want = key, gen, last, spec, ix, want
        return ix

    def of(self, kind: str) -> list:
        """A kind's items kept, the latest first (as ``items.project`` lists them)."""
        return sorted(self.items.get(kind, {}).values(), key=lambda i: -i.last)


def unblocked(d, b, got: list) -> list:
    """The hook for ``takes: {unblocked: true}`` (SPEC §9.5): of the items a block may take (``Dispatcher.ready``, in
    its order), those whose precedence relations name only finished items, the critical first
    (``precedence.order_ready``). Any other block's are as they were."""
    if not got or not getattr(b.takes, "unblocked", False):
        return got
    import time

    from ..precedence import order_ready
    return order_ready(d.p.events, d.spec, b.takes.kind, got, time.time())


def order_key(v, down: bool = False) -> tuple:
    """A field's value as ``takes: {order: FIELD}`` sorts it (SPEC §9.5): numbers, then text, then nothing (last
    either way); ``down`` (``-FIELD``): the highest first."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (0, -float(v) if down else float(v), ())
    if v is None or v == "":
        return (2, 0.0, ())
    return (1, 0.0, tuple(-ord(c) for c in str(v)) + (1,) if down else tuple(ord(c) for c in str(v)))


def take_key(order: list[str], at: list[str], state: str, fields: dict, critical: float = 0.0) -> tuple:
    """Where an item stands in a block's queue (SPEC §9.5), the one comparator of the dispatcher and the completion
    estimates: by its ``order:`` fields, then the states of ``at`` in order, then the critical first; the caller's
    order (oldest first) among equals."""
    return (tuple(order_key(fields.get(f.lstrip("-")), f.startswith("-")) for f in order or ()),
            at.index(state) if state in at else len(at), critical)


def ordered(b, got: list) -> list:
    """The items a block may take (oldest first, or the critical first: ``unblocked``), in its take order."""
    return sorted(got, key=lambda i: take_key(b.takes.order, b.takes.at, i.state, i.fields)) if got else got
