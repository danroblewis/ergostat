"""Items (SPEC §5a): the record projected into things with an id, a kind, a state and fields.

An item is every event about one id (``github/pull_request/4231``), replayed in order: each event is
a changeset folded into the item's document, its ``fields`` (a JSON Patch, a whole new document, or
``data`` folded by the kind's rules: ``changes``), and every change is kept, per path, with the
event that made it (``history``). An event whose type the kind maps to a state moves the item to
that state. An item starts in its kind's first state. Ids have a
``/`` in them; ergostat's own events, which are about parts (``inbox-short``), never do, so the two
never mix.

A stock may be measured by counting items (in some states, matching some fields), and a flow by
the rate at which items enter or leave a state: the record is the instrument."""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field

from ..leases import PREFIX as LEASE_PREFIX
from ..leases import fold as lease_fold
from .changes import fold_event, form_of
from .ir import ItemKind, Sensor, Spec

REOPENED = "ergostat.item.reopened"   # any item moved back, by ergostat, to a state its data names (SPEC §12h)
TRANSCRIPT_TYPES = "claude.*"     # a Claude Code transcript, line by line (transcripts.py): left out unless asked for
SNAPSHOT = "ergostat.item.snapshot"    # an item's older events, folded into one (rollup.py): its document as a set
LISTED = 500                           # the most items one listing carries; page through with offset


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
    changes: list[dict] = field(default_factory=list)  # {time, event, type, form, op, path, before, after, rule}, when kept
    refused: list[dict] = field(default_factory=list)  # {time, event, type, form, why}: changesets that did not apply
    rolled: int = 0                  # a transcript's lines rolled into its snapshot, when they are not folded

    def as_dict(self, moves: bool = False, history: bool = False) -> dict:
        d = {"id": self.id, "kind": self.kind, "state": self.state, "fields": self.fields, "first": self.first,
             "last": self.last, "entered": self.entered, "events": self.n, "latest": self.latest}
        if moves:
            d["moves"] = self.moves
        if history:
            d["history"] = self.history()
            d["refused"] = self.refused
        return d

    def history(self, path: str | None = None) -> dict[str, list[dict]]:
        """Each field's changes, oldest first, keyed by the field (a change deeper in it, at its own
        path, is the field's too); ``""`` for changes to the whole document."""
        out: dict[str, list[dict]] = {}
        for c in self.changes:
            top = field_of(c["path"])
            if path is None or top == path:
                out.setdefault(top, []).append(c)
        return out


def field_of(path: str) -> str:
    """The top-level field a JSON Pointer is in."""
    if not path:
        return ""
    return path[1:].split("/", 1)[0].replace("~1", "/").replace("~0", "~")


def kind_of(spec: Spec, id: str) -> ItemKind | None:
    return next((k for k in spec.items.values() if k.matches(id)), None)


def restore(it: Item, e: dict, history: bool = False, transcript: bool = True) -> None:
    """A snapshot (``rollup.py``): the item as it stood after every event it replaced (it takes the
    place of all of them, so it is the first thing folded). Its document is a ``set``, the whole
    document at once; the rest of what the fold keeps (state, moves, counts, what was refused, each
    field's history summarised) is in its ``rollup``. Where a transcript's lines were rolled up too,
    the fold with them is kept beside the one without (``rollup.transcript``), and a fold that reads
    a transcript takes that one."""
    r = (e.get("data") or {}).get("rollup") or {}
    doc = e.get("set") or {}
    if transcript and r.get("transcript"):
        r = r["transcript"]
        doc = r.get("set") or {}
    it.fields = copy.deepcopy(doc)
    it.moves = [dict(m) for m in r.get("moves") or []]
    it.state, it.entered = r.get("state"), r.get("entered", e["time"])
    it.first, it.last = r.get("first", e["time"]), r.get("last", e["time"])
    it.n, it.latest = r.get("n", 1), r.get("latest", e["type"])
    it.refused = [dict(x) for x in r.get("refused") or []]
    it.rolled = 0 if transcript else (e["data"].get("rollup") or {}).get("lines", 0)
    if history:
        for f, h in (r.get("fields") or {}).items():
            it.changes.append({"time": h["last"]["time"], "event": e["id"], "type": SNAPSHOT, "form": "set", "op": "rolled up",
                               "path": "/" + f.replace("~", "~0").replace("/", "~1") if f else "", "before": None,
                               "after": it.fields.get(f), "count": h["changes"], "first": h["first"], "last": h["last"]})


def fold(id: str, events: list[dict], kind: ItemKind | None, history: bool = False, it: Item | None = None,
         transcript: bool = True) -> Item:
    """One item from its events, oldest first: each event's changeset folded into its fields in
    turn, and, with ``history``, every change kept (or ``it``, folded further with what came after).
    ``transcript``: whether these events include its transcript's lines (a snapshot holds both folds)."""
    it = it or Item(id, kind.name if kind else None)
    rules = kind.fold if kind else {}
    for e in events:
        if e["type"] == SNAPSHOT:
            restore(it, e, history, transcript)
            continue
        if not it.n:
            it.first = e["time"]
            if kind and kind.states:                 # it arrives: a move into its first state, counted like any other
                it.state, it.entered = kind.states[0], e["time"]
                it.moves.append({"time": e["time"], "from": None, "to": it.state, "event": e["id"], "type": e["type"]})
        it.n += 1
        it.last = max(it.last, e["time"])
        it.latest = e["type"]
        if e["type"].startswith(LEASE_PREFIX):              # a lease taken, renewed, ended (SPEC §9.5): ergostat's own
            to, why = lease_fold.apply(it, e, kind, history)
            if why is not None:
                it.refused.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "lease", "why": why})
                if history:
                    it.changes.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "lease",
                                       "op": "refused", "path": "", "before": None, "after": None, "why": why})
            elif to and to != it.state:
                it.moves.append({"time": e["time"], "from": it.state, "to": to, "event": e["id"], "type": e["type"]})
                it.state, it.entered = to, e["time"]
            continue
        lease = it.fields.get("lease")
        if not isinstance(lease, dict):                      # only an item's own lease is ergostat's (a workspace's
            lease = None                                     # or an action's `lease` is a fencing number: plain data)
        why = lease_fold.fenced(it, e) if lease is not None else None
        if why is not None:                                  # a run whose lease ended: what it says is refused
            it.refused.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": form_of(e), "why": why})
            if history:
                it.changes.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": form_of(e),
                                   "op": "refused", "path": "", "before": None, "after": None, "why": why})
            continue
        done, why = fold_event(it.fields, e, rules)
        if lease is not None and it.fields.get("lease") is not lease:   # the lease is ergostat's: no event's data replaces it
            it.fields["lease"] = lease
        if why is not None:
            it.refused.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": form_of(e), "why": why})
            if history:
                it.changes.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": form_of(e),
                                   "op": "refused", "path": "", "before": None, "after": None, "why": why})
        elif history and done:
            form = form_of(e)
            for op, path, before, after in done:
                c = {"time": e["time"], "event": e["id"], "type": e["type"], "form": form, "op": op, "path": path,
                     "before": before, "after": after}
                if form == "data":
                    c["rule"] = rules.get(field_of(path), "replace")
                it.changes.append(c)
        to = kind.on.get(e["type"]) if kind else None
        if e["type"] == REOPENED and kind and kind.states:     # reopened: back to the state it names (else the first)
            want = ((e.get("data") or {}).get("reopened") or {}).get("to")
            to = want if want in kind.states else kind.states[0]
        if to and to != it.state:
            it.moves.append({"time": e["time"], "from": it.state, "to": to, "event": e["id"], "type": e["type"]})
            it.state, it.entered = to, e["time"]
        if lease is not None:
            lease_fold.renew(it, e)
            lease_fold.news(it, e)
    return it


def asks_transcript(kinds, fields=()) -> bool:
    """Whether a fold needs a transcript's events (``claude.*``): its kind moves on one, or what is
    asked of it (a sensor's ``where:``, a column) names a field they fold into. Otherwise they are
    left out, and a session with thousands of lines folds as fast as one without."""
    from ..transcripts import FIELDS
    return any(t.startswith("claude.") for k in kinds for t in k.on) or \
        any(k.fold.get(f) and f in FIELDS for k in kinds for f in fields)


def _index(events, spec, transcript: bool):
    """The record's item index for these kinds, caught up (``itemindex.py``); None for a record kept
    nowhere on disk."""
    from .itemindex import index_for
    return index_for(events, spec, transcript)


def _late(ix, events, spec, kind: str | None, until: float | None, transcript: bool) -> dict[str, Item] | None:
    """The items (of ``kind``) with an event after ``until``, each folded again from the record up to
    then (dropped when it had none by then); None when that is most of them (a moment long past: the
    caller folds the record itself). Under the index's lock."""
    if until is None:
        return {}
    cap = max(50, ix.total(kind) // 10)
    ids = ix.late(until, kind, limit=cap + 1)
    if len(ids) > cap:
        return None
    skip = () if transcript else (TRANSCRIPT_TYPES,)
    out = {}
    for i in ids:
        evs = events.query(n=None, item=i, until=until, skip=skip)
        if evs:
            out[i] = fold(i, evs, kind_of(spec, i), transcript=transcript)
    return out


def project(events, spec: Spec, kind: str | None = None, until: float | None = None, fields=(),
            transcript: bool | None = None) -> list[Item]:
    """Every item (of ``kind``, when given) as it stood at ``until``, the latest first. A transcript's
    events are folded in only when asked (``transcript``) or needed (``asks_transcript``, for ``fields``).
    Read from the item index (``itemindex.py``), which follows the record; an item with something after
    ``until`` is folded again from the record. (Moves are history: a count of moves in a past span
    reads them from the items as they are now, ``until=None``, unless it also matches fields, which may
    have changed since; ``moved`` reads only the span's.) Every item of a kind is read from disk:
    what counts or pages through them (``measure``, ``moved``, ``listing``) reads only what it needs."""
    kinds = [spec.items[kind]] if kind else list(spec.items.values())
    if kind and not kinds:
        return []
    globs = [k.id for k in kinds] if kind else None
    if transcript is None:
        transcript = asks_transcript(kinds, fields)
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, kind, until, transcript)
            if late is not None:
                out = ix.items(kind, until=until) + [i for i in late.values() if not kind or i.kind == kind]
                return sorted(out, key=lambda i: -i.last)
    by: dict[str, list[dict]] = {}
    for e in events.of_items(globs, until=until, skip=() if transcript else (TRANSCRIPT_TYPES,)):
        by.setdefault(e["item"], []).append(e)
    out = []
    for id, evs in by.items():
        k = kind_of(spec, id)
        if kind and (k is None or k.name != kind):
            continue
        out.append(fold(id, evs, k, transcript=transcript))
    return sorted(out, key=lambda i: -i.last)


def moved(events, spec: Spec, kind: str, key: str, state: str | None, since: float, until: float,
          where: dict | None = None, at: float | None = None) -> list[float]:
    """When ``kind``'s items moved into (``key`` "to") or out of ("from") ``state``, between ``since``
    and ``until`` (both included), oldest first: read from the index's moves for the span alone. With
    ``where``, only items whose fields match it, as they stood at ``at`` (else as they are now)."""
    where = where or {}
    k = spec.items.get(kind)
    if k is None:
        return []
    transcript = asks_transcript([k], tuple(where))
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, kind, at, transcript) if where else {}
            if late is not None:
                got = ix.moved(kind, key, state, since, until, until_newest=at if where else None)
                if where:
                    ids = {i for i, _ in got}
                    ok = {i.id for i in ix.items(kind, ids=ids, moves=False) if matches(i, where)}
                    got = [(i, t) for i, t in got if i in ok]
                times = [t for _, t in got]
                times += [m["time"] for i in late.values() if i.kind == kind and matches(i, where)
                          for m in i.moves if m[key] == state and since <= m["time"] <= until]
                return sorted(times)
    its = project(events, spec, kind, until=at if where else None, fields=tuple(where), transcript=transcript)
    return sorted(m["time"] for i in its if matches(i, where) for m in i.moves if m[key] == state and since <= m["time"] <= until)


def in_states(events, spec: Spec, kind: str, states=None, where: dict | None = None, until: float | None = None,
              items: bool = False) -> tuple[int, float | None, list[Item]]:
    """``kind``'s items in ``states`` (any, when None) matching ``where``, as they stood at ``until``:
    how many, when the one longest in its state entered it, and (``items``, or with ``where``) the
    items themselves. Counted by the index when nothing asks for their fields."""
    where = where or {}
    k = spec.items.get(kind)
    if k is None:
        return 0, None, []
    transcript = asks_transcript([k], tuple(where))
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, kind, until, transcript)
            if late is not None:
                extra = [i for i in late.values() if i.kind == kind and (not states or i.state in states) and matches(i, where)]
                if where or items:
                    got = [i for i in ix.items(kind, states=states, until=until, moves=False) if matches(i, where)] + extra
                    return len(got), min((i.entered for i in got), default=None), got
                n = ix.count(kind, states, until)
                w, a = ix._where(kind, states, until)
                oldest = ix.db.execute(f"select min(entered) from items{w}", a).fetchone()[0]
                firsts = [x for x in (oldest, *(i.entered for i in extra)) if x is not None]
                return n + len(extra), min(firsts, default=None), extra
    got = [i for i in project(events, spec, kind, until=until, fields=tuple(where), transcript=transcript)
           if (not states or i.state in states) and matches(i, where)]
    return len(got), min((i.entered for i in got), default=None), got


def in_states_page(events, spec: Spec, kind: str, states=None, where: dict | None = None, until: float | None = None,
                   n: int = 500, offset: int = 0) -> tuple[int, list[Item]]:
    """``kind``'s items in ``states`` matching ``where`` as they stood at ``until``, the latest first: how many,
    and ``n`` of them from ``offset`` (a side panel's list, the Items page's set). Counted and paged by the
    index when nothing asks for their fields; else read without their moves and matched here."""
    where = where or {}
    k = spec.items.get(kind)
    if k is None:
        return 0, []
    transcript = asks_transcript([k], tuple(where) + tuple(k.show))
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, kind, until, transcript)
            if late is not None:
                extra = [i for i in late.values() if i.kind == kind and (not states or i.state in states) and matches(i, where)]
                if not where and not extra:
                    return ix.count(kind, states, until), ix.items(kind, states, until, n=n, offset=offset, moves=False)
                got = [i for i in ix.items(kind, states, until, moves=False) if matches(i, where)] + extra
                got.sort(key=lambda i: -i.last)
                return len(got), got[offset:offset + n]
    got = [i for i in project(events, spec, kind, until=until, fields=tuple(where) + tuple(k.show), transcript=transcript)
           if (not states or i.state in states) and matches(i, where)]
    return len(got), got[offset:offset + n]


def moved_items(events, spec: Spec, kind: str, key: str, states, since: float, until: float,
                where: dict | None = None) -> list[Item]:
    """``kind``'s items with a move into (``key`` "to") or out of ("from") one of ``states`` between ``since``
    and ``until``, matching ``where``, as they stood at ``until``, with their moves: the candidates are the
    index's moves for the span alone (the caller says which of their moves count)."""
    where = where or {}
    k = spec.items.get(kind)
    if k is None:
        return []
    transcript = asks_transcript([k], tuple(where) + tuple(k.show))
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, kind, until, transcript)
            if late is not None:
                ids = {i for s in states for i, _ in ix.moved(kind, key, s, since, until)} - set(late)
                got = ix.items(kind, until=until, ids=ids) + [i for i in late.values() if i.kind == kind]
                return [i for i in got if matches(i, where)
                        and any(m[key] in states and since <= m["time"] <= until for m in i.moves)]
    return [i for i in project(events, spec, kind, until=until, fields=tuple(where) + tuple(k.show), transcript=transcript)
            if matches(i, where) and any(m[key] in states and since <= m["time"] <= until for m in i.moves)]


def one(events, spec: Spec, id: str) -> Item | None:
    evs = events.query(n=None, item=id)
    return fold(id, evs, kind_of(spec, id)) if evs else None


def field_at(fields: dict, name: str):
    """A field's value, or a field's field's (``lease.back``) when no field has the whole name."""
    if name in fields or "." not in name:
        return fields.get(name)
    v = fields
    for part in name.split("."):
        if not isinstance(v, dict):
            return None
        v = v.get(part)
    return v


def same(have, want) -> bool:
    """Typed JSON equality (SPEC §6, ``where:``): numbers as numbers (1 is 1.0), strings as strings, booleans as
    booleans (true is not 1), null as null; a list or a map equal element by element."""
    if isinstance(have, bool) or isinstance(want, bool):
        return isinstance(have, bool) and isinstance(want, bool) and have == want
    if isinstance(have, int | float) and isinstance(want, int | float):
        return float(have) == float(want)
    if isinstance(have, list) and isinstance(want, list):
        return len(have) == len(want) and all(same(a, b) for a, b in zip(have, want, strict=True))
    if isinstance(have, dict) and isinstance(want, dict):
        return have.keys() == want.keys() and all(same(have[k], want[k]) for k in have)
    if have is None or want is None:
        return have is None and want is None
    if isinstance(have, str) or isinstance(want, str):
        return isinstance(have, str) and isinstance(want, str) and have == want
    return have == want


def typed_too(where: dict) -> dict:
    """A ``where`` typed as text (a page's or a command's filter, ``priority:1``): each value also as the JSON number,
    boolean or null it spells, so a filter typed as text matches the field whichever type it holds."""
    out = {}
    for k, v in where.items():
        vs = v if isinstance(v, list) else [v]
        more = []
        for x in vs:
            if isinstance(x, str):
                try:
                    j = json.loads(x)
                except ValueError:
                    continue
                if j is None or isinstance(j, bool | int | float):
                    more.append(j)
        out[k] = [*vs, *more]
    return out


def matches(it: Item, where: dict) -> bool:
    for k, want in where.items():
        have = field_at(it.fields, k)
        wants = want if isinstance(want, list) else [want]
        if not any(same(have, w) for w in wants):
            return False
    return True


def measure(events, spec: Spec, s: Sensor, now: float | None = None) -> tuple[float | None, str]:
    """A sensor that counts items: a stock's count (or its oldest item's age in hours), or a flow's
    rate per hour of items entering or leaving a state."""
    q = s.items or {}
    now = now or time.time()
    where = q.get("where") or {}
    if s.of.kind != "flow":                         # a stock, or an auxiliary: how many there are now
        if q.get("measure") == "age":                   # since it was first seen, whatever states it passed through
            _, _, got = in_states(events, spec, q["kind"], q.get("state") or None, where, until=now, items=True)
            return (max((now - i.first) / 3600 for i in got) if got else 0.0), ""
        n, entered, _ = in_states(events, spec, q["kind"], q.get("state") or None, where, until=now)
        if q.get("measure") == "oldest":
            return ((now - entered) / 3600 if n and entered is not None else 0.0), ""
        return float(n), ""
    over = q.get("over") or 3600.0
    since = now - over
    key, state = ("to", q["entering"]) if q.get("entering") else ("from", q.get("leaving"))
    n = sum(1 for t in moved(events, spec, q["kind"], key, state, since, now, where, at=now) if t > since)
    return n * 3600.0 / over, ""


def glob_ok(pattern: str) -> bool:
    return "/" in pattern and not pattern.startswith("/")


def kinds_of(spec) -> dict:
    return getattr(spec, "items", None) or {}


def listing(events, spec, kind: str | None = None, state: str | None = None, until: float | None = None,
            n: int = LISTED, offset: int = 0) -> dict:
    """What the Items page and ``ergostat item`` show: each kind with its count per state, and
    the items themselves (newest first), filtered by kind and state: ``n`` of them from ``offset``.
    Counted and paged by the item index: only the items shown are read."""
    kinds = kinds_of(spec)
    plain = spec is None or not kinds
    if plain:
        every = events.items()
        page = [fold(i["item"], events.query(n=None, item=i["item"], until=until, skip=(TRANSCRIPT_TYPES,)), None, transcript=False)
                for i in every[offset:offset + n]]
        counts: dict[str, dict[str, int]] = {}
        for i in page:
            c = counts.setdefault(i.kind or "", {})
            c[i.state or ""] = c.get(i.state or "", 0) + 1
        page = [i for i in page if (kind is None or (i.kind or "") == kind) and (state is None or (i.state or "") == state)]
        total = len(every)
    else:
        page, counts, total = _paged(events, spec, kind, state, until, n, offset)
    from ..transcripts import FIELDS
    lines = events.counted(TRANSCRIPT_TYPES, until=until)            # left out of the fold: counted, not read
    page = [copy.copy(i) for i in page]                                # what the index lent: changed only as copies
    for i in page:
        if (i.id in lines or i.rolled) and not any(f in i.fields for f in FIELDS):
            n_, last = lines.get(i.id, (0, i.last))
            i.n, i.last = i.n + n_ + i.rolled, max(i.last, last)
    from .item_systems import OTHER, groups, kind_systems
    where = kind_systems(spec)               # each kind's system (item_systems.py): the page groups by it
    unkinded = sum(counts.get("", {}).values())
    systems = groups(spec, {**where, **({"": {"system": OTHER}} if unkinded else {})})
    for g in systems:
        g["kinds"] = [k for k in g["kinds"] if k]
    return {"kinds": [{"name": k.name, "id": k.id, "states": k.states, "show": k.show, "formats": k.formats,
                       "description": k.description, "system": where[k.name]["system"], "system_why": where[k.name]["why"],
                       "relations": {r: x.kinds for r, x in k.relations.items()},
                       "counts": counts.get(k.name, {})} for k in kinds.values()],
            "systems": systems, "unkinded": unkinded,
            "total": total, "offset": offset,
            "items": [_listed(i, kinds, where) for i in page]}


def _paged(events, spec, kind: str | None, state: str | None, until: float | None, n: int, offset: int):
    """The listing's page of items, its counts per kind and state, and how many match."""
    kinds = kinds_of(spec)
    transcript = asks_transcript(list(kinds.values()), tuple(f for k in kinds.values() for f in k.show))

    def want(i: Item) -> bool:
        return (kind is None or (i.kind or "") == kind) and (state is None or (i.state or "") == state)
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, None, until, transcript)
            if late is not None:
                counts = ix.counts(until)
                for i in late.values():
                    c = counts.setdefault(i.kind or "", {})
                    c[i.state or ""] = c.get(i.state or "", 0) + 1
                states = None if state is None else [state]
                extra = [i for i in late.values() if want(i)]
                if extra:
                    page = sorted(ix.items(kind, states, until, n=offset + n) + extra, key=lambda i: -i.last)[offset:offset + n]
                else:
                    page = ix.items(kind, states, until, n=n, offset=offset)
                return page, counts, ix.count(kind, states, until) + len(extra)
    its = project(events, spec, until=until, transcript=transcript)
    counts = {}
    for i in its:
        c = counts.setdefault(i.kind or "", {})
        c[i.state or ""] = c.get(i.state or "", 0) + 1
    shown = [i for i in its if want(i)]
    return shown[offset:offset + n], counts, len(shown)


def _listed(i: Item, kinds: dict, where: dict | None = None) -> dict:
    """An item as a list shows it, with its kind's system: a conversation folded from its transcript
    only when a column asks."""
    from ..transcripts import FIELDS
    from .item_systems import OTHER
    d = i.as_dict()
    d["system"] = ((where or {}).get(i.kind or "") or {}).get("system", OTHER)
    k = kinds.get(i.kind or "")
    if any(f in d["fields"] for f in FIELDS):
        d["fields"] = {f: v for f, v in d["fields"].items() if f not in FIELDS or (k and f in k.show)}
    return d


HISTORY_SHOWN = 100     # each field's latest changes in the item's detail; all of them with history=None


def detail(events, spec, id: str, until: float | None = None, history: int | None = HISTORY_SHOWN) -> dict | None:
    """An item in full, as it stood at ``until``: its fields, its moves, each field's history (its latest
    ``history`` changes, and how many there were), what was refused, and its record."""
    evs = events.query(n=None, item=id, until=until)
    if not evs:
        return None
    k = kind_of(spec, id) if kinds_of(spec) else None
    it = fold(id, evs, k, history=True)
    d = it.as_dict(moves=True, history=True)
    d["changes"] = {f: len(cs) for f, cs in d["history"].items()}
    if history is not None:
        d["history"] = {f: cs[-history:] for f, cs in d["history"].items()}
    from .item_systems import OTHER, kind_systems
    d["system"] = kind_systems(spec)[k.name]["system"] if k else OTHER
    own = [e for e in evs if not e["type"].startswith("claude.")]
    snap = next((e for e in evs if e["type"] == SNAPSHOT), None)
    return {**d,
            "rollup": {k_: v for k_, v in (snap["data"].get("rollup") or {}).items() if k_ not in ("moves", "refused")}
            if snap else None,
            "record_total": len(own),
            "kind_of": {"name": k.name, "id": k.id, "states": k.states, "on": k.on, "show": k.show, "formats": k.formats,
                        "fold": k.fold} if k else None,
            "transcript_events": len(evs) - len(own),
            "relations": related(events, spec, it, k),
            "record": own[-500:]}


def related(events, spec, it: Item, k) -> dict | None:
    """An item's relations both ways (SPEC §5a, *Relations*): what its fields name, and what names it (the inverse,
    from the item index), each with the related item's kind, state and status; None when there are none."""
    from .relations import ids_in
    out: dict = {"out": {}, "in": {}}
    for r in (k.relations if k else {}):
        if ids_in(it.fields.get(r)):
            out["out"][r] = ids_in(it.fields.get(r))
    ix = _index(events, spec, False) if any(x.relations for x in kinds_of(spec).values()) else None
    if ix is not None:
        with ix.lock:
            for a, r, _ in ix.links_to([it.id]):
                ka = kind_of(spec, a)
                rel = ka.relations.get(r) if ka else None
                if rel is not None:
                    out["in"].setdefault(rel.inverse, []).append(a)
            ids = {x for v in (*out["out"].values(), *out["in"].values()) for x in v}
            seen = {i.id: i for i in ix.items(None, ids=ids, moves=False)} if ids else {}
    else:
        seen = {}
    if not out["out"] and not out["in"]:
        return None
    from ..precedence import Kinds, status
    info = Kinds(spec, ix)
    title = lambda x: x.fields.get("title") if isinstance(x.fields.get("title"), str) else ""      # noqa: E731
    out["items"] = {i: {"kind": x.kind, "state": x.state, "title": title(x), "done": status(x, info[x.kind], []) == "done"}
                    for i, x in seen.items()}
    prec = {r for r, rel in (k.relations.items() if k else []) if rel.precedence}
    out["waiting"] = [i for r in prec for i in out["out"].get(r, []) if not (out["items"].get(i) or {}).get("done")]
    out["relations"] = {r: {"kinds": rel.kinds, "precedence": rel.precedence, "inverse": rel.inverse, "group": rel.group}
                        for r, rel in (k.relations.items() if k else [])}
    return out
