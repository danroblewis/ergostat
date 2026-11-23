"""What is going through the wires (SPEC §5a, *Which items*): the items a stock counts now, and the items
that went through a flow in a span, as one filter the side panel and the Items page share, so a panel's
list and its link to the Items page are the same set.

A set is a kind, and either the states its items are in now (``state``), or the moves its items made in
a span (``moved``: from some states to others, between two times); either may also match fields
(``where``). It is read from the item index (``items.in_states_page``, ``items.moved_items``): a state's items counted
and paged there, a span's moves read there alone, never every item of a kind folded.

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
    since: float | None = None                                # the span (of moves, or of the process map): after since, up to until
    until: float | None = None
    # the process map's (process.py): through a node, along a line within an item, or along lines from other items
    by: str | None = None                                     # states or events: what the map's nodes are
    through: str | None = None                                # an activity; ^ started, $ ended
    followed: tuple[str, str] | None = None                   # one activity directly followed by the other
    caused: list[tuple[str, str, str]] = field(default_factory=list)   # (cause kind, its activity, this kind's)

    def process(self) -> bool:
        return self.through is not None or self.followed is not None or bool(self.caused)

    def params(self) -> dict[str, list[str]]:
        """The set as the Items page's address and the API's query say it (``/items?kind=pr&state=waiting``)."""
        q: dict[str, list[str]] = {"kind": [self.kind]}
        if self.states:
            q["state"] = [",".join(self.states)]
        if self.where:
            q["where"] = [f"{f}:{v}" for f, vs in self.where.items() for v in vs]
        if self.moved is not None:
            q["moved"] = [",".join(self.moved[0]) + ">" + ",".join(self.moved[1])]
        if self.by:
            q["by"] = [self.by]
        if self.through is not None:
            q["through"] = [self.through]
        if self.followed is not None:
            q["followed"] = [">".join(self.followed)]
        if self.caused:
            q["caused"] = [f"{k}:{a}>{b}" for k, a, b in self.caused]
        if self.moved is not None or self.process():
            q["moved_since"] = [stamp(self.since)]
            q["moved_until"] = [stamp(self.until)]
        return q

    def says(self) -> str:
        """The set in words, as its chip on the Items page says it."""
        out = []
        if self.states:
            out.append("in " + " or ".join(self.states))
        if self.moved is not None:                    # its span is the page's to say, in the reader's own time
            a, b = self.moved
            out.append(f"moved {' or '.join(a)} → {' or '.join(b)}" if a and b else
                       f"entering {' or '.join(b)}" if b else f"leaving {' or '.join(a)}")
        word = {"^": "started", "$": "ended"}
        if self.through is not None:
            out.append(word.get(self.through, "through " + self.through))
        if self.followed is not None:
            a, b = self.followed
            out.append("started, then " + b if a == "^" else a + ", then ended" if b == "$" else f"{a} → {b}")
        if self.caused:
            out.append(" or ".join(f"{b} caused by {a} on a {k}" for k, a, b in self.caused))
        if self.where:
            out.append("where " + ", ".join(f"{f} = {' or '.join(vs)}" for f, vs in self.where.items()))
        return " ".join([self.kind + ("," if out else ""), ", ".join(out)]).strip()

    def move_matches(self, m: dict) -> bool:
        a, b = self.moved or ([], [])
        if not (self.since < m["time"] <= self.until):
            return False
        ok_from = m["from"] in a if a else m["from"] not in b
        ok_to = m["to"] in b if b else m["to"] not in a
        return ok_from and ok_to


def stamp(t: float | None) -> str:
    return datetime.fromtimestamp(t or 0, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    return bool(q.get("where") or one("moved") or "," in (one("state") or "") or one("through") or one("followed")
                or q.get("caused"))


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
    s.by = one("by")
    if s.by is not None and s.by not in ("states", "events"):
        raise BadSet(f"by={s.by}: states or events")
    s.through = one("through")
    fl = one("followed")
    if fl:
        a, sep, b = fl.partition(">")
        if not sep or not a or not b:
            raise BadSet(f"followed={fl}: A>B, two activities (^ the start, $ the end)")
        s.followed = (a, b)
    for c in q.get("caused") or []:
        k, sep, rest = c.partition(":")
        a, sep2, b = rest.partition(">")
        if not sep or not sep2 or not k or not a or not b:
            raise BadSet(f"caused={c}: KIND:A>B, an activity on an item of KIND, and the one it caused here")
        s.caused.append((k, a, b))
    if s.process():
        now = now or time.time()
        s.until = s.until or (when(one("moved_until"), "moved_until") if one("moved_until") else now)
        s.since = s.since or (when(one("moved_since"), "moved_since") if one("moved_since") else s.until - 3600.0)
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
    moved: dict[str, list[float]] = {}
    if s.process():                                       # the process map's node or line: read as the map was
        return _through(events, spec, s, kinds, n, offset)
    if s.moved is None:                                   # counted and paged by the index
        total, page_its = its.in_states_page(events, spec, s.kind, s.states or None, its.typed_too(s.where), until, n, offset)
    else:                                                 # the span's moves, from the index; which count, here
        a, b = s.moved
        key, states = ("to", b) if b else ("from", a)
        got = its.moved_items(events, spec, s.kind, key, states, s.since, s.until, its.typed_too(s.where))
        for i in got:
            if not s.states or i.state in s.states:
                ts = [m["time"] for m in i.moves if s.move_matches(m)]
                if ts:
                    moved[i.id] = ts
        got = sorted((i for i in got if i.id in moved), key=lambda i: -moved[i.id][-1])
        total, page_its = len(got), got[offset:offset + n]
    from .item_systems import kind_systems
    where = kind_systems(spec)
    page = []
    for i in page_its:
        d = its._listed(i, kinds, where)
        if s.moved is not None:
            d["moved_at"] = moved[i.id]
        page.append(d)
    out = {"set": {"says": s.says(), "params": s.params()}, "total": total, "offset": offset, "items": page}
    if s.moved is not None:
        out["moves"] = sum(len(v) for v in moved.values())
    return out


def _through(events, spec, s: ItemSet, kinds: dict, n: int, offset: int) -> dict:
    """The items behind a node or a line of the process map, newest first, each with when (``moved_at``)."""
    from .. import process as pm
    for k, _, _ in s.caused:
        if k not in kinds and k != pm.SCHEDULE:
            raise BadSet(f"caused: no such kind of item as {k}")
    got = pm.items_through(events, spec, s.kind, s.since, s.until, s.by, s.through, s.followed, s.caused or None)
    if s.moved is not None:
        moved = {i.id for i in its.moved_items(events, spec, s.kind, "to" if s.moved[1] else "from",
                                               s.moved[1] or s.moved[0], s.since, s.until, its.typed_too(s.where))}
        got = {k: v for k, v in got.items() if k in moved}
    items = pm._folded(events, spec, s.kind, got)
    rows = sorted((i for i in items.values() if (not s.states or i.state in s.states) and its.matches(i, its.typed_too(s.where))),
                  key=lambda i: -got[i.id][-1])
    from .item_systems import kind_systems
    where = kind_systems(spec)
    page = []
    for i in rows[offset:offset + n]:
        d = its._listed(i, kinds, where)
        d["moved_at"] = got[i.id]
        page.append(d)
    return {"set": {"says": s.says(), "params": s.params()}, "total": len(rows), "offset": offset, "items": page,
            "moves": sum(len(got[i.id]) for i in rows)}


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
        # counting every state, its set is its kind alone: its link says to list the finished too (SPEC §5a)
        return {"set": {**x.params(), **({} if x.states else {"finished": ["show"]})}, "says": x.says(), "how": how}
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
    s = next((x for x in f.sensors.values() if x.commands), None)
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
        if s.commands:
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


def counted_by(spec, kind: str, name: str) -> dict | None:
    """What a stock's or a flow's sensor counts, in plain words, for the first line of its side panel (``says``, and
    ``kind`` when items): the unit alone did not say a stock was items of a kind. None when its sensor reads neither
    items, its stock's changes nor a daemon (``read by daemon NAME``)."""
    if kind == "sensor":                              # one sensor of a part: PART.SENSOR
        s = next((x for x in (spec.sensors() if spec else ()) if f"{x.of.name}.{x.name}" == name), None)
    else:
        part = (spec.flows if kind == "flow" else {**spec.auxiliaries, **spec.stocks}).get(name) if spec else None
        s = next((x for x in (getattr(part, "sensors", None) or {}).values() if x.items or x.changes or x.daemon), None)
    if s is None or not (s.items or s.changes or s.daemon):
        return None
    if s.daemon:
        return {"says": f"Read by daemon {s.daemon}" + (", which sends its readings by itself" if s.push else "")}
    if s.changes:
        st, what = s.changes.get("stock"), s.changes["what"]
        return {"says": f"The change of {st} that its other flows do not account for, rises and falls" if what == "rest"
                else f"Every {'rise' if what == 'rises' else 'fall' if what == 'falls' else 'net change'} of {st}, "
                     f"whatever caused it"}
    q = s.items
    where = "".join(f", where {f} is {' or '.join(vs)}" for f, vs in _where(q.get("where")).items())
    if kind == "flow":
        move = f"entering {q['entering']}" if q.get("entering") else f"leaving {q.get('leaving')}"
        return {"kind": q["kind"], "says": f"Items of kind {q['kind']} {move}{where}"
                + (f", summing their {q['sum']}" if q.get("sum") else "")}
    states = " or ".join(q.get("state") or []) or "any state"
    lead = {"oldest": "The hours the oldest has been in its state, of", "age": "The hours since the oldest was first seen, of"}
    return {"kind": q["kind"], "says": f"{lead.get(q.get('measure'), 'Counts')} items of kind {q['kind']} in state {states}{where}"}


def leased_by(events, spec, flow: str, until: float) -> list[dict]:
    """The blocks that take items (``takes:``, leased one to a run) and move this flow: for its valve's panel, each
    with its kind, how many it holds now, and the Items page's set of exactly those (``leased``, by that block)."""
    from .ir import LEASED, Ref
    out = []
    for b in (spec.blocks.values() if spec else ()):
        if b.takes and Ref("flow", flow) in b.targets():
            x = ItemSet(b.takes.kind, states=[LEASED], where={"lease.block": [b.name]})
            n, _, _ = its.in_states(events, spec, x.kind, x.states, {"lease.block": b.name}, until=until)
            out.append({"block": b.name, "agent": b.agent, "kind": x.kind, "held": n,
                        "set": x.params()})
    return out
