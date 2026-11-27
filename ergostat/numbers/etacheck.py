"""The completion estimates held against what happened (SPEC §5a, *Completion estimates*): at past moments, each open
item's finish is estimated from the record before it alone, and compared with when it did finish. Said per set of
components (``eta.ABLATIONS``, in the tests) and per kind (the Timeline's calibration, from the eta worker): the mean
absolute error of the p50 (over the items that finished), its bias (the estimate's mean against what happened: a
median is below the mean of a skewed finish, so its own bias is not one), the share finished by their p50 (a half,
unbiased), and the p90's coverage (the share that finished by their p90; one estimated beyond the horizon, or not
given a p90, that finished is a miss). An item unfinished at the record's end is a miss when its p90 is before that
end, and otherwise cannot be judged: it is counted apart (``unresolved``), so a record must run long enough past its
cuts for that to be few."""

from __future__ import annotations

import math

from . import eta
from .etamodel import read

WEEK = 7 * 86400.0
CUTS = 4
RUNS = 100
BUDGET = 5.0          # seconds a cut's runs take at most (and its levelled run as much again)
FEW = 10             # fewer judged than this: too few to say


def _tally() -> dict:
    return {"got": [], "none": 0}


def _said(t: dict, latest: bool) -> dict:
    seen = [j for j in t["got"] if j[1] is not None]
    if latest:                                       # an item's latest judged cut kept; unresolved: never judged
        seen = list({j[0]: j for j in seen}.values())
        left = len({j[0] for j in t["got"]} - {j[0] for j in seen})
    else:
        left = len(t["got"]) - len(seen)
    n, errs, bias = len(seen), [j[3] for j in seen if j[3] is not None], [j[4] for j in seen if j[4] is not None]
    return {"items": n, "unresolved": left, "not_worked_out": t["none"],
            "mae": sum(errs) / len(errs) if errs else None, "coverage": sum(j[1] for j in seen) / n if n else None,
            "p50": sum(j[2] for j in seen) / n if n else None, "bias": sum(bias) / len(bias) if bias else None}


def score(inputs: list, end: float, flags: eta.Flags | None = None, runs: int = RUNS, budget: float = BUDGET,
          latest: bool = False) -> dict:
    """The estimates at each of ``inputs`` (read with ``truth``, earliest first) against what happened by ``end``:
    ``{"items", "unresolved", "not_worked_out", "mae" (seconds, of the p50), "coverage" (by the p90), "p50" (the share
    finished by their p50), "bias" (seconds, the mean − actual), "projections": {projection: the same}}``. Each estimate judged is
    counted, an item open at several cuts once a cut; ``latest``: only its latest judged cut's, so ``items`` counts
    items."""
    whole, kinds = _tally(), {}
    for inp in inputs:
        if not inp.items:
            continue
        got = eta.simulate(inp, flags or eta.Flags(), runs=runs, budget=budget)
        for it in inp.items.values():
            kinds.setdefault(it.kind, _tally())
        if not got["runs"]:                          # no run finished within the budget: not worked out
            for it in inp.items.values():
                whole["none"] += 1
                kinds[it.kind]["none"] += 1
            continue
        for i, x in got["items"].items():
            done, p50, p90 = inp.finished_at.get(i), x["p50"], x["p90"]
            if done is None:                         # not finished by the record's end: a miss if its p90 is past,
                j = (i, False, False, None, None) if p90 is not None and p90 < end else (i, None, None, None, None)
            else:                                    # (else not judged: unresolved)
                j = (i, p90 is not None and done <= p90, p50 is not None and done <= p50,
                     abs(p50 - done) if p50 is not None else None,
                     x["mean"] - done if x.get("mean") is not None else None)
            for t in (whole, kinds[inp.items[i].kind]):
                t["got"].append(j)
    return {**_said(whole, latest), "projections": {k: _said(t, latest) for k, t in kinds.items()}}


def cuts(now: float, n: int = CUTS, over: float = WEEK) -> list[float]:
    """``n`` moments over the last ``over`` seconds before ``now``, the earliest ``over`` ago, evenly apart."""
    return [now - over * (n - j) / n for j in range(n)]


def calibration(p, spec, kinds: list[str], now: float, runs: int = RUNS, budget: float = BUDGET) -> dict[str, dict]:
    """Each kind → ``{"coverage", "items", "mae", "since", "said"}``: last week's estimates, at ``CUTS`` moments,
    against what happened by ``now`` (the record read up to ``now`` only); an item open at several cuts is judged
    once, by its latest judged cut, so ``items`` counts items."""
    at = cuts(now)
    last = p.events.query(n=1, until=now)
    end = min(now, last[0]["time"]) if last else now
    got = score([read(p, spec, kinds, t, truth=True) for t in at], end, runs=runs, budget=budget, latest=True)["projections"]
    out = {}
    for k in kinds:
        g = got.get(k) or {"items": 0, "coverage": None, "mae": None}
        c = {"coverage": g["coverage"], "items": g["items"], "mae": g["mae"], "since": at[0]}
        out[k] = {**c, "said": said(k, c)}
    return out


def said(kind: str, c: dict) -> str:
    """The Timeline's clause for a kind: 'last week's estimates: 8 in 10 tickets finished by their p90 (41 tickets)',
    the share rounded down (never said better than it was)."""
    many = kind if kind.endswith("s") else kind + "s"
    if c["items"] < FEW or c["coverage"] is None:
        return f"{many}: too few finished last week to check"
    return (f"last week's estimates: {math.floor(c['coverage'] * 10 + 1e-9)} in 10 {many} finished by their p90 "
            f"({c['items']} {many})")
