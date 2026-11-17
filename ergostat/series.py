"""Behaviour over time, for the charts beside the model (docs/proposals/charts.md): a part's values
over the window in equal buckets, a loop's scope (r, y, u, e) and an item kind's flow (its states
over time, and how long its finished items took).

A stock's or an auxiliary's value is its sensors' last reading in each bucket. A flow's rate (per
hour) is, in this order: its own sensors' readings (their mean in each bucket); else its items
entering or leaving a state, counted from the record; else what its valve's openings moved; else
its declared rate; else what its stock's readings did that its other flows do not explain (a
stock's successive changes). Each series says which (``how``)."""

from __future__ import annotations

import statistics

from .durations import human as dur
from .spec import items as its

POINTS = 120          # the default number of buckets over the window
MAX_POINTS = 1000


def span(p, snap: dict) -> tuple[float, float]:
    """The window the charts cover: the page's, from where the record starts when it is younger."""
    until = snap["at"]
    since = until - snap["window"]
    return (max(since, snap["starts"]) if snap.get("starts") and snap["starts"] < until else since), until


def times(since: float, until: float, n: int) -> list[float]:
    """Each bucket's middle."""
    w = (until - since) / n
    return [since + (i + 0.5) * w for i in range(n)]


def parse_ref(ref: str) -> tuple[str, str] | None:
    kind, _, name = ref.partition(".")
    return (kind, name) if kind in ("stock", "flow", "auxiliary") and name else None


def kind_of(m, name: str) -> str | None:
    """A part's kind, by its name: stock, auxiliary or flow."""
    if name in m.stocks:
        return "auxiliary" if m.stocks[name].auxiliary else "stock"
    return "flow" if name in m.flows else None


def _sensors(m, target: str) -> list[str]:
    return [s.name for s in m.sensors.values() if s.measures == target]


def level(p, name: str, since: float, until: float, n: int) -> list[float | None]:
    """A stock's (or an auxiliary's) last reading in each bucket, of whichever sensor read last."""
    out: list[float | None] = [None] * n
    when = [0.0] * n
    for s in _sensors(p.model, name):
        for b, _mean, t, v in p.measurements.bucketed(f"sensor/{s}", since, until, n):
            if t >= when[b]:
                out[b], when[b] = v, t
    return out


def _readings(p, flow: str, since: float, until: float, n: int) -> list[float | None] | None:
    """A measured flow's mean reading in each bucket (several sensors on one flow are averaged)."""
    sums, counts = [0.0] * n, [0] * n
    for s in _sensors(p.model, flow):
        for b, mean, _t, _v in p.measurements.bucketed(f"sensor/{s}", since, until, n):
            sums[b] += mean
            counts[b] += 1
    if not any(counts):
        return None
    return [sums[i] / counts[i] if counts[i] else None for i in range(n)]


def over(since: float, until: float, n: int) -> float:
    """How far back a rate counted from the record looks: a bucket, or a twelfth of the window when
    that is longer (one event in a bucket of seconds is not a rate of thousands an hour)."""
    return max((until - since) / n, (until - since) / 12)


def _per_hour(events: list[tuple[float, float]], since: float, until: float, n: int, back: float | None = None) -> list[float]:
    """Amounts at times, as a rate per hour at each bucket's end, over the time before it (``back``:
    the sensor's own window, when it has one)."""
    import bisect
    w, back = (until - since) / n, back or over(since, until, n)
    events = sorted(events)
    ts, sums = [t for t, _ in events], [0.0]
    for _, a in events:
        sums.append(sums[-1] + a)
    out = []
    for i in range(n):
        end = since + (i + 1) * w
        lo, hi = bisect.bisect_right(ts, end - back), bisect.bisect_right(ts, end)
        out.append((sums[hi] - sums[lo]) * 3600.0 / back)
    return out


def _moves(p, flow: str, since: float, until: float, n: int) -> list[float] | None:
    """A flow measured by counting items: its items entering (or leaving) the state, per hour."""
    spec = getattr(p.model, "spec", None)
    f = spec.flows.get(flow) if spec else None
    q = next((s.items for s in (f.sensors.values() if f else []) if s.items), None)
    if not q or q.get("kind") not in spec.items:
        return None
    key, state = ("to", q["entering"]) if q.get("entering") else ("from", q.get("leaving"))
    back = max(float(q.get("over") or 3600.0), (until - since) / n)       # the sensor's window: never the page's
    start = since - back
    moved = [(mv["time"], 1.0) for it in its.project(p.events, spec, q["kind"], until=until) if its.matches(it, q.get("where") or {})
             for mv in it.moves if mv[key] == state and start <= mv["time"] <= until]
    return _per_hour(moved, since, until, n, back)


def _opened(p, valves: list[str], since: float, until: float, n: int) -> list[float]:
    """What valves moved, per hour."""
    start = since - over(since, until, n)
    return _per_hour([(e["time"], float(e["data"].get("amount", 1) or 0)) for v in valves
                      for e in p.events.query(n=None, type="valve.opened", item=v, since=start, until=until)], since, until, n)


def _changes(p, flow: str, since: float, until: float, n: int) -> tuple[list[float | None], str] | None:
    """A flow nothing else measures, from its stock's successive readings: the stock's change per hour
    in each bucket, in the flow's direction, less what its other flows explain."""
    m = p.model
    f = m.flows[flow]
    stock = next((s for s in (f.target, f.source) if s and _sensors(m, s)), None)
    if stock is None:
        return None
    lv = level(p, stock, since, until, n)
    ts = times(since, until, n)
    sign = 1 if stock == f.target else -1
    others = []
    for g in m.flows_of(stock):
        if g.name == flow:
            continue
        got = rate(p, g.name, since, until, n, changes=False)
        if got is None:
            return None                          # two flows nothing measures: the stock cannot tell them apart
        others.append((1 if g.target == stock else -1, got[0]))
    out: list[float | None] = [None] * n
    prev = next(((i, v) for i, v in enumerate(lv) if v is not None), None)
    if prev is None:
        return None
    for i in range(prev[0] + 1, n):
        if lv[i] is None:
            continue
        net = (lv[i] - prev[1]) * 3600.0 / (ts[i] - ts[prev[0]])
        known = sum(sg * (r[i] or 0.0) for sg, r in others)
        out[i] = sign * (net - known)
        prev = (i, lv[i])
    return out, f"changes of {stock}"


def rate(p, flow: str, since: float, until: float, n: int, changes: bool = True) -> tuple[list, str] | None:
    """A flow's rate per hour in each bucket, and how it is known; None when nothing tells it."""
    m = p.model
    f = m.flows[flow]
    got = _readings(p, flow, since, until, n)
    if got is not None:
        return got, f"measured by {', '.join(_sensors(m, flow))}"
    back = dur(over(since, until, n))
    got = _moves(p, flow, since, until, n)
    if got is not None:
        q = next((s.items for s in m.spec.flows[flow].sensors.values() if s.items), {}) if getattr(m, "spec", None) else {}
        return got, f"items moving, from the record, over {dur(max(float(q.get('over') or 3600.0), (until - since) / n))}"
    valves = [v.name for v in m.valves.values() if v.flow == flow]
    if valves:
        return _opened(p, valves, since, until, n), f"opened by {', '.join(valves)}, over {back}"
    if f.rate is not None:
        return [f.rate] * n, "declared"
    return _changes(p, flow, since, until, n) if changes else None


def goal_of(m, name: str) -> dict | None:
    """The goal holding a stock or an auxiliary: its setpoint and tolerance, for the desired level."""
    c = next((c for c in m.controllers.values() if c.holds == name), None)
    if c is None:
        return None
    op, value = c.target()
    return {"name": c.name, "setpoint": c.setpoint, "op": op, "value": value, "tolerance": c.tolerance,
            "band": band(op, value, c.tolerance)}


def band(op: str, value: float, tol: float) -> list[float] | None:
    """The tolerance on the side that matters: above for <=, below for >=, both for ==."""
    if not tol:
        return None
    lo, hi = (value, value + tol) if op.startswith("<") else (value - tol, value) if op.startswith(">") else (value - tol, value + tol)
    return [round(lo, 9), round(hi, 9)]


def one(p, ref: str, since: float, until: float, n: int, role: str = "") -> dict | None:
    """One part's series."""
    got = parse_ref(ref)
    m = p.model
    if got is None:
        return None
    kind, name = got
    real = kind_of(m, name)
    if real is None or (kind == "flow") != (real == "flow"):
        return None
    out = {"ref": f"{real}.{name}", "kind": real, "name": name, "role": role}
    if real == "flow":
        f = m.flows[name]
        r = rate(p, name, since, until, n)
        stock = m.stocks.get(f.target or f.source or "")
        out.update(unit=f.unit or (stock.unit if stock else ""), per="hour", how=r[1] if r else "not known",
                   values=r[0] if r else [None] * n, disturbance=f.disturbance)
    else:
        out.update(unit=m.stocks[name].unit, values=level(p, name, since, until, n), goal=goal_of(m, name))
    out["values"] = [None if v is None else round(v, 6) for v in out["values"]]
    return out


def causes(m, ref: str) -> list[tuple[str, str]]:
    """What a causes strip shows under a part: a stock's inflows and outflows; a flow's and an
    auxiliary's driven-by, and a flow's stocks."""
    got = parse_ref(ref)
    if got is None:
        return []
    _, name = got
    kind = kind_of(m, name)
    spec = getattr(m, "spec", None)

    def driven(x, table) -> list[tuple[str, str]]:
        written = getattr(table.get(name), "driven_by", None) if spec else None
        if written is not None:
            return [(f"{r.kind}.{r.name}", "driven by") for r in written if r.kind in ("stock", "flow", "auxiliary")]
        return [(f"{kind_of(m, d)}.{d}", "driven by") for d in x.driven_by if kind_of(m, d)]
    out: list[tuple[str, str]] = []
    if kind == "stock":
        out = [(f"flow.{f.name}", "inflow") for f in m.flows_of(name) if f.target == name]
        out += [(f"flow.{f.name}", "outflow") for f in m.flows_of(name) if f.target != name]
    elif kind == "flow":
        f = m.flows[name]
        out = driven(f, spec.flows if spec else {})
        out += [(f"stock.{s}", w) for s, w in ((f.source, "from"), (f.target, "into")) if s and kind_of(m, s) == "stock"]
    elif kind == "auxiliary":
        out = driven(m.stocks[name], spec.auxiliaries if spec else {})
    seen, kept = {ref}, []
    for r, w in out:
        if r not in seen:
            seen.add(r)
            kept.append((r, w))
    return kept


def series(p, snap: dict, refs: list[str], n: int = POINTS, strip: bool = False) -> dict:
    """``GET /api/series``: each ref's values over the window, and with ``strip`` what drives each."""
    since, until = span(p, snap)
    n = max(2, min(n, MAX_POINTS))
    asked: list[tuple[str, str]] = []
    for r in refs:
        asked.append((r, ""))
        if strip:
            asked += causes(p.model, r)
    out = [s for r, role in asked if (s := one(p, r, since, until, n, role))]
    return {"since": since, "until": until, "points": n, "times": [round(t, 3) for t in times(since, until, n)], "series": out}


def off_stretches(p, loop: str, since: float, until: float) -> list[list[float]]:
    """When a loop was off in a span, from every crossing."""
    crossings = p.events.query(n=None, item=loop, type="loop.*", until=until, unvoided=True)
    out, off_from = [], None
    for e in crossings:
        if e["type"] == "loop.off" and off_from is None:
            off_from = max(e["time"], since)
        elif e["type"] == "loop.holding" and off_from is not None:
            if e["time"] > since:
                out.append([off_from, e["time"]])
            off_from = None
    if off_from is not None:
        out.append([off_from, until])
    return out


def scope(p, snap: dict, goal: str, n: int = POINTS) -> dict | None:
    """``GET /api/loop-scope``: a loop as a control engineer's scope: r and y, u, e, on one time axis."""
    m = p.model
    lp = snap["loops"].get(goal)
    c = m.controllers.get(goal)
    if lp is None or c is None:
        return None
    since, until = span(p, snap)
    n = max(2, min(n, MAX_POINTS))
    op, r = c.target()
    y = level(p, c.holds, since, until, n)
    e = [None if v is None else round(c.error(v), 6) for v in y]
    u: dict = {"how": None, "values": None, "openings": None, "limits": [None, None], "unit": "", "saturated": None}
    spec = getattr(m, "spec", None)
    valves = [v for v in (lp["valves"] or (c.drives if c.through else [])) if v in m.valves]   # the long way: where it acts first
    if valves:
        opened = sorted((e_["time"], float(e_["data"].get("amount", 1) or 0), v)
                        for v in valves for e_ in p.events.query(n=None, type="valve.opened", item=v, since=since, until=until))
        most = [m.valves[v].max for v in valves if m.valves[v].max is not None]
        hi = max(most) if most else None
        flow = m.flows.get(m.valves[valves[0]].flow)
        lo = -hi if hi is not None and flow is not None and flow.two_way else 0.0
        sat = [o for o in opened if hi is not None and abs(o[1]) >= hi - 1e-9]
        step = max(1, len(opened) // (MAX_POINTS // 2))
        u.update(how=f"moved by {', '.join(valves)}, each opening", openings=[[round(t, 3), a] for t, a, _ in opened[::step]],
                 total=len(opened), limits=[lo, hi], unit=getattr(flow, "unit", "") or m.stocks[c.holds].unit,
                 saturated=(len(sat) / len(opened)) if opened and hi is not None else None)
    else:
        knob = next((x.split(".", 1)[1] for x in c.through if x.startswith("auxiliary.")), None)
        if knob and knob in m.stocks:
            vals = level(p, knob, since, until, n)
            setter = spec.setter_of(knob) if spec else None
            lim = [None, None]
            stepper = next((b for f in spec.flows_of(knob) if (b := spec.actuator_of(f.name)) is not None
                            and b.params.get("limits")), None) if spec and setter is None else None
            if stepper is not None:                      # a setting a block steps: its law's range
                lim = [float(x) for x in stepper.params["limits"]]
            elif setter is not None:
                lim = [setter.min if setter.min is not None else setter.params.get("min"),
                       setter.max if setter.max is not None else setter.params.get("max")]
                lim = [None if x is None else float(x) for x in lim]
            got = [v for v in vals if v is not None]
            at = [v for v in got if (lim[0] is not None and v <= lim[0] + 1e-9) or (lim[1] is not None and v >= lim[1] - 1e-9)]
            u.update(how=f"{knob}, as {setter.name if setter else 'its setter'} set it", values=vals, limits=lim,
                     unit=m.stocks[knob].unit, knob=knob,
                     saturated=(len(at) / len(got)) if got and any(x is not None for x in lim) else None)
    last = lp.get("last_decision")
    return {"goal": goal, "stock": c.holds, "kind": kind_of(m, c.holds), "unit": m.stocks[c.holds].unit,
            "setpoint": c.setpoint, "op": op, "r": r, "tolerance": c.tolerance, "band": band(op, r, c.tolerance),
            "since": since, "until": until, "points": n, "times": [round(t, 3) for t in times(since, until, n)],
            "y": [None if v is None else round(v, 6) for v in y], "e": e, "u": u,
            "off": off_stretches(p, goal, since, until), "status": lp["status"], "open_loop": lp["open_loop"],
            "numbers": {"off_share": lp["off_share"], "back_in": lp["back_in"], "times_off": lp["times_off"],
                        "saturated": u["saturated"],
                        "last_decision": {"time": last["time"], "decision": last["data"].get("decision")} if last else None}}


def finished_states(kind, moved: list) -> list[str]:
    """The states a kind's items finish in: those after the first that no item has left, as the
    record shows; the last state when every state has been left."""
    left = {mv["from"] for it in moved for mv in it.moves if mv["from"]}
    done = [s for s in kind.states[1:] if s not in left]
    return done or kind.states[-1:]


def items_flow(p, snap: dict, kind: str, n: int = POINTS) -> dict | None:
    """``GET /api/items-flow``: a kind's items in each state over the window (a cumulative flow
    diagram's bands), and each item finished in it, when and how long it took."""
    spec = getattr(p.model, "spec", None)
    k = its.kinds_of(spec).get(kind)
    if k is None:
        return None
    since, until = span(p, snap)
    n = max(2, min(n, MAX_POINTS))
    ts = times(since, until, n)
    items = its.project(p.events, spec, kind, until=until)
    counts = {s: [0] * n for s in k.states}
    for it in items:
        mv = sorted(it.moves, key=lambda x: x["time"])
        j, state = 0, None
        for i, t in enumerate(ts):
            while j < len(mv) and mv[j]["time"] <= t:
                state = mv[j]["to"]
                j += 1
            if state in counts:
                counts[state][i] += 1
    done = finished_states(k, items)
    finished = []
    for it in items:
        if not it.moves:
            continue
        end = next((mv["time"] for mv in it.moves if mv["to"] in done), None)
        if end is not None and since <= end <= until:
            finished.append({"id": it.id, "time": round(end, 3), "took": round(end - it.moves[0]["time"], 3)})
    finished.sort(key=lambda x: x["time"])
    return {"kind": kind, "states": k.states, "since": since, "until": until, "points": n, "times": [round(t, 3) for t in ts],
            "counts": counts, "now": {s: sum(1 for it in items if it.state == s) for s in k.states},
            "finished_states": done, "finished": finished,
            "median": statistics.median([f["took"] for f in finished]) if finished else None}
