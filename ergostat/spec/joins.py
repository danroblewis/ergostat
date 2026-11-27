"""A parent moved on by its children (SPEC §5a, *Join*): fork-join as a rule on the parent's projection, over the relation
its children name it by.

```yaml
projections:
  epic:
    states: [planned, underway, shipped]
    join:
      - {children: parent, any: [doing, review, done], to: underway}   # the first ticket started
      - {children: parent, all: done, to: shipped}                      # every ticket done
  ticket:
    relations: {parent: epic}
```

- **When.** On each move of an item of a projection whose relation names the parent's kind, read from the item index (its
  moves, followed by row; its links, both ways), and once for every parent when ergostat starts: what moved while it
  was stopped is joined then. The engine looks each time its loop wakes on a write (``notify.py``): no clock.
- **What.** A parent with children, all (or any) of them in the states, in a state before ``to`` in its projection's order,
  is moved there by ``ergostat.item.joined`` (caused by the latest move of its children), folded like any move and so
  counted like any other (``entering``). Never backwards: a child reopened leaves its parent where it is."""

from __future__ import annotations

from .ir import DEAD, LEASED, Join
from .items import JOINED
from .load import Problem

JOIN_KEYS = {"children", "all", "any", "to"}
SIDE = ("cancelled", "canceled", "closed", "abandoned", "rejected", "dropped", "dismissed", "wontfix")   # an exit
SOURCE = "ergostat"


def compile_join(c, m, what: str) -> list[Join]:
    raw = m.get("join")
    if raw is None:
        return []
    out = []
    for i, r in enumerate(raw if isinstance(raw, list) else [raw]):
        w = f"{what}.join" + (f"[{i}]" if isinstance(raw, list) else "")
        if not isinstance(r, dict):
            c.err(f"{w}: a map: children: (the relation its children name it by), all: or any: (their states), to: "
                  f"(where it goes)", m.at("join"), "not-a-map")
            continue
        c.keys(r, JOIN_KEYS, w)
        states = r.get("all") if r.get("all") is not None else r.get("any")
        states = [states] if isinstance(states, str) else states
        ok = isinstance(r.get("children"), str) and isinstance(r.get("to"), str)
        if not ok or (r.get("all") is None) == (r.get("any") is None) or not isinstance(states, list) or not states \
                or not all(isinstance(x, str) for x in states):
            c.err(f"{w}: children: (a relation), all: or any: (a state or a list, one of the two) and to: (a state): "
                  f"{{children: parent, all: done, to: shipped}}", m.at("join"), "bad-join")
            continue
        out.append(Join(r["children"], list(states), r["to"], r.get("all") is not None))
    return out


def check_joins(c, spec) -> None:
    """Once every projection is known: each join's relation is one some projection names it by, its states are those kinds', and
    its ``to`` is its own."""
    for k in spec.items.values():
        good = []
        for j in k.join:
            w = f"projection {k.name}.join"
            kids = [x for x in spec.items.values() if j.children in x.relations and k.name in x.relations[j.children].kinds]
            if not kids:
                c.err(f"{w}: no projection names {k.name} by a relation {j.children!r} (relations: {{{j.children}: {k.name}}} on "
                      f"its children's projection)", k.where, "bad-join")
            elif j.to not in k.states:
                c.err(f"{w}.to: {j.to!r} is not a state of {k.name} ({', '.join(k.states) or 'it has none'})", k.where,
                      "unknown-state")
            elif bad := [s for s in j.states if not any(s in x.states for x in kids)]:
                c.err(f"{w}: {', '.join(map(repr, bad))} not a state of {', '.join(x.name for x in kids)}", k.where,
                      "unknown-state")
            else:
                good.append(j)
        k.join = good
        if good:                                        # a side state before a join's to: is moved on from too
            last = max(k.states.index(j.to) for j in good)
            done = set((getattr(getattr(spec, "messages", None), "done", None) or {}).get(k.name) or ())
            side = [x for x in k.states[:last] if x not in {j.to for j in good} | {LEASED, DEAD}
                    and (x in done or x in SIDE)]
            if side:
                c.problems.append(Problem(
                    "finding", f"projection {k.name}.join: a join moves an item on from any state before its to:, so "
                    f"{', '.join(side)} (before {k.states[last]} in states:) would be moved on too; if "
                    f"{'they are' if len(side) > 1 else 'it is'} a side state (cancelled), list it after {k.states[last]}",
                    k.where, "join-side-state", f"projections.{k.name}"))


class Joins:
    """The joins of the engine's model, looked at each time its loop wakes."""

    def __init__(self, eng):
        self.e = eng
        self.ix = self.epoch = None
        self.mv: int | None = None                      # the last move looked at (None: look at every parent)
        self.top = -1

    def look(self) -> None:
        spec = self.e.spec
        if not any(k.join and self.e.own(f"projection.{k.name}", spec) for k in spec.items.values()):
            return                                      # (no join of its shard's: none looked at)
        top = self.e.p.events.last_seq()
        if top == self.top:
            return
        self.top = top
        from .itemindex import index_for
        ix = index_for(self.e.p.events, spec, False)
        if ix is None:
            return
        with ix.lock:
            todo = ix.guard(lambda: self._look(ix, spec))
        for parent, to, cause, data in todo:
            self.e.p.events.add(JOINED, item=parent, source=SOURCE, causedby=cause, data={"joined": {"to": to, **data}})
            self.e.say(f"{parent}: {to}, joined by its {data['n']} children ({'all' if 'all' in data else 'any'} "
                       f"{', '.join(data.get('all') or data.get('any'))})")

    def _look(self, ix, spec) -> list[tuple]:
        db = ix.db
        epoch = ix._meta("epoch")
        if ix is not self.ix or epoch != self.epoch:   # (a new index, or one made again: every parent once)
            self.ix, self.epoch, self.mv = ix, epoch, None
        top = db.execute("select coalesce(max(rowid), 0) from moves").fetchone()[0]
        kinds = {k.name: k for k in spec.items.values() if k.join and self.e.own(f"projection.{k.name}", spec)}   # (SPEC §9.8)
        if self.mv is None:
            parents = [i.id for kn in kinds for i in ix.items(kn, moves=False)]
        else:                                           # the parents of the children that moved since
            rels = {j.children for k in kinds.values() for j in k.join}
            kids = [x for x in (ix.known(c.name) for c in spec.items.values() if rels & set(c.relations)) if x != -1]
            moved = [r[0] for r in db.execute(f"select distinct i.id from moves m join items i on i.rid = m.rid where "
                                              f"m.rowid > ? and m.kind in ({','.join('?' * len(kids))})", (self.mv, *kids))]
            parents = sorted({d for _, r, d in ix.links_from(moved) if r in rels})
        self.mv = top
        out = []
        for p in ix.items(ids=parents, moves=False) if parents else []:
            k = kinds.get(p.kind)
            state = p.state
            for j in k.join if k else ():
                if state == j.to or (state in k.states and k.states.index(state) > k.states.index(j.to)):
                    continue                            # only forward
                kids = [a for a, r, _ in ix.links_to([p.id]) if r == j.children]
                if not kids:
                    continue
                got = {i.id: i for i in ix.items(ids=kids, moves=False)}
                ins = [x in got and got[x].state in j.states for x in kids]
                if not (all(ins) if j.all else any(ins)):
                    continue
                cause = db.execute(f"select m.event from moves m join items i on i.rid = m.rid where i.id in "
                                   f"({','.join('?' * len(got))}) order by m.t desc, m.rowid desc limit 1", list(got)).fetchone()
                out.append((p.id, j.to, cause[0] if cause else None,
                            {"children": j.children, "all" if j.all else "any": j.states, "n": len(kids)}))
                state = j.to
        return out
