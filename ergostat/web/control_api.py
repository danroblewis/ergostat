"""The page's view of a loop as a control engineer reads it (``GET /api/loop-control?goal=g``): its
process identified, its controller's law, their step responses, Bode plot and margins, the loop's
performance, and the proposals (``ergostat/control``); and the owner's answers to those proposals
(``POST /api/control/ID/accept`` or ``/dismiss``), the page's only other writes."""

from __future__ import annotations

import threading

from ..control import loop as lp
from ..control import proposals as cp
from ..webaccess import who

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
        a = _analysed(p, goal, None if snap.get("live", True) else snap["at"])
        live.keep(key, a)
    return a


def _analysed(p, goal: str, at: float | None) -> dict | None:
    a = lp.analyse(p, goal, at)
    if a is not None:
        a["proposals"] = cp.offered(p, a)
        a["decided"] = {k: v for k, v in cp.decisions(p).items() if v.get("goal") == goal}
    return a


PERF_LIFE = 300.0     # a goal's performance, worked out in the background, is worked out again after 5 minutes


def summary(a: dict | None) -> dict:
    """What performanceWord (control.js), processWord and nextWord (review.js) read of an analysis, without its charts;
    ``not_analysed`` as loop-control's null."""
    if a is None:
        return {"not_analysed": True}
    pick = lambda d, *ks: {k: d[k] for k in ks if k in (d or {})}        # noqa: E731
    return {**pick(a, "why", "performance", "u", "y", "declared", "known", "step_test_waiting", "step_test_refused",
                    "systems"),
            "identified": pick(a.get("identified"), "found", "proposable", "why"),
            "tuning": pick(a.get("tuning"), "why"), "controller": pick(a.get("controller"), "law", "says"),
            "proposals": [{"kind": x.get("kind")} for x in a.get("proposals") or []]}


def performances(live, p, snap: dict, goals) -> dict:
    """Each goal's summary from the background (goal_work.py), ``{"working": True}`` until worked out, ``None`` for a
    loop that is no goal of the model's: never an identification in the request itself."""
    mine = [g for g in goals if g in (getattr(getattr(p.model, "spec", None), "goals", None) or {})]

    def work(goal, at):
        with WORKING:
            return summary(_analysed(p, goal, at))
    got = live.work.ask("performance", mine, None if snap.get("live", True) else snap["at"], live.mtime, work, PERF_LIFE)
    return {g: (got[g] or {"working": True}) if g in got else None for g in goals}


def post(live, path: str) -> tuple[int, dict]:
    p = live.get()
    parts = path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "control" or parts[2] not in ("accept", "dismiss"):
        return 404, {"error": "not found"}
    if getattr(p.model, "spec", None) is None:
        return 400, {"error": "the model is an ergostat.toml: a process is written in ergostat.yaml"}
    try:
        if parts[2] == "dismiss":
            got = cp.dismiss(p, parts[1], by=who())
        else:
            got = cp.accept(p, parts[1], by=who())
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
    live.work.forget("performance")
