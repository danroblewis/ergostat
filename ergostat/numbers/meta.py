"""How the improvement loop itself is doing, as built-in measures a goal can hold (SPEC §12f), beside the improver's
own ``ergostat.model.*`` (``fit``, ``unexplained``, ``unidentified-loops``, ``open-findings``, which say how good the
model is). Over the last ``WEEK`` of record:

- ``ergostat.model.accepted-per-day``: changes written to the model, a day;
- ``ergostat.model.regressed``: changes written that the prediction check (``verify.py``) flagged for revert;
- ``ergostat.model.verified-share``: of the changes checked, the share whose forecasts held (none until one is);
- ``ergostat.model.fit-gained``: what the changes written lowered the scaled error by, together (each one's fit
  before minus after, as Accept measured it): the fit over time, as the loop moved it;
- ``ergostat.model.cost-per-accepted``: what the blocks that make changes spent (the ``cost_usd`` their runs
  record), over the changes written (none while nothing is written).

``ergostat bench meta`` prints them. Read through ``bench/adapter.py``, so they mean the same on either loop."""

from __future__ import annotations

import time

from ..bench import adapter as ad

WEEK = 7 * 86400.0
MEASURES = {
    "ergostat.model.accepted-per-day": "changes written to the model a day, over the last week",
    "ergostat.model.regressed": "changes written over the last week that the prediction check flagged for revert",
    "ergostat.model.verified-share": "of the changes the prediction check scored over the last week, the share whose "
                                     "forecasts held",
    "ergostat.model.fit-gained": "what the changes written over the last week lowered the scaled error by, together",
    "ergostat.model.cost-per-accepted": "dollars the blocks that make changes spent over the last week, over the "
                                        "changes written",
}


def _since(p, now: float) -> float:
    first = p.events.first_time() or now
    return max(now - WEEK, first)


def accepted_per_day(p, now: float | None = None) -> float:
    now = now or time.time()
    since = _since(p, now)
    n = sum(1 for x in ad.Loop(p).accepted() if since <= x["time"] <= now)
    return n / max((now - since) / 86400.0, 1.0)


def _verdicts(p, since: float, now: float) -> dict[str, int]:
    out = {"verified": 0, "regressed": 0}
    for t, k in ((ad.VERIFIED, "verified"), (ad.VERIFIED_OUT, "verified"), (ad.REGRESSED, "regressed"),
                 (ad.REGRESSED_OUT, "regressed")):
        out[k] += len(p.events.query(n=None, type=t, since=since, until=now))
    return out


def regressed(p, now: float | None = None) -> float:
    now = now or time.time()
    return float(_verdicts(p, now - WEEK, now)["regressed"])


def verified_share(p, now: float | None = None) -> float | None:
    now = now or time.time()
    v = _verdicts(p, now - WEEK, now)
    n = v["verified"] + v["regressed"]
    return v["verified"] / n if n else None


def fit_gained(p, now: float | None = None) -> float:
    now = now or time.time()
    total = 0.0
    for x in ad.Loop(p).accepted():
        if now - WEEK <= x["time"] <= now:
            a = x.get("applied") or {}
            b, f = (a.get("fit_before") or {}).get("nmse"), (a.get("fit_after") or {}).get("nmse")
            if b is not None and f is not None:
                total += b - f
    return total


def cost_per_accepted(p, now: float | None = None) -> float | None:
    now = now or time.time()
    since = now - WEEK
    loop = ad.Loop(p)
    makers = {x.get("made_by") for x in loop.changes().values() if x.get("made_by")} - {None, "ergostat", "owner"}
    n = sum(1 for x in loop.accepted() if since <= x["time"] <= now)
    if not n:
        return None
    spent = 0.0
    for e in p.events.query(n=None, since=since, until=now):
        c = (e.get("data") or {}).get("cost_usd")
        item = str(e.get("item") or "").rsplit("/", 1)[-1]
        if isinstance(c, int | float) and (e.get("source") in makers or any(item.startswith(f"{m}-") for m in makers)):
            spent += float(c)
    return spent / n


READERS = {"ergostat.model.accepted-per-day": accepted_per_day, "ergostat.model.regressed": regressed,
           "ergostat.model.verified-share": verified_share, "ergostat.model.fit-gained": fit_gained,
           "ergostat.model.cost-per-accepted": cost_per_accepted}


def all_of(p, now: float | None = None) -> dict[str, float | None]:
    return {n: f(p, now) for n, f in READERS.items()}
