"""Items (SPEC §5a): the record projected into things with an id, a kind, a state and fields.

An item is every event about one id (``github/pull_request/4231``), replayed in order: each event's
``data`` is merged into the item's fields (last write wins), and an event whose type the kind maps
to a state moves the item to that state. An item starts in its kind's first state. Ids have a
``/`` in them; ergostat's own events, which are about parts (``inbox-short``), never do, so the two
never mix.

A stock may be measured by counting items (in some states, matching some fields), and a flow by
the rate at which items enter or leave a state: the record is the instrument."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .ir import ItemKind, Sensor, Spec


@dataclass
class Item:
    id: str
    kind: str | None
    state: str | None = None
    fields: dict = field(default_factory=dict)
    first: float = 0.0
    last: float = 0.0
    entered: float = 0.0             # when it came into its state
    n: int = 0
    latest: str = ""                 # the latest event's type
    moves: list[dict] = field(default_factory=list)   # {time, from, to, event, type}

    def as_dict(self, moves: bool = False) -> dict:
        d = {"id": self.id, "kind": self.kind, "state": self.state, "fields": self.fields, "first": self.first,
             "last": self.last, "entered": self.entered, "events": self.n, "latest": self.latest}
        if moves:
            d["moves"] = self.moves
        return d


def kind_of(spec: Spec, id: str) -> ItemKind | None:
    return next((k for k in spec.items.values() if k.matches(id)), None)


def fold(id: str, events: list[dict], kind: ItemKind | None) -> Item:
    """One item from its events, oldest first."""
    it = Item(id, kind.name if kind else None)
    for e in events:
        if not it.n:
            it.first = e["time"]
            if kind and kind.states:                 # it arrives: a move into its first state, counted like any other
                it.state, it.entered = kind.states[0], e["time"]
                it.moves.append({"time": e["time"], "from": None, "to": it.state, "event": e["id"], "type": e["type"]})
        it.n += 1
        it.last = e["time"]
        it.latest = e["type"]
        it.fields.update(e.get("data") or {})
        to = kind.on.get(e["type"]) if kind else None
        if to and to != it.state:
            it.moves.append({"time": e["time"], "from": it.state, "to": to, "event": e["id"], "type": e["type"]})
            it.state, it.entered = to, e["time"]
    return it


def project(events, spec: Spec, kind: str | None = None, until: float | None = None) -> list[Item]:
    """Every item (of ``kind``, when given) as it stood at ``until``, the latest first."""
    kinds = [spec.items[kind]] if kind else list(spec.items.values())
    if kind and not kinds:
        return []
    globs = [k.id for k in kinds] if kind else None
    by: dict[str, list[dict]] = {}
    for e in events.of_items(globs, until=until):
        by.setdefault(e["item"], []).append(e)
    out = []
    for id, evs in by.items():
        k = kind_of(spec, id)
        if kind and (k is None or k.name != kind):
            continue
        out.append(fold(id, evs, k))
    return sorted(out, key=lambda i: -i.last)


def one(events, spec: Spec, id: str) -> Item | None:
    evs = events.query(n=None, item=id)
    return fold(id, evs, kind_of(spec, id)) if evs else None


def matches(it: Item, where: dict) -> bool:
    for k, want in where.items():
        have = it.fields.get(k)
        wants = want if isinstance(want, list) else [want]
        if not any(str(have) == str(w) for w in wants):
            return False
    return True


def measure(events, spec: Spec, s: Sensor, now: float | None = None) -> tuple[float | None, str]:
    """A sensor that counts items: a stock's count (or its oldest item's age in hours), or a flow's
    rate per hour of items entering or leaving a state."""
    q = s.items or {}
    now = now or time.time()
    its = [i for i in project(events, spec, q["kind"], until=now) if matches(i, q.get("where") or {})]
    if s.of.kind == "stock":
        states = q.get("state")
        inside = [i for i in its if not states or i.state in states]
        if q.get("measure") == "oldest":
            return (max((now - i.entered) / 3600 for i in inside) if inside else 0.0), ""
        return float(len(inside)), ""
    over = q.get("over") or 3600.0
    since = now - over
    key, state = ("to", q["entering"]) if q.get("entering") else ("from", q.get("leaving"))
    n = sum(1 for i in its for m in i.moves if m[key] == state and since < m["time"] <= now)
    return n * 3600.0 / over, ""


def glob_ok(pattern: str) -> bool:
    return "/" in pattern and not pattern.startswith("/")


def kinds_of(spec) -> dict:
    return getattr(spec, "items", None) or {}


def listing(events, spec, kind: str | None = None, state: str | None = None, until: float | None = None,
            n: int = 500) -> dict:
    """What the Items page and ``ergostat item`` show: each kind with its count per state, and
    the items themselves (newest first), filtered by kind and state."""
    kinds = kinds_of(spec)
    if spec is None or not kinds:
        its = [fold(i["item"], events.query(n=None, item=i["item"], until=until), None) for i in events.items()[:n]]
    else:
        its = project(events, spec, until=until)
    counts: dict[str, dict[str, int]] = {}
    for i in its:
        c = counts.setdefault(i.kind or "", {})
        c[i.state or ""] = c.get(i.state or "", 0) + 1
    shown = [i for i in its if (kind is None or (i.kind or "") == kind) and (state is None or (i.state or "") == state)]
    return {"kinds": [{"name": k.name, "id": k.id, "states": k.states, "show": k.show, "formats": k.formats,
                       "description": k.description,
                       "counts": counts.get(k.name, {})} for k in kinds.values()],
            "unkinded": sum(counts.get("", {}).values()),
            "total": len(shown),
            "items": [i.as_dict() for i in shown[:n]]}


def detail(events, spec, id: str, until: float | None = None) -> dict | None:
    evs = events.query(n=None, item=id, until=until)
    if not evs:
        return None
    k = kind_of(spec, id) if kinds_of(spec) else None
    it = fold(id, evs, k)
    return {**it.as_dict(moves=True),
            "kind_of": {"name": k.name, "id": k.id, "states": k.states, "on": k.on, "show": k.show, "formats": k.formats}
            if k else None,
            "record": evs[-500:]}
