"""How well the replay fits what was measured, as system dynamics measures it (Sterman, "Appropriate
summary statistics for evaluating the historical fit of system dynamics models", *Dynamica*, 1984;
*Business Dynamics*, ch. 21): for each stock, and in total,

- **R²**: how much of the measured variation the replay moves with (the squared correlation);
- **MAPE**: the mean absolute error as a share of what was measured (over the points not 0);
- **Theil's inequality statistics**, which split the mean squared error into where it comes from:
  **U_M**, bias (the replay runs high or low on average), **U_S**, unequal variation (it swings
  more or less than the record) and **U_C**, unequal covariation (it moves at other moments: the
  point-by-point noise a model need not reproduce). They sum to 1. A good fit has its error mostly
  in U_C; a large U_M or U_S is a systematic error worth a structural question.

Computed on demand, and recorded per model version over time (``<state>/fit/history.jsonl``)."""

from __future__ import annotations

import json
import math
import time

from .. import series
from ..spec.ir import Spec
from . import simulate as sim
from . import version as ver

RECORD_EVERY = 300.0             # a version's fit is recorded at most this often
HISTORY_FILE = "fit/history.jsonl"
WORDS = {
    "r2": "how much of the measured variation the replay moves with (1: all of it)",
    "mape": "the mean absolute error, as a share of what was measured",
    "um": "bias: the replay runs high or low on average",
    "us": "unequal variation: it swings more, or less, than the record",
    "uc": "unequal covariation: it moves at other moments (noise a model need not follow)",
}


def stats(sim_: list, meas: list) -> dict | None:
    """The fit of one series: n, R², MAPE, RMSE, the means, and Theil's U_M, U_S, U_C."""
    pts = [(s, a) for s, a in zip(sim_, meas, strict=False) if s is not None and a is not None]
    n = len(pts)
    if n < 3:
        return None
    ms = sum(s for s, _ in pts) / n
    ma = sum(a for _, a in pts) / n
    ss = math.sqrt(sum((s - ms) ** 2 for s, _ in pts) / n)
    sa = math.sqrt(sum((a - ma) ** 2 for _, a in pts) / n)
    mse = sum((s - a) ** 2 for s, a in pts) / n
    r = (sum((s - ms) * (a - ma) for s, a in pts) / n / (ss * sa)) if ss > 0 and sa > 0 else None
    nonzero = [(s, a) for s, a in pts if abs(a) > 1e-12]
    mape = sum(abs(s - a) / abs(a) for s, a in nonzero) / len(nonzero) if nonzero else None
    out = {"n": n, "r2": None if r is None else r * r, "mape": mape, "mape_n": len(nonzero), "rmse": math.sqrt(mse),
           "mean_replay": ms, "mean_measured": ma, "mse": mse, "um": None, "us": None, "uc": None}
    if mse > 1e-18:
        out["um"] = (ms - ma) ** 2 / mse
        out["us"] = (ss - sa) ** 2 / mse
        out["uc"] = max(0.0, 1.0 - out["um"] - out["us"])          # 2(1 − r)·S_s·S_a / MSE, by its definition
    else:
        out["exact"] = True                                         # no error to split: the replay is the record
    out["scale"] = sa * sa + ma * ma                                # for a total across units
    return out


def total(per: dict[str, dict]) -> dict | None:
    """Across stocks in different units: R² and MAPE their means; Theil's shares from the squared
    errors each scaled by its stock's own size (mean square measured), so no unit outweighs another."""
    got = [s for s in per.values() if s]
    if not got:
        return None
    r2 = [s["r2"] for s in got if s["r2"] is not None]
    mape = [s["mape"] for s in got if s["mape"] is not None]
    scaled = [(s, s["scale"] or 1.0) for s in got]
    mse = sum(s["mse"] / k for s, k in scaled)
    parts = {u: sum((s[u] or 0.0) * s["mse"] / k for s, k in scaled) / mse if mse > 1e-18 else None for u in ("um", "us", "uc")}
    return {"stocks": len(got), "n": sum(s["n"] for s in got), "r2": sum(r2) / len(r2) if r2 else None,
            "mape": sum(mape) / len(mape) if mape else None, "nmse": mse / len(got), **parts}


def compare(spec: Spec, data: sim.Data, run: sim.Run) -> dict:
    """Each stock the replay integrated, and each equation whose part is measured, against the record."""
    stocks, eqs = {}, {}
    for ref, vals in run.values.items():
        meas = data.values.get(ref)
        if meas is None or (not ref.startswith("stock.") and all(v is None for v in meas)):
            continue                                 # an equation whose part nothing measures: nothing to compare
        got = stats(vals, meas)
        (stocks if ref.startswith("stock.") else eqs)[ref] = got
    return {"stocks": stocks, "equations": eqs, "total": total(stocks)}


def objective(fit: dict, refs: set[str] | None = None) -> float | None:
    """One number to make small: each series' mean squared error over its own size, summed."""
    vals = [s["mse"] / (s["scale"] or 1.0) for part in ("stocks", "equations") for r, s in fit[part].items()
            if s and (refs is None or r in refs)]
    return sum(vals) if vals else None


def compute(p, snap: dict, n: int | None = None) -> tuple[sim.Data, sim.Run, dict]:
    spec = p.model.spec
    since, until = series.span(p, snap)
    data = sim.measured(p, sim.Grid(since, until, n or series.POINTS))
    run = sim.replay(spec, data)
    return data, run, compare(spec, data, run)


def _slim(s: dict | None) -> dict | None:
    return None if s is None else {k: (round(v, 6) if isinstance(v, float) else v) for k, v in s.items()
                                   if k in ("n", "r2", "mape", "um", "us", "uc", "rmse", "stocks", "exact")}


def history_path(p):
    return p.dir / HISTORY_FILE


def history(p) -> list[dict]:
    try:
        return [json.loads(x) for x in history_path(p).read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def record(p, fit: dict, window: float, force: bool = False, now: float | None = None) -> dict | None:
    """Keep this version's fit in its history: at most every RECORD_EVERY seconds, unless forced (an
    accepted proposal records the fit after it at once)."""
    spec = p.model.spec
    now = time.time() if now is None else now
    v, st = ver.version(spec), ver.structure(spec)
    past = [h for h in history(p) if h.get("version") == v]
    if past and not force and now - past[-1]["time"] < RECORD_EVERY:
        return None
    entry = {"time": now, "version": v, "structure": st, "window": window, "total": _slim(fit["total"]),
             "stocks": {r: _slim(s) for r, s in fit["stocks"].items()}}
    path = history_path(p)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def versions(p) -> list[dict]:
    """The history, one row per version: when it was first and last fitted, its latest total fit."""
    rows: dict[str, dict] = {}
    for h in history(p):
        r = rows.setdefault(h["version"], {"version": h["version"], "structure": h.get("structure"), "first": h["time"]})
        r.update(last=h["time"], total=h.get("total"), window=h.get("window"), fits=r.get("fits", 0) + 1)
    return sorted(rows.values(), key=lambda r: r["first"])
