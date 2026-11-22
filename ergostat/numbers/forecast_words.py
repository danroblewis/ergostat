"""A goal's forecast (closedloop.risk's Monte Carlo) in words a product manager can act on: a sentence, a short form
for the goal row's ``expected`` cell, and how it was worked out (p, the runs, the horizon, the method) for a title and
a closed disclosure. One function, so every surface says the same."""

from __future__ import annotations

import math
import time

LIKELY = 0.5        # the chance of being off at which a moment reads as off


def odds(q: float) -> str:
    """A chance as 'N in 10', rounded half up; under 0.05 and over 0.95 said as under 1 and over 9."""
    n = math.floor(q * 10 + 0.5)
    return "under 1 in 10" if n < 1 else "over 9 in 10" if n > 9 else f"{n} in 10"


def clock(t: float, now: float) -> str:
    """A clock time: '14:10' today, 'Tue 14:10' within the week, else 'Nov 30 14:10' (local time)."""
    a, b = time.localtime(t), time.localtime(now)
    same = (a.tm_year, a.tm_yday) == (b.tm_year, b.tm_yday)
    return time.strftime("%H:%M" if same else "%a %H:%M" if abs(t - now) < 6 * 86400 else "%b %d %H:%M", a)


def span(s: float) -> str:
    """A duration in whole minutes, hours or days: '8 minutes', '3 hours', '2 days'."""
    for unit, size, upto in (("minute", 60, 90 * 60), ("hour", 3600, 48 * 3600), ("day", 86400, math.inf)):
        if s < upto:
            n = max(1, round(s / size))
            return f"{n} {unit}{'s' if n != 1 else ''}"
    return ""


def said(got: dict | None, goal: str, now: float, why: str = "too little history") -> dict:
    """``{"sentence", "short", "title", "how": [[label, value]]}``; with no forecast for the goal, 'No estimate: WHY'."""
    x = ((got or {}).get("goals") or {}).get(goal)
    if not x or not got.get("made") or not x.get("p_off"):
        why = why if got is None or not got.get("stopped") else got["stopped"]
        return {"sentence": f"No estimate: {why}", "short": "no estimate", "title": why, "how": []}
    from .closedloop import MOST_HORIZON
    p, horizon = x["p_off"], min(got["horizon"], MOST_HORIZON)
    at = [now + (i + 1) * horizon / len(p) for i in range(len(p))]
    ahead = f"for the next {span(horizon)}"
    if p[0] >= LIKELY:
        back = next((i for i, v in enumerate(p) if v < LIKELY), None)
        sentence, short = ((f"Expected back within its bound by {clock(at[back], now)}", f"back by {clock(at[back], now)}")
                           if back is not None else
                           (f"Likely to stay outside its bound {ahead} (about {odds(p[-1])})", f"off, {odds(p[-1])}"))
    else:
        cross = next((i for i, v in enumerate(p) if v >= LIKELY), None)
        sentence, short = ((f"Likely to cross its bound around {clock(at[cross], now)} (about {odds(max(p))})",
                            f"cross ~{clock(at[cross], now)}, {odds(max(p))}") if cross is not None else
                           (f"Likely to stay within its bound {ahead} (about {odds(1 - max(p))})",
                            f"within, {odds(1 - max(p))}"))
    runs = f"{got['made']}" + (f" ({got['invalid']} not valid, counted as off)" if got.get("invalid") else "")
    how = [["chance off at the horizon", f"p≈{x['p_off_end']:.2g}"], ["highest chance off", f"p≈{max(p):.2g}"],
           ["runs", runs + (f"; {got['stopped']}" if got.get("stopped") else "")],
           ["horizon", f"{span(horizon)}, to {clock(now + horizon, now)}"],
           ["method", "the loops run forward that many times over the identified models', the estimates' and the "
                      "inputs' errors (a fixed seed); a moment reads as off when half the runs or more are off"]]
    return {"sentence": sentence, "short": short, "title": "; ".join(f"{k}: {v}" for k, v in how), "how": how}
