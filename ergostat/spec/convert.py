"""``ergostat convert``: an ``ergostat.toml`` written as ``ergostat.yaml`` (SPEC §14).

What converts by itself: stocks, flows, systems, the ``[budget]``, goals (from controllers), and blocks (from valves
and the agents behind disturbances). Where the old file let ergostat only watch, the new one closes
the loop: a controller that held a stock through a valve becomes an ``onoff`` block commanding
that valve's block, so the valve runs when its goal is off instead of on a timer.

What needs a person is listed at the top of the file: programs that measured and acted in one run
(they are now a sensor's command and a block's), and agents that said decisions or events."""

from __future__ import annotations

import re

import yaml

from .. import model as mdl


def fix(name: str) -> str:
    n = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return n if n and n[0].isalpha() else f"x-{n}"


def schedule(a: mdl.Agent | None) -> dict:
    if a is None:
        return {}
    if a.cron:
        return {"cron": a.cron}
    if a.every:
        return {"every": human(a.every)}
    return {}


def human(sec: float) -> str:
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if sec >= n and sec % n == 0:
            return f"{int(sec // n)}{unit}"
    return f"{sec:g}s"


def convert(m: mdl.Model) -> tuple[str, list[str]]:
    notes: list[str] = []
    roles: dict[str, list[str]] = {}
    for t in (m.sensors, m.valves):              # a controller's role is ergostat's now: only these are programs
        for p in t.values():
            if p.agent:
                roles.setdefault(p.agent, []).append(f"{p.kind} {p.name}")
    for f in m.flows.values():
        if f.agent:
            roles.setdefault(f.agent, []).append(f"disturbance {f.name}")
    for a, rs in roles.items():
        ag = m.agents.get(a)
        acts = [r for r in rs if not r.startswith("disturbance ")]
        if len(rs) > 1 and acts and ag and ag.command:
            notes.append(f"agent {a} ran one program for {', '.join(rs)}. Its command is now each one's; split it so "
                         f"each prints only its own number (a sensor its reading, a block what it moved)")
    out: dict = {"name": m.name}
    if m.keep != 30 * 86400.0:
        out["keep"] = human(m.keep)
    if m.budget is not None:           # the money limit carries over; dropping it would un-refuse runs
        out["budget"] = {"daily": m.budget.daily, "max-cost": m.budget.max_cost}
    systems = {fix(n): ({"description": s.description} if s.description else None) for n, s in m.systems.items()}
    for n in m.system_names():
        systems.setdefault(fix(n), None)
    if systems:
        out["systems"] = systems

    def common(p, d: dict) -> dict:
        if p.systems:
            d["system"] = fix(p.systems[0])
            if len(p.systems) > 1:
                notes.append(f"{p.kind} {p.name} was in {', '.join(p.systems)}; a part now belongs to one system "
                             f"({fix(p.systems[0])})")
        if p.description:
            d["description"] = p.description
        return d

    def sensors_of(target: str) -> dict:
        got = {}
        for s in m.sensors.values():
            if s.measures != target:
                continue
            a = m.agents.get(s.agent or "")
            if a is not None and a.kind == "person":
                body = {"manual": True}
            elif a is not None and a.command:
                body = {"run": a.command, **schedule(a)}
                if a.parse:
                    body["parse"] = a.parse
            else:
                body = {"manual": True}
                notes.append(f"sensor {s.name} had no agent with a command: it is manual now")
            if s.unit:
                body["unit"] = s.unit
            if s.description:
                body["description"] = s.description
            got[fix(s.name)] = body
        return got
    stocks = {}
    for st in m.stocks.values():
        d = {"unit": st.unit} if st.unit else {}
        d = common(st, d)
        sn = sensors_of(st.name)
        if sn:
            d["sensors"] = sn
        stocks[fix(st.name)] = d or None
    out["stocks"] = stocks
    flows = {}
    for f in m.flows.values():
        d = {}
        if f.source:
            d["from"] = fix(f.source)
        if f.target:
            d["to"] = fix(f.target)
        if f.unit:
            d["unit"] = f.unit
        if f.rate is not None:
            d["rate"] = f.rate
        d = common(f, d)
        sn = sensors_of(f.name)
        if sn:
            d["sensors"] = sn
        flows[fix(f.name)] = d
    out["flows"] = flows
    goals, blocks = {}, {}
    commanded: dict[str, str] = {}                          # valve → the onoff block that now commands it
    for c in m.controllers.values():
        sp = c.setpoint.strip()
        g = {"stock": fix(c.holds), "hold": "=" + sp if re.match(r"^=\s*[^=]", sp) else sp}
        if c.tolerance:
            g["tolerance"] = c.tolerance
        goals[fix(c.name)] = common(c, g)
        lp = m.loop(c.name)
        if c.open_loop or not lp or not lp.closes:
            if c.drives and c.open_loop:
                notes.append(f"controller {c.name} was open loop (a timer): its valves keep their schedules; goal "
                             f"{fix(c.name)} is watched, not served")
            continue
        ca = m.agents.get(c.agent or "")
        valve_agents = {m.valves[v].agent for v in lp.valves}
        if ca and ca.command and c.agent not in valve_agents:
            name = fix(c.agent)
            blocks[name] = {"type": "ai" if ca.kind == "ai" else "program", **({"prompt": ca.command} if ca.kind == "ai"
                            else {"run": ca.command}), "in": f"goal.{fix(c.name)}",
                            "out": [f"block.{fix(v)}" for v in lp.valves] if len(lp.valves) > 1 else f"block.{fix(lp.valves[0])}",
                            **schedule(ca)}
            notes.append(f"agent {c.agent} decided for {c.name}: it is block {name} now; it must print commands "
                         f'({{"out": "block.{fix(lp.valves[0])}", "command": 1}}), not decisions')
            for v in lp.valves:
                commanded[v] = name
            continue
        for v in lp.valves:
            commanded[v] = "goal:" + fix(c.name)
        notes.append(f"controller {c.name} is goal {fix(c.name)}; {', '.join(fix(v) for v in lp.valves)} now run"
                     f"{'s' if len(lp.valves) == 1 else ''} while it is off (goal: {fix(c.name)}), not on a timer")
    for v in m.valves.values():
        a = m.agents.get(v.agent or "")
        name = fix(v.name)
        if a is not None and a.kind == "person":
            b = {"type": "person", "ask": a.description or f"open {v.name}"}
        elif a is not None and a.kind == "ai":
            b = {"type": "ai", "prompt": a.description or f"do {v.name}"}
            if a.command:
                b["run"] = a.command
        else:
            b = {"type": "program", "run": (a.command if a and a.command else "true")}
            if not (a and a.command):
                notes.append(f"valve {v.name} had no command: block {name} runs `true` until you give it one")
        if a is not None and a.parse:
            b["parse"] = a.parse
        if commanded.get(v.name, "").startswith("goal:"):
            b["goal"] = commanded[v.name][5:]
        elif v.name in commanded:
            b["in"] = f"block.{commanded[v.name]}"
        else:
            b.update(schedule(a))
        b["out"] = f"flow.{fix(v.flow)}"
        if v.max is not None:
            b["max"] = v.max
        if v.mode == "advise":
            b["mode"] = "advise"
        if a is not None and a.timeout != 300.0:
            b["timeout"] = human(a.timeout)
        blocks[name] = common(v, b)
    loads: dict[str, list[str]] = {}
    for f in m.flows.values():
        if f.disturbance and f.agent:
            loads.setdefault(f.agent, []).append(f.name)
    for ag, fl in loads.items():
        a = m.agents.get(ag)
        if a is None or not a.command or a.kind == "person":
            continue
        name = fix(ag) if fix(ag) not in blocks else f"{fix(ag)}-load"
        b = {"type": "program", "run": a.command, **schedule(a),
             "out": f"flow.{fix(fl[0])}" if len(fl) == 1 else [f"flow.{fix(x)}" for x in fl]}
        if a.description:
            b["description"] = a.description
        blocks[name] = b
        if len(fl) > 1:
            notes.append(f"block {name} moves {', '.join(fl)}: it must say how much of each "
                         f'({{"out": "flow.{fix(fl[0])}", "moved": n}}), or the record cannot tell them apart')
    if goals:
        out["goals"] = goals
    if blocks:
        out["blocks"] = blocks
    shared = {}
    for a in m.agents.values():
        uses = [b for b in blocks.values() if b.get("agent") == a.name]
        if len(uses) > 1:
            shared[fix(a.name)] = {"kind": a.kind}
    if shared:
        out["agents"] = shared
    for a in m.agents.values():
        if a.on:
            notes.append(f"agent {a.name} listened for {', '.join(a.on)}; blocks are commanded by blocks now, not by "
                         f"events")
    text = yaml.dump(whole(out), Dumper=Dumper, sort_keys=False, default_flow_style=False, width=10_000, allow_unicode=True)
    text = re.sub(r"^(\s+(?:hold|until): )'?([<>=][^'\n]*)'?$", r'\1"\2"', text, flags=re.M)
    text = re.sub(r"^(\s+\w[\w-]*:) null$", r"\1", text, flags=re.M)
    head = f"# {m.name}: converted from {m.path.name if m.path else 'ergostat.toml'} by ergostat convert\n"
    if notes:
        head += "#\n# To look at:\n" + "".join(f"#   - {n}\n" for n in dict.fromkeys(notes))
    return head + "\n" + spaced(text), notes


class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):       # lists indented under their key
        return super().increase_indent(flow, False)


def whole(x):
    """2.0 written as 2."""
    if isinstance(x, dict):
        return {k: whole(v) for k, v in x.items()}
    if isinstance(x, list):
        return [whole(v) for v in x]
    if isinstance(x, float) and x == int(x):
        return int(x)
    return x


def spaced(text: str) -> str:
    """A blank line between top-level sections, and between the entries of each."""
    lines, out = text.splitlines(), []
    for i, ln in enumerate(lines):
        if i and (re.match(r"^\S", ln) or (re.match(r"^  \S", ln) and not lines[i - 1].endswith(":"))):
            out.append("")
        out.append(ln)
    return "\n".join(out) + "\n"
