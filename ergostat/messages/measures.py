"""How the owner's messages reach the work, as measures (SPEC §12h): ``ergostat.messages.*``.

``unrouted`` and ``awaiting`` are levels, now: the messages that reached no work, and those routed and not yet
delivered. ``received``, ``routed``, ``delivered``, ``answered`` and ``missed`` count those over the last ``WEEK``;
``reached`` is the share of the messages received then that were delivered. A sensor reads one (``builtin:
ergostat.messages.unrouted``) on a stock or an auxiliary, so a goal can hold it."""

from __future__ import annotations

import time

from ..spec.ir import MESSAGE, MESSAGE_MEASURES
from . import record

WEEK = 7 * 86400.0


def counts(p, now: float | None = None, since: float | None = None) -> dict[str, float]:
    now = time.time() if now is None else now
    since = now - WEEK if since is None else since
    msgs = record.stored(p, until=now)
    out = {"unrouted": 0, "awaiting": 0, "received": 0, "routed": 0, "delivered": 0, "answered": 0, "missed": 0}
    reached = 0
    for m in msgs.values():
        if m["state"] == "unrouted":
            out["unrouted"] += 1
        elif m["state"] == "routed":
            out["awaiting"] += 1
        if m["time"] >= since:
            out["received"] += 1
            if any(mv["to"] in ("delivered", "answered") for mv in m["moves"]):
                reached += 1
    steps = p.events.query(n=None, type=f"{MESSAGE}.routed,{MESSAGE}.delivered,{MESSAGE}.answered,{MESSAGE}.missed",
                           since=since, until=now)
    for what in ("routed", "delivered", "answered", "missed"):
        out[what] = len({e["item"] for e in steps if e["type"] == f"{MESSAGE}.{what}"})
    out["reached"] = reached / out["received"] if out["received"] else 0.0
    return {k: float(v) for k, v in out.items()}


def measure(p, name: str, now: float | None = None) -> float:
    if name not in MESSAGE_MEASURES:
        raise ValueError(f"no measure {name!r}: {', '.join(MESSAGE_MEASURES)}")
    return counts(p, now)[name.rsplit(".", 1)[1]]
