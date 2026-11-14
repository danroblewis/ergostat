"""The parts one at a time: ``ergostat stock|flow|valve|sensor|controller|disturbance``."""

from __future__ import annotations

import sys
import time

from .. import show
from ..show import ago, c, table
from ..state import fmt
from .common import open_project, out_json, parts_of, snap_of, window
from .record import event_line


def cmd_part(args) -> int:
    p = open_project(args)
    m = p.model
    snap = snap_of(p, args)
    parts = parts_of(args, m)
    topic = args.topic
    if topic == "disturbance":
        items = {n: f for n, f in m.flows.items() if f.disturbance}
    elif topic == "flow":
        items = {n: f for n, f in m.flows.items() if not f.disturbance}
    else:
        items = m.tables()[topic]
    items = {n: x for n, x in items.items() if n in parts}
    if args.name:
        x = items.get(args.name)
        if x is None:
            print(f"no {topic} {args.name!r}", file=sys.stderr)
            return 2
        detail = {k: v for k, v in x.__dict__.items() if v not in ("", [], None, False)}
        if getattr(x, "disturbance", False):                # say it the way the file does
            detail.pop("disturbance", None)
            if detail.pop("target", None):
                detail["into"] = x.target
            if detail.pop("source", None):
                detail["out_of"] = x.source
        elif topic == "flow":
            if "source" in detail:
                detail["from"] = detail.pop("source")
            if "target" in detail:
                detail["to"] = detail.pop("target")
        now = {"stock": snap["stocks"].get(x.name), "flow": snap["flows"].get(x.name),
               "disturbance": snap["flows"].get(x.name)}.get(topic)
        if topic == "sensor":
            now = {"readings": [{"at": t, "value": v} for t, v in
                                p.measurements.range(f"sensor/{x.name}", time.time() - window(args))][-10:]}
        if topic == "valve":
            now = {"openings": p.events.query(n=10, type="valve.opened", item=x.name)}
        if topic == "controller":
            now = {"loop": snap["loops"].get(x.name), "decisions": p.events.query(n=10, type="controller.decided", item=x.name)}
        if args.json:
            return out_json({"model": detail, "now": now})
        print(f"{c(topic, 'dim')} {x.name}" + (f" · {x.description}" if x.description else ""))
        for k, v in detail.items():
            if k not in ("name", "description"):
                print(f"  {k:<12} {', '.join(v) if isinstance(v, list) else v}")
        if now:
            print(c("recent" if topic in ("valve", "sensor", "controller") else "now", "dim"))
            if topic == "stock":
                print(f"  value       {fmt(now['value'])} {x.unit}  {show.spark(now['points'])}")
                print(f"  measured    {ago(now['at']) if now['at'] else 'never'}" + (f" by {now['sensor']}" if now["sensor"] else ""))
                print(f"  in / out    {fmt(now['inflow'])}/h in, {fmt(now['outflow'])}/h out")
            elif topic in ("flow", "disturbance"):
                print(f"  rate        {fmt(now['rate'])}/h ({now['how']})")
            elif topic == "sensor":
                for r in now["readings"]:
                    print(f"  {ago(r['at']):<12} {fmt(r['value'])}")
            elif topic == "valve":
                for e in now["openings"]:
                    print("  " + event_line(e))
            elif topic == "controller":
                if now["loop"]:
                    print("  " + show.loop_line(now["loop"], x.name))
                for e in now["decisions"]:
                    print("  " + event_line(e))
        return 0
    rows = []
    for n, x in items.items():
        if topic == "stock":
            s = snap["stocks"][n]
            rows.append([n, f"{fmt(s['value'])} {x.unit}".strip(), show.spark(s["points"], 16), s["sensor"] or c("unmeasured", "warn")])
        elif topic in ("flow", "disturbance"):
            fl = snap["flows"][n]
            rows.append([n, x.source or "outside", x.target or "outside", f"{fmt(fl['rate'])}/h", fl["how"]])
        elif topic == "valve":
            fl = snap["flows"].get(x.flow, {})
            last = (fl.get("openings") or {}).get("last")
            rows.append([n, x.flow, x.mode, show.agent_tag(m, x.agent), ago(last) if last else c("never", "dim")])
        elif topic == "sensor":
            got = p.measurements.latest(f"sensor/{n}")
            rows.append([n, x.measures, show.agent_tag(m, x.agent), f"{fmt(got[1])} {ago(got[0])}" if got else c("no reading", "dim")])
        elif topic == "controller":
            lp = snap["loops"][n]
            rows.append([n, f"{x.holds} {x.setpoint}", show.status_word(lp["status"]), show.agent_tag(m, x.agent)])
    heads = {"stock": ["STOCK", "NOW", "TREND", "MEASURED BY"],
             "flow": ["FLOW", "FROM", "TO", "RATE", "HOW WE KNOW"],
             "disturbance": ["DISTURBANCE", "FROM", "TO", "RATE", "HOW WE KNOW"],
             "valve": ["VALVE", "FLOW", "MODE", "FILLED BY", "LAST OPENED"],
             "sensor": ["SENSOR", "MEASURES", "FILLED BY", "LAST READING"],
             "controller": ["CONTROLLER", "HOLDS", "STATUS", "FILLED BY"]}[topic]
    if args.json:
        return out_json({n: x.__dict__ for n, x in items.items()})
    print(table(heads, rows, f"no {topic}s"))
    return 0
