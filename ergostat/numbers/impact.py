"""The impact of a change, as a careful operator wants it before approving one (SPEC §12n): what broke and since when,
which goals the model projects to fail without the fix, what rolling it out at each time ahead costs and the best time,
and the change-management fields (what else it touches, whether it writes, the rollback, the risk, the confidence).

Built on the closed-loop projection (closedloop.py): the failing block's identified model, identified on the record
before the failure, is run as its failing self (its flow at the share it still moves) and restored from each rollout
time. Bounded in wall time (``budget``) and in runs (``MOST_TIMES`` rollout times, the risk's ``runs``)."""

from __future__ import annotations

import time
from statistics import fmean

from ..durations import human
from ..spec.ir import DEAD, MODEL_CHANGE, Spec
from . import closedloop as cl
from . import fit as ft
from . import observe as ob
from . import simulate as sim

FAILURE = "ergostat.failure"
TIMES, MOST_TIMES = 12, 24          # rollout times tried, by default and at most
UNITS = 7                           # ... over this many of the model's time unit
POINTS = 96                         # points along a projection
RUNS, BUDGET = 40, 20.0             # the risk's runs; seconds of wall time the whole report may take
STOPPED = 0.1                       # a flow under this share of its rate before has stopped (else it is degraded)
BACK = 0.05                         # a stock is back within this share of its level when the failure began
WEEK, DAY = 7 * 86400.0, 86400.0


class ImpactError(ValueError):
    pass


def resolve(p, spec: Spec, parts) -> dict:
    """What changes: ``{"block": NAME}`` or ``{"change": ID}``, with what a failure item says (its block, since, commit,
    tests)."""
    for x in [parts] if isinstance(parts, str) else list(parts or []):
        x = str(x)
        if x.startswith(FAILURE + "/"):
            f: dict = {}
            for e in p.events.query(n=None, item=x):             # its fields: each key's latest value
                f.update(e.get("data") or {})
            if f.get("block") not in spec.blocks:
                raise ImpactError(f"{x} names no block of the model")
            return {"block": f["block"], "item": x, **{k: f[k] for k in ("since", "commit", "tests") if f.get(k) is not None}}
        if x.startswith(MODEL_CHANGE + "/"):
            x = x.split("/", 1)[1]
        name = x[6:] if x.startswith("block.") else x
        if name in spec.blocks:
            return {"block": name}
        if x.startswith("flow.") and (b := spec.actuator_of(x[5:])) is not None:
            return {"block": b.name}
        from . import proposals as pr
        if x in pr.stored(p):
            return {"change": x}
    raise ImpactError(f"{parts!r}: not a block, a flow a block moves, a failure or a change to the model")


def failure_began(p, block: str, until: float) -> float | None:
    """The first ``agent.failed`` of the block's last unbroken run of failures (None: its last run did not fail)."""
    began = None
    for e in p.events.query(n=500, type="agent.ran,agent.failed", item=block, until=until):
        began = (began or e["time"]) if e["type"] == "agent.failed" else None
    return began


def _mean(vals) -> float | None:
    xs = [v for v in vals or [] if v is not None]
    return fmean(xs) if xs else None


def broken(p, spec: Spec, block: str, since: float, at: float) -> dict:
    """The flows the block moves, their rate before the failure and since, and the stocks building up."""
    b = spec.blocks[block]
    flows = [f"flow.{t.name}" for t in b.targets() if t.kind == "flow" and t.name in spec.flows]
    span = min(DAY, max(3600.0, at - since))
    before = ob.measured(p, ob.Grid(since - span, since, max(2, min(120, int(span // ob.MIN_BUCKET)))), spec)
    after = ob.measured(p, ob.Grid(since, max(at, since + 1.0), max(2, min(120, int((at - since) // ob.MIN_BUCKET)))), spec)
    rows, shares = [], []
    for r in flows:
        a, z = _mean(before.values.get(r)), _mean(after.values.get(r))
        share = None if not a else max(0.0, min(1.0, (z or 0.0) / a))
        shares += [share] if share is not None else []
        how = ("not measured" if a is None and z is None else "stopped" if (share is not None and share < STOPPED) or not (a or z)
               else "degraded" if share is not None and share < 1 - STOPPED else "still moving")
        rows.append({"ref": r, "before": a, "since": z, "said": f"{r[5:]}: {cl._rate(a)} before, {cl._rate(z)} since: {how}"})
    ends = [(spec.flows[r[5:]].source, spec.flows[r[5:]].target) for r in flows]
    lv = []
    for r in dict.fromkeys(f"stock.{s}" for e in ends for s in e if s):
        x0, x1 = before.last(r), after.last(r)
        if x0 is not None or x1 is not None:
            lv.append({"ref": r, "at_failure": x0, "now": x1, "building": x0 is not None and x1 is not None and x1 > x0 + 1e-9})
    return {"block": block, "since": since, "flows": rows, "stocks": lv, "share": min(shares) if shares else 0.0,
            "drains": [f"stock.{src}" for src, _ in ends if src]}


class Outage:
    """A block's identified model while it fails: its flow at ``share`` of the model's, until ``fixed`` (None: never)."""

    def __init__(self, healthy: cl.BlockModel, share: float, fixed: float | None = None):
        self.healthy, self.share, self.fixed, self.t = healthy, share, fixed, 0.0

    def __getattr__(self, k):
        return getattr(self.healthy, k)

    def at(self, t: float) -> None:
        self.t = t

    def rate(self, V, on, x=None, eqv=None, dt=0.0):
        v = self.healthy.rate(V, on, x, eqv, dt)
        return v if self.fixed is not None and self.t >= self.fixed else v * self.share


def unit_of(run: sim.Run) -> float:
    """The model's time unit, by its slowest time constant: a day, an hour or a minute (seconds)."""
    slow = 3 * 3600.0 * max((v for r, v in run.time_constants.items() if r.startswith("stock.")), default=1.0)
    return DAY if slow >= DAY else 3600.0 if slow >= 3600.0 else 60.0


def daily(p, spec: Spec, into: list[str], at: float) -> tuple[list[float] | None, list[str]]:
    """How busy each hour of the day is, 0 (the quietest) to 1 (the busiest): the record's mean rate at that hour, over
    the last week at most, of the flows from outside into ``into`` (else every flow from outside). None: no pattern."""
    ins = [f"flow.{f.name}" for f in spec.flows.values() if not f.source and f.target and f"stock.{f.target}" in into]
    ins = ins or [f"flow.{f.name}" for f in spec.flows.values() if not f.source and f.target]
    oldest = min((t for t in (p.events.first_time(), p.measurements.first_time()) if t), default=at)
    span = min(WEEK, at - oldest)
    if not ins or span < DAY:
        return None, ins
    end = at // 3600 * 3600                                      # buckets of whole clock hours
    data = ob.measured(p, ob.Grid(end - span // 3600 * 3600, end, int(span // 3600)), spec)
    by: dict[int, list[float]] = {}
    for i, t in enumerate(data.grid.times()):
        vs = [data.values.get(r, [None] * data.grid.n)[i] for r in ins]
        if any(v is not None for v in vs):
            by.setdefault(time.localtime(t).tm_hour, []).append(sum(v or 0.0 for v in vs))
    prof = [fmean(by[h]) if by.get(h) else None for h in range(24)]
    known = [v for v in prof if v is not None]
    if len(known) < 24 or max(known) <= min(known):
        return None, ins
    lo, hi = min(known), max(known)
    return [(v - lo) / (hi - lo) for v in prof], ins


def _recovery(cr: cl.ClosedRun, d: float, goals: list[str], stocks: list[str], level: dict) -> float | None:
    """Hours after ``d`` until, to the end, ``goals`` hold and ``stocks`` are near ``level`` (where fixing now settles them)."""
    def ok(i: int) -> bool:
        return not any(cr.off_end[g][i] for g in goals) and all((v := (cr.values.get(r) or [None])[i]) is None or level.get(r) is None or
                   v <= level[r] + BACK * max(abs(level[r]), 1.0) for r in stocks)
    first = None
    for i, t in enumerate(cr.times):
        if t < d:
            continue
        first = (t if first is None else first) if ok(i) else None
    return None if first is None else max(0.0, first - d) / 3600.0


def _goal_rows(spec: Spec, cr: cl.ClosedRun, before: dict | None = None) -> dict:
    out = {}
    for name, g in spec.goals.items():
        ends = cr.off_end.get(name) or []
        i = next((k for k, v in enumerate(ends) if v), None)
        out[name] = {"of": str(g.of), "hold": str(g.hold), "off_at": cr.times[i] if i is not None else None, "off_before": (
            before or {}).get(name) == "off", "off_end": bool(ends and ends[-1]), "hours_off": round(cr.off_hours.get(name, 0.0), 4)}
    return out


def _charts(spec: Spec, data: ob.Data, refs: list[str], without, with_) -> list[dict]:
    out = []
    for r in refs[:6]:
        kind, name = r.split(".", 1)
        part = spec.stocks.get(name) if kind == "stock" else spec.flows.get(name)
        g = next((g for g in spec.goals.values() if str(g.of) == r and g.hold.value is not None), None)
        out.append({"ref": r, "name": name, "kind": kind, "unit": getattr(part, "unit", "") or "", "per": kind == "flow",
                    "goal": {"value": g.hold.value, "setpoint": str(g.hold)} if g else None,
                    "measured": data.values.get(r) or [], "without": without.values.get(r), "with": with_.values.get(r) if with_ else None})
    return out


def _ends(spec: Spec, refs) -> list[str]:
    """``refs`` and the stocks their flows move."""
    return list(dict.fromkeys([f"stock.{s}" for r in refs if r.startswith("flow.") and r[5:] in spec.flows
                               for s in (spec.flows[r[5:]].source, spec.flows[r[5:]].target) if s] + list(refs)))


def _around(spec: Spec, refs: set[str], but: str | None = None) -> tuple[list[str], list[str]]:
    """The blocks that read ``refs`` or the stocks their flows move (other than ``but``), and the goals on them."""
    moved = set(_ends(spec, refs))
    held = {(z.items.get("kind"), st) for r in moved if r.startswith("stock.") and r[6:] in spec.stocks   # a block that takes
            for z in spec.stocks[r[6:]].sensors.values() if z.items                                     # items from those
            for st in (z.items.get("state") if isinstance(z.items.get("state"), list) else [z.items.get("state")])}   # reads them
    reads = lambda o: any(str(r) in moved for r in o.reads()) or (o.takes and any((o.takes.kind, a) in held for a in o.takes.at))  # noqa: E731
    return (sorted(o.name for o in spec.blocks.values() if o.name != but and reads(o)),
            sorted(g.name for g in spec.goals.values() if str(g.of) in moved))


def touches(p, spec: Spec, block: str) -> dict:
    """What else the block touches, whether it writes, and the rollback."""
    b = spec.blocks[block]
    readers, goals = _around(spec, {str(t) for t in b.targets() if t.kind == "flow"}, block)
    commands = sorted(t.name for t in b.targets() if t.kind in ("block", "goal"))
    acts = [{"name": a, "gate": spec.actions[a].gate if a in spec.actions else "?"} for a in b.params.get("actions") or []]
    items = None
    if b.takes:
        from ..spec import items as its
        counts = (next((k for k in its.listing(p.events, spec, kind=b.takes.kind, n=1)["kinds"] if k["name"] == b.takes.kind),
                       {}).get("counts") or {})
        items = {"kind": b.takes.kind, "states": {s: counts.get(s, 0) for s in b.takes.at}, "dead": counts.get(DEAD, 0)}
    return {"touches": {"blocks": readers, "goals": goals, "commands": commands, "actions": acts},
            "read_only": not acts, "writes": [a["name"] for a in acts], "items": items}


def _rollback(t: dict, commit: str | None, block: str) -> dict:
    how = f"git revert {commit}" if commit else "revert the fix's commit (git revert COMMIT)"
    it = t.pop("items")
    said = f"{how}: {block} fails again as before"
    if it:
        waiting = ", ".join(f"{n} in {s}" for s, n in it["states"].items())
        said += (f"; the {it['kind']} items it moved stay where they are, the ones it would take next wait ({waiting} now), "
                 f"and a run in flight gives its item back when its lease expires")
        if it["dead"]:
            said += (f". {it['dead']} {it['kind']} items are dead letters now (given up on after their attempts): the fix does "
                     f"not bring them back; redrive them once it is in (ergostat lease ITEM --redrive)")
    if t["writes"]:
        said += f"; what its actions did outside ({', '.join(t['writes'])}) is not undone by the revert"
    return {"how": how, "items": it, "said": said}


def risk_level(t: dict, tests: str | None) -> dict:
    acts = [(2 if a["gate"] == "auto" else 1, a["name"]) for a in t["touches"]["actions"] if a["gate"] in ("auto", "approve")]
    pts = sum(k for k, _ in acts)
    why = [f"it writes: {n} ({'runs without asking' if k == 2 else 'held for approval'})" for k, n in acts]
    radius = sum(len(t["touches"][k]) for k in ("blocks", "goals", "commands"))
    for k, said in ((1 if radius > 3 else 0, f"a blast radius of {radius} parts"), (1 if not tests else 0, "its tests were not run"),
                    (4 if tests and tests != "passed" else 0, "its tests failed")):
        pts, why = pts + k, why + [said] if k else why
    return {"level": "low" if pts <= 1 else "medium" if pts <= 3 else "high", "why": why or ["reads only, a small radius, tested"]}


def confidence(spec: Spec, data: ob.Data, run: sim.Run, models: dict, refs: list[str], valid: bool) -> dict:
    fit = ft.compare(spec, data, run) if run.valid else {"stocks": {}}
    parts = [{"ref": m.label or m.block, "how": f"assumed: {m.assumed}" if m.assumed else f"identified from {m.basis}"}
             for m in models.values()]
    skills, low = [], [x["ref"] for x in parts if x["how"].startswith("assumed")]
    for r in refs:
        s = fit["stocks"].get(r)
        if s and s.get("n") and not s.get("exact") and s.get("r2") is not None:
            parts.append({"ref": r, "how": "fit on the reference window", "r2": s.get("r2"), "skill": s.get("skill")})
            if s.get("skill") is not None:
                skills.append(s["skill"])
                low += [r] if s["skill"] < 0 else []
    level = "low" if low or not valid else "high" if skills and min(skills) >= 0.5 else "medium"
    said = (f"low: {', '.join(low)} assumed, or fitting worse than its mean" if low else "low: the projection is not valid"
            if level == "low" else "high: every stock it charts fits with skill 0.5 or more" if level == "high" else
            "medium: the parts involved are identified, but not every stock it charts fits well" if skills else
            "medium: the parts involved are identified; no stock it charts has an equation to fit")
    return {"level": level, "parts": parts, "said": said}


def report(p, parts, since: float | None = None, *, at: float | None = None, within: float | None = None, times: int = TIMES,
           penalty: float | None = None, share: float | None = None, tests: str | None = None, commit: str | None = None,
           runs: int = RUNS, budget: float = BUDGET) -> dict:
    """The impact report (SPEC §12n)."""
    began = time.monotonic()
    spec = p.model.spec
    what = resolve(p, spec, parts)
    at = at if at is not None else time.time()
    data = ob.measured(p, ob.reference(p, at, POINTS))
    run = sim.replay(spec, data, sim.plan(spec))
    if what.get("change"):
        return _change(p, spec, what["change"], data, run, at, began)
    block = what["block"]
    since = float(since if since is not None else what.get("since") or failure_began(p, block, at) or 0) or None
    if since is None:
        raise ImpactError(f"{block}'s last run did not fail: say when its failure began (--since)")
    tests, commit = tests if tests is not None else what.get("tests"), commit or what.get("commit")
    br = broken(p, spec, block, since, at)
    share = br["share"] if share is None else max(0.0, min(1.0, share))
    br["share"] = share
    from ..web.numbers_api import horizon_of
    base = horizon_of(run, data.grid.until - data.grid.since)
    unit = unit_of(run)
    within = within if within is not None else UNITS * unit
    horizon = min(within + max(base, within), cl.MOST_HORIZON)   # room after the last rollout time to recover
    n = max(2, min(int(times), MOST_TIMES))
    penalty = penalty if penalty is not None else unit / 3600.0
    models = cl.identify(p, spec, data)
    healthy = cl.identify(p, spec, ob.measured(p, ob.reference(p, since)))
    mine = [r["ref"] for r in br["flows"] if r["ref"] in healthy]
    start = cl.start_of(p, spec, at)
    notes = [] if mine else [f"{block} moves no flow the projection runs: its failure changes nothing projected"]

    def run_with(fixed: float | None) -> cl.ClosedRun:
        ms = dict(models)
        for r in mine:
            ms[r] = Outage(healthy[r], share, fixed)
        return cl.closed(spec, data, run, horizon, None, POINTS, ms, start)

    without, now_fixed = run_with(None), run_with(at)
    was = cl.start_of(p, spec, since).status                    # each goal as it was when the failure began
    held = [g for g in spec.goals if was.get(g) != "off"]       # what the failure can put off, and the fix restore
    goals, fixed_now = _goal_rows(spec, without, was), _goal_rows(spec, now_fixed)
    for g, x in goals.items():
        x["hours_off_fixed_now"] = fixed_now[g]["hours_off"]
        x["due"] = not x["off_before"] and x["hours_off"] > x["hours_off_fixed_now"] + 0.01 * horizon / 3600.0
    put_off = [g for g in held if goals[g]["due"]]              # what the failure puts off: recovered once they hold
    building = [s["ref"] for s in br["stocks"] if s["building"]] or br["drains"]
    level = {r: next((v for v in reversed(now_fixed.values.get(r) or []) if v is not None), None) for r in building}
    prof, ins = daily(p, spec, br["drains"], at)
    if prof is None:
        notes.append("the record has no daily pattern of arrivals (a day of it at least): no rollout time is busier than another")
    options, stopped = [], None
    for i in range(n):
        if i and time.monotonic() - began > budget * 0.6:       # now is always tried: its run is made already
            stopped = f"stopped at {budget * 0.6:g} s of wall time, after {i} of {n} rollout times"
            break
        d = at + within * i / max(1, n - 1)
        cr = now_fixed if i == 0 else run_with(d)
        each = {g: round(cr.off_hours[g], 4) for g in put_off if cr.off_hours[g] > 0}   # the cost of waiting: the goals the
        # failure puts off (what the fix itself puts off happens whenever it is rolled out, and only leaves the horizon later)
        moved = sum(v for r in mine for v in cr.values.get(r) or [] if v is not None) * horizon / POINTS / 3600.0
        off = sum(each.values())
        busy = prof[time.localtime(d).tm_hour] if prof else 0.0
        peak = max((v for r in building for v in (cr.values.get(r) or []) if v is not None), default=None)
        options.append({"at": d, "hours_off": round(off, 4), "goals_off": each, "peak": peak, "busy": round(busy, 3), "moved": moved,
                        "recovery": _recovery(cr, d, put_off, building, level), "cost": round(off + penalty * busy, 4),
                        "_run": cr})
    with_best = (best := min(options, key=lambda o: (o["cost"], o["at"]))).pop("_run")   # the cheapest, the earliest of equals
    [o.pop("_run", None) for o in options]
    left = budget - (time.monotonic() - began)
    if spec.goals and left > 0.5 and runs > 0:
        from . import sensitivity as sens
        failing = {**models, **{r: Outage(healthy[r], share) for r in mine}}
        rk = cl.risk(spec, data, run, horizon, POINTS, failing, start, sens.estimates(p, spec), runs=runs, budget=left)
        for g, x in rk["goals"].items():
            goals[g].update({"p_off_end": x["p_off_end"], "expected_off": x["expected_off"], "p_off": x["p_off"],
                             "said": cl.risk_said(rk, g)})
        if rk.get("stopped"):
            notes.append(f"risk {rk['stopped']}")
    t = touches(p, spec, block)
    rollback = _rollback(t, commit, block)
    refs = list(dict.fromkeys(building + [s["ref"] for s in br["stocks"]] + mine +
                              [x["of"] for x in goals.values() if x["off_at"] is not None]))
    ro = {"unit": human(unit), "penalty": penalty, "busy_from": ins if prof else [], "options": options, "best": best,
          "said": _best_said(options, best, penalty)}
    out = {"kind": "failure", "about": f"block {block}", "at": at, "broken": br, "horizon": horizon,
           "times": data.grid.times(), "ptimes": without.times, "charts": _charts(spec, data, refs, without, with_best),
           "goals": goals, "rollout": ro,
           "fields": {**t, "rollback": rollback, "risk": risk_level(t, tests),
                      "confidence": confidence(spec, data, run, {r: healthy[r] for r in mine}, refs, without.valid)},
           "notes": notes + without.notes, "stopped": stopped, "seconds": round(time.monotonic() - began, 3)}
    out["said"] = _said(out)
    return out


def _best_said(options: list[dict], best: dict, penalty: float) -> str:
    first, h = options[0], (lambda x: human(x * 3600) if x else "none")
    if best is first:
        lost = first["moved"] - options[-1]["moved"]
        why = ("every wait adds goal-off time" if len(options) > 1 and options[-1]["hours_off"] > first["hours_off"] else
               "waiting gains nothing") + (f", and its flows move {lost:.3g} less by the last time tried" if lost > 1e-6 else "")
        off = f"{h(first['hours_off'])} of goal-off time" if first["hours_off"] else "no goal goes off"
        return f"roll it out now: {why} ({off})" + (f", though this hour is busy ({first['busy']:.0%})" if first["busy"] > 0.5 else "")
    when = f"at {time.strftime('%a %H:%M', time.localtime(best['at']))} (+{human(best['at'] - first['at'])})"
    if first["busy"] - best["busy"] > 1e-9 and best["hours_off"] >= first["hours_off"]:
        why = (f"it avoids rolling out in a busy hour ({first['busy']:.0%} busy now, {best['busy']:.0%} then; the busiest costs "
               f"{h(penalty)}) for {h(best['hours_off'] - first['hours_off'])} more goal-off time")
    else:
        worse = max(first["goals_off"], key=lambda g: first["goals_off"][g] - best["goals_off"].get(g, 0.0), default=None)
        why = (f"the model projects less goal-off time ({h(best['hours_off'])} against {h(first['hours_off'])} now)" +
               (f": rolled out now, {worse} is off {h(first['goals_off'][worse] - best['goals_off'].get(worse, 0.0))} longer, "
                f"as what the fix restores moves on to it" if worse else ""))
    lost = first["moved"] - best["moved"]
    return f"roll it out {when}: {why}" + (f"; waiting, its flows move {lost:.3g} less over the horizon" if lost > 1e-6 else "")


def _said(r: dict) -> str:
    br = r["broken"]
    flows = "; ".join(x["said"] for x in br["flows"]) or "it moves no flow"
    up = [f"{s['ref'][6:]} {s['at_failure']:.3g} → {s['now']:.3g}" for s in br["stocks"] if s["building"]]
    off = sorted(((g, x) for g, x in r["goals"].items() if x["due"]), key=lambda gx: gx[1]["off_at"])
    already = [g for g, x in r["goals"].items() if x["off_before"]]
    goals = "; ".join(f"{g} off at +{human(max(0.0, x['off_at'] - r['at']))}" + (f" (p≈{x['p_off_end']:.2g} off at the horizon)"
                                                                                if x.get("p_off_end") is not None else "")
                      for g, x in off[:3]) or "no goal that held goes off for want of it"
    goals += f" (off before it failed: {', '.join(already)})" if already else ""
    flows += f"; {dead} items are dead letters" if (dead := (r["fields"]["rollback"]["items"] or {}).get("dead")) else ""
    return (f"{br['block']} has failed since {time.strftime('%a %H:%M', time.localtime(br['since']))} "
            f"({human(r['at'] - br['since'])} ago): {flows}" + (f"; building up: {', '.join(up)}" if up else "") +
            f". Without the fix: {goals} within {human(r['horizon'])}. {r['rollout']['said'][0].upper()}{r['rollout']['said'][1:]}."
            f" Risk {r['fields']['risk']['level']}, confidence {r['fields']['confidence']['level']}.")


def _change(p, spec: Spec, pid: str, data: ob.Data, run: sim.Run, at: float, began: float) -> dict:
    """A model change: what it touches, its forecast as the model is and with it, the goals' time off under both."""
    from . import proposals as pr
    from . import review as rv
    from . import trial as tr
    x = pr.stored(p)[pid]
    try:
        after = tr.spec_after(p, tr.edits_of(x))
        fc = rv.forecast(p, spec, after, [x], at)
    except tr.TrialError as e:
        raise ImpactError(f"{pid}: {e}") from None
    b, a = fc["before"], fc["after"]
    refs = [r for r in (x.get("parts") or []) if r.startswith(("stock.", "flow."))] or \
        [str(g.of) for g in spec.goals.values() if g.of.kind == "stock"]
    refs = _ends(spec, refs)
    goals = _goal_rows(spec, b) if isinstance(b, cl.ClosedRun) else {}
    if isinstance(a, cl.ClosedRun):
        for g, y in _goal_rows(after, a).items():
            goals.setdefault(g, y)["hours_off_fixed_now"] = y["hours_off"]
    readers, near = _around(spec, set(refs))
    blocks = sorted({str(r)[6:] for r in x.get("parts") or [] if str(r).startswith("block.")} & set(spec.blocks) | set(readers))
    t = {"touches": {"blocks": blocks, "goals": near, "commands": [], "actions": []}, "read_only": True, "writes": []}
    rollback = {"how": "revert the change's edit to the model (git revert its commit)", "items": None,
                "said": "revert the edit: the model and its forecast return to as they were; the record is untouched"}
    said = (fc["predicts"] or {}).get("said") or "it changes nothing the model forecasts"
    out = {"kind": "change", "about": f"change {pid}", "at": at, "broken": None, "horizon": fc["horizon"],
           "times": data.grid.times(), "ptimes": b.times, "charts": _charts(spec, data, refs, b, a), "goals": goals,
           "rollout": None, "notes": ["a change to the model revises its forecast, not the world: when it is accepted "
                                      "changes nothing the record will show, so no rollout time is tried"],
           "fields": {**t, "rollback": rollback, "risk": risk_level(t, "passed" if x.get("state") in ("passed", "accepted") else None),
                      "confidence": confidence(spec, data, run, {}, refs, b.valid)},
           "stopped": None, "seconds": round(time.monotonic() - began, 3)}
    f = out["fields"]
    out["said"] = f"{x.get('title') or pid}: {said}. Risk {f['risk']['level']}, confidence {f['confidence']['level']}."
    return out
