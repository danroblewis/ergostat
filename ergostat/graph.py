"""A system as a graph to draw: the control diagram (stocks, flows with their valves or
disturbances, sensors, controllers) and the wiring diagram (agents, and how each one's output
reaches another). Both are plain data; the web page lays them out and the terminal prints them."""

from __future__ import annotations

from .state import fmt


def _node(id, kind, label, **kw):
    return {"id": id, "kind": kind, "label": label, **kw}


def _edge(src, dst, kind, **kw):
    return {"id": f"{kind}:{src}->{dst}", "source": src, "target": dst, "kind": kind, **kw}


def select(model, system: str | None = None, around: str | None = None, depth: int = 1) -> set[str]:
    """The parts to draw: a system's members, everything, or the parts within ``depth`` steps of one."""
    if around is None:
        return model.members(system)
    kind, _, name = around.rpartition("/")
    if kind == "loop" or model.part(name) is None:
        lp = model.loop(name)
        if lp is None:
            raise KeyError(around)
        others = model.flows_of(lp.stock)                # everything that moves its stock, disturbances too
        return {lp.stock, lp.controller.name, *lp.sensors, *lp.valves, *lp.flows, *(f.name for f in others),
                *(v.name for f in others if (v := model.valve_of(f.name)))}
    adj: dict[str, set[str]] = {}

    def link(a, b):
        if a and b:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    for f in model.flows.values():
        link(f.name, f.source)
        link(f.name, f.target)
    for v in model.valves.values():
        link(v.name, v.flow)
    for s in model.sensors.values():
        link(s.name, s.measures)
    for c in model.controllers.values():
        link(c.name, c.holds)
        for x in c.reads + c.drives:
            link(c.name, x)
    seen, edge = {name}, {name}
    for _ in range(max(depth, 1) * 2):              # a valve and its flow count as one step
        edge = {n for e in edge for n in adj.get(e, ())} - seen
        seen |= edge
    return seen


def _rate(rate, unit: str) -> str:
    """``12 jobs/h``; ``?/h`` when unknown."""
    if rate is None:
        return "?" + unit
    return fmt(rate) + (" " if unit != "/h" else "") + unit


def _when(a) -> str:
    """An agent's schedule in a word or two, for its badge."""
    from .durations import human
    if a.every:
        return human(a.every)
    if a.cron:                                  # short enough for a badge: "every 2 minutes" is "2m"
        import re

        from .model import cron_words
        w = cron_words(a.cron)
        for pat, rep in ((r"^every minute$", "1m"), (r"^every (\d+) minutes$", r"\1m"), (r"^every hour$", "1h"),
                         (r"^hourly at (:\d\d)$", r"hourly \1"), (r"^every (\d+) hours at (:\d\d)$", r"\1h \2"),
                         (r"^daily at (\S+)$", r"daily \1"), (r"^weekdays at (\S+)$", r"weekdays \1")):
            if re.match(pat, w):
                return re.sub(pat, rep, w)
        return "cron"
    if a.on:
        return "on " + a.on[0].split("@")[0] + ("…" if len(a.on) > 1 or "@" in a.on[0] else "")
    return ""


def readings(project, at: float | None = None) -> dict:
    """Each sensor's latest reading by its name, and each valve's latest position as ``valve/<name>``."""
    out = {}
    for n in project.model.sensors:
        got = project.measurements.latest(f"sensor/{n}", at)
        if got is not None:
            out[n] = got[1]
    for n in project.model.valves:
        got = project.measurements.latest(f"valve/{n}", at)
        if got is not None:
            out[f"valve/{n}"] = got[1]
    return out


def _badge(m, name: str | None) -> dict | None:
    if not name or name not in m.agents:
        return None
    a = m.agents[name]
    return {"name": a.name, "kind": a.kind, "rung": a.rung, "when": _when(a), "schedule": a.schedule}


def control(model, snap: dict, parts: set[str], readings: dict | None = None) -> dict:
    """``readings``: each sensor's latest value, by name."""
    readings = readings or {}
    nodes, edges, loops = [], [], {}
    m = model
    agent_of = {}
    for t in (m.sensors, m.controllers, m.valves):
        for p in t.values():
            if p.agent and p.agent in m.agents:
                a = m.agents[p.agent]
                agent_of[p.name] = {"name": a.name, "kind": a.kind, "rung": a.rung, "when": _when(a), "schedule": a.schedule}

    in_system = {}
    for sysname in m.system_names():
        for part in m.members(sysname):
            in_system.setdefault(part, []).append(sysname)
    stocks_drawn = {n for n in parts if n in m.stocks}
    flows_drawn = {n for n in parts if n in m.flows}
    for f in list(flows_drawn):                     # a drawn flow brings both its ends
        for end in (m.flows[f].source, m.flows[f].target):
            if end:
                stocks_drawn.add(end)
    for n in (x for x in m.stocks if x in stocks_drawn):
        s, st = m.stocks[n], snap["stocks"].get(n, {})
        nodes.append(_node(f"stock:{n}", "variable" if s.variable else "stock", n, unit=s.unit, value=st.get("value"),
                           valueText=fmt(st.get("value")), points=st.get("points", []), description=s.description,
                           outside=n not in parts, systems=in_system.get(n, []),
                           agent=_badge(m, s.setter) if s.variable and s.setter else None))
        for src in s.driven_by:                               # what a variable follows: an influence
            edges.append(_edge(f"flow:{src}" if src in m.flows else f"stock:{src}", f"stock:{n}", "influence"))
    for n in (x for x in m.flows if x in flows_drawn):
        f, fl = m.flows[n], snap["flows"].get(n, {})
        v = m.valve_of(n)
        glyph = "disturbance" if f.disturbance else "valve"
        pos = readings.get(f"valve/{v.name}") if v else None
        end = m.stocks.get(f.target or "") or m.stocks.get(f.source or "")
        unit = (end.unit + "/h") if end and end.unit else "/h"
        nodes.append(_node(f"flow:{n}", glyph, v.name if v else n, flow=n, rate=fl.get("rate"), position=pos,
                           rateText=_rate(fl.get("rate"), unit),
                           how=fl.get("how"), estimated=fl.get("estimated", False), mode=v.mode if v else None, max=v.max if v else None,
                           agent=agent_of.get(v.name) if v else _badge(m, f.agent), load=not v and bool(f.agent),
                           description=(v.description if v else f.description),
                           systems=in_system.get(n, [])))
        src = f"stock:{f.source}" if f.source else f"cloud:{n}:in"
        dst = f"stock:{f.target}" if f.target else f"cloud:{n}:out"
        for end, cid in ((f.source, src), (f.target, dst)):
            if not end:
                nodes.append(_node(cid, "cloud", "", flow=n, systems=in_system.get(n, [])))
        edges.append(_edge(src, f"flow:{n}", "pipe", flow=n))
        edges.append(_edge(f"flow:{n}", dst, "pipe", flow=n, arrow=True))
    for n in (x for x in m.flows if x in flows_drawn):      # what a flow's rate follows: an influence, not a pipe
        for src in m.flows[n].driven_by:
            sid = f"flow:{src}" if src in m.flows else f"stock:{src}"         # a stock's or a variable's node
            edges.append(_edge(sid, f"flow:{n}", "influence"))
    for n in (x for x in m.sensors if x in parts):
        s = m.sensors[n]
        if s.implied:                                         # a variable's set value: the block's badge says who set it
            continue
        target = f"stock:{s.measures}" if s.measures in m.stocks else f"flow:{s.measures}"
        got = readings.get(n)
        unit = "/h" if s.measures in m.flows else ""
        nodes.append(_node(f"sensor:{n}", "sensor", n, measures=s.measures, agent=agent_of.get(n), description=s.description,
                           reading=(fmt(got) + unit) if got is not None else None, systems=in_system.get(n, [])))
        if (s.measures in stocks_drawn) or (s.measures in flows_drawn):
            edges.append(_edge(target, f"sensor:{n}", "measure"))
    for n in (x for x in m.controllers if x in parts):
        c = m.controllers[n]
        lp = snap["loops"].get(n, {})
        nodes.append(_node(f"controller:{n}", "controller", n, setpoint=f"{c.holds} {c.setpoint}", status=lp.get("status"),
                           error=lp.get("error"), agent=agent_of.get(n), description=c.description,
                           decision=((lp.get("last_decision") or {}).get("data") or {}).get("decision"),
                           decisionAt=(lp.get("last_decision") or {}).get("time"), openLoop=c.open_loop,
                           systems=in_system.get(n, [])))
        for s in ([] if c.open_loop else c.reads):        # an open loop reads nothing, whatever it lists
            if s in parts:
                edges.append(_edge(f"sensor:{s}", f"controller:{n}", "signal"))
        for v in c.drives:
            if v in m.valves and m.valves[v].flow in flows_drawn:
                edges.append(_edge(f"controller:{n}", f"flow:{m.valves[v].flow}", "action"))
        first = next((p for p in c.through if p.startswith(("flow.", "variable."))), None)
        if not c.drives and first and first.startswith("variable.") and first[9:] in stocks_drawn:
            edges.append(_edge(f"controller:{n}", f"stock:{first[9:]}", "action"))       # it acts by setting a variable
        lpm = m.loop(n)
        if lpm is not None:
            members = {f"controller:{n}", f"stock:{lpm.stock}", *(f"sensor:{s}" for s in lpm.sensors),
                       *(f"flow:{f}" for f in lpm.flows)}
            for p in c.through:                         # the long way round: its stocks and flows are in the loop too
                k, _, nm = p.partition(".")
                if k in ("stock", "flow"):
                    members.add(f"{k}:{nm}")
            loops[n] = {"status": lp.get("status"), "nodes": sorted(members), "closes": lpm.closes, "through": c.through,
                        "stock": lpm.stock, "setpoint": c.setpoint, "value": lp.get("value"), "error": lp.get("error"),
                        "band": lp.get("band", ""), "openLoop": c.open_loop}
    ids = {x["id"] for x in nodes}
    edges = [e for e in edges if e["source"] in ids and e["target"] in ids]
    for e in edges:
        e["loops"] = [k for k, lp in loops.items() if e["source"] in lp["nodes"] and e["target"] in lp["nodes"]]
    return {"kind": "control", "nodes": nodes, "edges": edges, "loops": loops}


def wiring(model, project, snap: dict, parts: set[str]) -> dict:
    """Agents as boxes; an arrow when one agent's output reaches another: through an event type it
    listens for, or through a stock (one agent's valve moves it, another's sensor measures it)."""
    m = model
    involved = {p.agent for t in (m.sensors, m.controllers, m.valves, m.flows) for p in t.values()
                if p.name in parts and getattr(p, "agent", None) in m.agents}
    nodes = []
    for n in (x for x in m.agents if x in involved):
        a, s = m.agents[n], snap["agents"].get(n, {})
        nodes.append(_node(f"agent:{n}", "agent", n, agentKind=a.kind, rung=a.rung, roles=s.get("roles", []),
                           runs=s.get("runs", 0), failing=s.get("failing", False), every=a.every, on=a.on, schedule=a.schedule,
                           loads=[f.name for f in m.flows.values() if f.disturbance and f.agent == n]))
    edges = {}

    def add(src, dst, via):
        if src == dst or src not in involved or dst not in involved:
            return
        e = edges.setdefault((src, dst), _edge(f"agent:{src}", f"agent:{dst}", "wire", via=[]))
        if via not in e["via"]:
            e["via"].append(via)
    # through stocks
    for f in m.flows.values():
        v = m.valve_of(f.name)
        mover = v.agent if v else f.agent                  # a valve's agent, or the agent a disturbance is the doing of
        if not mover:
            continue
        for stock in (f.source, f.target):
            for s in m.sensors.values():
                if s.measures == stock and s.agent:
                    add(mover, s.agent, f"stock {stock}")
    # sensor -> controller, controller -> valve (a decision handed on)
    for c in m.controllers.values():
        for s in c.reads:
            if s in m.sensors and m.sensors[s].agent and c.agent:
                add(m.sensors[s].agent, c.agent, f"sensor {s}")
        for v in c.drives:
            if v in m.valves and m.valves[v].agent and c.agent:
                add(c.agent, m.valves[v].agent, f"valve {v}")
    # events one agent published that another listens for (from the record)
    from .runner import matches
    published: dict[str, set[tuple[str, str]]] = {}               # agent -> (type, item) it causes
    for ev in project.events.query(n=2000):
        src = ev.get("source")
        if src in involved:
            published.setdefault(src, set()).add((ev["type"], ev.get("item") or ""))
        if src == "ergostat" and ev["type"].startswith("loop.") and ev.get("item") in m.controllers:
            lp = m.loop(ev["item"])
            for s in lp.sensors if lp else []:
                if m.sensors[s].agent:
                    published.setdefault(m.sensors[s].agent, set()).add((ev["type"], ev["item"]))
    for b in involved:
        for pat in m.agents[b].on:
            for a, kinds in published.items():
                for t, item in kinds:
                    if matches(pat, {"type": t, "item": item}):
                        add(a, b, f"event {t}" + (f"@{item}" if "@" in pat else ""))
    es = list(edges.values())
    return {"kind": "wiring", "nodes": nodes, "edges": es, "loops": {}, "cycles": cycles(m, es)}


def cycles(model, edges: list[dict], longest: int = 6) -> list[dict]:
    """The simple cycles among agents in the wiring (each found once, from its first agent by name),
    and for each the declared loop whose roles its agents fill, if there is one. A cycle no loop
    accounts for is something running that nobody designed."""
    nxt: dict[str, list[tuple[str, list[str]]]] = {}
    for e in edges:
        nxt.setdefault(e["source"].split(":", 1)[1], []).append((e["target"].split(":", 1)[1], e["via"]))
    found, seen = [], set()

    def walk(start, node, path, vias):
        for to, via in nxt.get(node, []):
            if to == start and len(path) > 1:
                key = tuple(sorted(path))
                if key not in seen:
                    seen.add(key)
                    found.append((list(path), vias + [via]))
            elif to not in path and to > start and len(path) < longest:
                walk(start, to, path + [to], vias + [via])
    for a in sorted(nxt):
        walk(a, a, [a], [])
    out = []
    for path, vias in found:
        agents = set(path)
        loop = None
        for lp in model.loops():
            fillers = {p.agent for p in (lp.controller, *(model.sensors[s] for s in lp.sensors),
                                         *(model.valves[v] for v in lp.valves)) if p.agent}
            if agents <= fillers:
                loop = lp.name
                break
        out.append({"agents": path, "via": [v[0] if v else "" for v in vias], "loop": loop})
    return out
