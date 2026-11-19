"""Validate the closed-loop projection on a project's own record: the model is identified on the record up to a split,
projected past it held (open loop) and with its loops running, and both compared with the record held out after the
split, by Sterman's measures (R², MAPE, Theil's U_M, U_S, U_C and the scaled error: numbers/fit.py). Then the extreme
condition: with the inputs from outside doubled, what the stocks and the stand-ins do.

    python scripts/closedloop_validate.py DIR [--held-out 10m] [--splits 3] [--double flow.directed] [--json]

DIR is a project with a record (a demo run for a while). Nothing is written."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ergostat import model as mdl
from ergostat.durations import human, parse_duration
from ergostat.numbers import closedloop as cl
from ergostat.numbers import fit as ft
from ergostat.numbers import observe as ob
from ergostat.numbers import simulate as sim
from ergostat.store import Project


def compare(spec, proj: sim.Run, truth: ob.Data, refs: list[str]) -> dict:
    per = {}
    for r in refs:
        got = ft.stats(proj.values.get(r) or [], truth.values.get(r) or [])
        if got:
            per[r] = got
    return {"stocks": per, "total": ft.total(per)}


def one_split(p, spec, split: float, held_out: float, points: int, fit_span: float) -> dict:
    first = min(t for t in (p.events.first_time(), p.measurements.first_time()) if t)
    since = max(first, split - fit_span)
    n = max(2, min(240, int((split - since) // ob.MIN_BUCKET)))
    data = ob.measured(p, ob.Grid(since, split, n))
    pl = sim.plan(spec)
    run = sim.replay(spec, data, pl)
    stand = cl.identify(p, spec, data)
    start = cl.start_of(p, spec, split)
    held = sim.project(spec, data, run, held_out, pl, points=points, held=set())
    closed = cl.closed(spec, data, run, held_out, pl, points, stand, start)
    truth = ob.measured(p, ob.Grid(split, split + held_out, points))
    refs = sorted(r for r in closed.values if r.startswith("stock.") and sum(v is not None for v in truth.values.get(r) or []) >= 3)
    near = sim.controlled(spec)
    out = {"split": split, "fit_span": split - since, "held": compare(spec, held, truth, refs),
           "closed": compare(spec, closed, truth, refs), "controlled": sorted(r for r in refs if r in near),
           "assumed": sorted({s.block for s in stand.values() if s.assumed}), "standins": len(stand)}
    sub = [r for r in refs if r in near]
    out["held_controlled"] = compare(spec, held, truth, sub)
    out["closed_controlled"] = compare(spec, closed, truth, sub)
    return out


def doubled(p, spec, inputs: list[str], until: float, horizon: float, points: int) -> dict:
    first = min(t for t in (p.events.first_time(), p.measurements.first_time()) if t)
    since = max(first, until - 86400)
    data = ob.measured(p, ob.Grid(since, until, max(2, min(240, int((until - since) // ob.MIN_BUCKET)))))
    run = sim.replay(spec, data)
    stand = cl.identify(p, spec, data)
    start = cl.start_of(p, spec, until)
    base = cl.closed(spec, data, run, horizon, None, points, stand, start, whatif=cl.WhatIf(flows={r: ("x", 1.0) for r in inputs}))
    w = cl.WhatIf(flows={r: ("x", 2.0) for r in inputs})
    two = cl.closed(spec, data, run, horizon, None, points, stand, start, whatif=w)
    stocks = {r: {"now": data.recent(r), "base": base.values[r][-1], "doubled": two.values[r][-1]}
              for r in sorted(base.values) if r.startswith("stock.")}
    sat = {}
    for r, s in stand.items():
        cap = s.capacity()
        if cap and cap > 0:
            vals = [v for v in two.values.get(r) or [] if v is not None]
            sat[r] = {"block": s.block, "capacity": cap, "share_at_capacity_base": _share(base.values.get(r), cap),
                      "share_at_capacity_doubled": _share(vals, cap)}
    for r, s in stand.items():                         # a block that fills to a goal's setpoint: held at that limit
        if s.form == "fill":
            g = spec.goals[s.goal]
            limit = start.setpoint.get(s.goal, g.hold.value)
            at = lambda vals, lim=limit: _share([1.0 if v is not None and v >= 0.95 * lim else 0.0 for v in vals or []], 1.0)  # noqa: E731
            sat[r] = {"block": s.block, "limit": f"{s.target} at {g.name}'s setpoint ({limit:g})",
                      "share_at_limit_base": at(base.values.get(f"stock.{s.target}")),
                      "share_at_limit_doubled": at(two.values.get(f"stock.{s.target}"))}
    goals = {g: {"hours_off_base": base.off_hours[g], "hours_off_doubled": two.off_hours[g]} for g in spec.goals}
    return {"inputs": inputs, "horizon": horizon, "stocks": stocks, "saturation": sat, "goals": goals}


def _share(vals, cap) -> float | None:
    vals = [v for v in vals or [] if v is not None]
    return sum(1 for v in vals if v >= 0.95 * cap) / len(vals) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--held-out", default="10m")
    ap.add_argument("--splits", type=int, default=3)
    ap.add_argument("--fit-span", default="1d", help="how much record before each split is identified from")
    ap.add_argument("--points", type=int, default=40)
    ap.add_argument("--double", action="append", default=[], metavar="FLOW", help="an input to double (flow.NAME)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--per-stock", action="store_true", help="each stock's scaled error, held and closed")
    a = ap.parse_args()
    p = Project(mdl.load(Path(a.dir)))
    spec = p.model.spec
    h = parse_duration(a.held_out, "--held-out")
    newest = p.measurements.newest()
    until = max(v[0] for v in newest.values())
    splits = [until - h * (k + 1) for k in range(a.splits)]
    got = {"project": spec.name, "held_out": h, "splits": [one_split(p, spec, s, h, a.points, parse_duration(a.fit_span))
                                                          for s in splits]}
    if a.double:
        got["doubled"] = doubled(p, spec, a.double, until, h, a.points)
    if a.json:
        print(json.dumps(got, indent=1, default=str))
        return 0
    print(f"{spec.name}: {len(splits)} held-out stretches of {human(h)}")
    for x in got["splits"]:
        print(f"\n split at -{human(until - x['split'])}, identified on {human(x['fit_span'])} of record before it; "
              f"{x['standins']} stand-ins, assumed: {', '.join(x['assumed']) or 'none'}")
        for which in ("", "_controlled"):
            print(f"  {'every stock' if not which else 'stocks downstream of a controller'}:")
            for mode in ("held", "closed"):
                t = x[mode + which]["total"]
                if not t:
                    print(f"    {mode:7s} too few points")
                    continue
                print(f"    {mode:7s} scaled error {t['nmse']:.3g}  R² {t['r2'] if t['r2'] is None else round(t['r2'], 2)}  "
                      f"MAPE {t['mape'] if t['mape'] is None else round(t['mape'], 2)}  "
                      f"U_M {t['um']:.2f}  U_S {t['us']:.2f}  U_C {t['uc']:.2f}  ({t['stocks']} stocks)")
    if a.per_stock:
        for x in got["splits"]:
            print(f"\n split at -{human(until - x['split'])}, each stock's scaled error (held → closed):")
            for r in sorted(x["closed"]["stocks"], key=lambda r: -x["held"]["stocks"].get(r, {}).get("nmse", 0)):
                hs, cs = x["held"]["stocks"].get(r), x["closed"]["stocks"][r]
                print(f"  {r[6:]:28s} {hs['nmse'] if hs else float('nan'):10.3g} → {cs['nmse']:.3g}"
                      f"   (measured mean {cs['mean_measured']:.4g}; held {hs['mean_replay'] if hs else float('nan'):.4g}, "
                      f"closed {cs['mean_replay']:.4g})")
    if a.double:
        d = got["doubled"]
        print(f"\n{', '.join(d['inputs'])} at their mean, and doubled, {human(d['horizon'])} ahead with the loops running:")
        for r, x in d["stocks"].items():
            if x["base"] is not None and abs((x["doubled"] or 0) - x["base"]) > 1e-6 * max(1, abs(x["base"])):
                print(f"  {r[6:]:28s} now {x['now']!s:>10.8} → {x['base']:.4g} at the mean, {x['doubled']:.4g} doubled")
        for g, x in d["goals"].items():
            if x["hours_off_base"] != x["hours_off_doubled"]:
                print(f"  goal {g}: off {human(x['hours_off_base'] * 3600)} at the mean, {human(x['hours_off_doubled'] * 3600)} doubled")
        for r, x in d["saturation"].items():
            if "limit" in x:
                print(f"  {x['block']} ({r[5:]}): {x['limit']} {x['share_at_limit_base'] or 0:.0%} of the time at the mean, "
                      f"{x['share_at_limit_doubled'] or 0:.0%} doubled")
                continue
            print(f"  {x['block']} ({r[5:]}): at its capacity ({x['capacity']:.3g}/h) {x['share_at_capacity_base'] or 0:.0%} "
                  f"of the time at the mean, {x['share_at_capacity_doubled'] or 0:.0%} doubled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
