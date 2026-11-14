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

WINDOW = 3600.0
STALE_RUNS = 3          # a reading older than this many of its agent's periods is stale


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


def moved(project, flow: str, t0: float, t1: float) -> float | None:
    """How much a measured flow moved between ``t0`` and ``t1``: its readings are rates per hour,
    each covering the time since the reading before it."""
    total, any_sensor = 0.0, False
    for s in _sensor_for(project.model, flow):
        pts = project.measurements.range(f"sensor/{s.name}", t0 - 3600, t1)
        prev = None
        for t, r in pts:
            if prev is not None and t > t0:
                total += r * (t - max(prev, t0)) / 3600.0
            prev = t
        any_sensor = any_sensor or bool(pts)
    return total if any_sensor else None


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
                rate, how = got[1], f"measured by {s.name}"
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
        steps = sorted(d for a, b in zip(pts, pts[1:], strict=False) if (d := abs(b[1] - a[1])) > 0)
        typical = steps[len(steps) // 2] if len(steps) >= 2 and len(pts) >= 4 else 0.0
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
        share = unexplained / len(estimated) if estimated else 0.0
        backwards = [f for f in estimated if (1 if f.target == name else -1) * share < 0]
        if estimated and not backwards and abs(unexplained) > 1e-9:
            for f in estimated:
                sign = 1 if f.target == name else -1
                flows[f.name].update(rate=sign * share / span, how=f"estimated from {name}", estimated=True)
            residuals[name] = {"unexplained": unexplained, "explained": explained, "change": s["change"],
                               "absorbed_by": [f.name for f in estimated], "significant": False, "hours": span}
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
            last = project.events.query(n=1, item=lp.name, type="loop.*", until=now)
            status = c.status(value, was_off=bool(last and last[-1]["type"] == "loop.off"))
        decisions = project.events.query(n=1, type="controller.decided", item=c.name, until=now)
        last_open = max((o["time"] for v in lp.valves for o in project.events.query(n=1, type="valve.opened", item=v, until=now)),
                        default=None)
        reads = [project.measurements.latest(f"sensor/{s}", now) for s in lp.sensors]
        last_read = max((r[0] for r in reads if r), default=None)
        # how much of the recorded window the loop spent off, from its crossings
        crossings = project.events.query(n=None, item=lp.name, type="loop.*", until=now)
        off_time, off_from = 0.0, None
        before = [e for e in crossings if e["time"] < start]
        if before and before[-1]["type"] == "loop.off":
            off_from = start
        for e in crossings:
            if e["time"] < start:
                continue
            if e["type"] == "loop.off" and off_from is None:
                off_from = e["time"]
            elif e["type"] == "loop.holding" and off_from is not None:
                off_time += e["time"] - off_from
                off_from = None
        if off_from is not None:
            off_time += now - off_from
        off_share = off_time / max(now - start, 1.0)
        cycled = bool(last_read and last_read >= since and ((decisions and decisions[-1]["time"] >= since)
                                                           or (last_open and last_open >= since)))
        loops[lp.name] = {"stock": c.holds, "setpoint": c.setpoint, "tolerance": c.tolerance, "band": c.band_text(), "value": value,
                          "error": error, "status": status, "gaps": lp.gaps, "sensors": lp.sensors, "valves": lp.valves,
                          "flows": lp.flows, "controller": c.name, "last_read": last_read,
                          "last_decision": decisions[-1] if decisions else None, "last_opening": last_open,
                          "observed": cycled, "off_share": round(off_share, 3)}

    agents = {}
    for a in m.agents.values():
        counted = project.events.runs(a.name, since, now)
        last_any = max(project.events.query(n=1, item=a.name, type="agent.ran", until=now) +
                       project.events.query(n=1, item=a.name, type="agent.failed", until=now), key=lambda e: e["seq"], default=None)
        begun = project.events.query(n=1, item=a.name, type="agent.started", until=now)
        running_since = begun[-1]["time"] if begun and (last_any is None or begun[-1]["seq"] > last_any["seq"]) else None
        roles = m.roles_of(a.name)
        stale = []
        if a.every:
            for r in roles:
                if r.kind == "sensor":
                    got = project.measurements.latest(f"sensor/{r.name}", now)
                    if got is None or now - got[0] > STALE_RUNS * a.every:
                        stale.append(r.name)
        agents[a.name] = {"kind": a.kind, "rung": a.rung, "roles": [{"kind": r.kind, "name": r.name} for r in roles],
                          "every": a.every, "on": a.on, "cron": a.cron, "schedule": a.schedule, **counted,
                          "last": last_any, "failing": bool(last_any and last_any["type"] == "agent.failed"),
                          "stale": stale, "runs_itself": bool(a.command and a.kind != "person"),
                          "running_since": running_since}

    snap = {"at": now, "live": live, "window": window, "recorded": max(0.0, now - start) if oldest else 0.0,
            "starts": oldest, "before_record": bool(oldest and now < oldest),
            "stocks": stocks, "flows": flows, "loops": loops, "residuals": residuals,
            "agents": agents}
    snap["hints"] = ladder_hints(project, snap)
    return snap


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


def ladder_hints(project, snap: dict) -> list[dict]:
    """Roles a cheaper agent could fill: a controller whose agent is a person, an AI agent or a
    decision, and that decided the same thing at least 80% of at least 10 times in the window."""
    m = project.model
    out = []
    since = snap["at"] - snap["window"]
    for name, lp in snap["loops"].items():
        # a loop off most of the time though its agents act: first, can its valve keep up with the load
        # at all (saturation)? only if it can, is it sampling too slowly?
        if not (lp.get("off_share", 0) >= 0.5 and lp["observed"] and snap.get("recorded", 0) >= 600):
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
        if load > 0 and ours < 0.95 * load:
            says = (f"loop {name} was off {off}% of the time: its valve moved {fmt(ours)}/h "
                    f"{'out' if drains else 'in'} while {fmt(load)}/h came {'in' if drains else 'out'}. It is saturated: "
                    f"a valve with more capacity, or less load, not faster sampling")
        elif a and (a.every or a.cron):
            says = (f"loop {name} was off {off}% of the time though its valve can keep up: its controller runs "
                    f"{a.schedule}; run it more often")
        else:
            says = f"loop {name} was off {off}% of the time though its valve can keep up: it acts too late (on {a.schedule if a else '?'})"
        out.append({"controller": name, "agent": c.agent, "kind": a.kind if a else "", "share": lp["off_share"],
                    "count": 0, "decision": "", "about": "loop", "says": says})
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
        if a["stale"] and running:
            out.append({"level": "warn", "what": f"agent {name}", "says": f"no recent reading from {', '.join(a['stale'])}"})
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
