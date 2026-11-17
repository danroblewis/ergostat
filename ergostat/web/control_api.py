"""The page's view of a loop as a control engineer reads it (``GET /api/loop-control?goal=g``): its
process identified, its controller's law, their step responses, Bode plot and margins, the loop's
performance, and the proposals (``ergostat/control``); and the owner's answers to those proposals
(``POST /api/control/ID/accept`` or ``/dismiss``), the page's only other writes."""

from __future__ import annotations

import threading

from ..control import loop as lp
from ..control import proposals as cp

WORKING = threading.Lock()        # one analysis at a time: each fits a few hundred models


def get(live, p, snap: dict, goal: str) -> dict | None:
    if getattr(p.model, "spec", None) is None or goal not in p.model.spec.goals:
        return None
    key = ("control", goal, live.mtime, snap["at"] if not snap.get("live", True) else round(snap["at"] / 30))
    got = live.cached(key)
    if got is not None:
        return got
    with WORKING:
        got = live.cached(key)
        if got is not None:
            return got
        a = lp.analyse(p, goal, None if snap.get("live", True) else snap["at"])
        if a is not None:
            a["proposals"] = cp.offered(p, a)
            a["decided"] = {k: v for k, v in cp.decisions(p).items() if v.get("goal") == goal}
        live.keep(key, a)
    return a


def post(live, path: str) -> tuple[int, dict]:
    p = live.get()
    parts = path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "control" or parts[2] not in ("accept", "dismiss"):
        return 404, {"error": "not found"}
    if getattr(p.model, "spec", None) is None:
        return 400, {"error": "the model is an ergostat.toml: a process is written in ergostat.yaml"}
    try:
        if parts[2] == "dismiss":
            got = cp.dismiss(p, parts[1])
        else:
            got = cp.accept(p, parts[1], by="owner")
            live.reloaded()
    except cp.ProposalError as e:
        return 409, {"error": str(e)}
    forget(live)
    return 200, got


def forget(live) -> None:
    """A decision made: the loops' analyses are worked out again, without what was decided."""
    with live._lock:
        for k in [k for k in live._kept if isinstance(k, tuple) and k and k[0] == "control"]:
            live._kept.pop(k, None)
