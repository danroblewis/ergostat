"""The parts one at a time: ``ergostat stock|flow|valve|sensor|controller|disturbance``."""

from __future__ import annotations

import sys
import time

from .. import rates, show
from ..show import ago, c, table
from ..state import fmt
from .common import open_project, out_json, parts_of, snap_of, window
from .record import event_line


def record_by_a_person(args) -> int | None:
    """``valve NAME --opened N``, ``sensor NAME --read V``, ``controller NAME --decided TEXT``: a
    person says what they did, for a role a person fills. The same lines an agent prints, checked
    the same way. None when nothing was asked."""
    said = {"valve": ("opened", "amount"), "sensor": ("read", "value"), "controller": ("decided", "decision")}.get(args.topic)
    if not said or getattr(args, said[0], None) is None:
        return None
    import json

    from ..runner import Recorder
    p = open_project(args)
    if getattr(p.model, "spec", None) is not None:
        if args.topic == "sensor":
            from .spec_cmds import read_manual
            return read_manual(p, args.name or "", args.read)
        print(f"a YAML model's {args.topic}s are not reported this way: a person's block reports with "
              f"ergostat block NAME --done N", file=sys.stderr)
        return 2
    part = p.model.tables()[args.topic].get(args.name or "")
    if part is None:
        print(f"no {args.topic} {args.name!r}", file=sys.stderr)
        return 2
    who = p.model.agents.get(part.agent or "")
    if who is None or who.kind != "person":
        print(f"{args.topic} {part.name} is filled by {part.agent or 'nobody'}, not a person: its agent says this itself",
              file=sys.stderr)
        return 2
    value = getattr(args, said[0])
    line = {args.topic: part.name, said[1]: value if said[1] == "decision" else float(value)}
    if args.topic == "valve" and getattr(args, "note", None):
        line["note"] = args.note
    rec = Recorder(p, who, None)
    rec.take(json.dumps(line))
    if rec.counts["refused"]:
        why = p.events.query(n=1, type="agent.refused", item=who.name)[-1]["data"]["why"]
        print(f"refused: {why}", file=sys.stderr)
        return 1
    print(f"recorded, as {who.name}: {args.topic} {part.name} {said[0]} {value}")
    return 0


def forget_readings(args) -> int | None:
    """``sensor NAME --forget-above V`` / ``--forget-below V``: set wrong readings aside (a broken
    first run, a unit mix-up). They are kept apart, out of every estimate, and the record says so."""
    above, below = getattr(args, "forget_above", None), getattr(args, "forget_below", None)
    if args.topic != "sensor" or (above is None and below is None):
        return None
    p = open_project(args)
    if args.name not in p.model.sensors:
        print(f"no sensor {args.name!r}", file=sys.stderr)
        return 2
    gone = p.measurements.forget(f"sensor/{args.name}", above, below)
    if not gone:
        print(f"no reading of {args.name} is {'above ' + fmt(above) if above is not None else ''}"
              f"{' or ' if above is not None and below is not None else ''}{'below ' + fmt(below) if below is not None else ''}")
        return 0
    # the crossings those readings caused go with them: a loop is judged again on what remains
    values, since = {v for _, v in gone}, min(t for t, _ in gone)
    loops = [lp.name for lp in p.model.loops() if args.name in lp.sensors]
    voids = [e["id"] for lp in loops for e in p.events.query(n=None, item=lp, type="loop.*", since=since - 1)
             if e["data"].get("value") in values]
    p.events.add("ergostat.forgotten", item=args.name, source="ergostat",
                 data={"above": above, "below": below, "count": len(gone), "values": [v for _, v in gone[:20]], "voids": voids})
    from ..runner import edges
    edges(p, None, sensor=args.name)
    print(f"set aside {len(gone)} reading{'' if len(gone) == 1 else 's'} of {args.name}: "
          + ", ".join(f"{fmt(v)} ({ago(t)})" for t, v in gone[:5]) + (" ..." if len(gone) > 5 else ""))
    return 0


def cmd_part(args) -> int:
    done = record_by_a_person(args)
    if done is None:
        done = forget_readings(args)
    if done is not None:
        return done
    p = open_project(args)
    m = p.model
    spec = getattr(m, "spec", None)
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
        detail = {k: v for k, v in x.__dict__.items() if v not in ("", [], None, False) and k != "mode_set"}
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
                print(f"  in / out    {rates.text(now['inflow'])} in, {rates.text(now['outflow'])} out")
            elif topic in ("flow", "disturbance"):
                print(f"  rate        {rates.text(now['rate'], '', rates.override_of(spec, x.name))} ({now['how']})")
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
            rows.append([n, x.source or "outside", x.target or "outside", rates.text(fl["rate"], "", rates.override_of(spec, n)),
                         fl["how"]])
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
        return out_json({n: {k: v for k, v in x.__dict__.items() if k != "mode_set"} for n, x in items.items()})
    print(table(heads, rows, f"no {topic}s"))
    return 0
