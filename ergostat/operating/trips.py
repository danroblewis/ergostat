"""Trips (SPEC §9.5, *Operating states*): a goal's condition entering a state, once per spell, judged from the record
only, so a restart neither enters again nor resets a clock. Run by the dispatcher's thread once a second, under its
lock, across the read, the decision and the write.

A trip ``(state, goal)`` has a current spell:

- **crossing**: the goal's newest unvoided ``loop.*`` event is ``loop.off``: ``off:<its id>``;
- **unread** (with ``unknown-after``): each sensor of the goal's part has its newest reading; the clock starts at the
  oldest of them (one live sensor never hides a dead one), or, when a sensor was never read, at this trip's
  ``watching`` event (written by the first check that finds none). Past ``unknown-after``: ``unread:<sensor>:<its
  reading's time>`` or ``unread:<sensor>:never``.

A spell no earlier ``entered`` of the state names is recorded as ``entered`` by trip, whether the state is entered or
not, so the owner's later ``leave`` covers it. Spells are compared for equality on what was read (ids, stored reading
times), never as newer or older."""

from __future__ import annotations

import time

from . import ENTERED, WATCHING, item_of

SOURCE = "ergostat"


def _part(spec, goal):
    g = spec.goals.get(goal)
    if g is None:
        return None
    return {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries}.get(g.of.kind, {}).get(g.of.name)


def _watching(p, state: str, goal: str) -> float | None:
    got = [e for e in p.events.query(n=None, item=f"goal.{goal}", type=WATCHING) if (e.get("data") or {}).get("state") == state]
    return got[0]["time"] if got else None


def _spells(p, spec, state: str, goal: str, after: float | None, now: float, watch: list) -> list[tuple]:
    """The current spells of one trip: ``(spell, cause, why)``. Raises when an input cannot be read."""
    out = []
    last = p.events.query(n=1, item=goal, type="loop.*", unvoided=True)
    if last and last[-1]["type"] == "loop.off":
        out.append((f"off:{last[-1]['id']}", last[-1]["id"], f"goal {goal} off"))
    if after is None:
        return out
    part = _part(spec, goal)
    reads = {name: p.measurements.latest(s.series) for name, s in sorted((part.sensors if part else {}).items())}
    if not reads:
        raise LookupError(f"goal {goal}: its part has no sensor to time")
    never = [n for n, r in reads.items() if r is None]
    if never:
        start = _watching(p, state, goal)
        if start is None:                                      # (written once; its time is the clock's start)
            watch.append((state, goal))
            start = now
        sensor, spell = never[0], f"unread:{never[0]}:never"
    else:
        sensor = min(reads, key=lambda n: reads[n][0])
        start = reads[sensor][0]
        spell = f"unread:{sensor}:{start!r}"
    if now - start > after:
        out.append((spell, None, f"goal {goal}: sensor {sensor} unread for {now - start:.0f}s (unknown-after {after:g}s)"))
    return out


def answered(p, state: str) -> set[tuple[str, str]]:
    """The (goal, spell) pairs every earlier ``entered`` of the state named."""
    return {(d.get("goal"), d.get("spell")) for e in p.events.query(n=None, item=item_of(state), type=ENTERED)
            for d in [e.get("data") or {}] if d.get("spell") is not None}


def _record(p, state: str, goal: str, spell: str, cause: str | None, why: str) -> dict:
    return p.events.add(ENTERED, item=item_of(state), source=SOURCE, causedby=cause,
                        data={"by": "trip", "why": why, "goal": goal, "spell": spell})


def check(p, spec, now: float | None = None, say=lambda s: None) -> str | None:
    """Every trip looked at once: each spell not yet answered entered. Returns None, or why the trips' inputs could not
    be read: then nothing is recorded, and dispatch holds (pool 0) until a check reads cleanly."""
    if not spec.operating:
        return None
    now = time.time() if now is None else now
    todo, watch = [], []
    try:
        for state, st in sorted(spec.operating.items()):
            if not st.trips:
                continue
            done = answered(p, state)
            for goal, after in sorted(st.trips.items()):
                todo += [(state, goal, *s) for s in _spells(p, spec, state, goal, after, now, watch) if (goal, s[0]) not in done]
    except Exception as e:
        return f"the trips' inputs could not be read ({type(e).__name__}: {e}): pool 0 until they can"
    for state, goal in watch:
        p.events.add(WATCHING, item=f"goal.{goal}", source=SOURCE, at=now, data={"state": state})
    for state, goal, spell, cause, why in todo:
        _record(p, state, goal, spell, cause, why)
        say(f"operating: {state} entered by trip ({why})")
    return None
