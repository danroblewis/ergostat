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

import time

from .durations import human

WINDOW = 3600.0
STALE_RUNS = 3          # a reading older than this many of its agent's periods is stale



def crossings_of(project, loop: str, since: float, until: float) -> list[dict]:
    """A loop's crossings in a span, and the last one before it (whether it was off when the span
    began): never every crossing of the whole record."""
    before = project.events.query(n=1, item=loop, type="loop.*", until=since - 1e-6, unvoided=True)
    return before + project.events.query(n=None, item=loop, type="loop.*", since=since, until=until, unvoided=True)

def _sensor_for(m, target: str) -> list:
    return [s for s in m.sensors.values() if s.measures == target]


def stock_value(project, stock: str, at: float | None = None) -> dict:
    m = project.model
    best = None
    for s in _sensor_for(m, stock):
        got = project.measurements.latest(f"sensor/{s.name}", at)
        if got and (best is None or got[0] > best[0]):
            best = (got[0], got[1], s.name)
    if best is None:
        return {"value": None, "at": None, "sensor": None}
    return {"value": best[1], "at": best[0], "sensor": best[2]}


def history(project, stock: str, since: float, until: float | None = None) -> list[tuple[float, float]]:
    pts = []
    for s in _sensor_for(project.model, stock):
        pts += project.measurements.sampled(f"sensor/{s.name}", since, until)
    return sorted(pts)


def mean_rate(project, flow: str, t0: float, t1: float) -> float | None:
    """A measured flow's average rate per hour between ``t0`` and ``t1``. Each reading is a rate
    covering the time since the reading before it (the first in the window covers back to ``t0``),
    and the last one holds until ``t1``. Several sensors on one flow are averaged, not added. None
    when no sensor has a reading in the window."""
    rates = []
    for s in _sensor_for(project.model, flow):
        pts = project.measurements.range(f"sensor/{s.name}", t0, t1)
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
    return float(sum(1 for it in its.project(project.events, spec, q["kind"],
                                                     until=t1 if where else None, fields=tuple(where)) if its.matches(it, where)
                     for mv in it.moves if mv[key] == state and t0 < mv["time"] <= t1))


def moved(project, flow: str, t0: float, t1: float) -> float | None:
    """How much a measured flow moved between ``t0`` and ``t1``: what it counted, when it counts items;
    else from its readings, rates per hour."""
    got = counted(project, flow, t0, t1)
    if got is not None:
        return got
    r = mean_rate(project, flow, t0, t1)
    return None if r is None else r * (t1 - t0) / 3600.0


def snapshot(project, window: float = WINDOW, now: float | None = None) -> dict:
    """The state at ``now`` (default: now), over the window before it; a past ``now`` looks back."""
    m = project.model
    live = now is None
    now = now or time.time()
    since = now - window
    oldest = min((t for t in (project.events.first_time(), project.measurements.first_time()) if t), default=None)
    start = max(since, oldest) if oldest else since    # every rate is over the time actually recorded
    hours = max(now - start, 60.0) / 3600.0
    stocks, flows, loops, residuals = {}, {}, {}, {}
    full: dict[str, list] = {}

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
    for f in m.flows.values():
        rate, how, opened = None, None, None
        if f.rate is not None:
            rate, how = f.rate, "declared"
        sensors = _sensor_for(m, f.name)
        for s in sensors:
            got = project.measurements.latest(f"sensor/{s.name}", now)
            if got is not None:
                # the average over the window, not the latest reading: one quiet scan is not a stopped flow
                avg = mean_rate(project, f.name, start, now)
                rate = avg if avg is not None else got[1]
                how = f"measured by {s.name}"
        valve = m.valve_of(f.name)
        if valve is not None:
            opened = project.events.opened(valve.name, start, now)
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
                    explained += sign * project.events.opened(flows[f.name]["valve"], pts[0][0], pts[-1][0])["amount"]
                elif f.rate is not None:
                    explained += sign * f.rate * span
                else:
                    got = moved(project, f.name, pts[0][0], pts[-1][0])
                    explained += sign * (got if got is not None else known[f.name] * span)
        rest = change - explained
        raw = [x for s_ in _sensor_for(m, name) for x in project.measurements.range(f"sensor/{s_.name}", pts[0][0], pts[-1][0])]
        raw = sorted(raw) if len(raw) <= 5000 else sorted(raw)[:5000]      # the ordinary step of the readings themselves
        steps = sorted(d for a, b in zip(raw, raw[1:], strict=False) if (d := abs(b[1] - a[1])) > 0)
        typical = steps[len(steps) // 2] if len(steps) >= 2 and len(raw) >= 4 else 0.0
        return change, explained, rest, abs(rest) > max(1e-9, 0.05 * (abs(change) + abs(explained)), 2 * typical)

    for name, s in stocks.items():
        if s["change"] is None or not m.flows_of(name):    # no flows declared: a plain measurement, nothing to explain
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

    for lp in m.loops():
        c = lp.controller
        value = stocks.get(c.holds, {}).get("value")
        if not lp.closes:
            status, error = "open", None
        elif value is None:
            status, error = "unknown", None
        else:
            error = c.error(value)
            last = project.events.query(n=1, item=lp.name, type="loop.*", until=now, unvoided=True)
            status = c.status(value, was_off=bool(last and last[-1]["type"] == "loop.off"))
        decisions = project.events.query(n=1, type="controller.decided", item=c.name, until=now)
        acts_on = lp.valves or (c.drives if c.through else [])    # the long way: where its controller acts, first along it
        last_open = max((o["time"] for v in acts_on for o in project.events.query(n=1, type="valve.opened", item=v, until=now)),
                        default=None)
        knob = next((p.split(".", 1)[1] for p in c.through if p.startswith("auxiliary.")), None) if not acts_on else None
        if knob:                                                  # it acts by setting an auxiliary: when it last set it
            last_open = max((e["time"] for t in ("auxiliary.set", "variable.set")      # variable.set: its old name, in old records
                             for e in project.events.query(n=1, type=t, item=knob, until=now)), default=None)
        reads = [project.measurements.latest(f"sensor/{s}", now) for s in lp.sensors]
        last_read = max((r[0] for r in reads if r), default=None)
        # how much of the recorded window the loop spent off, from its crossings
        crossings = crossings_of(project, lp.name, start, now)
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
        opens = sorted(e["time"] for v in acts_on
                       for e in project.events.query(n=None, type="valve.opened", item=v, since=start, until=now))
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
        loops[lp.name] = {"stock": c.holds, "setpoint": c.setpoint, "tolerance": c.tolerance, "band": c.band_text(), "value": value,
                          "error": error, "status": status, "gaps": lp.gaps, "sensors": lp.sensors, "valves": lp.valves,
                          "flows": lp.flows, "controller": c.name, "last_read": last_read,
                          "last_decision": decisions[-1] if decisions else None, "last_opening": last_open,
                          "observed": cycled, "off_share": round(off_share, 3), "open_loop": lp.open_loop,
                          "answers_in": answers[len(answers) // 2] if answers else None,
                          "back_in": recoveries[len(recoveries) // 2] if recoveries else None,
                          "back_in_slowest": recoveries[-1] if recoveries else None, "times_off": len(recoveries)}

    contradicted: dict[str, list[dict]] = {}          # claims the record contradicts, by the block that made them (SPEC §12g)
    for e in project.events.query(n=500, type="ergostat.claim.contradicted", since=since, until=now):
        contradicted.setdefault(e["data"].get("block") or "", []).append(e)
    agents = {}
    for a in m.agents.values():
        counted = project.events.runs(a.name, since, now)
        last_any = max(project.events.query(n=1, item=a.name, type="agent.ran", until=now) +
                       project.events.query(n=1, item=a.name, type="agent.failed", until=now), key=lambda e: e["seq"], default=None)
        begun = project.events.query(n=1, item=a.name, type="agent.started", until=now)
        running_since = begun[-1]["time"] if begun and (last_any is None or begun[-1]["seq"] > last_any["seq"]) else None
        roles = m.roles_of(a.name)
        stale = []
        if a.every or a.cron:                             # a reading older than a few of its runs is stale
            for r in roles:
                if r.kind == "sensor":
                    got = project.measurements.latest(f"sensor/{r.name}", now)
                    if got is None or _missed(a, got[0], now):
                        stale.append(r.name)
        agents[a.name] = {"kind": a.kind, "rung": a.rung, "roles": [{"kind": r.kind, "name": r.name} for r in roles],
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
    snap["actions"], snap["quarantined"] = held_actions(project, now), quarantined(project)
    return snap


def held_actions(project, now: float) -> list[dict]:
    """The gated actions held for the owner's approval (SPEC §12k), as of now: each needs attention."""
    spec = getattr(project.model, "spec", None)
    if spec is None or not spec.actions:
        return []
    from .actions import record
    try:
        got = record.stored(project, until=now)
    except Exception:
        return []
    return [{"id": a["id"], "action": a.get("action"), "item": a.get("item"), "command": a.get("command") or "",
             "time": a["time"]} for a in got.values() if a["state"] == "requested"][-20:]


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
        if snap.get("recorded", 0) < 600:                # too little record to tell saturation from slow sampling
            out.append({"controller": name, "agent": m.controllers[name].agent, "kind": "", "share": lp["off_share"],
                        "count": 0, "decision": "", "about": "loop",
                        "says": f"loop {name} was off {round(lp['off_share'] * 100)}% of the time; why (a valve too small, "
                                f"or acting too seldom) is said after 10m of record ({human(snap.get('recorded', 0))} so far)"})
            continue
        c = m.controllers[name]
        a = m.agents.get(c.agent or "")
        stock = c.holds
        mine = set(lp["flows"])
        drains = any(m.flows[f].source == stock for f in mine)
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
            amounts = [e["data"].get("amount") for v in lp["valves"]
                       for e in project.events.query(n=50, type="valve.opened", item=v, since=since, until=snap["at"])]
            limits = [m.valves[v].max for v in lp["valves"] if m.valves[v].max]
            at_limit = (bool(limits) and len(amounts) >= 3 and sum(a >= limits[0] * 0.999 for a in amounts) >= len(amounts) / 2) or (
                not limits and len(amounts) >= 3 and len(set(amounts)) == 1 and (amounts[0] or 0) > 0)
            says = (f"loop {name} was off {off}% of the time, falling behind: its valve moved {fmt(ours)}/h {way[0]} while "
                    f"{fmt(load)}/h came {way[1]}" + (f", and {stock} grew by {fmt(grew)}" if grew and grew > 0 else "") + ". "
                    + ((f"Its openings ran at its max of {fmt(limits[0])}" if limits else f"Every opening moved {fmt(amounts[0])}")
                   + ": the valve is at its limit (saturated); it needs more per run, or less load" if at_limit else
                       "More per run, or acting more often" + (f" ({slowest} is the slowest stage)" if slowest else "")))
        elif slowest:
            says = (f"loop {name} was off {off}% of the time though its valve keeps up on average: it answers too late; "
                    f"{slowest} is the slowest stage")
        else:
            says = f"loop {name} was off {off}% of the time though its valve keeps up on average: it answers too late"
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
                    "count": 0, "decision": "", "about": "loop", "says": says})
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
                                "count": 0, "decision": "", "about": "loop",
                                "says": f"loop {up} keeps feeding {down_stock} ({fmt(moved)}/h) while loop {down} is off "
                                        f"{round(dl['off_share'] * 100)}% of the time: work piles up downstream. Hold {up} back "
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
                                                  f"{lower} could fill controller {c.name}"})
    return out


LEVELS = {"bad": 0, "warn": 1, "hint": 2}
UNKNOWN_GRACE = 120.0          # a loop with no reading this long after the record starts is a problem


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
    for name, lp in snap["loops"].items():
        if lp["status"] == "off":
            out.append({"level": "bad", "what": f"loop {name}", "says": f"{lp['stock']} is {fmt(lp['value'])}, "
                        f"setpoint {setpoint_text(lp)} (off by {fmt(abs(lp['error']))})"})
        elif lp["status"] == "open":
            out.append({"level": "warn", "what": f"loop {name}", "says": "cannot close: " + "; ".join(lp["gaps"])})
        elif lp["status"] == "unknown" and running and snap.get("recorded", 0) > UNKNOWN_GRACE:
            who = ""
            if model is not None:
                fillers = [model.sensors[s].agent for s in lp["sensors"] if model.sensors[s].agent in model.agents]
                kinds = {model.agents[a].kind for a in fillers}
                who = (" (its sensor is filled by a person, who has reported no reading)" if kinds == {"person"}
                       else f" (sensor {', '.join(lp['sensors'])})")
            out.append({"level": "warn", "what": f"loop {name}", "says": f"no reading of {lp['stock']} yet: "
                        f"the loop cannot tell whether it holds{who}"})
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
    for a in snap.get("actions", []):                # gated actions held for the owner (SPEC §12k)
        short = a["id"].split("/", 1)[1]
        cmd = a["command"] if len(a["command"]) <= 80 else a["command"][:77] + "..."
        out.append({"level": "warn", "what": f"action {short}", "item": a["id"],
                    "says": f"{a['action']}" + (f" for {a['item']}" if a.get("item") else "") + f" waits for approval: "
                    f"{cmd}. Approve or deny it on its page, or ergostat actions {short} --approve (--deny)"})
    for w in snap.get("quarantined", []):
        out.append({"level": "warn", "what": f"workspace {w['pool']}-{w['slot']}",
                    "says": f"quarantined ({w.get('why') or 'dirty or broken'}): never reused until freed, ergostat "
                    f"workspaces {w['pool']} --free {w['slot']}"})
    for h in snap.get("hints", []):
        out.append({"level": "hint", "what": f"controller {h['controller']}", "says": h["says"]})
    for name, r in snap["residuals"].items():
        if r["significant"]:
            out.append({"level": "warn", "what": f"stock {name}", "says": f"changed {fmt(r['change'])}, the known flows explain "
                        f"{fmt(r['explained'])}: {fmt(r['unexplained'])} unexplained" + (f" ({r['why']})" if r.get("why") else "")})
    return sorted(out, key=lambda a: LEVELS.get(a["level"], 1))


def fmt(x) -> str:
    if x is None:
        return "?"
    if isinstance(x, float):
        if x == int(x) and abs(x) < 1e9:
            return str(int(x))
        return f"{x:.3g}" if abs(x) < 100 else f"{x:.0f}"
    return str(x)
