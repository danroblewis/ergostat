"""How the improvement loop itself is doing, as built-in measures a goal can hold (SPEC §12f), beside the improver's
own ``ergostat.model.*`` (``fit``, ``unexplained``, ``unidentified-loops``, ``open-findings``, which say how good the
model is). Over the last ``WEEK`` of record:

- ``ergostat.model.accepted-per-day``: changes written to the model, a day;
- ``ergostat.model.regressed``: changes written that the prediction check (``verify.py``) flagged for revert;
- ``ergostat.model.verified-share``: of the changes checked, the share whose forecasts held (none until one is);
- ``ergostat.model.fit-gained``: what the changes written lowered the scaled error by, together (each one's fit
  before minus after, as Accept measured it): the fit over time, as the loop moved it;
- ``ergostat.model.cost-per-accepted``: what the blocks that make changes spent (the ``cost_usd`` their runs
  record), over the changes written (none while nothing is written);
- ``ergostat.model.reviews-passed``, ``-revised``, ``-rejected``: the reviewer's verdicts (``reviewer.py``), and
  ``ergostat.model.review-misses``: changes it passed that the prediction check later flagged for revert.

Each is read by a sensor like the model's own (``builtin: ergostat.model.accepted-per-day``); ``ergostat measure``
and ``ergostat bench meta`` print them."""

from __future__ import annotations

import time

from ..bench import adapter as ad
from ..spec.ir import MODEL_MEASURES

WEEK = 7 * 86400.0
MEASURES = {n: d for n, d in MODEL_MEASURES.items() if n in (
    "ergostat.model.accepted-per-day", "ergostat.model.regressed", "ergostat.model.verified-share",
    "ergostat.model.fit-gained", "ergostat.model.cost-per-accepted", "ergostat.model.reviews-passed",
    "ergostat.model.reviews-revised", "ergostat.model.reviews-rejected", "ergostat.model.review-misses")}


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
    for t, k in ((ad.VERIFIED, "verified"), (ad.REGRESSED, "regressed")):
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


def _reviews(which: str):
    def read(p, now: float | None = None) -> float:     # the reviewer's verdicts over the week, and its misses
        from . import reviewer as rv
        now = now or time.time()
        return float(rv.counts(p, now - WEEK, now)[which])
    return read


READERS = {"ergostat.model.accepted-per-day": accepted_per_day, "ergostat.model.regressed": regressed,
           "ergostat.model.verified-share": verified_share, "ergostat.model.fit-gained": fit_gained,
           "ergostat.model.cost-per-accepted": cost_per_accepted, "ergostat.model.reviews-passed": _reviews("pass"),
           "ergostat.model.reviews-revised": _reviews("revise"), "ergostat.model.reviews-rejected": _reviews("reject"),
           "ergostat.model.review-misses": _reviews("missed")}


def all_of(p, now: float | None = None) -> dict[str, float | None]:
    return {n: f(p, now) for n, f in READERS.items()}
