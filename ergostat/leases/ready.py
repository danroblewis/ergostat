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
