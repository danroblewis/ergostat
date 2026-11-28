"""``ergostat system`` (drawn, listed, as blocks or wiring) and ``ergostat loop``."""

from __future__ import annotations

import sys
import time

from .. import graph, rates, show
from .. import state as st
from ..durations import human
from ..show import ago, c, table
from ..state import fmt
from .common import as_of, at_of, open_project, out_json, parts_of, snap_of


def cmd_system(args) -> int:
    p = open_project(args)
    m = p.model
    snap = snap_of(p, args)
    if (args.blocks or args.wiring) and not args.name and not args.around:
        args.all = True                                   # blocks or wiring of everything, unless a system is named
    if not args.name and not args.all and not args.around:
        rows = []
        for s in m.system_names():
            mem = m.members(s)
            lps = [n for n in snap["loops"] if n in mem]
            off = [n for n in lps if snap["loops"][n]["status"] in ("off", "open")]
            rows.append([s, (m.systems[s].description if s in m.systems else ""), str(len(mem)), str(len(lps)),
                         c(str(len(off)), "bad") if off else "0"])
        if args.json:
            return out_json([{"system": s, "description": m.systems[s].description if s in m.systems else "",
                              "parts": len(m.members(s)), "loops": [n for n in snap["loops"] if n in m.members(s)],
                              "off": [n for n in snap["loops"] if n in m.members(s) and snap["loops"][n]["status"] in ("off", "open")]}
                             for s in m.system_names()])
        print(table(["SYSTEM", "DESCRIPTION", "PARTS", "GOALS", "OFF"], rows, "no systems: tag parts with systems = [...]"))
        print(c("\ndraw one: ergostat system NAME · everything: ergostat system --all", "dim"))
        return 0
    if args.name and args.name not in m.system_names():
        print(f"no system {args.name!r}; systems: {', '.join(m.system_names()) or 'none'}", file=sys.stderr)
        return 2
    try:
        parts = graph.select(m, None if args.all else args.name, args.around, args.depth)
    except KeyError:
        print(f"no part {args.around!r}", file=sys.stderr)
        return 2
    g = graph.wiring(m, p, snap, parts) if args.wiring else graph.control(m, snap, parts, graph.readings(p, at_of(args)))
    if args.json:
        return out_json(g)
    if args.open:
        from ..runner import running_pid, web_url
        url = web_url(p) if running_pid(p) else None
        if not url:
            print("the web page is not running: ergostat run (or ergostat web)", file=sys.stderr)
            return 2
        from urllib.parse import urlencode
        q = {"view": "wiring" if args.wiring else "dynamics", **({"system": args.name} if args.name else {}),
             **({"around": args.around} if args.around and not args.name else {})}
        page = f"{url}/diagram?{urlencode(q)}"
        import webbrowser
        webbrowser.open(page)
        print(page)
        return 0
    title = args.name or ("around " + args.around if args.around else "everything")
    print(c(f"system {title}", "bold"))
    if args.list:
        rows = [[n["kind"], n["label"], n.get("valueText") or n.get("rateText") or n.get("setpoint") or ""]
                for n in g["nodes"] if n["kind"] != "cloud"]
        print(table(["KIND", "PART", "NOW"], rows))
        return 0
    if args.blocks:
        loops = [lp.name for lp in m.loops() if lp.name in parts or lp.controller.name in parts]
        for name in loops:
            print(show.block_text(m, snap, graph.readings(p, at_of(args)), name))
            print()
        if not loops:
            print(c("no goals in this selection", "dim"))
        return 0
    if args.wiring:
        print(c(f"what the record shows, over the {human(g['span'])} "
                f"{'recorded' if g['span'] < snap['window'] * 0.95 else 'window'} ({g['events']} events)", "dim"))
        for n in g["nodes"]:
            pub = ", ".join(f"{x['type']} {x['count']}" for x in n["published"][:4]) or "nothing"
            runs = f"ran {n['runs']}, " if n["runs"] else ""
            state = c("silent", "dim") if n["silent"] else f"{runs}published {pub}"
            print(f"  [{n['label']} · {n['agentKind']}{'' if n['declared'] else ', not in the model'}]  {state}")
        for e in g["edges"]:
            ends = f"{e['source'].split(':', 1)[1]} ─▶ {e['target'].split(':', 1)[1]}"
            if not e["seen"]:
                print(f"  {c(ends, 'dim')}  {c('declared, never seen: ' + '; '.join(e['declaredAs']), 'warn')}")
                continue
            types = ", ".join(f"{t['type']} {t['count']}" for t in e["types"])
            print(f"  {ends}  {types} {c('· ' + ', '.join(e['evidence']), 'dim')}"
                  + (c("  undeclared", "warn") if e["undeclared"] else ""))
        if g.get("cycles"):
            print(c("\ncycles among the machines", "dim"))
            for cy in g["cycles"]:
                ring = " ─▶ ".join(cy["agents"] + [cy["agents"][0]])
                print(f"  {ring}  " + (c("goal " + cy["loop"], "ok") if cy["loop"] else c("not a declared loop", "warn")))
        return 0
    print(show.system_lines(m, snap, parts))
    return 0

def cmd_loop(args) -> int:
    p = open_project(args)
    m = p.model
    snap = snap_of(p, args)
    parts = parts_of(args, m)
    if not args.name:
        rows = [[n + (c(" ⏲", "dim") if lp.get("open_loop") else ""), show.status_word(lp["status"]), lp["stock"],
                 fmt(lp["value"]), st.setpoint_text(lp),
                 fmt(lp["error"]) if lp["error"] is not None else "",
                 f"{round(lp['off_share'] * 100)}%" if lp.get("off_share") else "0%",
                 human(max(lp["back_in"], 1)) if lp.get("back_in") is not None else "-",
                 m.controllers[n].agent or "-", "yes" if lp["observed"] else c("no", "dim")]
                for n, lp in snap["loops"].items() if n in parts]
        if args.json:
            return out_json({n: lp for n, lp in snap["loops"].items() if n in parts})
        print(table(["GOAL", "STATUS", "HOLDS", "NOW", "SETPOINT", "E = R − Y", "TIME OFF", "BACK IN", "CONTROLLER AGENT", "ACTED"], rows,
                    "no goals: a goal is a goals: entry holding a stock"))
        if rows:
            print(c(f"\nACTED: in the last {human(snap['window'])}, its sensor read and its controller decided or its valve opened. "
                    f"BACK IN: typically, from going off to holding again", "dim"))
        return 0
    lp = snap["loops"].get(args.name)
    if lp is None:
        print(f"no goal {args.name!r}; goals: {', '.join(snap['loops']) or 'none'}", file=sys.stderr)
        return 2
    if args.json:
        return out_json(lp)
    ctl = m.controllers[args.name]
    print(c("goal ", "dim") + show.loop_line(lp, args.name) + as_of(snap))
    if ctl.description:
        print(c("  " + ctl.description, "dim"))
    if lp.get("off_share"):
        print(f"  off {round(lp['off_share'] * 100)}% of the {human(min(snap['window'], snap['recorded'] or snap['window']))} recorded")
    if lp.get("answers_in") is not None or lp.get("back_in") is not None:
        parts = []
        if lp.get("answers_in") is not None:
            parts.append(f"its valve opens {human(max(lp['answers_in'], 1))} after it goes off")
        if lp.get("back_in") is not None:
            parts.append(f"it holds again {human(max(lp['back_in'], 1))} after (slowest {human(max(lp['back_in_slowest'], 1))}, "
                         f"{lp['times_off']} time{'s' if lp['times_off'] != 1 else ''})")
        print("  typically " + "; ".join(parts))
    pts = snap["stocks"].get(lp["stock"], {}).get("points", [])
    if pts:
        span = pts[-1][0] - pts[0][0] if len(pts) > 1 else 0
        over = human(span) if span < 0.9 * snap["window"] else human(snap["window"])
        print(f"  {lp['stock']} over the {over} recorded: {show.spark(pts)}")
    for g in lp["gaps"]:
        print("  " + c("cannot close: " + g, "warn"))
    if lp.get("stuck"):                                   # off: where its loop stops, then each step along it
        print("  " + c("where it stops: ", "bad") + lp["stuck"]["says"])
        for s_ in lp["stuck"]["steps"]:
            print(c("    ", "dim") + ("● " if s_.get("stuck") else "· ") + s_["says"])
            for k in s_.get("counts") or []:
                print(c(f"        {k['n']:>4}  {k['says']}" + (f": {k['latest']}" if k.get("latest") else ""), "dim"))
    print()
    rows = []
    for s in lp["sensors"] or [None]:
        if s is None:
            rows.append(["sensor", c("none", "warn"), "", ""])
            continue
        got = p.measurements.latest(f"sensor/{s}")
        rows.append(["sensor", s, show.agent_tag(m, m.sensors[s].agent),
                     f"read {ago(got[0])}: {fmt(got[1])}" if got else c("no reading yet", "dim")])
    d = lp["last_decision"]
    rows.append(["controller", args.name, show.agent_tag(m, ctl.agent),
                 f"decided {ago(d['time'])}: {d['data'].get('decision')}" if d else c(
                     "open loop: acts on its schedule, reads nothing" if ctl.open_loop else
                     "decides inside its job (says nothing)" if any(m.valves[v].agent == ctl.agent for v in lp["valves"] if v in m.valves)
                     and ctl.agent and p.events.query(n=1, type="valve.opened", source=ctl.agent) else "no decision yet", "dim")])
    for v in lp["valves"] or [None]:
        if v is None:
            rows.append(["valve", c("none", "warn"), "", ""])
            continue
        op = p.events.last_opening(v)
        mode = m.valves[v].mode
        moved = f"{fmt(op['amount'])}" + (f" in {op['count']} openings" if op and op["count"] > 1 else "") if op else ""
        rows.append(["valve", f"{v} {c('(mode ' + mode + ')', 'dim')}", show.agent_tag(m, m.valves[v].agent),
                     f"opened {ago(op['time'])}: {moved}" if op else c("never opened", "dim")])
    flows = [f"{f} {rates.text(snap['flows'][f]['rate'], '', rates.override_of(getattr(m, 'spec', None), f))}" for f in lp["flows"]]
    rows.append(["moves", ", ".join(flows) or "-", "", ""])
    print(table(["PART", "NAME", "FILLED BY", "LAST"], rows))
    all_crossings = p.events.query(n=None, item=args.name, type="loop.*", since=snap["at"] - snap["window"], until=snap["at"])
    crossings = all_crossings[-8:]
    if crossings:
        more = f", the newest {len(crossings)} of {len(all_crossings)}" if len(all_crossings) > len(crossings) else ""
        print(c(f"\ncrossings of its setpoint in {human(min(snap['window'], snap['recorded'] or snap['window']))}{more}", "dim"))
        for e in crossings:
            word = e["type"].split(".", 1)[1]
            print(f"  {time.strftime('%H:%M:%S', time.localtime(e['time']))}  {show.status_word(word)}  "
                  f"{lp['stock']} {fmt(e['data'].get('value'))}" + (f", off by {fmt(abs(e['data']['error']))}" if word == "off" else ""))
    d = st.decisions(p, args.name, snap["at"] - snap["window"], snap["at"])
    if d["count"]:
        print(c(f"\ndecisions in {human(min(snap['window'], snap['recorded'] or snap['window']))}: {d['count']}, "
                f"alike when only their numbers differ (N)", "dim"))
        for word, n in d["kinds"][:5]:
            print(f"  {n:>5}  {word.replace('#', 'N')}")
    for h in snap["hints"]:
        if h["controller"] == args.name:
            print(c("\nhint: ", "accent") + h["says"])
    return 0
