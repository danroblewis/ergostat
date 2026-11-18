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
import threading
import time
import weakref
from dataclasses import dataclass, field

from ..leases import PREFIX as LEASE_PREFIX
from ..leases import fold as lease_fold
from .changes import fold_event, form_of
from .ir import ItemKind, Sensor, Spec

REOPENED = "ergostat.item.reopened"   # any item moved back, by ergostat, to a state its data names (SPEC §12h)
TRANSCRIPT_TYPES = "claude.*"     # a Claude Code transcript, line by line (transcripts.py): left out unless asked for
SNAPSHOT = "ergostat.item.snapshot"    # an item's older events, folded into one (rollup.py): its document as a set
CHUNK = 50_000                         # events folded at a time into the kept fold
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
    return it


def asks_transcript(kinds, fields=()) -> bool:
    """Whether a fold needs a transcript's events (``claude.*``): its kind moves on one, or what is
    asked of it (a sensor's ``where:``, a column) names a field they fold into. Otherwise they are
    left out, and a session with thousands of lines folds as fast as one without."""
    from ..transcripts import FIELDS
    return any(t.startswith("claude.") for k in kinds for t in k.on) or \
        any(k.fold.get(f) and f in FIELDS for k in kinds for f in fields)


class _Folded:
    """Every item of one record, folded once and then kept up to date with what is new (after the
    last ``seq`` folded): the engine counts items every few seconds, and the page asks for them on
    every refresh, and neither should fold the whole record each time. Folded again from the start
    when the record loses events (``generation``: pruned, rolled up) or the model changes. One for
    folds with a transcript's lines, one without."""

    def __init__(self, spec, transcript: bool):
        self.spec, self.transcript, self.lock = spec, transcript, threading.Lock()
        self.reset(None)

    def reset(self, gen) -> None:
        self.items: dict[str, Item] = {}
        self.newest: dict[str, float] = {}           # each item's latest event time (an event may arrive late)
        self.seq, self.gen = 0, gen

    def take(self, events, kind: str | None, until: float | None) -> list[Item] | None:
        """Every item (of ``kind``) as it stood at ``until``: the kept ones themselves, so a caller must not
        change them (``listing`` copies what it changes). An item with something after
        ``until`` is folded again from the record up to then; None when that is most of them (a
        moment long past: the caller folds the record itself)."""
        skip = () if self.transcript else (TRANSCRIPT_TYPES,)
        with self.lock:
            gen = events.generation()
            if gen != self.gen:
                self.reset(gen)
            while True:                                  # a chunk at a time: the whole record is never in memory at once
                new = events.of_items(None, after_seq=self.seq, skip=skip, limit=CHUNK)
                self._fold(new)
                if len(new) < CHUNK:
                    break
            late = [] if until is None else [i for i, t in self.newest.items() if t > until]
            if len(late) > max(50, len(self.items) // 10):
                return None
            gone = set(late)
            out = [it for i, it in self.items.items() if i not in gone and (not kind or it.kind == kind)]
        for i in late:
            k = kind_of(self.spec, i)
            if kind and (k is None or k.name != kind):
                continue
            evs = events.query(n=None, item=i, until=until, skip=skip)
            if evs:
                out.append(fold(i, evs, k, transcript=self.transcript))
        return out

    def _fold(self, new: list[dict]) -> None:
        by: dict[str, list[dict]] = {}
        for e in new:
            by.setdefault(e["item"], []).append(e)
            self.seq = max(self.seq, e["seq"])
            if e["time"] > self.newest.get(e["item"], float("-inf")):
                self.newest[e["item"]] = e["time"]
        for id, evs in by.items():
            have = self.items.get(id)
            k = kind_of(self.spec, id)
            self.items[id] = fold(id, evs, k, it=have, transcript=self.transcript)


_FOLDED: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_FOLDED_LOCK = threading.Lock()


def _kinds_key(spec) -> tuple:
    """What a fold depends on in the model: its item kinds (a change being tried shares the kept fold
    when it leaves them as they are)."""
    return tuple((k.name, k.id, tuple(k.states), tuple(sorted(k.on.items())), tuple(sorted(k.fold.items())))
                 for k in spec.items.values())


def _folded(events, spec, kind: str | None, until: float | None, transcript: bool) -> list[Item] | None:
    if not hasattr(events, "generation"):
        return None
    key = (_kinds_key(spec), transcript)
    with _FOLDED_LOCK:
        mine = _FOLDED.setdefault(events, {})
        f = mine.get(key)
        if f is None:
            if len(mine) >= 6:                       # a few models at once (a change being tried), not every one ever
                mine.pop(next(iter(mine)))
            f = mine[key] = _Folded(spec, transcript)
    return f.take(events, kind, until)


def project(events, spec: Spec, kind: str | None = None, until: float | None = None, fields=(),
            transcript: bool | None = None) -> list[Item]:
    """Every item (of ``kind``, when given) as it stood at ``until``, the latest first. A transcript's
    events are folded in only when asked (``transcript``) or needed (``asks_transcript``, for ``fields``).
    Folded once and kept (``_Folded``), with what is new folded in on each ask. (Moves are history: a
    count of moves in a past span reads them from the items as they are now, ``until=None``, unless it
    also matches fields, which may have changed since.)"""
    kinds = [spec.items[kind]] if kind else list(spec.items.values())
    if kind and not kinds:
        return []
    globs = [k.id for k in kinds] if kind else None
    if transcript is None:
        transcript = asks_transcript(kinds, fields)
    kept = _folded(events, spec, kind, until, transcript)
    if kept is not None:
        return sorted(kept, key=lambda i: -i.last)
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
    where = q.get("where") or {}
    its = [i for i in project(events, spec, q["kind"], until=now, fields=tuple(where)) if matches(i, where)]
    if s.of.kind != "flow":                         # a stock, or an auxiliary: how many there are now
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
            n: int = LISTED, offset: int = 0) -> dict:
    """What the Items page and ``ergostat item`` show: each kind with its count per state, and
    the items themselves (newest first), filtered by kind and state: ``n`` of them from ``offset``."""
    kinds = kinds_of(spec)
    plain = spec is None or not kinds
    if plain:
        every = events.items()
        its = [fold(i["item"], events.query(n=None, item=i["item"], until=until, skip=(TRANSCRIPT_TYPES,)), None, transcript=False)
               for i in every[offset:offset + n]]
    else:
        its = project(events, spec, until=until, fields=tuple(f for k in kinds.values() for f in k.show))
    from ..transcripts import FIELDS
    lines = events.counted(TRANSCRIPT_TYPES, until=until)            # left out of the fold: counted, not read
    its = [copy.copy(i) for i in its]                                  # the kept fold's own: changed only as copies
    for i in its:
        if (i.id in lines or i.rolled) and not any(f in i.fields for f in FIELDS):
            n_, last = lines.get(i.id, (0, i.last))
            i.n, i.last = i.n + n_ + i.rolled, max(i.last, last)
    counts: dict[str, dict[str, int]] = {}
    for i in its:
        c = counts.setdefault(i.kind or "", {})
        c[i.state or ""] = c.get(i.state or "", 0) + 1
    shown = [i for i in its if (kind is None or (i.kind or "") == kind) and (state is None or (i.state or "") == state)]
    from .item_systems import OTHER, groups, kind_systems
    where = kind_systems(spec)               # each kind's system (item_systems.py): the page groups by it
    unkinded = sum(counts.get("", {}).values())
    systems = groups(spec, {**where, **({"": {"system": OTHER}} if unkinded else {})})
    for g in systems:
        g["kinds"] = [k for k in g["kinds"] if k]
    return {"kinds": [{"name": k.name, "id": k.id, "states": k.states, "show": k.show, "formats": k.formats,
                       "description": k.description, "system": where[k.name]["system"], "system_why": where[k.name]["why"],
                       "counts": counts.get(k.name, {})} for k in kinds.values()],
            "systems": systems, "unkinded": unkinded,
            "total": len(every) if plain else len(shown), "offset": offset,
            "items": [_listed(i, kinds, where) for i in (shown if plain else shown[offset:offset + n])]}


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
            "record": own[-500:]}
