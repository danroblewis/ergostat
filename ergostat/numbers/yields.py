"""Group counts (SPEC §5a, *Group counts*): from the one simulation's runs (``eta.simulate``'s ``counts``: per run, when
each of a set's open members came out and when each was lost), how many come out by a date, the chance at least N
do, the expected loss, and how many to start to get N out at a stated confidence. In yield's terms: a member **comes
out** when it reaches a finished state that is not a loss; it is **lost** when it ends dead, or in a finished state
its kind declares ``lost:``; one that does neither within the horizon (or cannot move) is neither.

How many to start (``start``): the smallest M with P(Binomial(M, y) ≥ N) ≥ the confidence, where y is the share of
these members that came out by the date over every run (each started item taken to come out as these did, alone of
the others; not a simulation of the extra items' own waits)."""

from __future__ import annotations

import bisect
import math

MOST_N = 10_000             # the most an ask may want out, and the most it may say to start
MOST_BY = 500               # a group's members said one by one in ``by`` (the k-th out's date)


def _stats(xs: list[float]) -> dict:
    v = sorted(xs)
    q = lambda u: v[min(len(v) - 1, int(u * len(v)))]   # noqa: E731
    return {"mean": round(sum(v) / len(v), 3), "p10": q(0.1), "p50": q(0.5), "p90": q(0.9)}


def _date(xs: list[float], u: float) -> float | None:
    v = sorted(xs)
    x = v[min(len(v) - 1, int(u * len(v)))]
    return None if x == math.inf else x


def summary(members: int, draws: list) -> dict:
    """The forecast's own group counts: how many come out and are lost within the horizon (mean, p10, p50, p90), the
    yield, and ``by``: for each k up to ``MOST_BY``, the dates by which at least k are out in half and in nine tenths
    of the runs (``[k, p50, p90]``, None past the horizon)."""
    outs = [len(o) for o, _ in draws]
    by = [[k, _date(ks, 0.5), _date(ks, 0.9)]
          for k in range(1, min(members, MOST_BY) + 1)
          for ks in [[o[k - 1] if len(o) >= k else math.inf for o, _ in draws]]]
    return {"members": members, "out": _stats(outs), "lost": _stats([len(lo) for _, lo in draws]),
            "yield": round(sum(outs) / (members * len(draws)), 4) if members else None, "by": by}


def _whole(v) -> int:
    if isinstance(v, bool) or isinstance(v, float) and not v.is_integer():
        raise ValueError(v)
    return int(v)


def parse(q: dict) -> dict | None:
    """An ask from a request's ``group``, ``by`` (Unix seconds), ``at_least`` and ``confidence``; None when it names
    no group. A value that is not one raises ValueError with the words, never read as not asked."""
    g = q.get("group")
    if g is None:
        return None
    if not isinstance(g, str) or not g:
        raise ValueError("group: a group's parent id")
    out: dict = {"group": g}
    for key, cast, ok, words in (("by", float, math.isfinite, "a time, in Unix seconds"),
                                 ("at_least", _whole, lambda n: 1 <= n <= MOST_N, f"a whole number from 1 to {MOST_N}"),
                                 ("confidence", float, lambda c: 0 < c < 1, "a share between 0 and 1, not either")):
        v = q.get(key)
        if v is None:
            continue
        try:
            out[key] = cast(v)
            good = not isinstance(v, bool) and ok(out[key])
        except (TypeError, ValueError, OverflowError):
            good = False
        if not good:
            raise ValueError(f"{key}: {words}, not {str(v)[:40]!r}")
    if "confidence" in out and "at_least" not in out:
        raise ValueError("confidence: how sure to be of at_least out; give at_least too")
    return out


def ask(members: int, draws: list, asked: dict) -> dict:
    """One ask's answer (``parse``): by ``by`` (else the horizon), how many come out and are lost, the chance at least
    ``at_least`` come out, and with ``confidence`` how many to start to get that many out."""
    by = asked.get("by", math.inf)
    outs = [bisect.bisect_right(o, by) for o, _ in draws]
    got = {**asked, "members": members, "runs": len(draws), "out": _stats(outs),
           "lost": _stats([bisect.bisect_right(lo, by) for _, lo in draws])}
    n = asked.get("at_least")
    if n is not None:
        got["chance"] = round(sum(x >= n for x in outs) / len(outs), 4)
    if n is not None and "confidence" in asked:
        y = sum(outs) / (members * len(draws)) if members else 0.0
        got["start"] = start_for(n, asked["confidence"], y)
    return got


def _tail(m: int, n: int, y: float) -> float:
    """P(Binomial(m, y) ≥ n), summed in logs (exact, no normal approximation)."""
    if n <= 0:
        return 1.0
    if y >= 1.0:
        return 1.0 if m >= n else 0.0
    ly, lq = math.log(y), math.log1p(-y)
    base = math.lgamma(m + 1)
    below = sum(math.exp(base - math.lgamma(j + 1) - math.lgamma(m - j + 1) + j * ly + (m - j) * lq)
                for j in range(min(n, m + 1)))
    return max(0.0, 1.0 - below)


def start_for(n: int, confidence: float, y: float) -> dict:
    """``{"n": M, "yield": y}``: the fewest to start for at least ``n`` out with ``confidence``; ``n`` None and
    ``none`` why when none come out, or more than ``MOST_N`` would be needed."""
    if y <= 0:
        return {"n": None, "yield": 0.0, "none": "no member comes out in any run: no number started is enough"}
    lo, hi = n, n
    while _tail(hi, n, y) < confidence:
        if hi >= MOST_N:
            return {"n": None, "yield": round(y, 4), "none": f"more than {MOST_N} would be needed"}
        lo, hi = hi + 1, min(MOST_N, hi * 2)
    while lo < hi:                                     # (the chance only grows with more started)
        mid = (lo + hi) // 2
        lo, hi = (lo, mid) if _tail(mid, n, y) >= confidence else (mid + 1, hi)
    return {"n": lo, "yield": round(y, 4)}
