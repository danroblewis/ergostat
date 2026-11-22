"""A system as a graph to draw: the control diagram (stocks, flows with their valves or
disturbances, sensors, controllers) and the wiring diagram (the machines on the event log, and
what the log proves passed between them). Both are plain data; the web page lays them out and the terminal prints them."""

from __future__ import annotations

from . import rates
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
    spec = getattr(m, "spec", None)
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
        nodes.append(_node(f"stock:{n}", "auxiliary" if s.auxiliary else "stock", n, unit=s.unit, value=st.get("value"),
                           valueText=fmt(st.get("value")), points=st.get("points", []), description=s.description,
                           outside=n not in parts, systems=in_system.get(n, []), memory=not s.auxiliary,
                           **({"exogenous": True} if s.exogenous else {}),
                           agent=_badge(m, s.setter) if s.auxiliary and s.setter else None))
        for src in s.driven_by:                               # what an auxiliary follows: an influence, with its sign
            edges.append(_edge(f"flow:{src}" if src in m.flows else f"stock:{src}", f"stock:{n}", "influence",
                               polarity=s.polarity.get(src)))
    for n in (x for x in m.flows if x in flows_drawn):
        f, fl = m.flows[n], snap["flows"].get(n, {})
        v = m.valve_of(n)
        glyph = "disturbance" if f.disturbance else "valve"
        pos = readings.get(f"valve/{v.name}") if v else None
        end = m.stocks.get(f.target or "") or m.stocks.get(f.source or "")
        nodes.append(_node(f"flow:{n}", glyph, v.name if v else n, flow=n, rate=fl.get("rate"), position=pos,
                           rateText=rates.text(fl.get("rate"), end.unit if end else "", rates.override_of(spec, n)),
                           how=fl.get("how"), estimated=fl.get("estimated", False), mode=v.mode if v else None, max=v.max if v else None,
                           agent=agent_of.get(v.name) if v else _badge(m, f.agent), load=not v and bool(f.agent),
                           twoWay=f.two_way,
                           description=(v.description if v else f.description),
                           systems=in_system.get(n, [])))
        src = f"stock:{f.source}" if f.source else f"cloud:{n}:in"
        dst = f"stock:{f.target}" if f.target else f"cloud:{n}:out"
        for end, cid in ((f.source, src), (f.target, dst)):
            if not end:
                nodes.append(_node(cid, "cloud", "", flow=n, systems=in_system.get(n, [])))
        # polarity: the flow's effect on the stock at that end (an outflow lowers its source, an inflow raises its target)
        edges.append(_edge(src, f"flow:{n}", "pipe", flow=n, polarity="-" if f.source else None, twoWay=f.two_way))
        edges.append(_edge(f"flow:{n}", dst, "pipe", flow=n, arrow=True, polarity="+" if f.target else None, twoWay=f.two_way))
    for n in (x for x in m.flows if x in flows_drawn):      # what a flow's rate follows: an influence, not a pipe
        for src in m.flows[n].driven_by:
            sid = f"flow:{src}" if src in m.flows else f"stock:{src}"         # a stock's or an auxiliary's node
            edges.append(_edge(sid, f"flow:{n}", "influence", polarity=m.flows[n].polarity.get(src)))
    # a sensor is drawn where it is in a loop: read by a controller. One that only records a value is
    # instrumentation, not part of the system's structure: its reading is shown on what it measures
    read = {s for c in m.controllers.values() if not c.open_loop for s in c.reads}
    for n in (x for x in m.sensors if x in parts):
        s = m.sensors[n]
        if s.implied or n not in read:                        # (implied: an auxiliary's set value, said by the block's badge)
            continue
        target = f"stock:{s.measures}" if s.measures in m.stocks else f"flow:{s.measures}"
        got = readings.get(n)
        nodes.append(_node(f"sensor:{n}", "sensor", n, measures=s.measures, agent=agent_of.get(n), description=s.description,
                           reading=(rates.text(got, "", rates.override_of(spec, s.measures)) if s.measures in m.flows else fmt(got))
                           if got is not None else None, systems=in_system.get(n, [])))
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
        first = next((p for p in c.through if p.startswith(("flow.", "auxiliary."))), None)
        knob = first.split(".", 1)[1] if first and first.startswith("auxiliary.") else None
        if not c.drives and knob and knob in stocks_drawn:
            edges.append(_edge(f"controller:{n}", f"stock:{knob}", "action"))       # it acts by setting an auxiliary
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
    in_loops: dict[str, set[str]] = {}               # a node → the loops it is in (matched by index, not edge × loop)
    for k, lp in loops.items():
        for x in lp["nodes"]:
            in_loops.setdefault(x, set()).add(k)
    order = {k: i for i, k in enumerate(loops)}
    for e in edges:
        both = in_loops.get(e["source"], set()) & in_loops.get(e["target"], set())
        e["loops"] = sorted(both, key=order.__getitem__)
    causal = causal_loops(m)
    on_pair: dict[tuple[str, str], list[str]] = {}
    for c in causal:
        for pair in c["_pairs"]:
            on_pair.setdefault(pair, []).append(c["name"])
    for e in edges:
        e["causal"] = list(on_pair.get((e["source"], e["target"]), ()))
    for c in causal:
        del c["_pairs"]
    return {"kind": "control", "nodes": nodes, "edges": edges, "loops": loops, "causalLoops": causal}


def node_of(spec, part: str) -> str | None:
    """The control diagram's node for a part of a causal loop: a stock's or an auxiliary's, a
    flow's (its valve), a goal's controller; a block is drawn as the controller of a goal it serves."""
    kind, _, name = part.partition(".")
    if kind in ("stock", "auxiliary"):
        return f"stock:{name}"
    if kind == "flow":
        return f"flow:{name}"
    if kind == "goal":
        return f"controller:{name}"
    return None


def causal_loops(model) -> list[dict]:
    """The model's feedback loops for the system dynamics view (``spec/causal.py``): each with its
    members (as parts and as the nodes drawn for them), its polarity (R, B, or None: not known), a
    stable name, and the sign of each link along it."""
    spec = getattr(model, "spec", None)
    if spec is None:
        return []
    kept = spec.lookups().kept                      # worked out once per model (docs/proposals/scale.md, #11)
    if "graph.causal_loops" not in kept:
        kept["graph.causal_loops"] = _causal_loops(spec)
    return [{**c, "goals": list(c["goals"]), "parts": list(c["parts"]), "nodes": list(c["nodes"]),
             "links": [dict(x) for x in c["links"]], "_pairs": set(c["_pairs"])} for c in kept["graph.causal_loops"]]


def goal_loops(model, goal: str) -> dict:
    """A goal's loops, from the spec only: the feedback loops that close it (each with its Dynamics label, R1, B2),
    and its control loop's parts (sensor, controller, actuator), as Blocks draws them."""
    from .dynamics import labels
    spec = getattr(model, "spec", None)
    if spec is None or goal not in spec.goals:
        return {"feedback_loops": [], "control_loop": None}
    every = causal_loops(model)
    tags = labels(every)
    lp = spec.loop(goal)
    return {"feedback_loops": [{"name": c["name"], "label": tags[c["name"]], "polarity": c["polarity"]}
                               for c in every if goal in c["goals"]],        # each loop through its gap, as SPEC says
            "control_loop": {"name": goal, "sensors": list(lp.sensors), "controllers": list(lp.controllers),
                             "actuators": list(lp.actuators)}}


def _causal_loops(spec) -> list[dict]:
    from .spec.causal import loops
    from .spec.ir import sign_text
    out = []
    for lp in loops(spec):
        nodes: list[str] = []
        for p in lp.parts:
            nid = node_of(spec, p)
            if p.startswith("block."):                     # a controller's block: drawn as the goal's controller
                served = [g for g in lp.goals if p.split(".", 1)[1] in spec.loop(g).controllers]
                nid = f"controller:{served[0]}" if served else None
            if nid and (not nodes or nodes[-1] != nid):
                nodes.append(nid)
        if len(nodes) > 1 and nodes[0] == nodes[-1]:
            nodes.pop()
        pairs = {(a, b) for a, b in zip(nodes, nodes[1:] + nodes[:1], strict=False) if a != b}
        out.append({"name": lp.name, "polarity": lp.polarity, "goal": lp.goal, "goals": lp.goals, "parts": lp.parts, "nodes": nodes,
                    "links": [{"source": x.source, "target": x.target, "polarity": sign_text(x.sign), "kind": x.kind}
                              for x in lp.links], "_pairs": pairs})
    return out


RUN_RECORD = ("agent.started", "agent.ran", "agent.failed", "agent.refused", "block.commanded", "block.advised",
              "person.asked")     # what ergostat records about a block's run: the block's doing, not ergostat's
RUNNER = "ergostat"
MOST_EVENTS = 50000                 # the newest this many in the window are read for the wiring


def _machine(source: str | None) -> str | None:
    """The machine an event's ``source`` names: ``<machine>/<instance>`` is one of its instances."""
    return source.split("/", 1)[0] if source else None


def _actor(ev: dict) -> str | None:
    """Whose doing an event is: a run's record is the block's (ergostat writes it for it), the rest
    their source's."""
    if ev["type"] in RUN_RECORD and ev.get("source") == RUNNER and ev.get("item") and "/" not in ev["item"]:
        return ev["item"]
    return _machine(ev.get("source"))


def declared_wires(m) -> dict[tuple[str, str], list[str]]:
    """The connections between machines the model declares, each with how: a block commanding
    another (``out: block.X`` or ``in: block.X``, a goal's implied ``keep-`` block), a built-in
    block acting on a goal (whose crossings ergostat records), a block moving a flow of a stock a goal
    is on (ergostat reads it again at once), a sensor's agent reading a loop's stock, and an
    agent's ``on:`` subscription to what a named part's agent (or ergostat) publishes."""
    out: dict[tuple[str, str], list[str]] = {}

    def add(a, b, how):
        if a and b and a != b and how not in out.setdefault((a, b), []):
            out[(a, b)].append(how)
    spec = getattr(m, "spec", None)
    if spec is not None:
        goals_on: dict[str, list[str]] = {}
        for g in spec.goals.values():
            goals_on.setdefault(g.of.name, []).append(g.name)
        for b in spec.blocks.values():
            for c in spec.commanders_of(b.name):
                add(c.name, b.name, f"{c.name} commands {b.name}")
            if b.builtin:                                  # its decisions follow the goal's crossings
                for r in b.reads():
                    if r.kind == "goal":
                        add(RUNNER, b.name, f"{b.name} acts on goal {r.name}'s crossings, which ergostat records")
            for t in b.targets():
                if t.kind == "flow" and t.name in spec.flows:
                    f = spec.flows[t.name]
                    for st in (f.source, f.target):
                        for g in goals_on.get(st or "", []):
                            add(b.name, RUNNER, f"{b.name} moves {t.name}, of {st}: ergostat reads it and judges goal {g}")
    for lp in m.loops():                                   # a sensor's readings decide its loop's crossings
        for sn in lp.sensors:
            s = m.sensors.get(sn)
            if s and s.agent:
                add(s.agent, RUNNER, f"{s.agent} reads {sn}, whose readings decide loop {lp.name}")
    from .runner import matches
    for b, a in m.agents.items():
        for pat in a.on:
            t, _, item = pat.partition("@")
            if matches(pat, {"type": "loop.off", "item": item or "x"}) or matches(pat, {"type": "loop.holding", "item": item or "x"}):
                add(RUNNER, b, f"{b} listens for {pat}")
            if not item or any(ch in item for ch in "*?["):
                continue
            pub = (item if t.startswith("agent.") and item in m.agents else
                   getattr(m.valves.get(item), "agent", None) if t.startswith("valve.") else
                   getattr(m.controllers.get(item), "agent", None) if t.startswith("controller.") else None)
            add(pub, b, f"{b} listens for {pat}")
    return out


def wiring(model, project, snap: dict, parts: set[str]) -> dict:
    """The machines as the event log shows them, over the window: each one that published (an
    event's ``source``, instances grouped by machine; a block's runs are its own), and each one the
    model declares that never showed up (silent). A line from A to B only on evidence: an event of
    B's (or B's run) caused by A's event or run (``causedby``), or B listening (``on:``) for a type A
    published and running after it. Each line has its event types, how many, the rate, when last
    seen and which evidence; a connection the model declares that the log never shows is drawn as
    declared, never seen, and one seen but not declared is said to be undeclared."""
    m = model
    at, window = snap["at"], snap["window"]
    since = at - window
    span = max(60.0, min(window, snap.get("recorded") or window))      # the rate is over what was recorded
    whole = parts >= m.members(None)
    involved = set(m.agents) if whole else {
        p.agent for t in (m.sensors, m.controllers, m.valves, m.flows) for p in t.values()
        if p.name in parts and getattr(p, "agent", None) in m.agents}
    evs = project.events.query(n=MOST_EVENTS, since=since, until=at, skip=("claude.*",))   # a transcript is its item's
    by_id = {e["id"]: e for e in evs}
    looked: dict[str, dict | None] = {}

    def cause_of(cid):
        if cid in by_id:
            return by_id[cid]
        if cid not in looked and len(looked) < 2000:          # a cause from before the window
            looked[cid] = project.events.get(cid)
        return looked.get(cid)
    seen: dict[str, dict] = {}

    def machine(name):
        return seen.setdefault(name, {"published": {}, "runs": 0, "failed": 0, "last": None, "instances": set()})
    starts: dict[str, list[float]] = {}
    for e in evs:
        a = _actor(e)
        if not a:
            continue
        x = machine(a)
        x["last"] = max(x["last"] or 0, e["time"])
        src = e.get("source") or ""
        if "/" in src and _machine(src) == a:
            x["instances"].add(src.split("/", 1)[1])
        if e["type"] in RUN_RECORD and src == RUNNER:
            if e["type"] == "agent.started":
                x["runs"] += 1
                starts.setdefault(a, []).append(e["time"])
            elif e["type"] == "agent.failed":
                x["failed"] += 1
            continue
        p = x["published"].setdefault(e["type"], {"count": 0, "last": 0.0})
        p["count"] += 1
        p["last"] = max(p["last"], e["time"])
    wires: dict[tuple[str, str], dict] = {}

    def wire(a, b, t, how, evidence, cid, when, publisher):
        w = wires.setdefault((a, b), {})
        x = w.setdefault((t, how), {"type": t, "how": how, "ids": set(), "by": {}, "last": 0.0, "publisher": publisher})
        x["ids"].add(cid)
        x["by"].setdefault(evidence, set()).add(cid)
        x["last"] = max(x["last"], when)
    # caused by: B's event (or B's run) whose causedby is A's event or run
    for e in evs:
        cid = e.get("causedby")
        if not cid:
            continue
        cause = cause_of(cid)
        if cause is None:
            continue
        a, b = _actor(cause), _actor(e)
        if not a or not b or a == b:
            continue
        if cause["type"] in RUN_RECORD:                       # A's run caused it: what was caused is what is carried
            t, how, pub = ("block.commanded" if e["type"] in RUN_RECORD else e["type"]), "run", (a if e["type"] in RUN_RECORD else b)
        else:                                                 # A's event caused it: that event is what reached B
            t, how, pub = cause["type"], "sent", a
        wire(a, b, t, how, "caused-by", cid, e["time"], pub)
    # listened and ran: B listens for a type A published, and B ran after it
    import bisect

    from .runner import matches
    heard_by: dict[str, dict[str, int]] = {}
    for b, ag in m.agents.items():
        if not ag.on:
            continue
        runs = sorted(starts.get(b, []))
        heard = heard_by.setdefault(b, {})
        for e in evs:
            a = _actor(e)
            if not a or a == b or e.get("source") == b or (e.get("item") == b and e["type"].startswith("agent.")):
                continue
            pats = [pat for pat in ag.on if matches(pat, e)]
            if not pats:
                continue
            for pat in pats:
                heard[pat] = heard.get(pat, 0) + 1
            if bisect.bisect_left(runs, e["time"]) < len(runs):
                wire(a, b, e["type"], "sent", "listened-and-ran", e["id"], e["time"], a)
    declared = declared_wires(m)
    # which machines to draw: everything seen (or, for a selection, those in it and what joins them)
    if whole:
        names = set(seen) | set(m.agents)
    else:
        names = involved | {x for (a, b) in wires for x in (a, b) if a in involved or b in involved}
    if any(RUNNER in k and (k[0] in names or k[1] in names) for k in declared):
        names.add(RUNNER)                                  # what reads a goal, or moves a stock one is on, joins ergostat
    hours = span / 3600

    def kind_of(n):
        if n in m.agents:
            return m.agents[n].kind, m.agents[n].rung
        if n == RUNNER:
            return "ergostat", None
        if n in m.sensors:
            return "sensor", None
        return "not in the model", None
    nodes = []
    for n in sorted(names, key=lambda n: (n != RUNNER, n)):
        x = seen.get(n)
        kind, rung = kind_of(n)
        a = m.agents.get(n)
        pub = sorted(((t, v["count"], v["last"]) for t, v in (x["published"] if x else {}).items()), key=lambda r: -r[1])
        lines = [{"kind": "published", "name": f"{t} {c}×"} for t, c, _ in pub[:2]]
        if x and x["runs"]:
            lines.insert(0, {"kind": "ran", "name": f"{x['runs']}×" + (f", {x['failed']} failed" if x["failed"] else "")})
        if not x:
            lines = [{"kind": "silent:", "name": "nothing on the record in this window"}]
        nodes.append(_node(f"agent:{n}", "agent", n, machine=True, agentKind=kind, rung=rung if rung is not None else "–",
                           declared=n in m.agents or n == RUNNER or n in m.sensors, seen=x is not None, silent=x is None,
                           runs=x["runs"] if x else 0, failing=bool(x and x["failed"]), last=x["last"] if x else None,
                           instances=sorted(x["instances"]) if x else [],
                           published=[{"type": t, "count": c, "perHour": round(c / hours, 2), "last": lt} for t, c, lt in pub],
                           listens=list(a.on) if a else [], heard=heard_by.get(n, {}),
                           schedule=a.schedule if a else "", every=a.every if a else None, on=list(a.on) if a else [],
                           description=a.description if a else "", roles=lines[:3], loads=[]))
    edges = []
    for (a, b) in sorted(set(wires) | {k for k in declared if k[0] in names and k[1] in names}):
        if a not in names or b not in names:
            continue
        w = wires.get((a, b))
        decl = declared.get((a, b), [])
        if w:
            types = sorted(({"type": v["type"], "how": v["how"], "count": len(v["ids"]),
                             "perHour": round(len(v["ids"]) / hours, 2), "last": v["last"], "publisher": v["publisher"],
                             "evidence": sorted(v["by"]), **{k: len(ids) for k, ids in v["by"].items()}}
                            for v in w.values()), key=lambda r: -r["count"])
            count = sum(t["count"] for t in types)
            top = ", ".join(t["type"] for t in types[:2]) + (f" +{len(types) - 2}" if len(types) > 2 else "")
            via = [f"{top} · {count}" + ("" if decl else " · undeclared")]
            edges.append({**_edge(f"agent:{a}", f"agent:{b}", "wire"), "via": via, "types": types, "count": count,
                          "perHour": round(count / hours, 2), "last": max(t["last"] for t in types),
                          "evidence": sorted({ev for t in types for ev in t["evidence"]}), "seen": True,
                          "declared": bool(decl), "undeclared": not decl, "declaredAs": decl})
        else:
            e = _edge(f"agent:{a}", f"agent:{b}", "wire")
            e["id"] = "wire-unseen:" + e["id"].split(":", 1)[1]           # (drawn dashed: style.css)
            edges.append({**e, "via": ["declared, never seen"], "types": [], "count": 0, "perHour": 0, "last": None,
                          "evidence": [], "seen": False, "declared": True, "undeclared": False, "declaredAs": decl})
    seen_edges = [e for e in edges if e["seen"]]
    return {"kind": "events", "nodes": nodes, "edges": edges, "loops": {}, "cycles": cycles(m, seen_edges),
            "since": since, "until": at, "span": span, "events": len(evs), "capped": len(evs) >= MOST_EVENTS}


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
        agents = set(path) - {RUNNER}                  # ergostat records the crossings: it fills no role
        loop = None
        for lp in model.loops():
            fillers = {p.agent for p in (lp.controller, *(model.sensors[s] for s in lp.sensors),
                                         *(model.valves[v] for v in lp.valves)) if p.agent}
            if agents <= fillers:
                loop = lp.name
                break
        out.append({"agents": path, "via": [v[0] if v else "" for v in vias], "loop": loop})
    return out
