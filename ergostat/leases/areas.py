"""Areas that one stream at a time owns (SPEC §9.5, *Areas*): ``takes: {..., areas: {touches: FIELD, holding: [STATE],
map: {AREA: {paths: [PATTERN], owner: OWNER}}}}``. Off unless declared.

An item touches an area when a value of its FIELD (a text, or a list of them) matches one of the area's patterns
(``fnmatch``: ``*`` matches any run of characters, ``/`` included). An item **holds** the areas it touches while it is
leased, or in a ``holding`` state. An item not holding already is not taken while an area it touches is held by another
stream; once it holds, no area keeps it waiting (it entered first, so two holders never wait on each other). The
owner says what a stream is: ``lane`` (the default), each item its own, so one item at a time; ``{field: F}``, the
items sharing a value of F (a milestone's items together, and the next value once they are out); ``{block: B}``, the
area is block B's: no other block with this option takes an item touching it. Within one look, each item let through
holds its areas for the items after it.

A FIELD that cannot be read (not a text or a list of texts, or past ``TOUCHES`` values) touches every area: such an
item waits while any area is held, and, held, keeps every area (lesson-3: an unknown is the worst case). Said once."""

from __future__ import annotations

import json
import re
from fnmatch import fnmatchcase

from ..spec.ir import Area, Areas
from .fold import held as leased

KEYS, AREA_KEYS = {"touches", "holding", "map"}, {"paths", "owner"}
MOST = 200            # areas in a map at most
PATHS = 200           # patterns in an area at most
TOUCHES = 5000        # values of an item's field at most (more: unreadable, so every area)
NAME = re.compile(r"[^\s-]\S*")
OWNER = "lane, {field: F} (the items sharing F's value) or {block: B} (only block B takes them)"


# ---- the model

def compile_areas(c, raw, what: str) -> Areas | None:
    a = raw.get("areas")
    if a is None:
        return None
    w = f"{what}.takes.areas"
    if not isinstance(a, dict):
        c.err(f"{w}: a map: touches: (the item field naming what it touches), holding: (states) and map: (each area's "
              f"paths: and owner:)", raw.at("areas"), "bad-areas")
        return None
    c.keys(a, KEYS, w)
    t, hold, m = a.get("touches"), a.get("holding", []), a.get("map")
    hold = [hold] if isinstance(hold, str) else hold
    if not isinstance(t, str) or not NAME.fullmatch(t):
        c.err(f"{w}.touches: an item field's name (its text, or list of texts, says what the item touches)",
              a.at("touches") or raw.at("areas"), "bad-areas")
        return None
    if not isinstance(hold, list) or not all(isinstance(s, str) and s for s in hold):
        c.err(f"{w}.holding: a state, or a list of them (an item in one holds the areas it touches)",
              a.at("holding") or raw.at("areas"), "bad-areas")
        return None
    if not isinstance(m, dict) or not m or len(m) > MOST:
        c.err(f"{w}.map: a map of 1 to {MOST} areas, each {{paths: [PATTERN], owner: OWNER}}",
              a.at("map") or raw.at("areas"), "bad-areas")
        return None
    out = []
    for name, ar in m.items():
        got = area(c, name, ar, m.at(name), f"{w}.map.{name}")
        if got is None:
            return None
        out.append(got)
    return Areas(t, tuple(dict.fromkeys(hold)), tuple(out))


def area(c, name, ar, at, w: str) -> Area | None:
    if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(ar, dict):
        c.err(f"{w}: an area's name, and a map: paths: (patterns) and owner: ({OWNER})", at, "bad-areas")
        return None
    c.keys(ar, AREA_KEYS, w)
    ps = ar.get("paths")
    ps = [ps] if isinstance(ps, str) else ps
    if not isinstance(ps, list) or not 0 < len(ps) <= PATHS or not all(isinstance(p, str) and p.strip() for p in ps):
        c.err(f"{w}.paths: a pattern, or a list of 1 to {PATHS} (ergostat/leases/*.py)", ar.at("paths") or at,
              "bad-areas")
        return None
    o = ar.get("owner", "lane")
    if o == "lane":
        return Area(name, tuple(ps))
    if isinstance(o, dict) and len(o) == 1 and next(iter(o)) in ("field", "block") \
            and isinstance(v := next(iter(o.values())), str) and NAME.fullmatch(v):
        return Area(name, tuple(ps), next(iter(o)), v)
    c.err(f"{w}.owner: {OWNER}", ar.at("owner") or at, "bad-areas")
    return None


def check(c, spec, b) -> None:
    """The holding states are the kind's; a block owner is a block of the model. Else the option is refused whole."""
    a, k = b.takes.areas, spec.items.get(b.takes.kind)
    if a is None or k is None:
        return
    bad = [s for s in a.holding if s not in k.states]
    bad += [f"block {x.by!r}" for x in a.map if x.owner == "block" and x.by not in spec.blocks]
    if bad:
        c.err(f"block {b.name}.takes.areas: {', '.join(bad)}: not a state of {k.name} or a block of the model",
              b.where, "bad-areas")
        b.takes.areas = None


# ---- the rule

def touched(a: Areas, fields: dict) -> set[str] | None:
    """The areas an item touches; None when its field cannot be read (it touches them all)."""
    v = (fields or {}).get(a.touches)
    if v is None or v == "" or v == []:
        return set()
    v = [v] if isinstance(v, str) else v
    if not isinstance(v, list) or len(v) > TOUCHES or not all(isinstance(x, str) for x in v):
        return None
    return {ar.name for ar in a.map if any(fnmatchcase(x, p) for p in ar.paths for x in v)}


def stream(ar: Area, it) -> str:
    """Who an item is in this area: itself on a lane; its F's value on a field owner (none: itself)."""
    if ar.owner == "field":
        v = (it.fields or {}).get(ar.by)
        if v not in (None, "", [], {}):
            return "=" + (v if isinstance(v, str) else json.dumps(v, sort_keys=True))
    return "#" + it.id


def only(d, b, got: list, every: list) -> list:
    """Of the items a block may take (in its order), those no other stream's hold keeps out; each let through holds
    its areas for those after it. Off (``got`` as it is) unless the block declares ``areas:``."""
    a = getattr(b.takes, "areas", None)
    if a is None or not got:
        return got
    said = d.__dict__.setdefault("areas_said", set())
    by = {ar.name: ar for ar in a.map}
    going = d.going_items()
    holds: dict[str, dict[str, str]] = {n: {} for n in by}      # area → stream → an item holding it

    def hold(it, ns) -> None:
        for n in by if ns is None else ns:
            holds[n].setdefault(stream(by[n], it), it.id)

    def tell(key, msg) -> None:
        if key not in said:
            said.add(key)
            d.e.say(f"{b.name}: {msg}")

    for i in every:
        if leased(i.fields) or i.state in a.holding or i.id in going:
            ns = touched(a, i.fields)
            if ns is None:
                tell((i.id, "unread"), f"{i.id}'s {a.touches} cannot be read: it holds every area")
            hold(i, ns)
    out = []
    for it in got:
        ns = touched(a, it.fields)
        if ns is None:
            tell((it.id, "unread"), f"{it.id}'s {a.touches} cannot be read: it waits while any area is held")
        if it.state not in a.holding:
            mine = sorted(by if ns is None else ns)
            if other := next((n for n in mine if by[n].owner == "block" and by[n].by != b.name), None):
                tell((it.id, other), f"{it.id} is left to block {by[other].by}: it touches {other}")
                continue
            busy = next(((n, x) for n in mine if by[n].owner != "block"
                         for s, x in holds[n].items() if s != stream(by[n], it) and x != it.id), None)
            if busy:
                tell((it.id, busy), f"{it.id} waits: {busy[1]} holds {busy[0]}")
                continue
        hold(it, ns)
        out.append(it)
    return out
