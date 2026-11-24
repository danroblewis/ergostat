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

from .. import operating
from ..leases import PREFIX as LEASE_PREFIX
from ..leases import fold as lease_fold
from ..operating import KIND as OPERATING
from .changes import fold_event, form_of
from .ir import DEAD, ItemKind, Sensor, Spec

REOPENED = "ergostat.item.reopened"   # any item moved back, by ergostat, to a state its data names (SPEC §12h)
JOINED = "ergostat.item.joined"       # a parent moved on by its kind's join: to the state its data names (SPEC §5a)
TRANSCRIPT_TYPES = "claude.*"     # a Claude Code transcript, line by line (transcripts.py): left out unless asked for
SNAPSHOT = "ergostat.item.snapshot"    # an item's older events, folded into one (rollup.py): its document as a set
LISTED = 500                           # the most items one listing carries; page through with offset
TEXT_MOST = 65_536                     # characters of an item's text a search reads (text_of): words past them are not
SEARCH_WORDS = 8                       # the most words one search may hold


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
        if kind is not None and kind.sealed and not e["type"].startswith("ergostat."):
            it.refused.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "sealed",
                               "why": f"only ergostat writes a {kind.name}"})    # (SPEC §12r: M1)
            continue
        seen = it.n                                          # its events before this one: the count a reader saw
        if not it.n:
            it.first = e["time"]
            if kind and kind.states:                 # it arrives: a move into its first state, counted like any other
                it.state, it.entered = kind.states[0], e["time"]
                it.moves.append({"time": e["time"], "from": None, "to": it.state, "event": e["id"], "type": e["type"]})
        it.n += 1
        it.last = max(it.last, e["time"])
        it.latest = e["type"]
        if kind is not None and e["type"] in kind.if_unchanged:     # written from a reading of the item (SPEC §5a)
            data = e.get("data") if isinstance(e.get("data"), dict) else {}
            read = data.get("read")
            if type(read) is not int or read != seen:          # changed since it was read, or not said: nothing applies
                why = f"written from the item at {read!r} events, and it had {seen}: ignored"
                it.refused.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "read", "why": why})
                if history:
                    it.changes.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "read",
                                       "op": "refused", "path": "", "before": None, "after": None, "why": why})
                continue
            e = {**e, "data": {k: v for k, v in data.items() if k != "read"}}
        if e["type"].startswith(LEASE_PREFIX):             # a lease taken, renewed, ended (SPEC §9.5): ergostat's own
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
        if kind is not None and kind.name == OPERATING:      # an operating state entered or left (SPEC §9.5): ergostat's own
            why = operating.apply(it, e)
            if why is not None:
                it.refused.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "operating", "why": why})
            continue
        lease = it.fields.get("lease")
        if not isinstance(lease, dict):                     # only an item's own lease is ergostat's (a workspace's
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
        if e["type"] == JOINED and kind and kind.states:
            want = ((e.get("data") or {}).get("joined") or {}).get("to")      # only forward: a parent past it stays
            ahead = it.state not in kind.states or kind.states.index(it.state) < kind.states.index(want) \
                if want in kind.states else False
            to = want if ahead else None
        if why is not None and form_of(e) in ("patch", "set"):   # a refused patch or set moves nothing either: its
            to = None                                            # `test` is a precondition of the whole event (§5a)
        if to and to != it.state and kind and it.state not in kind.moves_from.get(e["type"], (it.state,)):
            why = f"moves only from {', '.join(kind.moves_from[e['type']])}, not from {it.state}: ignored"
            it.refused.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "from", "why": why})
            if history:
                it.changes.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "from",
                                   "op": "refused", "path": "", "before": None, "after": None, "why": why})
            to = None
        if to and to != it.state and kind and it.state in kind.final:             # final: a move out of it is ignored, and said
            it.refused.append({"time": e["time"], "event": e["id"], "type": e["type"], "form": "final",
                               "why": f"after {it.state}: ignored"})
            to = kind.final[it.state].get(to)
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


def late_cap(ix, kind: str | None = None) -> int:
    """How many items changed since a moment are each folded again from the record; past it, the whole record up to
    the moment is folded instead (``_late``, ``asof.AsOf``)."""
    return max(50, ix.total(kind) // 10)


def _late(ix, events, spec, kind: str | None, until: float | None, transcript: bool,
          keys: tuple | None = None) -> dict[str, Item] | None:
    """The items (of ``kind``) with an event after ``until``, each folded again from the record up to
    then (dropped when it had none by then); None when that is most of them (a moment long past: the
    caller folds the record itself). With ``keys``, only those whose fields ``keys`` may have changed
    since (``Index.still``): the caller reads the rest from the index. Under the index's lock."""
    if until is None:
        return {}
    cap = late_cap(ix, kind)
    ids = ix.late(until, kind, limit=cap + 1)
    if len(ids) > cap:
        return None
    if keys is not None:
        still = ix.still(ids, keys, until)
        ids = [i for i in ids if i not in still]
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
    if transcript is None:
        transcript = asks_transcript(kinds, fields)
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, kind, until, transcript)
            if late is not None:
                out = ix.items(kind, until=until) + [i for i in late.values() if not kind or i.kind == kind]
                return sorted(out, key=lambda i: -i.last)
    return fold_all(events, spec, kind, until, transcript)


def fold_all(events, spec: Spec, kind: str | None, until: float | None, transcript: bool) -> list[Item]:
    """Every item (of ``kind``; None: every item, of a kind or of none) as it stood at ``until``, folded from the
    record itself, the latest first."""
    by: dict[str, list[dict]] = {}
    for e in events.of_items([spec.items[kind].id] if kind else None, until=until,
                             skip=() if transcript else (TRANSCRIPT_TYPES,)):
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
            late = _late(ix, events, spec, kind, at, transcript, keys=tuple(where)) if where else {}
            if late is not None:                  # (the rest of those changed since ``at``: as they were then, to then)
                got = ix.moved(kind, key, state, since, until if not where or at is None else min(until, at))
                if where:
                    got = [(i, t) for i, t in got if i not in late]
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
              items: bool = False, transcript: bool | None = None) -> tuple[int, float | None, list[Item]]:
    """``kind``'s items in ``states`` (any, when None) matching ``where``, as they stood at ``until``:
    how many, when the one longest in its state entered it, and (``items``, or with ``where``) the
    items themselves. Counted by the index when nothing asks for their fields. ``transcript``: as ``project``."""
    where = where or {}
    k = spec.items.get(kind)
    if k is None:
        return 0, None, []
    transcript = asks_transcript([k], tuple(where)) if transcript is None else transcript
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

                def oldest_entered():
                    w, a = ix._where(kind, states, until)
                    return ix.db.execute(f"select min(entered) from items{w}", a).fetchone()[0]
                oldest = ix.guard(oldest_entered)
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


def current(events, spec: Spec, ids, fields=()) -> dict[str, Item]:
    """The items ``ids`` as they are now, by id (one with no event left out), without their moves: read from the item
    index, which folds a transcript's events in only when ``fields`` need them (``asks_transcript``), as every read of
    it does; for a record kept nowhere on disk, each folded from the record (``one``)."""
    ids = sorted({i for i in ids if i})
    ix = _index(events, spec, asks_transcript([k for i in ids if (k := kind_of(spec, i))], tuple(fields))) if ids else None
    if ix is None:
        return {i: it for i in ids if (it := one(events, spec, i)) is not None}
    with ix.lock:
        return {it.id: it for it in ix.items(ids=ids, moves=False)}


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
    if not (q.get("entering") or q.get("leaving")):  # a stock, or an auxiliary: how many there are now
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
    per = 3600.0 / over if s.of.kind == "flow" else 1.0   # a flow: per hour; an auxiliary: how many over the window
    if q.get("sum"):                                # a field summed over the items moving, not how many moved
        return sum(x for _, x in summed(events, spec, q, since, now)) * per, ""
    n = sum(1 for t in moved(events, spec, q["kind"], key, state, since, now, where, at=now) if t > since)
    return n * per, ""


def summed(events, spec: Spec, q: dict, since: float, until: float) -> list[tuple[float, float]]:
    """A flow's ``sum:`` sensor: each move of its items into (or out of) its state in the span, with the item's
    field ``q["sum"]`` (a number; else 0), as the item stood at ``until``."""
    key, state = ("to", q["entering"]) if q.get("entering") else ("from", q.get("leaving"))
    out = []
    for i in moved_items(events, spec, q["kind"], key, [state], since, until, q.get("where")):
        v = field_at(i.fields, q["sum"])
        v = float(v) if isinstance(v, int | float) and not isinstance(v, bool) else 0.0
        out += [(m["time"], v) for m in i.moves if m[key] == state and since < m["time"] <= until]
    return sorted(out)


def glob_ok(pattern: str) -> bool:
    return "/" in pattern and not pattern.startswith("/")


def text_of(fields: dict) -> str:
    """What a search reads of an item (SPEC §5a, *Search*): the string values of its fields, nested ones too, in the
    document's order, one per line, casefolded, cut to the first ``TEXT_MOST`` characters."""
    out, size, todo = [], 0, [fields]
    while todo and size < TEXT_MOST:
        v = todo.pop()
        if isinstance(v, str):
            out.append(v)
            size += len(v) + 1
        elif isinstance(v, (dict, list)):
            todo += reversed(list(v.values()) if isinstance(v, dict) else v)
    return "\n".join(out).casefold()[:TEXT_MOST]


def words(search: str) -> tuple[str, ...]:
    """A search's words, casefolded as ``text_of`` is: one at least, ``SEARCH_WORDS`` at most (else ``BadSet``)."""
    from .item_sets import BadSet
    got = tuple(search.casefold().split())
    if not got or len(got) > SEARCH_WORDS:
        raise BadSet(f"search: give 1 to {SEARCH_WORDS} words (an item matches when its fields hold every one)")
    return got


def kinds_of(spec) -> dict:
    return getattr(spec, "items", None) or {}


def listing(events, spec, kind: str | None = None, state: str | None = None, until: float | None = None,
            n: int = LISTED, offset: int = 0, search: str | None = None, states=None) -> dict:
    """What the Items page and ``ergostat item`` show: each kind with its count per state, and
    the items themselves (newest first), filtered by kind and state (or any of ``states``), and by ``search`` (``words``: items
    whose ``text_of`` holds every word): ``n`` of them from ``offset``.
    Counted and paged by the item index: only the items shown are read."""
    kinds = kinds_of(spec)
    ws = words(search) if search is not None else ()
    plain = (spec is None or not kinds) and not ws
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
        page, counts, total = _paged(events, spec, kind, state, until, n, offset, ws, states)
    from ..transcripts import FIELDS
    lines = events.counted(TRANSCRIPT_TYPES, until=until)            # left out of the fold: counted, not read
    page = [copy.copy(i) for i in page]                                # what the index lent: changed only as copies
    for i in page:
        if (i.id in lines or i.rolled) and not any(f in i.fields for f in FIELDS):
            n_, last = lines.get(i.id, (0, i.last))
            i.n, i.last = i.n + n_ + i.rolled, max(i.last, last)
    from .grouptally import offered
    from .item_systems import OTHER, TITLES, groups, kind_systems
    where = kind_systems(spec)              # each kind's system (item_systems.py): the page groups by it
    unkinded = sum(counts.get("", {}).values())
    systems = groups(spec, {**where, **({"": {"system": OTHER}} if unkinded else {})})
    for g in systems:
        g["kinds"] = [k for k in g["kinds"] if k]
    return {"kinds": [{"name": k.name, "title": TITLES.get(k.name), "id": k.id, "states": k.states, "show": k.show, "formats": k.formats,
                       "description": k.description, "system": where[k.name]["system"], "system_why": where[k.name]["why"],
                       "relations": {r: x.kinds for r, x in k.relations.items()},
                       "progress": [r for r, x in k.relations.items() if offered(k, x)],   # (grouptally.py)
                       "counts": counts.get(k.name, {}), **finishes(events, spec, k.name)} for k in kinds.values()],
            "systems": systems, "unkinded": unkinded,
            "total": total, "offset": offset,
            "items": [_listed(i, kinds, where) for i in page]}


def finishes(events, spec, kind: str) -> dict:
    """A kind's finished and paused states as the listing gives them (``finished.finish_of``), from the states its
    items have left by now (none known for a record kept nowhere on disk)."""
    from .finished import finish_of
    ix = _index(events, spec, False)
    if ix is not None:
        with ix.lock:
            left = set(ix.left(kind))
    f = finish_of(spec, kind, left if ix is not None else set())
    return {"finished": f["finished"], "paused": f["paused"], "dead": f["dead"], "finished_from": f["from"],
            "lives_on": f["lives_on"]}


def hidden_states(k: dict) -> list[str]:
    """The states the Items list leaves out unless asked (SPEC §5a, *Finished items*): a listed kind's finished
    states and ``dead``; none for a kind that lives on. Paused states stay."""
    return [] if k.get("lives_on") else [*k.get("finished", []), *([DEAD] if k.get("dead") else [])]


def _paged(events, spec, kind: str | None, state: str | None, until: float | None, n: int, offset: int, ws=(),
           states=None):
    """The listing's page of items, its counts per kind and state, and how many match: in ``state``, or any of
    ``states`` (a list; the index pages them)."""
    kinds = kinds_of(spec)
    transcript = asks_transcript(list(kinds.values()), tuple(f for k in kinds.values() for f in k.show))
    states = list(states) if states is not None else None if state is None else [state]

    def want(i: Item) -> bool:
        return (kind is None or (i.kind or "") == kind) and (states is None or (i.state or "") in states) and \
            all(w in text_of(i.fields) for w in ws)
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, None, until, transcript)
            if late is not None:
                counts = ix.counts(until)
                for i in late.values():
                    c = counts.setdefault(i.kind or "", {})
                    c[i.state or ""] = c.get(i.state or "", 0) + 1
                extra = [i for i in late.values() if want(i)]
                if extra:
                    page = sorted(ix.items(kind, states, until, n=offset + n, words=ws) + extra,
                                  key=lambda i: -i.last)[offset:offset + n]
                else:
                    page = ix.items(kind, states, until, n=n, offset=offset, words=ws)
                return page, counts, ix.count(kind, states, until, ws) + len(extra)
    its = project(events, spec, until=until, transcript=transcript)
    counts = {}
    for i in its:
        c = counts.setdefault(i.kind or "", {})
        c[i.state or ""] = c.get(i.state or "", 0) + 1
    shown = [i for i in its if want(i)]
    return shown[offset:offset + n], counts, len(shown)


SORTED_MOST = 5_000    # the most items a kind's page reads to sort by a field: past it, the newest of them (``kind_page``)


def _hit(i: Item, q: str | None, ws) -> bool:
    return not q or q in i.id or all(w in text_of(i.fields) for w in ws)


def _by_field(its: list[Item], sort: str) -> list[Item]:
    """``its`` ordered by a field (``-f``: down): numbers as numbers, then text; a missing or non-finite value last, the
    newest first among equals."""
    import math
    f, down = sort.lstrip("-"), sort.startswith("-")
    v = lambda i: field_at(i.fields, f)   # noqa: E731
    num = [i for i in its if isinstance(v(i), (int, float)) and not isinstance(v(i), bool) and math.isfinite(v(i))]
    seen = {id(i) for i in num}
    text = [i for i in its if id(i) not in seen and v(i) is not None and not isinstance(v(i), float)]
    seen |= {id(i) for i in text}
    word = lambda x: x if isinstance(x, str) else json.dumps(x, sort_keys=True, default=str)   # noqa: E731
    return sorted(num, key=v, reverse=down) + sorted(text, key=lambda i: word(v(i)), reverse=down) + \
        [i for i in its if id(i) not in seen]


def kind_page(events, spec, kind: str, state: str | None = None, until: float | None = None, n: int = LISTED,
              offset: int = 0, q: str | None = None, sort: str | None = None, states=None) -> dict:
    """One page of ``kind``'s items (in ``state``, or any of ``states``, when given), as a kind's own page lists them (SPEC §5a, *A kind's
    page*): with ``q``, only those whose id holds it or whose fields hold each of its words, out of every item of the
    kind, finished or not; newest first, or by a field (``sort``: ``f`` up, ``-f`` down) over the whole filtered set,
    the newest ``SORTED_MOST`` of it when larger (``cut``). ``offset`` past the end is the last page's. How many match
    (``total``), and how many of them are finished (``finished``, of the kind's finished states)."""
    k = spec.items[kind]
    ws = words(q) if q else ()
    states = list(states) if states is not None else None if state is None else [state]
    done = set(finishes(events, spec, kind)["finished"])
    transcript = asks_transcript([k], tuple(k.show))

    def paged(rows, fetch):                               # rows: (id, last, state, the item when already folded)
        total = len(rows)
        reach = min(total, SORTED_MOST) if sort else total
        at = max(0, min(offset, (reach - 1) // max(1, n) * max(1, n) if reach else 0))
        page = _by_field(fetch(rows[:SORTED_MOST]), sort)[at:at + n] if sort else fetch(rows[at:at + n])
        return {"items": page, "total": total, "offset": at, "finished": sum(r[2] in done for r in rows),
                "cut": SORTED_MOST if sort and total > SORTED_MOST else None}
    ix = _index(events, spec, transcript)
    if ix is not None:
        with ix.lock:
            late = _late(ix, events, spec, kind, until, transcript)
            if late is not None:
                def read():
                    got = {}
                    for ww, has in ([((), None)] if not q else [(ws, None), ((), q)]):
                        w, a = ix._where(kind, states, until, ww)
                        if has is not None:
                            w, a = (w + " and " if w else " where ") + "instr(id, ?) > 0", [*a, has]
                        for i, last, st in ix.db.execute(f"select id, last, state from items{w}", a):
                            got[i] = (i, last, ix.name(st), None)
                    return got
                got = ix.guard(read)
                for i in late.values():
                    got.pop(i.id, None)
                    if i.kind == kind and (states is None or i.state in states) and _hit(i, q, ws):
                        got[i.id] = (i.id, i.last, i.state, i)

                def fetch(rs):
                    have = {i.id: i for i in ix.items(kind, until=until, moves=False, ids=[r[0] for r in rs if r[3] is None])}
                    return [r[3] or have[r[0]] for r in rs if r[3] or r[0] in have]
                return paged(sorted(got.values(), key=lambda r: -r[1]), fetch)
    its = [i for i in project(events, spec, kind, until=until, fields=tuple(k.show), transcript=transcript)
           if (states is None or i.state in states) and _hit(i, q, ws)]
    return paged([(i.id, i.last, i.state, i) for i in its], lambda rs: [r[3] for r in rs])


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
    if k is not None and k.risk is not None:                 # its risk score now (numbers/itemrisk.py); none as of then
        from ..numbers.itemrisk import item as risk_of
        try:                                                  # (a score that fails is said, never the item's whole page)
            d["risk_score"] = risk_of(events, spec, k.name, id) if until is None else None
        except Exception as e:
            d["risk_score"] = {"score": None, "why": [], "said": f"failed: {type(e).__name__}: {e}"[:300]}
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
    from ..precedence import Kinds, starts, status
    info = Kinds(spec, ix)
    title = lambda x: x.fields.get("title") if isinstance(x.fields.get("title"), str) else ""      # noqa: E731
    out["items"] = {i: {"kind": x.kind, "state": x.state, "title": title(x), "done": status(x, info[x.kind], []) == "done"}
                    for i, x in seen.items()}
    prec = {r: rel for r, rel in (k.relations.items() if k else []) if rel.precedence}
    out["waiting"] = [i for r in prec for i in out["out"].get(r, []) if not (out["items"].get(i) or {}).get("done")
                      and not (i in seen and starts(seen[i], prec[r]))]
    out["relations"] = {r: {"kinds": rel.kinds, "precedence": rel.precedence, "inverse": rel.inverse, "group": rel.group,
                            "starts_at": rel.starts_at} for r, rel in (k.relations.items() if k else [])}
    return out
