"""What a change to the model forecasts, stated (SPEC §12e). A change to the model changes nothing in the world: it
revises the model's forecast. Each change's forecast is the closed-loop projection of the stocks it touches, as the model
is and with the change, over a stated horizon (``review.forecast``, the one function the review entry's strip and the
recorded forecast both come from), said in one sentence ("with it the model forecasts backlog settling at 12 within
2h; 30 as it is"). Accepting the change records it on its item (``predicted``); once its horizon has passed, the
judge's pass reads what those stocks did over the forecast's last ``WINDOW`` of the horizon and records it beside the
forecast (``observed``), with which forecast it was nearer to: the revised one or the model's as it was."""

from __future__ import annotations

from statistics import fmean

from ..durations import human as dur
from ..spec.ir import Spec
from . import observe as ob
from . import yamledit as ye

SETTLED = 0.02          # a stock has settled once it stays within this share of where it ends (or of 1)
WINDOW = 0.25           # the forecast is compared over this last share of its horizon: a mean, not one reading
MOST = 3                # stocks said in the sentence, at most


def _settles(times: list[float], vals: list, now: float) -> tuple[float | None, float | None]:
    """Its mean over the last WINDOW of the horizon, and how long after now it came within SETTLED of where it ends
    for good (None: still moving at the end)."""
    pts = [(t, v) for t, v in zip(times, vals or [], strict=False) if v is not None]
    if not pts:
        return None, None
    end = pts[-1][1]
    tail = [v for t, v in pts if t >= now + (1 - WINDOW) * (pts[-1][0] - now)] or [end]
    band = SETTLED * max(abs(end), 1.0)
    if any(abs(v - end) > band for _, v in pts[-max(2, len(pts) // 10):]):
        return fmean(tail), None
    since = pts[-1][0]
    for t, v in reversed(pts):
        if abs(v - end) > band:
            break
        since = t
    return fmean(tail), max(0.0, since - now)


def stated(spec: Spec, refs: list[str], before, after, now: float, horizon: float, loops: str = "closed") -> dict | None:
    """The forecast: each stock among ``refs`` (and the stocks of the flows among them), its mean over the horizon's
    last WINDOW as the model is and with the change, when it settles, and the sentence."""
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
            words.append(f"{name} at {n(a)}, unchanged")
        elif ta is not None:
            words.append(f"{name} settling at {n(a)} within {dur(ta) if ta else 'no time'} ({n(b)} as it is)")
        else:
            words.append(f"{name} at {n(a)} by +{dur(horizon)}, still moving ({n(b)} as it is)")
    if not got:
        return None
    more = f" (and {len(words) - MOST} more)" if len(words) > MOST else ""
    how = "with the loops running" if loops == "closed" else "held (open loop)"
    return {"at": now, "horizon": horizon, "window": [now + (1 - WINDOW) * horizon, now + horizon], "loops": loops,
            "stocks": got, "said": f"with it the model forecasts {'; '.join(words[:MOST])}{more} (over {dur(horizon)}, {how})"}


def of_change(p, spec: Spec, x: dict, at: float | None = None) -> dict | None:
    """The forecast of one change, exactly as its review entry shows it (the edit applied in memory, never written)."""
    from . import review as rv
    from . import trial as tr
    return rv.forecast(p, spec, tr.spec_after(p, tr.edits_of(x)), [x], at)["predicts"]


def _observed(p, spec: Spec, pid: str, x: dict, now: float) -> dict:
    w = x["predicted"]
    since, until = w.get("window") or (w["at"] + (1 - WINDOW) * w["horizon"], w["at"] + w["horizon"])
    data = ob.measured(p, ob.Grid(since, until, 12), spec)
    seen, words = {}, []
    for r, y in w["stocks"].items():
        vals = [v for v in data.values.get(r) or [] if v is not None]
        if not vals:
            continue
        v = seen[r] = round(fmean(vals), 6)
        nearer = "the revised forecast" if abs(v - y["after"]) <= abs(v - y["before"]) else "the model's forecast as it was"
        words.append(f"{r[6:]}: forecast {ye.number(y['after'])} with the change ({ye.number(y['before'])} without), observed "
                     f"{ye.number(v)} on average over {len(vals)} readings, nearer {nearer}")
    return {"at": now, "window": [since, until], "stocks": seen,
            "said": "; ".join(words) or "nothing it forecast was read in its window"}


def observe(p, now: float) -> int:
    """Each accepted change whose forecast's horizon has passed and that has no ``observed`` yet: what its stocks did
    over the forecast's window, recorded on its item beside the forecast. How many were recorded (one that cannot be
    read is left for the next pass, and never stops the rest)."""
    from . import proposals as pr
    spec, done = p.model.spec, 0
    for pid, x in pr.stored(p).items():
        w = x.get("predicted")
        if x["status"] != "accepted" or not w or x.get("observed") or now < w["at"] + w["horizon"]:
            continue
        try:
            pr.event(p, pid, x["state"], {"observed": _observed(p, spec, pid, x, now)})
            done += 1
        except Exception:                                    # one change's record unreadable: the others still are
            continue
    return done
