"""The model's operating state (normal, maintenance, freeze, incident) and the owner's presence (present, away), folded
from the record (SPEC §12k, *The operating state*). Each change is the owner's typed act: an
``ergostat.operating.STATE`` event, source ``owner``. Nothing is gated on it yet."""

from __future__ import annotations

import math
import time
from typing import NamedTuple

from ..durations import human

KIND = "ergostat.operating"
STATES = ("normal", "maintenance", "freeze", "incident")
LAYERS = ("incident", "freeze", "maintenance")        # strongest first: the first one held is the state in force
OWNER = "owner"
MOST_LEASE = 86400.0                                    # a maintenance lease is at most a day
AWAY_AFTER, AWAY_LEAST, AWAY_MOST = 7200.0, 300.0, 7 * 86400.0


class Operating(NamedTuple):
    state: str
    presence: str
    seq: int | None                                     # the event the state was read from (None: none recorded)
    reason: str
    note: str | None = None
    until: float | None = None                          # a maintenance lease's end
    actions: tuple = ()                                 # what a maintenance lease names


class OperatingError(Exception):
    """An act on the operating state that cannot be recorded as asked."""


def enter(p, state: str, note: str | None = None, lease: float | None = None, actions=()) -> dict:
    """Record the owner's act: enter ``state`` (``normal`` ends the state in force). Maintenance is a lease of
    ``lease`` seconds, more than 0 and at most a day."""
    if state not in STATES:
        raise OperatingError(f"{state!r}: one of {', '.join(STATES)}")
    if (lease is not None or actions) and state != "maintenance":
        raise OperatingError("--for and --actions belong to maintenance only")
    data: dict = {}
    if state == "maintenance":
        if lease is None or not math.isfinite(lease) or not 0 < lease <= MOST_LEASE:
            raise OperatingError(f"maintenance is a lease: --for a duration of at most {human(MOST_LEASE)} (it lapses "
                                 f"on its own)")
        data = {"until": time.time() + lease, "actions": [str(a) for a in actions]}
    if note:
        data["note"] = note
    return p.events.add(f"{KIND}.{state}", item=KIND, source=OWNER, data=data)


def fold(events: list[dict], now: float) -> tuple[str, int | None, str, dict]:
    """The state in force, the seq it was read from, why, and that entry's data. In ``seq`` order, never by ``at``:
    each entry replaces its layer whole (nothing carried from an earlier one); ``normal`` ends the strongest layer."""
    layers: dict[str, dict] = {}
    last = None
    for e in sorted(events, key=lambda e: e["seq"]):
        st = e["type"][len(KIND) + 1:]
        if st not in STATES:
            return "incident", e["seq"], f"event {e['seq']} names no operating state ({e['type']}): read as incident", {}
        last = e
        if st == "normal":
            top = next((x for x in LAYERS if x in layers), None)
            layers.pop(top, None)
        else:
            layers[st] = e
    lapsed = None
    for st in LAYERS:
        e = layers.get(st)
        if e is None:
            continue
        d = e.get("data") or {}
        if st == "maintenance":
            u = d.get("until")
            if isinstance(u, bool) or not isinstance(u, int | float) or not math.isfinite(u):
                return "incident", e["seq"], f"maintenance of event {e['seq']}: its end is not a number, read as incident", {}
            if now >= u:
                lapsed = e
                continue
        return st, e["seq"], f"{st}, entered by the owner (event {e['seq']})", d
    if lapsed is not None:
        return "normal", lapsed["seq"], f"normal: the maintenance lease of event {lapsed['seq']} lapsed", {}
    if last is not None:
        return "normal", last["seq"], f"normal: the state in force was ended by the owner (event {last['seq']})", {}
    return "normal", None, "normal: no operating state recorded", {}


def presence(p, away_after: float, now: float) -> tuple[str, str]:
    """``away`` when the record holds no event from the owner for ``away_after`` seconds; else ``present``."""
    got = p.events.query(n=1, source=OWNER)
    t = got[-1]["time"] if got else None
    if isinstance(t, bool) or not isinstance(t, int | float) or not math.isfinite(t):
        return "away", "no event from the owner on record"
    if now - t > away_after:
        return "away", f"no event from the owner for {human(now - t)} (away after {human(away_after)})"
    return "present", f"the owner's last event {human(max(now - t, 0))} ago"


def read(p, now: float | None = None) -> Operating:
    """The operating state now, the owner's presence, the seq it was read from, and why. A record that cannot be read
    counts as incident and away."""
    now = time.time() if now is None else now
    try:
        st, seq, why, d = fold(p.events.query(n=None, type=f"{KIND}.*"), now)
        pr, pwhy = presence(p, away_after(p), now)
    except Exception as e:                              # (unreadable: the strictest case, never normal)
        return Operating("incident", "away", None, f"the record cannot be read ({type(e).__name__}: {e}): read as "
                         f"incident, the owner as away")
    acts = d.get("actions")
    return Operating(st, pr, seq, f"{why}; {pr}: {pwhy}", d.get("note") and str(d["note"]), d.get("until"),
                     tuple(str(a) for a in acts) if isinstance(acts, list) else ())


def away_after(p) -> float:
    return getattr(getattr(p.model, "spec", None), "away_after", AWAY_AFTER)
