"""What a change to the model predicts, stated (SPEC §12e): the closed-loop projection of the stocks it touches, as the
model is and with the change, over a stated horizon, said in one sentence ("backlog settles at 12 instead of 30
within 2h"). The review entry's effect shows it above the strip (``review.effect``); accepting the change records it
on its item (``predicted``); once its horizon has passed, the judge's pass reads what those stocks did and records it
beside the prediction (``observed``), so each change's prediction is held against what happened."""

from __future__ import annotations

from ..durations import human as dur
from ..spec.ir import Spec
from . import observe as ob
from . import yamledit as ye

SETTLED = 0.02          # a stock has settled once it stays within this share of where it ends (or of 1)
MOST = 3                # stocks said in the sentence, at most


def _settles(times: list[float], vals: list, now: float) -> tuple[float | None, float | None]:
    """Where it ends, and how long after now it came within SETTLED of that for good (None: still moving at the end)."""
    pts = [(t, v) for t, v in zip(times, vals or [], strict=False) if v is not None]
    if not pts:
        return None, None
    end = pts[-1][1]
    band = SETTLED * max(abs(end), 1.0)
    if any(abs(v - end) > band for _, v in pts[-max(2, len(pts) // 10):]):
        return end, None
    since = pts[-1][0]
    for t, v in reversed(pts):
        if abs(v - end) > band:
            break
        since = t
    return end, max(0.0, since - now)


def stated(spec: Spec, refs: list[str], before, after, now: float, horizon: float, loops: str = "closed") -> dict | None:
    """The prediction: each stock among ``refs`` (and the stocks of the flows among them) at the horizon as the model is
    and with the change, when it settles, and the sentence."""
    stocks = [r for r in refs if r.startswith("stock.")]
    stocks += [f"stock.{s}" for r in refs if r.startswith("flow.") and r[5:] in spec.flows
               for s in (spec.flows[r[5:]].source, spec.flows[r[5:]].target) if s and f"stock.{s}" not in stocks]
    got, words = {}, []
    for r in dict.fromkeys(stocks):
        b, tb = _settles(before.times, before.values.get(r), now)
        a, ta = _settles(after.times, after.values.get(r), now)
        if a is None or b is None:
            continue
        got[r] = {"before": round(b, 6), "after": round(a, 6), "settles_before": tb, "settles_after": ta}
        name, n = r[6:], ye.number
        if abs(a - b) <= 1e-6 * max(1.0, abs(b)):
            words.append(f"{name} {'settles' if ta is not None else 'ends'} at {n(a)}, as without it")
        elif ta is not None:
            words.append(f"{name} settles at {n(a)} instead of {n(b)} within {dur(ta) if ta else 'no time'}")
        else:
            words.append(f"{name} is at {n(a)} instead of {n(b)} at +{dur(horizon)}, still moving")
    if not got:
        return None
    more = f" (and {len(words) - MOST} more)" if len(words) > MOST else ""
    how = "with the loops running" if loops == "closed" else "held (open loop)"
    return {"at": now, "horizon": horizon, "loops": loops, "stocks": got,
            "said": "; ".join(words[:MOST]) + more + f" (projected over {dur(horizon)}, {how})"}


def of_change(p, spec: Spec, x: dict, at: float | None = None) -> dict | None:
    """The prediction of one change, as ``review.effect`` works it out (never written: the edit applied in memory)."""
    from ..web.numbers_api import horizon_of
    from . import review as rv
    from . import simulate as sim
    from . import trial as tr
    after = tr.spec_after(p, tr.edits_of(x))
    grid = ob.reference(p, at, rv.CHART_POINTS)
    data, data_a = ob.measured(p, grid), ob.measured(p, grid, after)
    run, run_a = sim.replay(spec, data, sim.plan(spec)), sim.replay(after, data_a, sim.plan(after))
    if not run_a.valid:
        return None
    horizon = horizon_of(run, grid.until - grid.since)
    points = max(2, round(rv.CHART_POINTS * horizon / max(grid.until - grid.since, 1.0)))
    b, a, loops = rv._projections(p, spec, after, data, data_a, run, run_a, horizon, points)
    return stated(after, rv._charted(after, [x], 4 * rv.CHARTS) or rv._charted(spec, [x], 4 * rv.CHARTS), b, a, grid.until,
                  horizon, loops) if a else None


def observe(p, now: float) -> int:
    """Each accepted change whose prediction's horizon has passed and that has no ``observed`` yet: each stock's last
    reading by the horizon, recorded on its item beside the prediction, with which it was nearer to. How many."""
    from . import proposals as pr
    spec, done = p.model.spec, 0
    for pid, x in pr.stored(p).items():
        w = x.get("predicted")
        if x["status"] != "accepted" or not w or x.get("observed") or now < w["at"] + w["horizon"]:
            continue
        data = ob.measured(p, ob.Grid(w["at"], w["at"] + w["horizon"], 24), spec)
        seen, words = {}, []
        for r, y in w["stocks"].items():
            v = data.last(r)
            if v is None:
                continue
            seen[r] = round(v, 6)
            nearer = "the change's prediction" if abs(v - y["after"]) <= abs(v - y["before"]) else "the model as it was"
            words.append(f"{r[6:]}: predicted {ye.number(y['after'])} ({ye.number(y['before'])} without it), observed "
                         f"{ye.number(v)}, nearer {nearer}")
        pr.event(p, pid, x["state"], {"observed": {"at": now, "stocks": seen,
                                                   "said": "; ".join(words) or "nothing it predicted was read by its horizon"}})
        done += 1
    return done
