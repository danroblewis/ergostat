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


def stock_value(project, stock: str) -> dict:
    m = project.model
    best = None
    for s in _sensor_for(m, stock):
        got = project.measurements.latest(f"sensor/{s.name}")
        if got and (best is None or got[0] > best[0]):
            best = (got[0], got[1], s.name)
    if best is None:
        return {"value": None, "at": None, "sensor": None}
    return {"value": best[1], "at": best[0], "sensor": best[2]}


def history(project, stock: str, since: float) -> list[tuple[float, float]]:
    pts = []
    for s in _sensor_for(project.model, stock):
        pts += project.measurements.range(f"sensor/{s.name}", since)
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


def _openings(project, valve: str, since: float) -> list[dict]:
    return project.events.query(n=None, type="valve.opened", item=valve, since=since)


def snapshot(project, window: float = WINDOW, now: float | None = None) -> dict:
    m = project.model
    now = now or time.time()
    since = now - window
    hours = window / 3600.0
    stocks, flows, loops, residuals = {}, {}, {}, {}

    for name in m.stocks:
        v = stock_value(project, name)
        pts = history(project, name, since)
        stocks[name] = {**v, "unit": m.stocks[name].unit,
                        "change": (pts[-1][1] - pts[0][1]) if len(pts) >= 2 else None,
                        "points": pts[-60:], "inflow": 0.0, "outflow": 0.0}

    # flows known from sensors or valves; a measured flow's reading is a rate per hour
    known: dict[str, float] = {}
    for f in m.flows.values():
        rate, how, opened = None, None, None
        sensors = _sensor_for(m, f.name)
        for s in sensors:
            got = project.measurements.latest(f"sensor/{s.name}")
            if got is not None:
                rate, how = got[1], f"measured by {s.name}"
        valve = m.valve_of(f.name)
        if valve is not None:
            ops = _openings(project, valve.name, since)
            opened = {"count": len(ops), "amount": sum(o["data"].get("amount", 0) for o in ops),
                      "last": ops[-1]["time"] if ops else None}
            if rate is None:
                rate, how = opened["amount"] / hours, f"opened by {valve.name}"
        if rate is not None:
            known[f.name] = rate
        flows[f.name] = {"rate": rate, "how": how or ("estimated" if f.disturbance else "unknown"), "per": "hour",
                         "from": f.source, "to": f.target, "disturbance": f.disturbance, "valve": valve.name if valve else None,
                         "openings": opened, "estimated": False}

    # residuals, and the estimated disturbances drawn from them
    for name, s in stocks.items():
        if s["change"] is None:
            continue
        pts = s["points"]
        span = max(pts[-1][0] - pts[0][0], 1e-9) / 3600.0
        explained = 0.0
        for f in m.flows_of(name):
            if f.name in known:
                sign = 1 if f.target == name else -1
                if flows[f.name]["openings"] is not None and flows[f.name]["how"].startswith("opened"):
                    # what the valve moved between the first and the last reading
                    amount = sum(o["data"].get("amount", 0) for o in _openings(project, flows[f.name]["valve"], pts[0][0])
                                 if o["time"] <= pts[-1][0])
                    explained += sign * amount
                else:
                    got = moved(project, f.name, pts[0][0], pts[-1][0])
                    explained += sign * (got if got is not None else known[f.name] * span)
        unexplained = s["change"] - explained
        estimated = [f for f in m.flows_of(name) if f.disturbance and f.name not in known]
        scale = abs(s["change"]) + abs(explained)
        significant = abs(unexplained) > max(1e-9, 0.1 * scale)
        if estimated and significant:
            share = unexplained / len(estimated)
            for f in estimated:
                sign = 1 if f.target == name else -1
                flows[f.name].update(rate=max(0.0, sign * share / span), how=f"estimated from {name}", estimated=True)
            residuals[name] = {"unexplained": unexplained, "explained": explained, "change": s["change"],
                               "absorbed_by": [f.name for f in estimated], "significant": False, "hours": span}
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
            status = "holding" if abs(error) <= c.tolerance else "off"
        decisions = project.events.query(n=1, type="controller.decided", item=c.name)
        last_open = max((o["time"] for v in lp.valves for o in project.events.query(n=1, type="valve.opened", item=v)),
                        default=None)
        reads = [project.measurements.latest(f"sensor/{s}") for s in lp.sensors]
        last_read = max((r[0] for r in reads if r), default=None)
        cycled = bool(last_read and last_read >= since and ((decisions and decisions[-1]["time"] >= since)
                                                           or (last_open and last_open >= since)))
        loops[lp.name] = {"stock": c.holds, "setpoint": c.setpoint, "tolerance": c.tolerance, "value": value,
                          "error": error, "status": status, "gaps": lp.gaps, "sensors": lp.sensors, "valves": lp.valves,
                          "flows": lp.flows, "controller": c.name, "last_read": last_read,
                          "last_decision": decisions[-1] if decisions else None, "last_opening": last_open,
                          "observed": cycled}

    agents = {}
    for a in m.agents.values():
        ran = project.events.query(n=None, item=a.name, type="agent.*", since=since)
        done = [e for e in ran if e["type"] in ("agent.ran", "agent.failed")]
        last_any = max(project.events.query(n=1, item=a.name, type="agent.ran") +
                       project.events.query(n=1, item=a.name, type="agent.failed"), key=lambda e: e["seq"], default=None)
        roles = m.roles_of(a.name)
        stale = []
        if a.every:
            for r in roles:
                if r.kind == "sensor":
                    got = project.measurements.latest(f"sensor/{r.name}")
                    if got is None or now - got[0] > STALE_RUNS * a.every:
                        stale.append(r.name)
        agents[a.name] = {"kind": a.kind, "rung": a.rung, "roles": [{"kind": r.kind, "name": r.name} for r in roles],
                          "every": a.every, "on": a.on, "runs": len(done),
                          "failed": sum(1 for e in done if e["type"] == "agent.failed"),
                          "refused": sum(e["data"].get("refused", 0) for e in done),
                          "last": last_any, "failing": bool(last_any and last_any["type"] == "agent.failed"),
                          "stale": stale, "runs_itself": bool(a.command and a.kind != "person")}

    return {"at": now, "window": window, "stocks": stocks, "flows": flows, "loops": loops, "residuals": residuals,
            "agents": agents}


def attention(snap: dict) -> list[dict]:
    """What needs the owner, most important first."""
    out = []
    for name, lp in snap["loops"].items():
        if lp["status"] == "off":
            out.append({"level": "bad", "what": f"loop {name}", "says": f"{lp['stock']} is {fmt(lp['value'])}, "
                        f"setpoint {lp['setpoint']} (off by {fmt(abs(lp['error']))})"})
        elif lp["status"] == "open":
            out.append({"level": "warn", "what": f"loop {name}", "says": "cannot close: " + "; ".join(lp["gaps"])})
    for name, a in snap["agents"].items():
        if a["failing"]:
            note = (a["last"] or {}).get("data", {}).get("note", "failed")
            out.append({"level": "bad", "what": f"agent {name}", "says": f"its last run failed ({note})"})
        if a["refused"]:
            out.append({"level": "warn", "what": f"agent {name}", "says": f"{a['refused']} lines refused: it named parts it does not fill"})
        if a["stale"]:
            out.append({"level": "warn", "what": f"agent {name}", "says": f"no recent reading from {', '.join(a['stale'])}"})
    for name, r in snap["residuals"].items():
        if r["significant"]:
            out.append({"level": "warn", "what": f"stock {name}", "says": f"changed {fmt(r['change'])}, the known flows explain "
                        f"{fmt(r['explained'])}: {fmt(r['unexplained'])} unexplained"})
    return out


def fmt(x) -> str:
    if x is None:
        return "?"
    if isinstance(x, float):
        if x == int(x) and abs(x) < 1e9:
            return str(int(x))
        return f"{x:.3g}" if abs(x) < 100 else f"{x:.0f}"
    return str(x)
