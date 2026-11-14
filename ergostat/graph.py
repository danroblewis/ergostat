"""A system as a graph to draw: the control diagram (stocks, flows with their valves or
disturbances, sensors, controllers) and the wiring diagram (agents, and how each one's output
reaches another). Both are plain data; the web page lays them out and the terminal prints them."""

from __future__ import annotations

import fnmatch

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
        return {lp.stock, lp.controller.name, *lp.sensors, *lp.valves, *lp.flows}
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


def readings(project) -> dict:
    out = {}
    for n in project.model.sensors:
        got = project.measurements.latest(f"sensor/{n}")
        if got is not None:
            out[n] = got[1]
    return out


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
                agent_of[p.name] = {"name": a.name, "kind": a.kind, "rung": a.rung}

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
    for n in sorted(stocks_drawn):
        s, st = m.stocks[n], snap["stocks"].get(n, {})
        nodes.append(_node(f"stock:{n}", "stock", n, unit=s.unit, value=st.get("value"), valueText=fmt(st.get("value")),
                           points=st.get("points", []), description=s.description, outside=n not in parts,
                           systems=in_system.get(n, [])))
    for n in sorted(flows_drawn):
        f, fl = m.flows[n], snap["flows"].get(n, {})
        v = m.valve_of(n)
        glyph = "disturbance" if f.disturbance else "valve"
        nodes.append(_node(f"flow:{n}", glyph, v.name if v else n, flow=n, rate=fl.get("rate"),
                           rateText=(fmt(fl.get("rate")) + "/h") if fl.get("rate") is not None else "?/h",
                           how=fl.get("how"), estimated=fl.get("estimated", False), mode=v.mode if v else None,
                           agent=agent_of.get(v.name) if v else None, description=(v.description if v else f.description),
                           systems=in_system.get(n, [])))
        src = f"stock:{f.source}" if f.source else f"cloud:{n}:in"
        dst = f"stock:{f.target}" if f.target else f"cloud:{n}:out"
        for end, cid in ((f.source, src), (f.target, dst)):
            if not end:
                nodes.append(_node(cid, "cloud", "", flow=n, systems=in_system.get(n, [])))
        edges.append(_edge(src, f"flow:{n}", "pipe", flow=n))
        edges.append(_edge(f"flow:{n}", dst, "pipe", flow=n, arrow=True))
    for n in sorted(x for x in parts if x in m.sensors):
        s = m.sensors[n]
        target = f"stock:{s.measures}" if s.measures in m.stocks else f"flow:{s.measures}"
        got = readings.get(n)
        unit = "/h" if s.measures in m.flows else ""
        nodes.append(_node(f"sensor:{n}", "sensor", n, measures=s.measures, agent=agent_of.get(n), description=s.description,
                           reading=(fmt(got) + unit) if got is not None else None, systems=in_system.get(n, [])))
        if (s.measures in stocks_drawn) or (s.measures in flows_drawn):
            edges.append(_edge(target, f"sensor:{n}", "measure"))
    for n in sorted(x for x in parts if x in m.controllers):
        c = m.controllers[n]
        lp = snap["loops"].get(n, {})
        nodes.append(_node(f"controller:{n}", "controller", n, setpoint=f"{c.holds} {c.setpoint}", status=lp.get("status"),
                           error=lp.get("error"), agent=agent_of.get(n), description=c.description,
                           decision=((lp.get("last_decision") or {}).get("data") or {}).get("decision"),
                           systems=in_system.get(n, [])))
        for s in c.reads:
            if s in parts:
                edges.append(_edge(f"sensor:{s}", f"controller:{n}", "signal"))
        for v in c.drives:
            if v in m.valves and m.valves[v].flow in flows_drawn:
                edges.append(_edge(f"controller:{n}", f"flow:{m.valves[v].flow}", "action"))
        lpm = m.loop(n)
        if lpm is not None:
            members = {f"controller:{n}", f"stock:{lpm.stock}", *(f"sensor:{s}" for s in lpm.sensors),
                       *(f"flow:{f}" for f in lpm.flows)}
            loops[n] = {"status": lp.get("status"), "nodes": sorted(members), "closes": lpm.closes,
                        "stock": lpm.stock, "setpoint": c.setpoint}
    ids = {x["id"] for x in nodes}
    edges = [e for e in edges if e["source"] in ids and e["target"] in ids]
    for e in edges:
        e["loops"] = [k for k, lp in loops.items() if e["source"] in lp["nodes"] and e["target"] in lp["nodes"]]
    return {"kind": "control", "nodes": nodes, "edges": edges, "loops": loops}


def wiring(model, project, snap: dict, parts: set[str]) -> dict:
    """Agents as boxes; an arrow when one agent's output reaches another: through an event type it
    listens for, or through a stock (one agent's valve moves it, another's sensor measures it)."""
    m = model
    involved = {p.agent for t in (m.sensors, m.controllers, m.valves) for p in t.values()
                if p.name in parts and p.agent in m.agents}
    nodes = []
    for n in sorted(involved):
        a, s = m.agents[n], snap["agents"].get(n, {})
        nodes.append(_node(f"agent:{n}", "agent", n, agentKind=a.kind, rung=a.rung, roles=s.get("roles", []),
                           runs=s.get("runs", 0), failing=s.get("failing", False), every=a.every, on=a.on))
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
        if not v or not v.agent:
            continue
        for stock in (f.source, f.target):
            for s in m.sensors.values():
                if s.measures == stock and s.agent:
                    add(v.agent, s.agent, f"stock {stock}")
    # sensor -> controller, controller -> valve (a decision handed on)
    for c in m.controllers.values():
        for s in c.reads:
            if s in m.sensors and m.sensors[s].agent and c.agent:
                add(m.sensors[s].agent, c.agent, f"sensor {s}")
        for v in c.drives:
            if v in m.valves and m.valves[v].agent and c.agent:
                add(c.agent, m.valves[v].agent, f"valve {v}")
    # events one agent published that another listens for (from the record)
    published: dict[str, set[str]] = {}
    for ev in project.events.query(n=2000):
        src = ev.get("source")
        if src in involved:
            published.setdefault(src, set()).add(ev["type"])
        if src == "ergostat" and ev["type"].startswith("loop.") and ev.get("item") in m.controllers:
            lp = m.loop(ev["item"])
            for s in lp.sensors if lp else []:
                if m.sensors[s].agent:
                    published.setdefault(m.sensors[s].agent, set()).add(ev["type"])
    for b in involved:
        for pat in m.agents[b].on:
            for a, types in published.items():
                for t in types:
                    if fnmatch.fnmatchcase(t, pat):
                        add(a, b, f"event {t}")
    return {"kind": "wiring", "nodes": nodes, "edges": list(edges.values()), "loops": {}}
