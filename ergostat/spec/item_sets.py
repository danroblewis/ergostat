"""What is going through the wires (SPEC §5a, *Which items*): the items a stock counts now, and the items
that went through a flow in a span, as one filter the side panel and the Items page share, so a panel's
list and its link to the Items page are the same set.

A set is a kind, and either the states its items are in now (``state``), or the moves its items made in
a span (``moved``: from some states to others, between two times); either may also match fields
(``where``). It is read through ``items.project`` (the listing's own projection), never from the record
directly, so whatever keeps the items (the kept fold; an index on disk) serves it too.

What a part's set is comes from the model alone (``of_part``): a stock's (or an auxiliary's) ``items:``
sensor; a flow's own ``items:`` sensor, else the item states of the stocks it drains and fills; else the
events that measure it (its valve's openings, its sensor's observations); else nothing, said with why."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from . import items as its

SHOWN = 10                         # the items a side panel lists; the rest are on the Items page
OPENINGS = 300                     # the most openings (or observations) of a flow read for its items


class BadSet(ValueError):
    """A filter that is not one: said to whoever asked."""


@dataclass
class ItemSet:
    kind: str
    states: list[str] = field(default_factory=list)          # in one of these now (none: any)
    where: dict[str, list[str]] = field(default_factory=dict)  # field: any of these values
    moved: tuple[list[str], list[str]] | None = None          # from these states to these (one side empty: any other)
    since: float | None = None                                # the moves' span: after since, up to until
    until: float | None = None

    def params(self) -> dict[str, list[str]]:
        """The set as the Items page's address and the API's query say it (``/items?kind=pr&state=waiting``)."""
        q: dict[str, list[str]] = {"kind": [self.kind]}
        if self.states:
            q["state"] = [",".join(self.states)]
        if self.where:
            q["where"] = [f"{f}:{v}" for f, vs in self.where.items() for v in vs]
        if self.moved is not None:
            q["moved"] = [",".join(self.moved[0]) + ">" + ",".join(self.moved[1])]
            q["moved_since"] = [stamp(self.since)]
            q["moved_until"] = [stamp(self.until)]
        return q

    def says(self) -> str:
        """The set in words, as its chip on the Items page says it."""
        out = []
        if self.states:
            out.append("in " + " or ".join(self.states))
        if self.moved is not None:
            a, b = self.moved
            out.append(f"moved {' or '.join(a) or 'from elsewhere'} → {' or '.join(b) or 'elsewhere'}, "
                       f"{clock(self.since)} to {clock(self.until)}")
        if self.where:
            out.append("where " + ", ".join(f"{f} = {' or '.join(vs)}" for f, vs in self.where.items()))
        return " ".join([self.kind, ", ".join(out)]).strip()

    def move_matches(self, m: dict) -> bool:
        a, b = self.moved or ([], [])
        if not (self.since < m["time"] <= self.until):
            return False
        ok_from = m["from"] in a if a else m["from"] not in b
        ok_to = m["to"] in b if b else m["to"] not in a
        return ok_from and ok_to


def stamp(t: float | None) -> str:
    return datetime.fromtimestamp(t or 0, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def clock(t: float | None) -> str:
    return datetime.fromtimestamp(t or 0, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def when(text: str, what: str) -> float:
    """A time in an address: ISO 8601 (``2026-11-18T10:00:00Z``; no zone is UTC) or seconds since the epoch."""
    try:
        return float(text)
    except ValueError:
        pass
    try:
        d = datetime.fromisoformat(text.strip().replace(" ", "T"))
    except ValueError:
        raise BadSet(f"{what}: a time, as 2026-11-18T10:00:00Z or seconds since 1970") from None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp()


def asked(q: dict) -> bool:
    """Whether an Items query asks for a set the plain listing does not serve: matching fields, a move in a
    span, or more than one state."""
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    return bool(q.get("where") or one("moved") or "," in (one("state") or ""))


def parse(q: dict, now: float | None = None) -> ItemSet | None:
    """The set an Items query names (``kind``, ``state``, ``where``, ``moved`` with ``moved_since`` and
    ``moved_until``), or None when it names no kind and nothing else."""
    one = lambda k: (q.get(k) or [None])[0]       # noqa: E731
    kind = one("kind")
    if not kind:
        if asked(q):
            raise BadSet("a filter on state, where or moved needs kind=")
        return None
    s = ItemSet(kind, states=[x for x in (one("state") or "").split(",") if x])
    for w in q.get("where") or []:
        f, sep, v = w.partition(":")
        if not sep or not f:
            raise BadSet(f"where={w}: field:value")
        s.where.setdefault(f, []).append(v)
    mv = one("moved")
    if mv:
        a, sep, b = mv.partition(">")
        if not sep or not (a or b):
            raise BadSet(f"moved={mv}: FROM>TO, states joined by commas; one side may be empty")
        s.moved = ([x for x in a.split(",") if x], [x for x in b.split(",") if x])
        now = now or time.time()
        s.until = when(one("moved_until"), "moved_until") if one("moved_until") else now
        s.since = when(one("moved_since"), "moved_since") if one("moved_since") else s.until - 3600.0
    return s


def select(events, spec, s: ItemSet, until: float | None = None, n: int = its.LISTED, offset: int = 0) -> dict:
    """The items of a set, as the Items list shows them (newest first; a move's set by its latest move in
    the span), ``n`` from ``offset``: how many (``total``), and for a move's set how many moves (``moves``)
    and each item's (``moved_at``, oldest first)."""
    kinds = its.kinds_of(spec)
    k = kinds.get(s.kind)
    if k is None:
        raise BadSet(f"kind={s.kind}: no such kind of item")
    bad = [x for x in [*s.states, *((s.moved or ([], []))[0]), *((s.moved or ([], []))[1])] if x not in k.states]
    if bad:
        raise BadSet(f"{s.kind} has no state {', '.join(bad)} (its states: {', '.join(k.states) or 'none'})")
    got = its.project(events, spec, s.kind, until=until, fields=tuple(s.where) + tuple(k.show))
    got = [i for i in got if (not s.states or i.state in s.states) and its.matches(i, s.where)]
    moved: dict[str, list[float]] = {}
    if s.moved is not None:
        for i in got:
            ts = [m["time"] for m in i.moves if s.move_matches(m)]
            if ts:
                moved[i.id] = ts
        got = sorted((i for i in got if i.id in moved), key=lambda i: -moved[i.id][-1])
    from .item_systems import kind_systems
    where = kind_systems(spec)
    page = []
    for i in got[offset:offset + n]:
        d = its._listed(i, kinds, where)
        if s.moved is not None:
            d["moved_at"] = moved[i.id]
        page.append(d)
    out = {"set": {"says": s.says(), "params": s.params()}, "total": len(got), "offset": offset, "items": page}
    if s.moved is not None:
        out["moves"] = sum(len(v) for v in moved.values())
    return out


# --- a part's set: what the model says its items are


def _items_sensor(part):
    return next((x for x in (getattr(part, "sensors", None) or {}).values() if x.items), None)


def _stock_set(spec, name: str):
    """The states and fields a stock's (or an auxiliary's) ``items:`` sensor counts: (sensor, kind, states,
    where), or None."""
    part = spec.stocks.get(name) or spec.auxiliaries.get(name)
    s = _items_sensor(part) if part is not None else None
    if s is None:
        return None
    k = spec.items.get(s.items["kind"])
    return s, s.items["kind"], list(s.items.get("state") or (k.states if k else [])), _where(s.items.get("where"))


def _where(w) -> dict[str, list[str]]:
    return {str(f): [str(x) for x in (v if isinstance(v, list) else [v])] for f, v in (w or {}).items()}


def of_part(spec, kind: str, name: str, since: float, until: float, model=None) -> dict:
    """What a part's items are: ``{"set": params, "says", "how"}`` for a set of items, ``{"events": ...}``
    for a flow measured by events (its valve's openings, its sensor's observations), or ``{"none": why}``."""
    if spec is None:
        return {"none": "the model declares no kinds of item"}
    if kind in ("stock", "auxiliary"):
        got = _stock_set(spec, name)
        if got is None:
            return {"none": _no_items(spec, kind, name)}
        s, k, states, where = got
        x = ItemSet(k, states=list(s.items.get("state") or []), where=where)
        how = f"counted by its sensor {s.name}: the {k} items " + (f"in {' or '.join(states)}" if s.items.get("state") else "in any state")
        if s.items.get("measure") == "oldest":
            how += "; its value is the hours the oldest of them has been in its state"
        return {"set": x.params(), "says": x.says(), "how": how}
    f = spec.flows.get(name)
    if f is None:
        return {"none": "not a stock or a flow"}
    s = _items_sensor(f)
    if s is not None:                                     # its own sensor: exactly what it counts
        q = s.items
        a, b = ([q["leaving"]], []) if q.get("leaving") else ([], [q["entering"]])
        x = ItemSet(q["kind"], where=_where(q.get("where")), moved=(a, b), since=since, until=until)
        verb = f"leaving {q['leaving']}" if q.get("leaving") else f"entering {q['entering']}"
        return {"set": x.params(), "says": x.says(), "how": f"counted by its sensor {s.name}: {q['kind']} items {verb}"}
    src = _stock_set(spec, f.source) if f.source else None
    dst = _stock_set(spec, f.target) if f.target else None
    sides = [x for x in (src, dst) if x]
    if sides and len({x[1] for x in sides}) == 1:          # the stocks it moves between count items of one kind
        k = sides[0][1]
        where: dict[str, list[str]] = {}
        for side in sides:
            where.update(side[3])
        a, b = (src[2] if src else []), (dst[2] if dst else [])
        if set(a) & set(b):
            return {"none": f"its stocks {f.source} and {f.target} share a state of {k}, so no move between them is "
                            "only this flow's"}
        x = ItemSet(k, where=where, moved=(a, b), since=since, until=until)
        froms = f"{f.source} ({', '.join(a)})" if src else "outside"
        tos = f"{f.target} ({', '.join(b)})" if dst else "outside"
        return {"set": x.params(), "says": x.says(),
                "how": f"its stocks count {k} items: a move from {froms} to {tos} is one going through it"}
    if sides:
        return {"none": f"its stocks count different kinds of item ({', '.join(sorted({x[1] for x in sides}))})"}
    ev = _events_of(spec, f, model)
    if ev:
        return {"events": ev}
    return {"none": _no_items(spec, "flow", name)}


def _events_of(spec, f, model) -> dict | None:
    """A flow measured by events: the openings of the valve a block moves it by, or what its ``run`` sensor
    observed about items."""
    from .legacy import sensor_name
    v = model.valve_of(f.name) if model is not None and hasattr(model, "valve_of") else None
    if v is not None:
        return {"valve": v.name, "how": f"moved by {v.name}: each opening, and the items the run that opened it was about"}
    s = next((x for x in f.sensors.values() if x.run), None)
    if s is not None:
        return {"source": sensor_name(f.name, s.name),
                "how": f"its sensor {s.name} runs a command: the items it reported seeing, if any"}
    return None


def _no_items(spec, kind: str, name: str) -> str:
    """Why a part has no items: what measures it instead."""
    part = spec.measured("stock" if kind == "auxiliary" and name in spec.stocks else kind).get(name) \
        or spec.auxiliaries.get(name)
    sensors = list((getattr(part, "sensors", None) or {}).values())
    if getattr(part, "rate", None) is not None:
        return "its rate is declared: no items go through it that ergostat can see"
    for s in sensors:
        if s.query:
            return (f"measured by {s.name}, a query against {s.query.get('source', 'a source')}: a number from a metrics "
                    "store, which names no items")
        if s.changes:
            return f"measured by {s.name} from its stock's own readings, which name no items"
        if s.builtin:
            return f"measured by {s.name}, one of ergostat's own measures, which names no items"
        if s.manual:
            return f"read by hand ({s.name}): a reading names no items"
        if s.run:
            return f"measured by {s.name}, a command whose readings name no items"
    if kind == "flow":
        return "nothing measures it with items: it is estimated from what its stocks do"
    return "nothing counts it from items"


def events_items(events, ev: dict, since: float, until: float) -> dict:
    """The openings (or observations) of a flow measured by events, in a span, newest first, each with the
    items its run was about (or the item it observed): ``{"rows": [{time, amount, items, note}], "total"}``."""
    rows = []
    if ev.get("valve"):
        got = events.query(n=OPENINGS, type="valve.opened", item=ev["valve"], since=since, until=until)
        runs: dict[str, list[str]] = {}
        for e in got:
            r = e.get("causedby")
            if r and r not in runs:
                runs[r] = sorted({x["item"] for x in events.caused_by(r) if "/" in (x.get("item") or "")})
        for e in reversed(got):
            if not since < e["time"] <= until:
                continue
            rows.append({"time": e["time"], "amount": (e.get("data") or {}).get("amount", 1),
                         "note": (e.get("data") or {}).get("note"), "items": runs.get(e.get("causedby") or "", [])})
    elif ev.get("source"):
        got = events.query(n=OPENINGS, source=ev["source"], since=since, until=until)
        rows = [{"time": e["time"], "type": e["type"], "items": [e["item"]]} for e in reversed(got)
                if "/" in (e.get("item") or "") and since < e["time"] <= until]
    return {"rows": rows, "total": len(rows)}
