"""Reading ``operating:`` (SPEC §9.5, *Operating states*) into the spec, every mistake said with where it was written.
Called by the spec compiler with itself, for its ``keys``, ``duration`` and ``err``; after the goals, which trips name.
A model without ``operating:`` gets nothing: no kind, no fold read, no trip check (invariant 12)."""

from __future__ import annotations

import re

from ..spec.ir import OperatingState
from . import KIND, kind

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
KEYS = {"rank", "pool", "description", "trips"}
TRIP_KEYS = {"unknown-after"}
AWAY = "away-after"


def _whole(c, m, key: str, least: int, what: str) -> int | None:
    v = m.get(key)
    if isinstance(v, bool) or not isinstance(v, int) or v < least:
        c.err(f"{what}.{key}: a whole number, {least} or more", m.at(key) or m.where, "bad-number")
        return None
    return v


def section(c, spec) -> None:
    body = c.doc.sections.get("operating") or {}
    if not body:
        return
    ranks: dict[int, str] = {}
    for name, m in body.items():
        if name == AWAY:                                 # the owner's presence (SPEC §12k, actions/compile.py): no state
            continue
        what, w = f"operating state {name}", c.doc.defined[("operating", name)]
        if not isinstance(name, str) or not NAME.match(name):
            c.err(f"{what}: a name is lowercase letters, digits and -, starting with a letter or digit, at most 64",
                  w, "bad-name")
            continue
        if not isinstance(m, dict):
            c.err(f"{what}: a map of its keys (rank:, pool:, description:, trips:)", w, "not-a-map")
            continue
        m.where = m.where or w
        c.keys(m, KEYS, what)
        rank = _whole(c, m, "rank", 1, what)
        pool = _whole(c, m, "pool", 0, what) if m.get("pool") is not None else None
        if rank is not None and rank in ranks:
            c.err(f"{what}.rank: {rank} is {ranks[rank]}'s already: each state its own rank", m.at("rank"), "rank-taken")
            rank = None
        if rank is None:
            continue
        ranks[rank] = name
        spec.operating[name] = OperatingState(name, rank, pool, c.text(m, "description"), _trips(c, spec, m, what), m.where)
    if spec.operating:
        spec.items[KIND] = kind()                    # built in, when declared: the states entered and left
    climb = sorted(spec.operating.values(), key=lambda s: s.rank)
    for low, high in zip(climb, climb[1:], strict=False):          # (readability: in_force takes the least pool entered anyway)
        if (low.pool is not None) and (high.pool is None or high.pool > low.pool):
            c.err(f"operating state {high.name}: pool {'none' if high.pool is None else high.pool} above {low.name}'s "
                  f"{low.pool} at a lower rank: going up the ranks a pool stays the same or falls", high.where,
                  "pool-rises-with-rank")


def _trips(c, spec, m, what: str) -> dict[str, float | None]:
    raw = m.get("trips")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        c.err(f"{what}.trips: a map from a goal to {{unknown-after: DURATION}} or {{}}", m.at("trips"), "not-a-map")
        return {}
    out: dict[str, float | None] = {}
    for goal, t in raw.items():
        at = raw.at(goal) if hasattr(raw, "at") else m.at("trips")
        w = f"{what}.trips.{goal}"
        if goal not in c.doc.sections["goals"]:
            c.err(f"{w}: {goal!r} is not a goal" + c.suggest(str(goal), c.doc.sections["goals"]), at, "unknown-ref",
                  f"goal.{goal}")
            continue
        if t is not None and not isinstance(t, dict):
            c.err(f"{w}: {{unknown-after: DURATION}}, or {{}} for its crossing only", at, "not-a-map")
            continue
        after = None
        if t:
            t.where = getattr(t, "where", None) or at
            c.keys(t, TRIP_KEYS, w)
            after = c.duration(t, "unknown-after", w)
            if after is not None and after <= 0:
                c.err(f"{w}.unknown-after: a duration above 0", t.at("unknown-after"), "bad-duration")
                after = None
            g = spec.goals.get(goal)
            parts = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries}
            part = parts.get(g.of.kind, {}).get(g.of.name) if g else None
            if after is not None and g is not None and not (part and part.sensors):
                c.err(f"{w}.unknown-after: {g.of} has no sensor, so it is never read: nothing to time", t.at("unknown-after"),
                      "unknown-after-unmeasured")
                after = None
        out[str(goal)] = after
    return out
