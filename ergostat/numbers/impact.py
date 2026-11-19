"""The impact of a change, as a careful operator wants it before approving one (SPEC §12n): what broke and since when,
which goals the model projects to fail without the fix, what rolling it out at each time ahead costs and the best time,
and the change-management fields (impact_fields.py).

Built on the closed-loop projection (closedloop.py): the failing block's model, identified on the record before the
failure, is run as its failing self (its flow at the share it still moves) and restored from each rollout time. Every
rollout time is scored against fixing now over the same span, to ``T`` after it, so a late rollout's own effects are not
cut off by the horizon. Bounded in wall time (``budget``, from the call) and in runs (``MOST_TIMES``, the risk's
``runs``)."""

from __future__ import annotations

import time
from statistics import fmean

from ..durations import human
from ..spec.ir import MODEL_CHANGE, Spec
from . import closedloop as cl
from . import impact_fields as fl
from . import observe as ob
from . import predict as pd
from . import simulate as sim
from .impact_fields import ImpactError  # noqa: F401  (the callers' error)

FAILURE = "ergostat.failure"
TIMES, MOST_TIMES = 12, 24          # rollout times tried, by default and at most
UNITS = 7                           # ... over this many of the model's time unit
POINTS = 96                         # points along a projection
RUNS, BUDGET = 40, 20.0             # the risk's runs; seconds of wall time the whole report may take
STOPPED = 0.1                       # a flow under this share of its rate before has stopped (else it is degraded)
CAP = 500                           # runs read back to find when the failure began
WEEK, DAY = 7 * 86400.0, 86400.0
TESTS = (None, "passed", "failed")


def resolve(p, spec: Spec, parts) -> dict:
    """What changes, from the first part that resolves: ``{"block": NAME}`` or ``{"change": ID}``, with what a failure item
    says (its block, began, commit, tests)."""
    for x in [parts] if isinstance(parts, str) else list(parts or []):
        x = str(x)
        if x.startswith(FAILURE + "/"):
            f: dict = {}
            for e in p.events.query(n=None, item=x):             # its fields: each key's latest value
                f.update(e.get("data") or {})
            if f.get("block") not in spec.blocks:
                raise ImpactError(f"{x} names no block of the model")
            return {"block": f["block"], "item": x, **{k: f[k] for k in ("began", "commit", "tests") if f.get(k) is not None}}
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


def failure_began(p, block: str, until: float) -> tuple[float | None, bool]:
    """The first ``agent.failed`` of the block's last unbroken run of failures (None: its last run did not fail), and
    whether every one of the last ``CAP`` runs failed (it began earlier than can be said)."""
    began, evs = None, p.events.query(n=CAP, type="agent.ran,agent.failed", item=block, until=until)
    for e in evs:
        began = (began or e["time"]) if e["type"] == "agent.failed" else None
    return began, began is not None and len(evs) == CAP and evs[0]["time"] == began


def _mean(vals) -> float | None:
    xs = [v for v in vals or [] if v is not None]
    return fmean(xs) if xs else None


def broken(p, spec: Spec, block: str, began: float, at: float) -> dict:
    """The flows the block moves, their rate before the failure and during it, and the stocks building up."""
    b = spec.blocks[block]
    flows = [f"flow.{t.name}" for t in b.targets() if t.kind == "flow" and t.name in spec.flows]
    span = min(DAY, max(3600.0, at - began))
    before = ob.measured(p, ob.Grid(began - span, began, max(2, min(120, int(span // ob.MIN_BUCKET)))), spec)
    after = ob.measured(p, ob.Grid(began, max(at, began + 1.0), max(2, min(120, int((at - began) // ob.MIN_BUCKET)))), spec)
    rows, shares = [], []
    for r in flows:
        a, z = _mean(before.values.get(r)), _mean(after.values.get(r))
        share = None if not a else max(0.0, min(1.0, (z or 0.0) / a))
        shares += [share] if share is not None else []
        how = ("not measured" if a is None and z is None else "idle before and during: not seen to stop" if not (a or z) else
               "stopped" if share is not None and share < STOPPED else "degraded" if share is not None and share < 1 - STOPPED
               else "still moving")
        rows.append({"ref": r, "before": a, "during": z, "said": f"{r[5:]}: {cl._rate(a)} before, {cl._rate(z)} since: {how}"})
    lv = []
    for r in fl.ends(spec, flows):
        x0, x1 = before.last(r), after.last(r)
        if r.startswith("stock.") and (x0 is not None or x1 is not None):
            lv.append({"ref": r, "at_failure": x0, "now": x1, "building": x0 is not None and x1 is not None and x1 > x0 + 1e-9})
    return {"block": block, "began": began, "flows": rows, "stocks": lv, "share": min(shares) if shares else None,
            "drains": [f"stock.{spec.flows[r[5:]].source}" for r in flows if spec.flows[r[5:]].source]}


class Outage:
    """A block's identified model while it fails: its flow at ``share`` of the model's, until ``fixed`` (None: never)."""

    def __init__(self, healthy: cl.BlockModel, share: float, fixed: float | None = None):
        self.healthy, self.share, self.fixed, self.t = healthy, share, fixed, 0.0

    def __getattr__(self, k):
        return getattr(self.healthy, k)

    def at(self, t: float) -> None:
        self.t = t
        if hasattr(self.healthy, "at"):
            self.healthy.at(t)

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


def _recovery(cr: cl.ClosedRun, d: float, goals: list[str], stocks: list[str]) -> float | None:
    """Hours after ``d`` until ``goals`` hold to the end and ``stocks`` have settled (None: not within the horizon)."""
    hold = None
    for i, t in enumerate(cr.times):
        if t >= d:
            hold = (t if hold is None else hold) if not any(cr.off_end[g][i] for g in goals) else None
    settled = [pd._settles(cr.times, cr.values.get(r), d)[1] for r in stocks if cr.values.get(r)]
    if hold is None or None in settled:
        return None
    return max([hold - d] + [s for s in settled if s is not None]) / 3600.0


def _upto(cr: cl.ClosedRun, xs: list, end: float, step_h: float) -> float:
    return sum(x or 0.0 for t, x in zip(cr.times, xs, strict=False) if t <= end + 1e-6) * step_h


def report(p, parts, began: float | None = None, *, at: float | None = None, within: float | None = None, times: int = TIMES,
           penalty: float | None = None, share: float | None = None, tests: str | None = None, commit: str | None = None,
           runs: int = RUNS, budget: float = BUDGET) -> dict:
    """The impact report (SPEC §12n)."""
    t0 = time.monotonic()
    left = lambda: budget - (time.monotonic() - t0)   # noqa: E731
    if tests not in TESTS:
        raise ImpactError(f"tests: {tests!r}: passed or failed (or left out: not run)")
    spec = p.model.spec
    what = resolve(p, spec, parts)
    at = at if at is not None else time.time()
    data = ob.measured(p, ob.reference(p, at, POINTS))
    run = sim.replay(spec, data, sim.plan(spec))
    if what.get("change"):
        return fl.change_report(p, spec, what["change"], data, run, at, t0)
    block, notes, capped = what["block"], [], False
    began = began if began is not None else what.get("began")
    if began is None:
        began, capped = failure_began(p, block, at)
        if began is None:
            raise ImpactError(f"{block}'s last run did not fail: say when its failure began (--began)")
    try:
        began = float(began)
    except (TypeError, ValueError):
        raise ImpactError(f"began: {began!r} is not a time in epoch seconds") from None
    if capped:
        notes.append(f"the last {CAP} runs all failed: the failure began before the first of them, read as its start")
    tests = tests if tests is not None else what.get("tests")
    if tests not in TESTS:
        raise ImpactError(f"{what.get('item')}: tests {tests!r}: passed or failed")
    br = broken(p, spec, block, began, at)
    if share is None and br["share"] is None:
        notes.append("no rate of its flows was measured before the failure: taken as stopped (share 0)")
    share = max(0.0, min(1.0, share if share is not None else br["share"] or 0.0))
    br["share"] = share
    base, unit = sim.horizon_of(run, data.grid.until - data.grid.since), unit_of(run)
    within = within if within is not None else UNITS * unit
    n = max(2, min(int(times), MOST_TIMES))
    penalty = penalty if penalty is not None else unit / 3600.0
    models = cl.identify(p, spec, data)
    healthy = cl.identify(p, spec, ob.measured(p, ob.reference(p, began)))
    mine = [r["ref"] for r in br["flows"] if r["ref"] in healthy]
    projected = {**models, **{r: healthy[r] for r in mine}}
    start = cl.start_of(p, spec, at)
    if not mine:
        notes.append(f"{block} moves no flow the projection runs: its failure changes nothing projected")

    def run_with(fixed: float | None, horizon: float) -> cl.ClosedRun:
        return cl.closed(spec, data, run, horizon, None, POINTS, {**models, **{r: Outage(healthy[r], share, fixed) for r in mine}}, start)

    was = cl.start_of(p, spec, began).status                    # each goal as it was when the failure began
    building = [s["ref"] for s in br["stocks"] if s["building"]] or br["drains"]
    horizon = min(within + max(base, within), cl.MOST_HORIZON)
    for _ in range(2):                                          # again once if fixing now takes longer to recover than T
        without, now_fixed = run_with(None, horizon), run_with(at, horizon)
        goals, fixed_now = fl.goal_rows(spec, without, was), fl.goal_rows(spec, now_fixed)
        for g, x in goals.items():
            x["hours_off_fixed_now"] = fixed_now[g]["hours_off"]
            x["due"] = not x["off_before"] and x["hours_off"] > x["hours_off_fixed_now"] + 0.01 * horizon / 3600.0
        due = [g for g, x in goals.items() if x["due"]]
        rec_now = _recovery(now_fixed, at, due, building)
        want = min(within + max(base, 2 * 3600.0 * (rec_now if rec_now is not None else within / 3600.0)), cl.MOST_HORIZON)
        if want <= horizon * 1.01 or left() < budget * 0.6:
            break
        horizon = want
    T, step_h = horizon - within, horizon / POINTS / 3600.0
    prof, ins = daily(p, spec, br["drains"], at)
    if prof is None:
        notes.append("the record has no daily pattern of arrivals (a day of it at least): no rollout time is busier than another")
    options, stopped = [], None
    for i in range(n):
        if i and left() < budget * 0.4:                         # now is always tried: its run is made already
            stopped = f"stopped at {budget * 0.6:g} s of wall time, after {i} of {n} rollout times"
            break
        d = at + within * i / max(1, n - 1)
        cr, end = (now_fixed if i == 0 else run_with(d, horizon)), d + T
        extra = {g: round(_upto(cr, cr.off[g], end, step_h) - _upto(now_fixed, now_fixed.off[g], end, step_h), 4) for g in spec.goals}
        extra = {g: v for g, v in extra.items() if v > 1e-4}   # what waiting adds: putting off the fix's own effects earns nothing
        lost = max(0.0, sum(_upto(now_fixed, now_fixed.values.get(r) or [], end, step_h) - _upto(cr, cr.values.get(r) or [], end, step_h)
                            for r in mine))           # throughput lost: what fixing now moves by then and this does not
        outage = (1 - share) * (d - at) / 3600.0
        busy = prof[time.localtime(d).tm_hour] if prof else 0.0
        options.append({"at": d, "extra_off": round(sum(extra.values()), 4), "goals_off": extra, "outage": round(outage, 4),
                        "lost": round(lost, 4), "peak": max((v for r in building for v in (cr.values.get(r) or []) if v is not None),
                                                            default=None),
                        "busy": round(busy, 3), "recovery": _recovery(cr, d, due, building),
                        "cost": round(sum(extra.values()) + outage + penalty * busy, 4), "_run": cr})
    ideal = min(options, key=lambda o: (o["cost"], o["at"]))
    t = fl.touches(p, spec, block)
    refs = list(dict.fromkeys(building + [s["ref"] for s in br["stocks"]] + mine + [goals[g]["of"] for g in due]))
    conf = fl.confidence(spec, data, run, projected, refs, without.valid)
    best = options[0] if conf["level"] == "low" else ideal      # a low-confidence report never advises waiting
    with_best = best["_run"]
    [o.pop("_run", None) for o in options]
    if spec.goals and left() > 0.5 and runs > 0:                # the risk without the fix
        from . import sensitivity as sens
        failing = {**models, **{r: Outage(healthy[r], share) for r in mine}}
        rk = cl.risk(spec, data, run, horizon, POINTS, failing, start, sens.estimates(p, spec), runs=runs, budget=left())
        for g, x in rk["goals"].items():
            goals[g].update({"p_off_end": x["p_off_end"], "expected_off": x["expected_off"], "p_off": x["p_off"],
                             "said": cl.risk_said(rk, g)})
        if rk.get("stopped"):
            notes.append(f"risk {rk['stopped']}")
    ro = {"unit": human(unit), "penalty": penalty, "span": T, "busy_from": ins if prof else [], "options": options,
          "ideal": ideal, "best": best, "trusted": conf["level"] != "low", "said": _best_said(options, ideal, penalty, conf, tests)}
    out = {"kind": "failure", "about": f"block {block}", "at": at, "broken": br, "horizon": horizon,
           "times": data.grid.times(), "ptimes": without.times, "charts": fl.charts(spec, data, refs, without, with_best),
           "goals": goals, "rollout": ro, "fields": {**t, "rollback": fl.rollback(t, commit or what.get("commit"), block),
                                                     "risk": fl.risk_level(t, tests), "confidence": conf},
           "notes": notes + without.notes, "stopped": stopped, "seconds": round(time.monotonic() - t0, 3)}
    out["said"] = _said(out)
    return out


def _when(o: dict, now: float) -> str:
    return "now" if o["at"] <= now else f"at {time.strftime('%a %H:%M', time.localtime(o['at']))} (+{human(o['at'] - now)})"


def _best_said(options: list[dict], ideal: dict, penalty: float, conf: dict, tests: str | None) -> str:
    first, h = options[0], (lambda x: human(abs(x) * 3600) if x else "none")
    if conf["level"] == "low":
        go = "as soon as its tests pass" if tests != "passed" else "now"
        return (f"roll it out {go}: the model is too unsure to advise waiting" +
                (f" (its own ideal, {_when(ideal, first['at'])}, is not a reason to wait)" if ideal is not first else ""))
    if ideal is first:
        last = options[-1]
        return ("roll it out now: every wait costs" + (f" {h(last['outage'])} of outage" if last["outage"] else "") +
                (f", {last['lost']:.3g} of throughput lost" if last["lost"] > 1e-6 else "") +
                (f", {h(last['extra_off'])} more goal-off time" if last["extra_off"] > 0 else "") + " by the last time tried" +
                (f", though this hour is busy ({first['busy']:.0%})" if first["busy"] > 0.5 else ""))
    why = (f"the busy hour now ({first['busy']:.0%} busy against {ideal['busy']:.0%}; the busiest costs {h(penalty)}) outweighs "
           f"waiting's {h(ideal['outage'])} of outage" + (f" and {h(ideal['extra_off'])} more goal-off time" if ideal["extra_off"] > 0
                                                           else "")) if first["busy"] > ideal["busy"] else \
        f"the model projects {h(ideal['extra_off'])} less goal-off time than rolling out now, more than its {h(ideal['outage'])} of outage"
    return f"roll it out {_when(ideal, first['at'])}: {why}" + (f"; {ideal['lost']:.3g} of throughput lost meanwhile"
                                                                 if ideal["lost"] > 1e-6 else "")


def _said(r: dict) -> str:
    br, conf = r["broken"], r["fields"]["confidence"]
    flows = "; ".join(x["said"] for x in br["flows"]) or "it moves no flow"
    flows += f"; {dead} items are dead letters" if (dead := (r["fields"]["rollback"]["items"] or {}).get("dead")) else ""
    up = [f"{s['ref'][6:]} {s['at_failure']:.3g} → {s['now']:.3g}" for s in br["stocks"] if s["building"]]
    off = sorted(((g, x) for g, x in r["goals"].items() if x["due"]), key=lambda gx: gx[1]["off_at"])
    goals = "; ".join(f"{g} off at +{human(max(0.0, x['off_at'] - r['at']))}" + (f" (p≈{x['p_off_end']:.2g} off at the horizon)"
                                                                                if x.get("p_off_end") is not None else "")
                      for g, x in off[:3]) or "no goal that held goes off for want of it"
    goals += f" (off before it failed: {', '.join(already)})" if (already := [g for g, x in r["goals"].items() if x["off_before"]]) else ""
    lead = f"Low confidence: {conf['worst']}. " if conf["level"] == "low" else ""
    rs = r["rollout"]["said"]
    return (f"{lead}{br['block']} has failed since {time.strftime('%a %H:%M', time.localtime(br['began']))} "
            f"({human(r['at'] - br['began'])} ago): {flows}" + (f"; building up: {', '.join(up)}" if up else "") +
            f". Without the fix: {goals} within {human(r['horizon'])}. {rs[0].upper()}{rs[1:]}."
            f" Risk {r['fields']['risk']['level']}, confidence {conf['level']}.")
