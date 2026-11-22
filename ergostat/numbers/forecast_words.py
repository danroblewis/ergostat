"""A goal's forecast (closedloop.risk's Monte Carlo) in words a product manager can act on: a sentence, a short form
for the goal row's ``expected`` cell, and how it was worked out (p, the runs, the horizon, the method) for a title and
a closed disclosure. One function, so every surface says the same."""

from __future__ import annotations

import math
import time

LIKELY = 0.5        # the share of runs that have crossed (or come back) by which a moment is named


def odds(q: float) -> str:
    """A chance as 'N in 10', rounded half up; under 0.05 and over 0.95 said as under 1 and over 9."""
    n = math.floor(q * 10 + 0.5)
    return "under 1 in 10" if n < 1 else "over 9 in 10" if n > 9 else f"{n} in 10"


def about(q: float) -> str:
    """The odds as said in a sentence: 'about 7 in 10', but plainly 'under 1 in 10' and 'over 9 in 10' at the ends."""
    n = odds(q)
    return n if n[0] in "uo" else f"about {n}"


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


def _form(p0: float, ever_off: list, ever_on: list, at: list, ahead: str, now: float) -> tuple[str, str, float | None]:
    """The sentence, its short form and its chance, from the share of runs off at the first moment and the shares that
    have been off (and back within) at some moment by each moment ahead: whole runs, so a chance is for the horizon."""
    if p0 >= LIKELY:
        back = next((i for i, v in enumerate(ever_on) if v >= LIKELY), None)
        if back is not None:
            return f"Expected back within its bound by {clock(at[back], now)}", f"back by {clock(at[back], now)}", None
        return f"Likely to stay outside its bound {ahead}", "off", 1 - ever_on[-1]
    cross = next((i for i, v in enumerate(ever_off) if v >= LIKELY), None)
    if cross is not None:
        return f"Likely to cross its bound around {clock(at[cross], now)}", f"cross ~{clock(at[cross], now)}", ever_off[-1]
    return f"Likely to stay within its bound {ahead}", "within", 1 - ever_off[-1]


def said(got: dict | None, goal: str, now: float, why: str = "too little history") -> dict:
    """``{"sentence", "short", "title", "how": [[label, value]]}``; with no forecast for the goal, 'No estimate: WHY'.
    Runs that were not valid count as off; when they change what the sentence says, the sentence says how many."""
    x = ((got or {}).get("goals") or {}).get(goal)
    made, invalid = (got or {}).get("made") or 0, (got or {}).get("invalid") or 0
    if x and made and invalid >= made:
        why = f"none of the {made} runs of the model was valid"
    elif got is not None and got.get("stopped"):
        why = got["stopped"]
    if not x or not made or not x.get("p_off") or invalid >= made:
        return {"sentence": f"No estimate: {why}", "short": "no estimate", "title": why, "how": []}
    from .closedloop import MOST_HORIZON
    p, horizon = x["p_off"], min(got["horizon"], MOST_HORIZON)
    at = [now + (i + 1) * horizon / len(p) for i in range(len(p))]
    ahead = f"for the next {span(horizon)}"
    text, short, q = _form(p[0], x["p_ever_off"], x["p_ever_on"], at, ahead, now)
    valid = made - invalid                      # invalid runs are off at every moment: never back, off from the first
    alone = _form((p[0] * made - invalid) / valid, [(v * made - invalid) / valid for v in x["p_ever_off"]],
                  [v * made / valid for v in x["p_ever_on"]], at, ahead, now)
    notes = [about(q)] if q is not None else []
    short += f", {odds(q)}" if q is not None else ""
    if invalid and (alone[0], alone[2] is not None and about(alone[2])) != (text, q is not None and about(q)):
        notes.append(f"{invalid} of {made} runs not valid, counted as off")
    sentence = text + (f" ({'; '.join(notes)})" if notes else "")
    runs = f"{made}" + (f" ({invalid} not valid, counted as off)" if invalid else "")
    how = [["chance off at the horizon", f"p≈{x['p_off_end']:.2g}"], ["highest chance off", f"p≈{max(p):.2g}"],
           ["chance off at some moment", f"p≈{x['p_ever_off'][-1]:.2g}"],
           ["runs", runs + (f"; {got['stopped']}" if got.get("stopped") else "")],
           ["horizon", f"{span(horizon)}, to {clock(now + horizon, now)}"],
           ["method", "the loops run forward that many times over the identified models', the estimates' and the "
                      "inputs' errors (a fixed seed); a chance is the share of runs that leave (or come back within) "
                      "the bound at some moment ahead, and a time is when half the runs have"]]
    return {"sentence": sentence, "short": short, "title": "; ".join(f"{k}: {v}" for k, v in how), "how": how}
