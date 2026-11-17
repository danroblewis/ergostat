"""How well the model fits what was measured, as system dynamics measures it (Sterman, "Appropriate
summary statistics for evaluating the historical fit of system dynamics models", *Dynamica*, 1984;
*Business Dynamics*, ch. 21): for each series, and in total,

- **R²**: how much of the measured variation the replay moves with (the squared correlation);
- **MAPE**: the mean absolute error as a share of what was measured, only where no reading is near
  0 (else the mean absolute error as a share of the readings' mean, or of their range when they
  cross 0: a percentage of almost nothing says nothing);
- **Theil's inequality statistics**, which split the mean squared error into where it comes from:
  **U_M**, bias (the replay runs high or low on average), **U_S**, unequal variation (it swings
  more or less than the record) and **U_C**, unequal covariation (it moves at other moments: the
  point-by-point noise a model need not reproduce). They sum to 1. A good fit has its error mostly
  in U_C; a large U_M or U_S with a large error is a systematic error, and is said in words.

Like is compared with like: the model is read through the same measurement as the record
(``observe.py``): a level at its reading's moment, a counted flow by what it moved in each bucket, a
rate a sensor averages over a window by the model's own average over that window.

Two tests, each shown as itself (Homer, "Partial-model testing", 2012):

- the **partial-model test**: each equation against its part's readings with every input as
  measured, no stock integrated: the sharpest test of one equation;
- the **replay**: every stock integrated from its flows. The stocks an equation moves are the
  **model fit**, and they alone make the total and its history; a stock moved only by measured
  flows tests no equation, and is **accounting**: its error is a question about a measurement or a
  missing flow (the residuals), not about the model's equations.

A series is judged only on enough record: ``MIN_POINTS`` points, over at least ``COVER`` of the
slowest time constant the replay met in it. Computed on the reference window (``observe.reference``),
whatever the page shows, and recorded per model version over time (``<state>/fit/history.jsonl``)."""

from __future__ import annotations

import json
import math
import time

from ..durations import human as dur
from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim
from . import version as ver

RECORD_EVERY = 300.0             # a version's fit is recorded at most this often
HISTORY_FILE = "fit/history.jsonl"
MIN_POINTS = 10                  # fewer points than this say too little to judge a fit
COVER = 3.0                      # the record must span this many of the slowest time constant met
NEAR_ZERO = 0.1                  # a reading below this share of the mean |reading| makes MAPE meaningless
LARGE = 0.1                      # an error is large past this share of the readings' size; a share of it past this, worth saying
WORDS = {
    "r2": "how much of the measured variation the replay moves with (1: all of it)",
    "mape": "the mean absolute error, as a share of what was measured (where readings reach 0: of their mean, or range)",
    "um": "bias: the replay runs high or low on average",
    "us": "unequal variation: it swings more, or less, than the record",
    "uc": "unequal covariation: it moves at other moments (noise a model need not follow)",
    "partial": "each equation against its readings with every input as measured: the partial-model test",
    "replay": "each equation and stock with every stock integrated from its flows",
    "accounting": "stocks moved only by measured flows: they test no equation; an error here is a measurement's, or a missing flow's",
}


def stats(sim_: list, meas: list) -> dict | None:
    """The fit of one series: n, R², MAPE (or the error's share of the readings' mean or range),
    RMSE, the means, Theil's U_M, U_S, U_C, and what its error says in words."""
    pts = [(s, a) for s, a in zip(sim_, meas, strict=False) if s is not None and a is not None]
    n = len(pts)
    if n < 3:
        return None
    ms = sum(s for s, _ in pts) / n
    ma = sum(a for _, a in pts) / n
    ss = math.sqrt(sum((s - ms) ** 2 for s, _ in pts) / n)
    sa = math.sqrt(sum((a - ma) ** 2 for _, a in pts) / n)
    mse = sum((s - a) ** 2 for s, a in pts) / n
    mae = sum(abs(s - a) for s, a in pts) / n
    r = (sum((s - ms) * (a - ma) for s, a in pts) / n / (ss * sa)) if ss > 0 and sa > 0 else None
    size = sum(abs(a) for _, a in pts) / n
    lo, hi = min(a for _, a in pts), max(a for _, a in pts)
    near = lo < 0 < hi or size == 0 or any(abs(a) < NEAR_ZERO * size for _, a in pts)
    out = {"n": n, "r2": None if r is None else r * r, "rmse": math.sqrt(mse), "mae": mae,
           "mean_replay": ms, "mean_measured": ma, "sd_replay": ss, "sd_measured": sa, "mse": mse, "um": None, "us": None, "uc": None}
    if near:
        base, of = ((size, "mean") if not lo < 0 < hi and size > 0 else (hi - lo, "range"))
        out.update(mape=None, error_share=(mae / base) if base > 0 else None, error_of=of)
    else:
        out.update(mape=sum(abs(s - a) / abs(a) for s, a in pts) / n, error_share=None, error_of=None)
    if mse > 1e-18 and mse > 1e-12 * (ma * ma + sa * sa):
        out["um"] = (ms - ma) ** 2 / mse
        out["us"] = (ss - sa) ** 2 / mse
        out["uc"] = max(0.0, 1.0 - out["um"] - out["us"])          # 2(1 − r)·S_s·S_a / MSE, by its definition
    else:
        out["exact"] = True                                         # no error to split: the replay is the record
    out["scale"] = sa * sa + ma * ma                                # for a total across units
    out["says"] = says(out)
    return out


def says(s: dict) -> str:
    """A large error's kind, in words (Sterman 1984): bias, unequal swing, or only timing."""
    if s.get("exact") or s.get("um") is None:
        return ""
    size = max(abs(s["mean_measured"]), s["sd_measured"], 1e-12)
    if s["rmse"] <= LARGE * size:
        return ""
    words = []
    if s["um"] > LARGE:
        words.append("runs high" if s["mean_replay"] > s["mean_measured"] else "runs low")
    if s["us"] > LARGE:
        words.append("swings more than the record" if s["sd_replay"] > s["sd_measured"] else "swings less than the record")
    if not words:
        words.append("out of step with the record")
    return ", and ".join(words)


def total(per: dict[str, dict]) -> dict | None:
    """Across stocks in different units: R² and MAPE their means; Theil's shares from the squared
    errors each scaled by its stock's own size (mean square measured), so no unit outweighs another."""
    got = [s for s in per.values() if s and not s.get("too_little")]
    if not got:
        return None
    r2 = [s["r2"] for s in got if s["r2"] is not None]
    mape = [s["mape"] for s in got if s["mape"] is not None]
    scaled = [(s, s["scale"] or 1.0) for s in got]
    mse = sum(s["mse"] / k for s, k in scaled)
    parts = {u: sum((s[u] or 0.0) * s["mse"] / k for s, k in scaled) / mse if mse > 1e-18 else None for u in ("um", "us", "uc")}
    return {"stocks": len(got), "n": sum(s["n"] for s in got), "r2": sum(r2) / len(r2) if r2 else None,
            "mape": sum(mape) / len(mape) if mape else None, "nmse": mse / len(got), **parts}


# ---- the model read through the record's own measurement

def _cumulative(moved: list) -> list[float]:
    c = [0.0]
    for m in moved:
        c.append(c[-1] + (m or 0.0))
    return c


def _at(c: list[float], edges: list[float], t: float) -> float:
    w = (edges[-1] - edges[0]) / (len(edges) - 1)
    x = (t - edges[0]) / w
    i = max(0, min(int(x), len(edges) - 2))
    return c[i] + (c[i + 1] - c[i]) * (x - i)


def pairs(spec: Spec, data: ob.Data, run: sim.Run, ref: str) -> list[tuple[int, float, float]] | None:
    """The model and the record of one part, bucket by bucket, on one basis: (bucket, model, measured).
    None when there is nothing to compare (not measured, or not something this run works out)."""
    meas = data.values.get(ref)
    if meas is None or ref not in run.how or all(v is None for v in meas):
        return None
    g = data.grid
    kind = ref.split(".", 1)[0]
    if kind in ("stock", "auxiliary"):
        at = data.at.get(ref) or []
        exact = run.at_reading.get(ref)
        return [(i, m, a) for i, (t, a) in enumerate(zip(at, meas, strict=False))
                if t is not None and a is not None and
                (m := (exact[i] if exact and exact[i] is not None else None if exact else run.value_at(ref, t))) is not None]
    moved = run.moved.get(ref)
    if moved is None:
        return None
    w_h = g.width / 3600.0
    window = data.window.get(ref, 0.0)
    if ob.is_counted(data, ref) or window <= g.width:
        return [(i, moved[i] / w_h, a) for i, a in enumerate(meas) if a is not None and moved[i] is not None]
    c, edges, times = _cumulative(moved), run.edges, g.times()
    return [(i, (_at(c, edges, times[i]) - _at(c, edges, times[i] - window)) * 3600.0 / window, a)
            for i, a in enumerate(meas) if a is not None and times[i] - window >= g.since]


def _judged(s: dict | None, span_h: float, slowest: float | None) -> dict | None:
    if s is None:
        return None
    if s["n"] < MIN_POINTS:
        s["too_little"] = f"{s['n']} points; at least {MIN_POINTS} are needed"
    elif slowest and span_h < COVER * slowest:
        s["too_little"] = (f"the record spans {dur(span_h * 3600)}, under {COVER:g} of its slowest time constant "
                           f"({dur(slowest * 3600)})")
    return s


def _stats(spec, data, run, ref, slowest: float | None = None) -> dict | None:
    got = pairs(spec, data, run, ref)
    if not got:
        return None
    s = stats([m for _, m, _ in got], [a for _, _, a in got])
    if s is not None:
        span = (data.grid.width * (got[-1][0] - got[0][0] + 1)) / 3600.0
        s = _judged(s, span, slowest)
    return s


def moved_by_equation(spec: Spec, run: sim.Run, stock: str) -> bool:
    return any(run.how.get(f"flow.{f.name}") == "equation" for f in spec.flows_of(stock))


def compare(spec: Spec, data: ob.Data, run: sim.Run, partial: sim.Run | None = None) -> dict:
    """The replay's stocks (the model fit, and accounting), its equations, and the partial test of
    each equation, against the record."""
    stocks, accounting, eqs, part, judged_by = {}, {}, {}, {}, {}
    for ref in run.how:
        if not ref.startswith("stock."):
            continue
        name = ref[6:]
        tc = run.time_constants.get(ref)
        got = _stats(spec, data, run, ref, tc)
        (stocks if moved_by_equation(spec, run, name) else accounting)[ref] = got
    for ref, how in run.how.items():
        if how != "equation":
            continue
        if ob.from_its_stock(spec, ref):
            f = spec.flows[ref[5:]]
            judged_by[ref] = next((f"stock.{s}" for s in (f.target, f.source) if s), None)
            continue
        tc = run.time_constants.get(ref)
        got = _stats(spec, data, run, ref, tc)
        if got is not None:
            eqs[ref] = got
        if partial is not None and ref in partial.how:
            pg = _stats(spec, data, partial, ref, tc)
            if pg is not None:
                part[ref] = pg
    return {"stocks": stocks, "accounting": accounting, "equations": eqs, "partial": part, "judged_by_stock": judged_by,
            "total": total(stocks) if run.valid else None, "invalid": list(run.invalid),
            "span": data.grid.until - data.grid.since}


def compute(p, snap: dict | None = None, n: int | None = None) -> tuple[ob.Data, sim.Run, dict]:
    """The fit on the reference window (the last day of record), whatever window the page shows;
    ``snap["at"]`` is the moment it looks back from."""
    spec = p.model.spec
    data = ob.measured(p, ob.reference(p, (snap or {}).get("at"), n))
    pl = sim.plan(spec)
    run = sim.replay(spec, data, pl)
    partial = sim.replay(spec, data, sim.plan(spec, integrate=set()))
    return data, run, compare(spec, data, run, partial)


def _slim(s: dict | None) -> dict | None:
    return None if s is None else {k: (round(v, 6) if isinstance(v, float) else v) for k, v in s.items()
                                   if k in ("n", "r2", "mape", "um", "us", "uc", "rmse", "stocks", "exact", "error_share",
                                            "error_of", "says", "too_little", "nmse")}


def history_path(p):
    return p.dir / HISTORY_FILE


def history(p) -> list[dict]:
    try:
        return [json.loads(x) for x in history_path(p).read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def record(p, fit: dict, window: float | None = None, force: bool = False, now: float | None = None) -> dict | None:
    """Keep this version's fit in its history: at most every RECORD_EVERY seconds, unless forced (an
    accepted proposal records the fit after it at once). Each row says the span it was fitted over."""
    spec = p.model.spec
    now = time.time() if now is None else now
    v, st = ver.version(spec), ver.structure(spec)
    past = [h for h in history(p) if h.get("version") == v]
    if past and not force and now - past[-1]["time"] < RECORD_EVERY:
        return None
    entry = {"time": now, "version": v, "structure": st, "window": fit.get("span", window), "total": _slim(fit["total"]),
             "stocks": {r: _slim(s) for r, s in fit["stocks"].items()}}
    path = history_path(p)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def versions(p) -> list[dict]:
    """The history, one row per version: when it was first and last fitted, its latest total fit,
    and the span of record that fit covered."""
    rows: dict[str, dict] = {}
    for h in history(p):
        r = rows.setdefault(h["version"], {"version": h["version"], "structure": h.get("structure"), "first": h["time"]})
        r.update(last=h["time"], total=h.get("total"), window=h.get("window"), fits=r.get("fits", 0) + 1)
    return sorted(rows.values(), key=lambda r: r["first"])
