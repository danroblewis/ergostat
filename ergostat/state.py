"""What we believe is true now, estimated from the record with the model.

- A stock's value is the latest reading of a sensor that measures it (unmeasured: unknown).
- A flow's rate (per hour, over the window) is its sensor's latest reading when one measures it;
  otherwise the amounts its valve opened, summed; a disturbance nothing measures is estimated
  from what its stock did that the known flows do not explain.
- A loop is open (it cannot close), unknown (no reading yet), holding (within its setpoint, give or
  take its tolerance) or off.
- A stock's residual is the change its readings show minus the change its known flows explain.
  When an estimated disturbance pushes that stock, the residual is what the disturbance is
  estimated from; otherwise it is unexplained."""

from __future__ import annotations

import threading
import time

from .durations import human
from .spec.goal_per import cascade_setpoint as per_setpoint
from .spec.goal_per import says as per_says
from .spec.goal_per import worst as per_worst
from .spec.ir import OWN_TEMPLATES, upkeep_of
from .spec.observer import opted, shown_stale

WINDOW = 3600.0
STALE_RUNS = 3          # a reading older than this many of its agent's periods is stale



def crossings_of(project, loop: str, since: float, until: float) -> list[dict]:
    """A loop's crossings in a span, and the last one before it (whether it was off when the span
    began): never every crossing of the whole record."""
    from .spec.projections import query
    before = query(project, "loop.*", n=1, item=loop, until=since - 1e-6, unvoided=True)
    return before + query(project, "loop.*", n=None, item=loop, since=since, until=until, unvoided=True)


def _crossings(project, loops: list[str], since: float, until: float) -> dict[str, list[dict]]:
    """``crossings_of`` for each of several loops, read together (from the item index's ``marks``)."""
    from .spec.projections import query
    got = {lp: query(project, "loop.*", n=1, item=lp, until=since - 1e-6, unvoided=True) for lp in loops}
    for e in query(project, "loop.*", n=None, since=since, until=until, unvoided=True):
        if e.get("item") in got:
            got[e["item"]].append(e)
    return got


_BY: tuple = (None, 0, {})     # the model's sensors last asked of, how many, and each part's (what measures it)
_NEWEST = threading.local()    # while a snapshot is made: the store's newest reading of every series (``_latest``)


def _sensor_for(m, target: str) -> list:
    # (the cache is read once into ``got`` and replaced whole: another thread or model swapping it between the
    # check and the read cannot hand this call another model's sensors)
    global _BY
    got, sensors = _BY, m.sensors
    if got[0] is not sensors or got[1] != len(sensors):
        by: dict[str, list] = {}
        for s in sensors.values():
            by.setdefault(s.measures, []).append(s)
        got = (sensors, len(sensors), by)
        _BY = got
    return list(got[2].get(target, ()))


def _latest(project, series: str, at: float | None):
    """``measurements.latest(series, at)``: while a snapshot is made, from the store's ``newest()`` (read once for it)
    when that reading is at or before ``at``."""
    got = (getattr(_NEWEST, "got", None) or {}).get(series, ())
    if got and (at is None or got[0] <= at):
        return got
    return project.measurements.latest(series, at) if got or getattr(_NEWEST, "got", None) is None else None


def stock_value(project, stock: str, at: float | None = None) -> dict:
    m = project.model
    best = None
    for s in _sensor_for(m, stock):
        got = _latest(project, f"sensor/{s.name}", at)
        if got and (best is None or got[0] > best[0]):
            best = (got[0], got[1], s.name)
    if best is None:
        return {"value": None, "at": None, "sensor": None}
    return {"value": best[1], "at": best[0], "sensor": best[2]}


def _range(project, series: str, since: float, until: float, sampled: bool = False) -> list[tuple[float, float]]:
    """``measurements.range`` (``sampled``: ``.sampled``) of a span: while a snapshot is made, from the window's raw
    readings it read together (``Measurements.ranges``), where they answer it alone, as the store would."""
    raw, span = getattr(_NEWEST, "raw", None), getattr(_NEWEST, "span", None)
    got = raw.get(series) if raw is not None and span[0] <= since and until <= span[1] else None
    if got is not None:
        rows = got if (since, until) == span else [x for x in got if since <= x[0] <= until]
        if not sampled or len(rows) <= 1200:              # (``sampled``'s own: its 600 points, twice)
            return rows
    m = project.measurements
    return m.sampled(series, since, until) if sampled else m.range(series, since, until)


def history(project, stock: str, since: float, until: float | None = None) -> list[tuple[float, float]]:
    pts = []
    for s in _sensor_for(project.model, stock):
        pts += (project.measurements.sampled(f"sensor/{s.name}", since, until) if until is None else
                _range(project, f"sensor/{s.name}", since, until, sampled=True))
    return sorted(pts)


def mean_rate(project, flow: str, t0: float, t1: float) -> float | None:
    """A measured flow's average rate per hour between ``t0`` and ``t1``. Each reading is a rate
    covering the time since the reading before it (the first in the window covers back to ``t0``),
    and the last one holds until ``t1``. Several sensors on one flow are averaged, not added. None
    when no sensor has a reading in the window."""
    rates = []
    for s in _sensor_for(project.model, flow):
        pts = _range(project, f"sensor/{s.name}", t0, t1)
        pts = [(t, r) for t, r in pts if t0 <= t <= t1]
        if not pts:
            continue
        if t1 - t0 <= 0:
            rates.append(pts[-1][1])
            continue
        total, prev = 0.0, t0
        for t, r in pts:
            total += r * (t - prev)
            prev = t
        total += pts[-1][1] * (t1 - prev)
        rates.append(total / (t1 - t0))
    return sum(rates) / len(rates) if rates else None


def counted(project, flow: str, t0: float, t1: float) -> float | None:
    """How many items a flow counted from the record moved between ``t0`` and ``t1``, as they moved
    (its readings, a rate over a trailing window, lag what happened): the replay's accounting basis."""
    spec = getattr(project.model, "spec", None)
    f = spec.flows.get(flow) if spec else None
    q = next((s.items for s in (f.sensors.values() if f else []) if s.items), None)
    if not q or q.get("kind") not in spec.items:
        return None
    from .spec import items as its
    key, state = ("to", q["entering"]) if q.get("entering") else ("from", q.get("leaving"))
    where = q.get("where") or {}
    return float(sum(1 for t in its.moved(project.events, spec, q["kind"], key, state, t0, t1, where, at=t1) if t > t0))


def moved(project, flow: str, t0: float, t1: float) -> float | None:
    """How much a measured flow moved between ``t0`` and ``t1``: what it counted, when it counts items;
    else from its readings, rates per hour."""
    got = counted(project, flow, t0, t1)
    if got is not None:
        return got
    r = mean_rate(project, flow, t0, t1)
    return None if r is None else r * (t1 - t0) / 3600.0


def snapshot(project, window: float = WINDOW, now: float | None = None) -> dict:
    """The state at ``now`` (default: now), over the window before it; a past ``now`` looks back. ``as_of``: the last
    event the record held as it was read (``seq``) and when the answer was made (``made``): how old it is. What it
    reads of the event log it reads from the item index's tables (``spec/projections.py``), caught up once."""
    from .spec.itemindex import pinned
    newest = getattr(project.measurements, "newest", None)
    with pinned():
        _NEWEST.got = dict(newest()) if newest is not None else None
        try:
            return _snapshot(project, window, now)
        finally:
            _NEWEST.got = _NEWEST.raw = _NEWEST.span = None


def _snapshot(project, window: float, now: float | None) -> dict:
    from .spec.projections import latest, openings, query, runs
    from .spec.projections import opened as opened_in
    m = project.model
    seq = project.events.last_seq() if hasattr(project.events, "last_seq") else None
    live = now is None
    now = now or time.time()
    since = now - window
    oldest = min((t for t in (project.events.first_time(), project.measurements.first_time()) if t), default=None)
    start = max(since, oldest) if oldest else since    # every rate is over the time actually recorded
    hours = max(now - start, 60.0) / 3600.0
    stocks, flows, loops, residuals = {}, {}, {}, {}
    full: dict[str, list] = {}
    ranges = getattr(project.measurements, "ranges", None)    # the window's readings of every sensor, read together
    _NEWEST.raw, _NEWEST.span = (ranges(sorted(f"sensor/{s}" for s in m.sensors), start, now), (start, now)) if ranges \
        else (None, None)

    for name in m.stocks:
        v = stock_value(project, name, now)
        pts = full[name] = history(project, name, start, now)
        step = max(1, len(pts) // 80)
        stocks[name] = {**v, "unit": m.stocks[name].unit,
                        "change": (pts[-1][1] - pts[0][1]) if len(pts) >= 2 else None,
                        "points": (pts[::step] + ([pts[-1]] if pts and (len(pts) - 1) % step else [])),
                        "inflow": 0.0, "outflow": 0.0}

    # flows known from sensors or valves; a measured flow's reading is a rate per hour
    known: dict[str, float] = {}
    opens = opened_in(project, sorted({v.name for f in m.flows.values() if (v := m.valve_of(f.name))}), start, now)
    for f in m.flows.values():
        rate, how, opened = None, None, None
        if f.rate is not None:
            rate, how = f.rate, "declared"
        sensors = _sensor_for(m, f.name)
        for s in sensors:
            got = _latest(project, f"sensor/{s.name}", now)
            if got is not None:
                # the average over the window, not the latest reading: one quiet scan is not a stopped flow
                avg = mean_rate(project, f.name, start, now)
                rate = avg if avg is not None else got[1]
                how = f"measured by {s.name}"
        valve = m.valve_of(f.name)
        if valve is not None:
            opened = dict(opens[valve.name])
            if rate is None:
                rate, how = opened["amount"] / hours, f"opened by {valve.name}"
        if rate is not None:
            known[f.name] = rate
        flows[f.name] = {"rate": rate, "how": how or ("estimated" if f.disturbance else "unknown"), "per": "hour",
                         "from": f.source, "to": f.target, "disturbance": f.disturbance, "valve": valve.name if valve else None,
                         "openings": opened, "estimated": False}

    # residuals, and the estimated disturbances drawn from them
    def explain(name: str, pts: list) -> tuple[float, float, float, bool]:
        """Over the readings ``pts``: the change, what the known flows explain, the rest, and
        whether the rest is more than noise (5% of the flow, and twice an ordinary step)."""
        span = max(pts[-1][0] - pts[0][0], 1e-9) / 3600.0
        change = pts[-1][1] - pts[0][1]
        explained = 0.0
        for f in m.flows_of(name):
            if f.name in known:
                sign = 1 if f.target == name else -1
                if flows[f.name]["openings"] is not None and flows[f.name]["how"].startswith("opened"):
                    v = flows[f.name]["valve"]
                    explained += sign * opened_in(project, [v], pts[0][0], pts[-1][0])[v]["amount"]
                elif f.rate is not None:
                    explained += sign * f.rate * span
                else:
                    got = moved(project, f.name, pts[0][0], pts[-1][0])
                    explained += sign * (got if got is not None else known[f.name] * span)
        rest = change - explained
        raw = [x for s_ in _sensor_for(m, name) for x in _range(project, f"sensor/{s_.name}", pts[0][0], pts[-1][0])]
        raw = sorted(raw) if len(raw) <= 5000 else sorted(raw)[:5000]      # the ordinary step of the readings themselves
        steps = sorted(d for a, b in zip(raw, raw[1:], strict=False) if (d := abs(b[1] - a[1])) > 0)
        typical = steps[len(steps) // 2] if len(steps) >= 2 and len(raw) >= 4 else 0.0
        return change, explained, rest, abs(rest) > max(1e-9, 0.05 * (abs(change) + abs(explained)), 2 * typical)

    from .remote import remote_parts
    theirs = remote_parts(getattr(m, "spec", None))
    for name, s in stocks.items():
        if s["change"] is None or not m.flows_of(name):    # no flows declared: a plain measurement, nothing to explain
            continue
        if f"stock.{name}" in theirs:                      # a remote's stock: its flows are explained there (SPEC §4c)
            continue
        pts = full[name]
        span = max(pts[-1][0] - pts[0][0], 1e-9) / 3600.0
        _, explained, unexplained, significant = explain(name, pts)
        # a real unexplained flow persists: it shows in the recent half of the window too, the same
        # way; something that happened once, long ago in the window, is not flagged for an hour
        mid = pts[0][0] + (pts[-1][0] - pts[0][0]) / 2
        recent = [p for p in pts if p[0] >= mid]
        if significant and len(recent) >= 4:
            _, _, rest2, sig2 = explain(name, recent)
            significant = sig2 and (rest2 > 0) == (unexplained > 0)
        estimated = [f for f in m.flows_of(name) if f.disturbance and f.name not in known]
        # the rest is shared among the unmeasured disturbances that push the way it went
        able = [f for f in estimated if (1 if f.target == name else -1) * unexplained > 0]
        backwards = [] if able else estimated
        share = unexplained / len(able) if able else 0.0
        if able and abs(unexplained) > 1e-9:
            for f in able:
                sign = 1 if f.target == name else -1
                flows[f.name].update(rate=sign * share / span, how=f"estimated from {name}", estimated=True)
            residuals[name] = {"unexplained": unexplained, "explained": explained, "change": s["change"],
                               "absorbed_by": [f.name for f in able], "significant": False, "hours": span}
        elif estimated and significant:
            # the disturbance would have to run backwards to explain it: something else is happening
            residuals[name] = {"unexplained": unexplained, "explained": explained, "change": s["change"],
                               "absorbed_by": [], "significant": True, "hours": span,
                               "why": f"{', '.join(f.name for f in backwards)} would have to run backwards to explain it"}
        else:
            residuals[name] = {"unexplained": unexplained, "explained": explained, "change": s["change"],
                               "absorbed_by": [], "significant": significant, "hours": span}

    for name, s in stocks.items():
        for f in m.flows_of(name):
            r = flows[f.name]["rate"]
            if r is not None:
                s["inflow" if f.target == name else "outflow"] += r

    all_loops = list(m.loops())
    crossed = _crossings(project, [lp.name for lp in all_loops], start, now)
    acting = sorted({v for lp in all_loops for v in (lp.valves or (lp.controller.drives if lp.controller.through else []))})
    opened_at = openings(project, acting, start, now)
    last_opened = latest(project, "valve.opened", acting, now)
    decided = latest(project, "controller.decided", sorted({lp.controller.name for lp in all_loops}), now)
    spec = getattr(m, "spec", None)
    for lp in all_loops:
        c = lp.controller
        value = stocks.get(c.holds, {}).get("value")
        g = spec.goals.get(lp.name) if spec is not None else None
        r = per_setpoint(spec, project.measurements, g, now) if g is not None and g.per and value is not None else None
        held = per_worst(spec, g, r, project.events, now) if g is not None and g.per and value is not None else None
        if held:
            value = held[0]                              # the worst item's or group's (SPEC §8, per:), against its cascade's
        if not lp.closes:
            status, error = "open", None
        elif value is None:
            status, error = "unknown", None
        else:
            last = query(project, "loop.*", n=1, item=lp.name, until=now, unvoided=True)
            was_off = bool(last and last[-1]["type"] == "loop.off")
            error, status = (g.hold.error(value, r), g.status(value, was_off, r)) if held else \
                (c.error(value), c.status(value, was_off=was_off))
        decisions = [decided[c.name]] if decided.get(c.name) else []
        acts_on = lp.valves or (c.drives if c.through else [])    # the long way: where its controller acts, first along it
        last_open = max((o["time"] for v in acts_on if (o := last_opened.get(v))), default=None)
        knob = next((p.split(".", 1)[1] for p in c.through if p.startswith("auxiliary.")), None) if not acts_on else None
        if knob:                                                  # it acts by setting an auxiliary: when it last set it
            last_open = max((e["time"] for t in ("auxiliary.set", "variable.set")      # variable.set: its old name, in old records
                             if (e := latest(project, t, [knob], now)[knob])), default=None)
        reads = [_latest(project, f"sensor/{s}", now) for s in lp.sensors]
        last_read = max((r[0] for r in reads if r), default=None)
        stale = shown_stale(project, m.spec, lp.name, status, now) if getattr(m, "spec", None) else None
        if stale is not None:                             # its reading is too old to trust (SPEC §9.6)
            status = "stale"
        # how much of the recorded window the loop spent off, from its crossings
        crossings = crossed[lp.name]
        off_time, off_from = 0.0, None
        before = [e for e in crossings if e["time"] < start]
        if before and before[-1]["type"] == "loop.off":
            off_from = start
        episodes = []                                    # (went off, back holding) within the window
        for e in crossings:
            if e["time"] < start:
                continue
            if e["type"] == "loop.off" and off_from is None:
                off_from = e["time"]
            elif e["type"] == "loop.holding" and off_from is not None:
                off_time += e["time"] - off_from
                episodes.append((off_from, e["time"]))
                off_from = None
        if off_from is not None:
            off_time += now - off_from
        off_share = off_time / max(now - start, 1.0)
        # how fast it answers: from going off to its valve's first opening, and to holding again
        import bisect
        opens = sorted(t for v in acts_on for t in opened_at.get(v, ()))
        answers = []
        for t0, t1 in episodes + ([(off_from, now)] if off_from is not None and off_from > start else []):
            if t0 <= start:                               # went off before the window: its start is unknown
                continue
            i = bisect.bisect_left(opens, t0)
            if i < len(opens) and opens[i] < t1:          # an opening while it was off, not after it came back
                answers.append(opens[i] - t0)
        recoveries = sorted(t1 - t0 for t0, t1 in episodes if t0 > start)
        answers.sort()
        cycled = bool(last_read and last_read >= since and ((decisions and decisions[-1]["time"] >= since)
                                                           or (last_open and last_open >= since)))
        own = upkeep_of(spec, g) if g is not None else None
        loops[lp.name] = {"system": g.system if g is not None else None, **({"upkeep": own} if own else {}), "stock": c.holds,
                          "setpoint": c.setpoint, "tolerance": c.tolerance, "band": c.band_text(), "value": value,
                          "error": error, "status": status, "gaps": lp.gaps, "sensors": lp.sensors, "valves": lp.valves,
                          "flows": lp.flows, "controller": c.name, "last_read": last_read,
                          "last_decision": decisions[-1] if decisions else None, "last_opening": last_open,
                          "observed": cycled, "off_share": round(off_share, 3), "open_loop": lp.open_loop,
                          "off_since": off_from, "off_before_window": off_from is not None and off_from <= start,
                          "answers_in": answers[len(answers) // 2] if answers else None,
                          "back_in": recoveries[len(recoveries) // 2] if recoveries else None,
                          "back_in_slowest": recoveries[-1] if recoveries else None, "times_off": len(recoveries),
                          **({"stale": stale, "on_stale": opted(m.spec).goals[lp.name]} if stale is not None else {})}
        if held:
            loops[lp.name].update(per=g.per, breaking=held[1], breaking_n=held[2],
                                  **({"setpoint": f"{g.hold.op} {r:g}"} if r is not None else {}))
        loops[lp.name]["off_by_words"] = off_by_words(loops[lp.name]["setpoint"], error, c.tolerance,
                                                      getattr(m.stocks.get(c.holds), "unit", ""), status == "off")
        loops[lp.name].update(goal_row(loops[lp.name], getattr(m.stocks.get(c.holds), "unit", "")))

    contradicted: dict[str, list[dict]] = {}          # claims the record contradicts, by the block that made them (SPEC §12g)
    for e in query(project, "ergostat.claim.contradicted", n=500, since=since, until=now):
        contradicted.setdefault(e["data"].get("block") or "", []).append(e)
    agents = {}
    blocks = getattr(getattr(m, "spec", None), "blocks", None) or {}
    names = list(m.agents)
    ran, failed, started = (latest(project, t, names, now) for t in ("agent.ran", "agent.failed", "agent.started"))
    tallied = runs(project, names, since, now)
    for a in m.agents.values():
        counted = tallied[a.name]
        last_any = max((e for e in (ran[a.name], failed[a.name]) if e), key=lambda e: e["seq"], default=None)
        begun = started[a.name]
        running_since = begun["time"] if begun and (last_any is None or begun["seq"] > last_any["seq"]) else None
        roles = m.roles_of(a.name)
        b_ = getattr(getattr(m, "spec", None), "blocks", {}).get(a.name)
        keeps = b_.goal if b_ is not None and b_.implied and b_.goal in m.controllers else None   # keep-GOAL: it decides for GOAL
        stale = []
        if a.every or a.cron:                             # a reading older than a few of its runs is stale
            for r in roles:
                if r.kind == "sensor":
                    got = _latest(project, f"sensor/{r.name}", now)
                    if got is None or _missed(a, got[0], now):
                        stale.append(r.name)
        b = blocks.get(a.name)                            # its block: the goal its valves serve, and whether it takes items
        goal = b.goal if b is not None else None
        agents[a.name] = {"kind": a.kind, "rung": a.rung, "leased": bool(b is not None and b.takes),
                          "roles": [{"kind": r.kind, "name": r.name, **({"goal": goal} if goal and r.kind == "valve" else {})}
                                    for r in roles] + (
                              [{"kind": "controller", "name": keeps}] if keeps and all(r.name != keeps for r in roles) else []),
                          "every": a.every, "on": a.on, "cron": a.cron, "schedule": a.schedule, **counted,
                          "last": last_any, "failing": bool(last_any and last_any["type"] == "agent.failed"),
                          "stale": stale, "runs_itself": bool(a.command and a.kind != "person"),
                          "running_since": running_since, "contradicted": len(contradicted.get(a.name, [])),
                          "contradicted_latest": (contradicted[a.name][-1]["data"].get("why") if contradicted.get(a.name)
                                                  else None)}

    snap = {"at": now, "live": live, "window": window, "recorded": max(0.0, now - start) if oldest else 0.0,
            "starts": oldest, "before_record": bool(oldest and now < oldest),
            "stocks": stocks, "flows": flows, "loops": loops, "residuals": residuals,
            "agents": agents}
    snap["hints"] = ladder_hints(project, snap)
    snap["messages"] = unrouted_messages(project, now)
    snap["inbox"], snap["quarantined"] = inbox(project, now, live), quarantined(project)
    spec = getattr(m, "spec", None)
    for lp in loops.values():                         # the interventions loop's goal: its measures, on its panel (§12p)
        st_ = (spec.stocks.get(lp["stock"]) or spec.auxiliaries.get(lp["stock"])) if spec is not None else None
        if st_ is not None and any((x.builtin or "").startswith("ergostat.interventions.") for x in st_.sensors.values()):
            from .inbox.interventions import measures as iv
            try:
                lp["interventions"] = iv(project, spec, now)
            except Exception:
                pass
    snap["leases"] = lease_attention(project, now)
    snap["cycles"] = relation_cycles(project)
    snap["findings"] = findings(project)
    snap["reports"] = [{"id": r["id"], "title": r.get("title") or ""} for r in reports_drafted(project)]   # SPEC §12m
    snap["alarms"] = alarms(project, now)
    if getattr(getattr(project.model, "spec", None), "daemons", None):   # the long-lived runners, as the engine last saw them
        from .daemons.supervise import read_status
        snap["daemons"] = read_status(project.dir)
    snap["as_of"] = {"seq": seq, "made": time.time()}
    return snap


def age(snap: dict, now: float | None = None) -> dict:
    """How old a snapshot is: ``as_of`` and its ``age``, the seconds since it was made."""
    made = snap["as_of"]["made"]
    return {**snap["as_of"], "age": max(0.0, (time.time() if now is None else now) - made)}


def alarms(project, now: float) -> dict:
    """The ``alarm`` blocks raised at ``now`` (their output last recorded as 1): since when, and what they watch."""
    spec, out = getattr(project.model, "spec", None), {}
    for b in (spec.blocks.values() if spec is not None else ()):
        got = project.measurements.latest(f"block/{b.name}", now) if b.type == "alarm" else None
        if got and got[1]:
            bound = " and ".join(f"{k} {fmt(float(b.params[k]))}" for k in ("above", "below") if b.params.get(k) is not None)
            out[b.name] = {"since": got[0], "watches": ", ".join(str(r) for r in b.reads()), "bound": bound}
    return out


_CYCLES: dict = {}


def relation_cycles(project) -> list[list[str]]:
    """Items whose precedence relations go round (SPEC §5a, *Relations*): none of them can ever be ready. Each needs
    attention. Worked out again only when the record changes."""
    spec = getattr(project.model, "spec", None)
    if spec is None or not any(r.precedence for k in spec.items.values() for r in k.relations.values()):
        return []
    ev = project.events
    key = (id(spec), ev.last_seq() if hasattr(ev, "last_seq") else None, ev.generation() if hasattr(ev, "generation") else None)
    if key in _CYCLES:
        return _CYCLES[key]
    from .precedence import relation_cycles as found
    try:
        got = found(ev, spec)[:20]
    except Exception:
        return []
    _CYCLES.clear()
    _CYCLES[key] = got
    return got


_FINDINGS: dict = {}


def findings(project) -> list[dict]:
    """For each kind with ``attention: FIELD`` (SPEC §5a): its latest item (by its latest event, then its id) whose
    FIELD has words, and those words. Worked out again only when the record changes. A kind that cannot be read is
    said as unread, never left out."""
    spec = getattr(project.model, "spec", None)
    kinds = [k for k in (spec.items.values() if spec is not None else ()) if k.attention]
    if not kinds:
        return []
    ev = project.events
    key = (id(spec), ev.last_seq() if hasattr(ev, "last_seq") else None)
    if key in _FINDINGS:
        return _FINDINGS[key]
    from .spec import items as its
    out = []
    for k in kinds:
        try:
            got = [i for i in its.project(ev, spec, k.name, transcript=False)
                   if isinstance(i.fields.get(k.attention), str) and i.fields[k.attention].strip()]
        except Exception as e:
            out.append({"kind": k.name, "item": None, "field": k.attention, "says": None,
                        "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        if got:
            i = max(got, key=lambda x: (x.last, x.id))
            out.append({"kind": k.name, "item": i.id, "field": k.attention, "says": i.fields[k.attention].strip()})
    _FINDINGS.clear()
    _FINDINGS[key] = out
    return out


def inbox(project, now: float, live: bool) -> list[dict]:
    """Everything waiting on a person (SPEC §12o), each with its class's record: each needs attention, answerable."""
    from .inbox import stats
    spec = getattr(project.model, "spec", None)
    try:
        return stats.listing(project, spec, None if live else now) if spec is not None else []
    except Exception:
        return []


def quarantined(project) -> list[dict]:
    """The workspaces quarantined (SPEC §12k): dirty or broken, waiting for the owner."""
    spec = getattr(project.model, "spec", None)
    if spec is None or not spec.workspaces:
        return []
    from .workspaces import pool
    try:
        return [s for x in spec.workspaces.values() for s in pool.slots(project, spec, x).values()
                if s["state"] == "quarantined"]
    except Exception:
        return []


def lease_attention(project, now: float) -> list[dict]:
    """Dead letters, and leases that expired over the last hour (SPEC §9.5): each needs attention."""
    spec = getattr(project.model, "spec", None)
    if spec is None or not any(b.takes for b in spec.blocks.values()):
        return []
    from .leases import measures
    try:
        return measures.attention(project, spec, now)
    except Exception:
        return []


def reports_drafted(project) -> list[dict]:
    """Reports upstream drafted and not yet read by the owner (SPEC §12m)."""
    if getattr(project.model, "spec", None) is None:
        return []
    from .reports.record import drafted
    return drafted(project)


def unrouted_messages(project, now: float) -> list[dict]:
    """The owner's messages that reached no work (SPEC §12h), as of now: each needs attention."""
    if getattr(project.model, "spec", None) is None:
        return []
    from .messages import record
    try:
        got = record.stored(project, until=now, n=2000)
    except Exception:
        return []
    return [{"id": m["id"], "text": m.get("text") or "", "why": m.get("why") or "", "time": m["time"]}
            for m in got.values() if m["state"] == "unrouted"][-20:]


def decisions(project, controller: str, since: float, until: float | None = None) -> dict:
    """What a controller decided in the window, grouped by its words with the numbers taken out:
    how many decisions, and how often each kind came up, commonest first."""
    import re
    kinds: dict[str, int] = {}
    total = 0
    for words, n in project.events.decided(controller, since, until):
        k = re.sub(r"-?\d+(\.\d+)?", "#", str(words)).strip() or "(no words)"
        kinds[k] = kinds.get(k, 0) + n
        total += n
    return {"count": total, "kinds": sorted(kinds.items(), key=lambda kv: -kv[1])}


LADDER_MIN, LADDER_SHARE = 10, 0.8


def _period(agent, now: float | None = None) -> float | None:
    """How often an agent runs, in seconds: its ``every``, or the gap between its next two cron
    times after ``now``; None for one that runs on events."""
    if agent.every:
        return float(agent.every)
    if agent.cron:
        from .cron import Cron
        try:
            c = Cron(agent.cron)
            t = c.next_after(now if now is not None else time.time())
            return c.next_after(t) - t
        except Exception:
            return None
    return None


def _missed(agent, since: float, now: float) -> bool:
    """Whether the agent should have run STALE_RUNS times between ``since`` and ``now``: a reading
    older than that is stale. Cron is walked run by run, so a job idle out of its hours is not."""
    if agent.every:
        return now - since > STALE_RUNS * agent.every
    if agent.cron:
        from .cron import Cron
        try:
            c, t = Cron(agent.cron), since
            for _ in range(STALE_RUNS):
                t = c.next_after(t)
                if t > now:
                    return False
            return True
        except Exception:
            return False
    return False


def ladder_hints(project, snap: dict) -> list[dict]:
    """Roles a cheaper agent could fill: a controller whose agent is a person, an AI agent or a
    decision, and that decided the same thing at least 80% of at least 10 times in the window."""
    m = project.model
    out = []
    since = snap["at"] - snap["window"]
    for name, lp in snap["loops"].items():
        # a loop off most of the time though its agents act: first, can its valve keep up with the load
        # at all (saturation)? only if it can, is it sampling too slowly?
        if not (lp.get("off_share", 0) >= 0.5 and lp["observed"]):
            continue
        if snap.get("recorded", 0) < 600:                # too little record to tell saturation from slow sampling: no
            lp["diagnosis_in"] = 600 - snap.get("recorded", 0)   # suggestion yet, only when its verdict is due
            continue
        c = m.controllers[name]
        a = m.agents.get(c.agent or "")
        stock = c.holds
        acts = [v for v in (lp["valves"] or (c.drives if c.through else [])) if v in m.valves]   # the long way: where it acts
        mine = {m.valves[v].flow for v in acts}           # what its own valves move, not the far flow it closes through
        acted = any((snap["agents"].get(m.valves[v].agent or "") or {}).get("runs") for v in acts)
        drains = any(m.flows[f].source == stock for f in lp["flows"])
        ours = sum(snap["flows"][f]["rate"] or 0 for f in mine)
        load = sum((snap["flows"][f.name]["rate"] or 0) for f in m.flows_of(stock)
                   if f.name not in mine and (f.target == stock if drains else f.source == stock))
        off = round(lp["off_share"] * 100)
        grew = snap["stocks"].get(stock, {}).get("change")
        way = ("out" if drains else "in", "in" if drains else "out")
        # the stages of the loop and how often each runs: the slowest bounds how fast it can answer
        stages = {}
        for role, part in (("sensor", (lp["sensors"] or [None])[0]), ("controller", name), ("valve", (lp["valves"] or [None])[0])):
            table = {"sensor": m.sensors, "controller": m.controllers, "valve": m.valves}[role]
            ag = m.agents.get(getattr(table.get(part), "agent", None) or "")
            if ag is not None and _period(ag, snap["at"]):
                stages[f"its {role} ({ag.name}, {ag.schedule})"] = _period(ag, snap["at"])
        slowest = max(stages, key=stages.get) if stages else None
        if load > 0 and ours < 0.95 * load:
            # falling behind: what went out was less than what came in. Saturated only when each
            # opening moved the same amount (the valve at its limit); else it may be asking too little
            from .spec.projections import opened_amounts
            amounts = [a for v in lp["valves"] for a in opened_amounts(project, v, since, snap["at"])]
            limits = [m.valves[v].max for v in lp["valves"] if m.valves[v].max]
            at_limit = (bool(limits) and len(amounts) >= 3 and sum(a >= limits[0] * 0.999 for a in amounts) >= len(amounts) / 2) or (
                not limits and len(amounts) >= 3 and len(set(amounts)) == 1 and (amounts[0] or 0) > 0)
            # the cause, in words no view rewrites, so every page says it alike (dynamics.words)
            cause = "saturated, moving its most each run" if at_limit else "falling behind the load"
            did = "it acts but moves nothing" if acted else "nothing ran to move any"
            says = (f"goal {name} was off {off}% of the time: {cause}: {did} {way[0]} of {stock} "
                    f"while {fmt(load)}/h came {way[1]}" + (f", and {stock} grew by {fmt(grew)}" if grew and grew > 0 else "")
                    if not ours else
                    f"goal {name} was off {off}% of the time: {cause}. Its valve moved {fmt(ours)}/h {way[0]} while "
                    f"{fmt(load)}/h came {way[1]}" + (f", and {stock} grew by {fmt(grew)}" if grew and grew > 0 else "") + ". "
                    + ((f"Its openings ran at its max of {fmt(limits[0])}" if limits else f"Every opening moved {fmt(amounts[0])}")
                   + ": it needs more per run, or less load" if at_limit else
                       "More per run, or acting more often" + (f" ({slowest} is the slowest stage)" if slowest else "")))
        else:
            says = (f"goal {name} was off {off}% of the time: answering too late, though it keeps up on average"
                    + (f"; {slowest} is the slowest stage" if slowest else ""))
        # a job that empties the stock on a schedule holds only if load × period fits the room under the setpoint
        pts = snap["stocks"].get(stock, {}).get("points") or []
        op, target = c.target()
        if load > 0 and pts and op in ("<=", "<") and slowest:
            room = target - min(v for _, v in pts)
            needed = room / (load / 3600.0) if room > 0 else None
            if needed is not None and stages[slowest] > needed:     # only when it runs less often than that
                says += (f". To hold it, it would have to act at least every {human(needed)}"
                         + (" (cron cannot: once a minute is its finest)" if needed < 60 and any(
                             x.cron for x in m.agents.values() if x.name in slowest) else ""))
        out.append({"controller": name, "agent": c.agent, "kind": a.kind if a else "", "share": lp["off_share"],
                    "count": 0, "decision": "", "about": "loop", "goal": name, "says": says})
    # upstream action piling up behind a loop that is off: the anti-windup question for loops in series
    for up, lp in snap["loops"].items():
        for f in lp["flows"]:
            down_stock = m.flows[f].target
            for down, dl in snap["loops"].items():
                if down == up or dl["stock"] != down_stock or dl.get("off_share", 0) < 0.5:
                    continue
                if m.controllers[down].target()[0] not in ("<=", "<"):   # only a stock kept low can be overfed
                    continue
                moved = snap["flows"].get(f, {}).get("rate") or 0
                if moved > 0:
                    out.append({"controller": up, "agent": m.controllers[up].agent, "kind": "", "share": dl["off_share"],
                                "count": 0, "decision": "", "about": "loop", "goal": up,
                                "says": f"goal {up} keeps feeding {down_stock} ({fmt(moved)}/h) while goal {down} is off "
                                        f"{round(dl['off_share'] * 100)}% of the time: work piles up downstream. Hold it back "
                                        f"while {down} is off (its controller can read {down_stock}, or listen for loop.holding@{down})"})
    for c in m.controllers.values():
        a = m.agents.get(c.agent or "")
        if a is None or a.rung > 3:
            continue
        d = decisions(project, c.name, since, snap["at"])
        if d["count"] >= LADDER_MIN and d["kinds"][0][1] / d["count"] >= LADDER_SHARE:
            word, n = d["kinds"][0]
            lower = "a rule" if a.rung >= 2 else "a decision or a rule"
            word = word.replace("#", "N")
            out.append({"controller": c.name, "agent": a.name, "kind": a.kind, "share": n / d["count"], "count": d["count"],
                        "decision": word, "about": "ladder", "says": f"{a.name} ({a.kind}) decided \"{word}\" {n} of {d['count']} times: "
                                                  f"{lower} could fill it"})
    return out


LEVELS = {"bad": 0, "warn": 1, "hint": 2}
UNKNOWN_GRACE = 120.0          # a loop with no reading this long after the record starts is a problem


WORDS = ("holding", "off", "open", "unknown", "stale")     # the words a reader sees for a goal's state


def goal_row(lp: dict, unit: str = "") -> dict:
    """A goal's one word and its row's columns, said once here for every surface that lists it (goalrow.js draws
    them). The word is its status for now; trend and expected are filled by later work, never by a page."""
    return {"word": lp["status"] if lp["status"] in WORDS else "unknown",
            "row": {"measure": lp["stock"], "value": lp["value"], "unit": unit,
                    "bound_words": f"{lp['setpoint']}{lp.get('band') or ''}", "trend": None, "expected": None}}


def off_by_words(setpoint: str, error, tolerance: float = 0.0, unit: str = "", off: bool = False) -> str | None:
    """How far a goal is from its bound, the one phrase every surface outside Blocks prints (Blocks says
    e = r − y with its sign): ``off by 36 tickets`` past a <= or >= bound, ``28 short of 180`` below a
    setpoint and ``12 over 80%`` above it, ``within its band`` inside its tolerance; None when not known.
    ``off`` is the loop's status (Controller.status, with its hysteresis): an off loop is never worded as
    inside, so it gets its distance even within its tolerance, and ``at its bound`` on a strict bound at e = 0."""
    import re
    got = re.match(r"\s*(<=|>=|==|[<>=≤≥])\s*(-?[\d.]+(?:e[-+]?\d+)?)", setpoint or "")
    if error is None or not got:
        return None
    d, at = abs(error), float(got.group(2))
    say = (lambda x: f"{fmt(x)}%") if unit == "%" else (lambda x: f"{fmt(x)} {unit}" if unit else fmt(x))
    if off and not d:
        return "at its bound"
    if d and d <= tolerance and not off:
        return "within its band"
    if got.group(1) not in ("==", "="):
        return f"off by {say(d)}" if d else "within its bound"
    return f"{fmt(d)} {'short of' if error > 0 else 'over'} {say(at)}" if d else "on its setpoint"


def goals_off(snap: dict, names: bool = False) -> dict:
    """The only count of goals not holding: ``system`` (off) and ``open`` count the goals no upkeep template made,
    ``own`` each upkeep template's goals off or open, ``unknown`` every goal without a reading (an upkeep goal's
    too); ``names`` gives the sorted names instead of counts. SPEC §8, upkeep goals."""
    out: dict = {"system": [], "unknown": [], "open": [], "own": {t: [] for t in sorted(OWN_TEMPLATES)}}
    for name, lp in sorted(snap["loops"].items()):
        t, s = lp.get("upkeep"), lp["status"]
        if t and s in ("off", "open"):
            out["own"].setdefault(t, []).append(name)
        elif s == "unknown" or (not t and s in ("open", "off")):
            out[{"off": "system"}.get(s, s)].append(name)
    return out if names else {**{k: len(out[k]) for k in ("system", "unknown", "open")},
                              "own": {t: len(v) for t, v in out["own"].items()}}


def goals_said(g: dict) -> str:
    """``goals_off``'s counts as the CLI says them (``ergostat`` and ``ergostat projects`` alike), as the header does."""
    return " · ".join([f"{g['system']} goal{'' if g['system'] == 1 else 's'} off"] + [f"{g[k]} {k}" for k in ("open", "unknown") if g[k]]
                      + ([f"model upkeep {sum(g['own'].values())}"] if sum(g["own"].values()) else []))


def quiet(project, snap: dict, system: str) -> str | None:
    """A quiet system's sentence: every goal of ``system`` or of a system within it (as its closed box folds them in;
    the goals in ``snap["loops"]``, as /api/loops has them) holding, and how many items their blocks hold leases on
    now; None when one is off, open, stale or unknown, or it has none (SPEC §8, a quiet system)."""
    spec = getattr(project.model, "spec", None)
    inside = (lambda s: system in spec.chain(s)) if spec is not None else (lambda s: s == system)
    said = [lp["status"] for lp in snap["loops"].values() if lp.get("system") and inside(lp["system"])]
    if not said or any(s != "holding" for s in said):
        return None
    from .spec import items as its
    from .spec.ir import LEASED
    n = sum(its.in_states(project.events, spec, b.takes.kind, [LEASED], {"lease.block": b.name}, until=snap["at"])[0]
            for b in (spec.blocks.values() if spec is not None else ()) if b.takes and b.system and inside(b.system))
    return (f"all {len(said)} goal{'s' * (len(said) != 1)} holding, "
            + (f"{n} item{'s' * (n != 1)} being worked" if n else "nothing being worked"))


def setpoint_text(lp: dict) -> str:
    return lp["setpoint"] + lp.get("band", "")


def attention(snap: dict, running: bool = True, model=None) -> list[dict]:
    """What needs the owner: problems first (bad, then warnings), suggestions (hints) last.
    Missing readings count only while running."""
    if snap.get("before_record"):
        import time as _t
        return [{"level": "warn", "what": "the record", "says": "this moment is before the record starts "
                 f"({_t.strftime('%Y-%m-%d %H:%M', _t.localtime(snap['starts']))}): nothing is known then"}]
    out = []
    from .remote import remote_parts
    spec = getattr(model, "spec", None)
    theirs = remote_parts(spec)
    mod = {i for i, u in (getattr(spec, "uses", None) or {}).items() if (u or {}).get("template") == "modelling"}
    for name, lp in snap["loops"].items():
        if f"goal.{name}" in theirs:                   # a remote's own loop: its business, said on its own page (SPEC §4c)
            continue
        if lp["status"] == "open" and f"stock.{lp['stock']}" in theirs:   # a goal here on a remote's stock: watched,
            continue                                                       # acted on there (nothing here may act on it)
        of = {"what": f"goal {name}", "goal": name}     # the goal by its name, a field: never parsed from the words
        if lp["status"] == "off" and lp.get("breaking"):
            n, each = lp["breaking_n"], lp["per"]
            out.append({"level": "bad", **of, "says": f"{n} {each}{'' if n == 1 else 's'} break{'s' if n == 1 else ''} "
                        f"it (each {each}'s {lp['stock']} {setpoint_text(lp)}): {per_says(lp)}"})
        elif lp["status"] == "off" and lp.get("per"):        # off, and none past its tolerance: holding only back within
            out.append({"level": "bad", **of, "says": f"the worst {lp['per']}'s {lp['stock']} is "
                        f"{fmt(lp['value'])}, setpoint {setpoint_text(lp)}: none is past its tolerance now; it holds again "
                        "once each is back within the setpoint"})
        elif lp["status"] == "off":
            out.append({"level": "bad", **of, "says": f"{lp['stock']} is {fmt(lp['value'])}, "
                        f"setpoint {setpoint_text(lp)} ({lp.get('off_by_words')})"})
        elif lp["status"] == "stale":
            does = {"act": "its controllers act on it as it was", "hold": "what it commands is held",
                    "off": "it counts as off"}[lp["on_stale"]]
            out.append({"level": "warn", **of, "says": f"{lp['stock']} was last read {human(lp['stale'])} "
                        f"ago, too long for its sensor: stale ({does}; on-stale: {lp['on_stale']})"})
        elif lp["status"] == "open":
            out.append({"level": "warn", **of, "says": "cannot close: " + "; ".join(lp["gaps"])})
        elif lp["status"] == "unknown" and running and snap.get("recorded", 0) > UNKNOWN_GRACE:
            who = ""
            if model is not None:
                fillers = [model.sensors[s].agent for s in lp["sensors"] if model.sensors[s].agent in model.agents]
                kinds = {model.agents[a].kind for a in fillers}
                who = (" (its sensor is filled by a person, who has reported no reading)" if kinds == {"person"}
                       else f" (sensor {', '.join(lp['sensors'])})")
            out.append({"level": "warn", **of, "says": f"no reading of {lp['stock']} yet: "
                        f"the loop cannot tell whether it holds{who}"})
        if out and out[-1].get("goal") == name:   # its state word, and whether the goal is modelling's (the page groups)
            out[-1].update(state=lp["status"], **({"modelling": True} if mod and getattr(spec.goals.get(name), "system",
                                                                                     None) in mod else {}))
            if lp.get("diagnosis_in"):                  # its suggestion, not yet due
                out[-1]["diagnosis_in"] = lp["diagnosis_in"]
    if model is not None and getattr(model, "spec", None) is not None:   # remotes that do not answer (SPEC §4c)
        from .remote import attention as remote_attention
        out += remote_attention(model.spec)
    for name, a in snap.get("alarms", {}).items():
        out.append({"level": "bad", "what": f"alarm {name}", "says": f"raised since "
                    f"{time.strftime('%H:%M', time.localtime(a['since']))}: {a['watches']} {a['bound']}"})
    from .daemons.supervise import of_daemon
    ds = snap.get("daemons", {})
    for name in dict.fromkeys(k.rpartition("#")[0] or k for k in ds):   # given up, or alarmed in the last hour (§9.7)
        d = of_daemon(ds, name)                       # (a warm one's processes together: one line, a partial give-up said)
        al = d.get("alarm") or {}
        if d.get("state") == "failed" or d.get("failed") or (al and time.time() - al.get("at", 0) < 3600):
            part = f"{d['state']}: " if d.get("processes") else ""
            log = f"logs/daemon-{name}#N.log" if d.get("processes") else f"logs/daemon-{name}.log"
            out.append({"level": "bad", "what": f"daemon {name}", "says": f"{part}{al.get('why') or d.get('why')} "
                        f"({time.strftime('%H:%M', time.localtime(al.get('at') or time.time()))}); its log: {log}"})
    for name, a in snap["agents"].items():
        if a["failing"]:
            note = (a["last"] or {}).get("data", {}).get("note", "failed")
            out.append({"level": "bad", "what": f"agent {name}", "says": f"its last run failed ({note})"})
        if a["refused"]:
            out.append({"level": "warn", "what": f"agent {name}", "says": f"{a['refused']} lines refused "
                        f"(a part it does not fill, or one of ergostat's own event types: ergostat event --type agent.refused)"})
        if a.get("unread"):
            out.append({"level": "warn", "what": f"agent {name}", "says": f"{a['unread']} lines looked meant for ergostat but "
                        f"could not be read (broken JSON, or naming no part or event); they are in its log"})
        if a.get("contradicted"):
            n = a["contradicted"]
            out.append({"level": "bad", "what": f"agent {name}", "says": f"{n} claim{'s' if n > 1 else ''} it made "
                        f"contradicted by the record (latest: {a.get('contradicted_latest')}; Items: ergostat.claim)"})
        if a["stale"] and running:
            out.append({"level": "warn", "what": f"agent {name}", "says": f"no recent reading from {', '.join(a['stale'])}"})
    for m in snap.get("messages", []):               # the owner's words that reached no work (SPEC §12h)
        short = m["id"].split("/", 1)[1]
        text = m["text"] if len(m["text"]) <= 80 else m["text"][:77] + "..."
        out.append({"level": "warn", "what": f"message {short}", "says": f"\u201c{text}\u201d reached no work: {m['why']}. "
                    f"Route it: ergostat messages {short} --about ITEM|PART, or on its page"})
    for x in snap.get("leases", []):                 # dead letters and stalls (SPEC §9.5)
        if x["what"] == "dead":
            last = f"; the last {x['how']}" + (f": {x['why']}" if x.get("why") else "") if x.get("how") else ""
            out.append({"level": "bad", "what": f"item {x['item']}", "says": f"a dead letter after {x.get('attempts')} "
                        f"attempts by {x.get('block')}{last}. Redrive it when its cause is fixed: ergostat lease {x['item']} "
                        f"--redrive"})
        else:
            silent = x.get("silent")
            out.append({"level": "warn", "what": f"item {x['item']}", "says": f"the lease {x.get('block')} held on it "
                        f"expired" + (f": its run was silent {fmt(silent / 60)} min" if silent else "")
                        + "; it went back to be taken again"})
    for c in snap.get("cycles", []):                 # precedence that goes round (SPEC §5a, relations)
        said = ", ".join(c[:6]) + (f" and {len(c) - 6} more" if len(c) > 6 else "")
        out.append({"level": "warn", "what": f"item {c[0]}", "item": c[0],
                    "says": f"a cycle of precedence relations: {said} each wait on another, so none can be ready. "
                    f"Take one of the links away"})
    for x in snap.get("findings", []):               # a kind's latest finding (its `attention:` field, SPEC §5a)
        if x.get("error"):
            out.append({"level": "warn", "what": f"items {x['kind']}", "says": f"its latest {x['field']} could not be "
                        f"read ({x['error']})"})
        else:
            text = x["says"] if len(x["says"]) <= 400 else x["says"][:397] + "..."
            out.append({"level": "warn", "what": f"item {x['item']}", "item": x["item"], "says": text})
    for w in snap.get("quarantined", []):
        out.append({"level": "warn", "what": f"workspace {w['pool']}-{w['slot']}",
                    "says": f"quarantined ({w.get('why') or 'dirty or broken'}): never reused until freed, ergostat "
                    f"workspaces {w['pool']} --free {w['slot']}"})
    if snap.get("reports"):                         # reports upstream waiting for the owner to read (SPEC §12m): one line
        rs = snap["reports"]
        out.append({"level": "warn", "what": "reports upstream", "waiting": True, **({"item": rs[0]["id"]} if len(rs) == 1 else {}),
                    "says": (f"{len(rs)} drafted" if len(rs) > 1 else f"\u201c{rs[0]['title'][:70]}\u201d drafted")
                    + " about ergostat itself, scrubbed, for you to read and submit by hand if you choose: ergostat report"})
    for h in snap.get("hints", []):                  # a goal's: the goal named once, as its heading
        goal = f"goal {h['goal']}" if h.get("goal") else None
        out.append({"level": "hint", "what": goal, "goal": h["goal"], "says": h["says"].removeprefix(goal + " ")} if goal
                   else {"level": "hint", "what": f"controller {h['controller']}", "controller": h["controller"], "says": h["says"]})
    for name, r in snap["residuals"].items():
        if r["significant"]:
            out.append({"level": "warn", "what": f"stock {name}", "says": f"changed {fmt(r['change'])}, the known flows explain "
                        f"{fmt(r['explained'])}: {fmt(r['unexplained'])} unexplained" + (f" ({r['why']})" if r.get("why") else "")})
    from .inbox import entries as en
    asks = [{"level": "warn", "what": e["id"], "link": e["link"], "answer": e["verbs"], "kind": e["kind"],   # waiting on a person
             **{k: e[k] for k in ("fold", "about", "system") if e.get(k)},
             "object": e.get("action") or e.get("block") or "",                         # what the answer is about
             **{k: e[k] for k in ("flow", "unit") if k in e},                    # what a number answered means
             "says": f"{e['summary']}, waiting {human(e['age'])}" + (f" (why: {e['why']})" if e.get("why") else "")
             + (f"; {e['record']}" if e.get("record") else "") + (f". {e['suggest']}" if e.get("suggest") else "")
             + (f". runs: {e['run']}" if e.get("run") else "") + (f". {en.command(e)}" if e["verbs"] else ""),
             "first": e["summary"] + (f" because {by}" if by else ""), "age": human(e["age"]), "run": e.get("run"),
             "cli": en.command(e), "record": e.get("record"), "suggest": e.get("suggest"),
             "more": None if by else e.get("why") or None}         # an action's reason ends its sentence, said once
            for e in snap.get("inbox", []) for by in [e["kind"] == "action" and not e.get("warn") and e.get("why")]]
    out = sorted(out, key=lambda a: LEVELS.get(a["level"], 1))           # problems first, then what waits on a person
    return [a for a in out if a["level"] == "bad"] + asks + [a for a in out if a["level"] != "bad"]


def fmt(x) -> str:
    if x is None:
        return "?"
    if isinstance(x, float):
        if x == int(x) and abs(x) < 1e9:
            return str(int(x))
        return f"{x:.3g}" if abs(x) < 100 else f"{x:.0f}"
    return str(x)
