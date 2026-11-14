"""The command line: ``ergostat [TOPIC] [NAME] [FLAGS]``. Every topic lists everything of its kind,
and shows one in detail when given a name. Nothing here changes the system except ``run`` (which
starts the agents) and ``chat`` (the Supervisor)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

from . import __version__, graph, show
from . import model as mdl
from . import state as st
from .durations import DurationError, human, parse_duration
from .show import ago, c, table
from .state import fmt

HELP = """ergostat keeps your work going. Design, watch and run the control system around it.

usage: ergostat [TOPIC] [NAME] [FLAGS]

  With no topic, ergostat shows what needs attention.

the system
  system         Draw a system (--wiring for how the agents talk), or list them
  loop           The feedback loops: what each holds, how far off, each part along it
  check          Is the model whole? Unknown names, loops that cannot close

who does the work
  agent          People, AI agents, decisions, programs and rules, and the roles they fill

what happened
  event          The raw record (--follow to watch)
  item           Events folded by id
  residual       What the model can't explain

run it
  run            Start the agents here, in the background, with the web page
  web            Serve the web page only
  chat           Talk to the Supervisor, who changes the system for you

the parts, one at a time
  stock  flow  valve  sensor  controller  disturbance

flags
  -C DIR             Run as if in DIR
  -s, --system NAME  Only the parts in this system
  --since TIME       The window to look at (10m, 2h, 1d; default 1h)
  --at TIME          As it was then: 30m (ago), 07:30, or epoch seconds
  --json             Output for scripts and agents
  -h, --help         Help (also: ergostat TOPIC --help)
  --version          Print the version

examples
  ergostat                        What needs attention
  ergostat system --all           Draw the whole system
  ergostat loop disk-under-80     One loop, part by part
  ergostat agent                  Who fills which roles, at what rung
  ergostat event --follow         Watch events arrive
  ergostat check --example        An example ergostat.toml to start from
"""

PART_TOPICS = ("stock", "flow", "valve", "sensor", "controller", "disturbance")


def out_json(obj) -> int:
    print(json.dumps(obj, indent=2, default=str))
    return 0


def open_project(args):
    from .store import Project
    here = Path(args.C).resolve() if args.C else Path.cwd()
    try:
        m = mdl.load(here)
    except FileNotFoundError:
        print(f"no {mdl.FILE} here or above {here}.\n"
              f"describe your system with `ergostat chat`, or write {mdl.FILE} (see `ergostat check --example`).",
              file=sys.stderr)
        raise SystemExit(2) from None
    except (mdl.ModelError, DurationError) as e:
        print(f"{mdl.FILE}: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    return Project(m)


def window(args) -> float:
    return parse_duration(args.since, "--since") if args.since else st.WINDOW


def at_of(args) -> float | None:
    """``--at``: a moment in the past, as ``30m`` (that long ago), ``07:30`` (today, or yesterday when
    that is still to come), or seconds since the epoch. None: now."""
    v = getattr(args, "at", None)
    if not v:
        return None
    import re
    from datetime import datetime, timedelta
    if m := re.fullmatch(r"(\d{1,2}):(\d{2})", v.strip()):
        t = datetime.now().replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if t > datetime.now():
            t -= timedelta(days=1)
        return t.timestamp()
    try:
        x = float(v)
        if x > 1e9:
            return x
    except ValueError:
        pass
    return time.time() - parse_duration(v, "--at")


def snap_of(p, args) -> dict:
    return st.snapshot(p, window(args), at_of(args))


def as_of(snap: dict) -> str:
    return "" if snap.get("live", True) else c(f" · as of {time.strftime('%H:%M:%S', time.localtime(snap['at']))} "
                                               f"({human(time.time() - snap['at'])} ago)", "accent")


def parts_of(args, m) -> set[str]:
    if getattr(args, "system", None):
        if args.system not in m.system_names():
            print(f"no system {args.system!r}; systems: {', '.join(m.system_names()) or 'none'}", file=sys.stderr)
            raise SystemExit(2)
        return m.members(args.system)
    return m.members(None)


# ---- status

def cmd_status(args) -> int:
    from .runner import running_pid, web_url
    p = open_project(args)
    m, snap = p.model, snap_of(p, args)
    pid = running_pid(p)
    att = st.attention(snap, running=bool(pid))
    if args.json:
        return out_json({"running": bool(pid), "web": web_url(p) if pid else None, "attention": att,
                         "loops": snap["loops"], "counts": counts(p)})
    run = c("running", "ok") + (f" · {web_url(p)}" if web_url(p) else "") if pid else c("not running", "warn") + " · start: ergostat run"
    print(f"{c('ergostat', 'bold')} · {m.name} · {run}{as_of(snap)}")
    if not m.stocks and not m.agents:
        print("the model is empty. describe your system with `ergostat chat`.")
        return 0
    print()
    if att:
        for a in att:
            dot = c("○", "accent") if a["level"] == "hint" else c("●", a["level"])
            print(f"  {dot} {a['what']}: {a['says']}")
    else:
        print(f"  {c('●', 'ok')} nothing needs you")
    print()
    if args.since:
        from . import history
        ch = history.changes(p, time.time() - window(args))
        print(c(f"the model, since {args.since} ago: " + (f"{len(ch)} changes" if ch else "no changes"), "dim"))
        for e in ch:
            d = e["data"]
            what = [f"+{x}" for x in d["added"]] + [f"-{x}" for x in d["removed"]] + [f"~{x}" for x in d["changed"]]
            print(f"  {time.strftime('%H:%M:%S', time.localtime(e['time']))}  " + "  ".join(what))
        print()
    loops = snap["loops"]
    if loops:
        print(table(["LOOP", "STATUS", "HOLDS", "NOW", "SETPOINT"],
                    [[n, show.status_word(lp["status"]), lp["stock"], fmt(lp["value"]), lp["setpoint"]]
                     for n, lp in loops.items()]))
        print()
    k = counts(p)
    print(c(f"{k['loops']} loops · {k['stocks']} stocks · {k['flows']} flows · {k['agents']} agents · "
            f"{k['events']} events · {k['measurements']} measurements", "dim"))
    return 0


def counts(p) -> dict:
    m = p.model
    return {"loops": len(m.controllers), "stocks": len(m.stocks), "flows": len(m.flows), "agents": len(m.agents),
            "events": p.events.count(), "measurements": p.measurements.count()}


def cmd_check(args) -> int:
    if args.example:
        print(EXAMPLE)
        return 0
    p = open_project(args)
    found = mdl.check(p.model)
    if args.json:
        return out_json([{"level": lv, "message": msg} for lv, msg in found])
    m = p.model
    errors = [x for x in found if x[0] == "error"]
    head = (f"{len(m.stocks)} stocks · {len(m.flows)} flows · {len(m.sensors)} sensors · {len(m.controllers)} controllers · "
            f"{len(m.valves)} valves · {len(m.agents)} agents · {len(m.system_names())} systems")
    print(f"{c('error', 'bad') if errors else c('ok', 'ok')}   {head}")
    for lv, msg in found:
        print(f"{c(lv, 'bad' if lv == 'error' else 'warn'):<5}  {msg}")
    return 1 if errors else 0


# ---- the system

def cmd_system(args) -> int:
    p = open_project(args)
    m = p.model
    snap = snap_of(p, args)
    if not args.name and not args.all and not args.around:
        rows = []
        for s in m.system_names():
            mem = m.members(s)
            lps = [n for n in snap["loops"] if n in mem]
            off = [n for n in lps if snap["loops"][n]["status"] in ("off", "open")]
            rows.append([s, (m.systems[s].description if s in m.systems else ""), str(len(mem)), str(len(lps)),
                         c(str(len(off)), "bad") if off else "0"])
        if args.json:
            return out_json([dict(zip(["system", "description", "parts", "loops", "off"], r, strict=True)) for r in rows])
        print(table(["SYSTEM", "DESCRIPTION", "PARTS", "LOOPS", "OFF"], rows, "no systems: tag parts with systems = [...]"))
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
        from .runner import running_pid, web_url
        url = web_url(p) if running_pid(p) else None
        if not url:
            print("the web page is not running: ergostat run (or ergostat web)", file=sys.stderr)
            return 2
        q = f"?system={args.name}" if args.name else ("?around=" + args.around if args.around else "")
        import webbrowser
        webbrowser.open(url + "/" + q + ("&" if q else "?") + ("view=wiring" if args.wiring else "view=control"))
        print(url)
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
            print(c("no loops in this selection", "dim"))
        return 0
    if args.wiring:
        for n in g["nodes"]:
            print(f"  [{n['label']} · {n['agentKind']}]  fills " + ", ".join(f"{r['kind']} {r['name']}" for r in n["roles"]))
        for e in g["edges"]:
            print(f"  {e['source'].split(':', 1)[1]} ─▶ {e['target'].split(':', 1)[1]}  {c('via ' + ', '.join(e['via']), 'dim')}")
        return 0
    print(show.system_lines(m, snap, parts))
    return 0


def cmd_loop(args) -> int:
    p = open_project(args)
    m = p.model
    snap = snap_of(p, args)
    parts = parts_of(args, m)
    if not args.name:
        rows = [[n, show.status_word(lp["status"]), lp["stock"], fmt(lp["value"]), lp["setpoint"],
                 fmt(abs(lp["error"])) if lp["error"] and lp["status"] == "off" else "", m.controllers[n].agent or "-",
                 "yes" if lp["observed"] else c("no", "dim")]
                for n, lp in snap["loops"].items() if n in parts]
        if args.json:
            return out_json({n: lp for n, lp in snap["loops"].items() if n in parts})
        print(table(["LOOP", "STATUS", "HOLDS", "NOW", "SETPOINT", "ERROR", "CONTROLLER AGENT", "CYCLED"], rows,
                    "no loops: a loop is a [[controller]] that holds a stock"))
        return 0
    lp = snap["loops"].get(args.name)
    if lp is None:
        print(f"no loop {args.name!r}", file=sys.stderr)
        return 2
    if args.json:
        return out_json(lp)
    ctl = m.controllers[args.name]
    print(c("loop ", "dim") + show.loop_line(lp, args.name) + as_of(snap))
    if ctl.description:
        print(c("  " + ctl.description, "dim"))
    pts = snap["stocks"].get(lp["stock"], {}).get("points", [])
    if pts:
        print(f"  {lp['stock']} over {human(snap['window'])}: {show.spark(pts)}")
    for g in lp["gaps"]:
        print("  " + c("cannot close: " + g, "warn"))
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
                 f"decided {ago(d['time'])}: {d['data'].get('decision')}" if d else c("no decision yet", "dim")])
    for v in lp["valves"] or [None]:
        if v is None:
            rows.append(["valve", c("none", "warn"), "", ""])
            continue
        ops = p.events.query(n=1, type="valve.opened", item=v)
        mode = m.valves[v].mode
        rows.append(["valve", f"{v} {c('(' + mode + ')', 'dim')}", show.agent_tag(m, m.valves[v].agent),
                     f"opened {ago(ops[-1]['time'])}: {fmt(ops[-1]['data'].get('amount'))}" if ops else c("never opened", "dim")])
    flows = [f"{f} {fmt(snap['flows'][f]['rate'])}/h" for f in lp["flows"]]
    rows.append(["moves", ", ".join(flows) or "-", "", ""])
    print(table(["PART", "NAME", "FILLED BY", "LAST"], rows))
    crossings = p.events.query(n=8, item=args.name, type="loop.*", since=snap["at"] - snap["window"], until=snap["at"])
    if crossings:
        print(c(f"\ncrossings in {human(snap['window'])}", "dim"))
        for e in crossings:
            word = e["type"].split(".", 1)[1]
            print(f"  {time.strftime('%H:%M:%S', time.localtime(e['time']))}  {show.status_word(word)}  "
                  f"{lp['stock']} {fmt(e['data'].get('value'))}" + (f", off by {fmt(abs(e['data']['error']))}" if word == "off" else ""))
    d = st.decisions(p, args.name, snap["at"] - snap["window"], snap["at"])
    if d["count"]:
        print(c(f"\ndecisions in {human(snap['window'])}: {d['count']}", "dim"))
        for word, n in d["kinds"][:5]:
            print(f"  {n:>5}  {word}")
    for h in snap["hints"]:
        if h["controller"] == args.name:
            print(c("\nhint: ", "accent") + h["says"])
    return 0


def cmd_agent(args) -> int:
    p = open_project(args)
    m = p.model
    snap = snap_of(p, args)
    if not args.name:
        if args.json:
            return out_json(snap["agents"])
        rows = []
        for n, a in sorted(snap["agents"].items(), key=lambda kv: (kv[1]["rung"], kv[0])):
            when = a["schedule"]
            if not a["runs_itself"]:
                when = "a person" if a["kind"] == "person" else "not run by ergostat"
            last = a["last"]
            if a.get("running_since"):
                state_txt = c(f"running for {human(time.time() - a['running_since'])}", "accent")
            else:
                state_txt = (c("failing", "bad") if a["failing"] else (ago(last["time"]) if last else c("never ran", "dim")))
            rows.append([n, f"{a['rung']} {a['kind']}", when.strip(), str(a["runs"]), state_txt,
                         ", ".join(f"{r['kind']} {r['name']}" for r in a["roles"]) or c("no roles", "dim")])
        print(table(["AGENT", "RUNG", "RUNS", f"RUNS IN {human(snap['window'])}", "LAST", "FILLS"], rows,
                    "no agents"))
        return 0
    a = m.agents.get(args.name)
    if a is None:
        print(f"no agent {args.name!r}", file=sys.stderr)
        return 2
    s = snap["agents"][a.name]
    if args.json:
        return out_json({"agent": a.__dict__, **s})
    print(f"{c('agent', 'dim')} {a.name} · rung {a.rung} {a.kind}" + (f" · {a.description}" if a.description else ""))
    if a.command:
        print(f"  command  {a.command}")
    print("  runs     " + (a.schedule or "not run by ergostat"))
    print("  fills    " + (", ".join(f"{r['kind']} {r['name']}" for r in s["roles"]) or "nothing"))
    runs = [e for e in p.events.query(n=200, item=a.name, type="agent.*") if e["type"] in ("agent.ran", "agent.failed")][-8:]
    print()
    print(table(["WHEN", "RESULT", "READINGS", "OPENINGS", "DECISIONS", "SECONDS"],
                [[ago(e["time"]), c("failed: " + e["data"].get("note", ""), "bad") if e["type"] == "agent.failed" else "ok",
                  str(e["data"].get("readings", 0)), str(e["data"].get("openings", 0)), str(e["data"].get("decisions", 0)),
                  str(e["data"].get("seconds", ""))] for e in runs], "no runs yet"))
    from .runner import log_path
    log = log_path(p, a.name)
    if log.exists():
        tail = log.read_text(errors="replace").splitlines()[-6:]
        if tail:
            print(c("\nend of its log (" + str(log) + ")", "dim"))
            print("\n".join("  " + x for x in tail))
    return 0


# ---- the record

def event_line(e: dict) -> str:
    t = time.strftime("%H:%M:%S", time.localtime(e["time"]))
    data = json.dumps(e["data"], separators=(",", ":")) if e["data"] else ""
    return f"{c(t, 'dim')}  {e['type']:<20} {e.get('item') or '-':<20} {c(e.get('source') or '-', 'accent')}  {data[:100]}"


def cmd_event(args) -> int:
    p = open_project(args)
    if args.name:
        e = p.events.get(args.name)
        if e is None:
            print(f"no event {args.name!r}", file=sys.stderr)
            return 2
        caused = p.events.caused_by(e["id"])
        if args.json:
            return out_json({**e, "caused": caused})
        print(json.dumps(e, indent=2, default=str))
        if e.get("causedby") and (up := p.events.get(e["causedby"])):
            print(c("caused by", "dim"))
            print("  " + event_line(up))
        if caused:
            print(c("caused", "dim"))
            for x in caused:
                print("  " + event_line(x))
        return 0
    since = time.time() - parse_duration(args.since, "--since") if args.since else None
    evs = p.events.query(n=args.n, type=args.type, item=args.item, source=args.source, since=since)
    if args.json and not args.follow:
        return out_json(evs)
    for e in evs:
        print(json.dumps(e, default=str) if args.json else event_line(e))
    if not args.follow:
        return 0
    seq = evs[-1]["seq"] if evs else p.events.last_seq()
    try:
        while True:
            for e in p.events.query(n=None, type=args.type, item=args.item, source=args.source, after_seq=seq):
                seq = e["seq"]
                print(json.dumps(e, default=str) if args.json else event_line(e), flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0


def cmd_item(args) -> int:
    p = open_project(args)
    if not args.name:
        since = time.time() - parse_duration(args.since, "--since") if args.since else None
        its = p.events.items(since, own=args.all)
        if args.json:
            return out_json(its)
        print(table(["ITEM", "EVENTS", "LATEST", "LAST", "FIRST"],
                    [[i["item"], str(i["n"]), i["latest"], ago(i["last"]), ago(i["first"])] for i in its[:args.n]],
                    "no items yet: an item is what your agents' events are about (\"item\": ...)"
                    + ("" if args.all else "; --all also lists the parts and agents")))
        return 0
    evs = p.events.query(n=None, item=args.name)
    if not evs:
        print(f"no item {args.name!r}", file=sys.stderr)
        return 2
    fields: dict = {}
    for e in evs:
        fields.update(e["data"])
    if args.json:
        return out_json({"item": args.name, "fields": fields, "events": evs})
    print(f"{c('item', 'dim')} {args.name} · {len(evs)} events · latest {evs[-1]['type']} {ago(evs[-1]['time'])}")
    for k, v in sorted(fields.items()):
        print(f"  {k:<14} {json.dumps(v, default=str)[:90]}")
    print()
    for e in evs[-args.n:]:
        print(event_line(e))
    return 0


def cmd_residual(args) -> int:
    p = open_project(args)
    snap = snap_of(p, args)
    parts = parts_of(args, p.model)
    res = {k: v for k, v in snap["residuals"].items() if k in parts and (not args.name or k == args.name)}
    if args.json:
        return out_json(res)
    rows = []
    for k, r in res.items():
        verdict = (c("unexplained", "warn") if r["significant"] else
                   (f"estimated as {', '.join(r['absorbed_by'])}" if r["absorbed_by"] else c("explained", "ok")))
        rows.append([k, fmt(r["change"]), fmt(r["explained"]), fmt(r["unexplained"]), verdict])
    print(table(["STOCK", "CHANGED", "EXPLAINED", "UNEXPLAINED", ""], rows,
                "no stock has two readings in this window yet"))
    print(c(f"\nover {human(snap['window'])}: what each stock's readings did, against what its known flows explain", "dim"))
    return 0


# ---- the parts

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
        detail = {k: v for k, v in x.__dict__.items() if v not in ("", [], None)}
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
                print(f"  {k:<12} {v}")
        if now:
            print(c("now", "dim"))
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


# ---- running

def cmd_run(args) -> int:
    from . import runner
    p = open_project(args)
    pid = runner.running_pid(p)
    if args.stop:
        if not pid:
            print("not running")
            return 0
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not runner.running_pid(p):
                break
            time.sleep(0.1)
        print(f"stopped ({pid})")
        return 0
    errors = [msg for lv, msg in mdl.check(p.model) if lv == "error"]
    if errors:
        print("the model has errors; fix them first (ergostat check):", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 2
    if not args.foreground:
        if pid:
            print(f"already running ({pid})" + (f" · {runner.web_url(p)}" if runner.web_url(p) else ""))
            return 0
        extra = [*(["--no-web"] if args.no_web else []), *(["--port", str(args.port)] if args.port else [])]
        child = runner.start_background(p, extra)
        for _ in range(100):
            if runner.running_pid(p) == child and (args.no_web or runner.web_url(p)):
                break
            time.sleep(0.1)
        print(f"running ({child}) · log {p.dir / 'run.log'}" + (f"\nweb: {runner.web_url(p)}" if runner.web_url(p) else ""))
        print(c("see it: ergostat · stop it: ergostat run --stop", "dim"))
        return 0
    runner.pid_file(p).write_text(str(os.getpid()))
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))
    server = None
    if not args.no_web:                                 # the page first, so its address is known at once
        from .web import serve
        server, url = serve(p, args.port)
        print(f"web: {url}", flush=True)
    r = runner.Runner(p, say=lambda s: print(time.strftime("%H:%M:%S"), s, flush=True))
    r.start()
    print(f"running {len(r.queues)} agents", flush=True)
    mtime = p.model.path.stat().st_mtime if p.model.path else 0
    reload = False
    try:
        while not stopping:
            time.sleep(0.5)
            try:
                now_m = p.model.path.stat().st_mtime if p.model.path else 0
            except OSError:
                continue
            if now_m != mtime:
                mtime = now_m
                try:
                    fresh = mdl.load(p.model.path.parent)
                except Exception as e:
                    print(f"{mdl.FILE} changed but does not load ({e}); still running the last one", flush=True)
                    continue
                if any(lv == "error" for lv, _ in mdl.check(fresh)):
                    print(f"{mdl.FILE} changed but has errors (ergostat check); still running the last one", flush=True)
                    continue
                print(f"{mdl.FILE} changed: restarting with it", flush=True)
                reload = True
                break
    except KeyboardInterrupt:
        pass
    r.close()
    if server:
        server.shutdown()
        server.server_close()
        (p.dir / "web.json").unlink(missing_ok=True)
    if reload:                                          # the same process, the new model: the pid file stays right
        os.execv(sys.executable, [sys.executable, "-m", "ergostat", "-C", str(p.repo), "run", "--foreground",
                                  *(["--no-web"] if args.no_web else []), *(["--port", str(args.port)] if args.port else [])])
    runner.pid_file(p).unlink(missing_ok=True)
    return 0


def cmd_web(args) -> int:
    from .web import serve
    p = open_project(args)
    server, url = serve(p, args.port)
    print(f"web: {url}  (Ctrl-C stops it)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        server.server_close()
        (p.dir / "web.json").unlink(missing_ok=True)
    return 0


def cmd_chat(args) -> int:
    from . import supervisor
    here = Path(args.C).resolve() if args.C else Path.cwd()
    return supervisor.chat(here, " ".join(args.message) or None, print_only=args.print_prompt)


EXAMPLE = '''# ergostat.toml: one loop. disk usage is held under 80% by a program that measures and cleans.
# (the project's name defaults to its folder's; ./clean.sh is yours to write: see `ergostat agent --help`)

[[stock]]
name = "disk-used"
unit = "%"
systems = ["host"]

[[disturbance]]
name = "logs-written"
into = "disk-used"
description = "what the services write; nothing here controls it"

[[flow]]
name = "cleaned"
from = "disk-used"

[[sensor]]
name = "disk-usage"
measures = "disk-used"
agent = "disk-cleaner"

[[controller]]
name = "disk-under-80"
holds = "disk-used"
setpoint = "<= 80"
reads = ["disk-usage"]
drives = ["delete-old-files"]
agent = "disk-cleaner"

[[valve]]
name = "delete-old-files"
flow = "cleaned"
agent = "disk-cleaner"

[[agent]]
name = "disk-cleaner"
kind = "program"
command = "./clean.sh"
every = "5m"
'''


# ---- parsing

def build() -> argparse.ArgumentParser:
    def flags(suppress: bool) -> argparse.ArgumentParser:
        """The flags every topic takes; a topic's copy never overwrites what came before the topic."""
        f = argparse.ArgumentParser(add_help=False)
        d = {"default": argparse.SUPPRESS} if suppress else {}
        f.add_argument("-C", metavar="DIR", **d)
        f.add_argument("-s", "--system", **d)
        f.add_argument("--since", **d)
        f.add_argument("--at", **d, help="look at a past moment: 30m (ago), 07:30, or epoch seconds")
        f.add_argument("--json", action="store_true", **d)
        return f
    common = flags(True)
    ap = argparse.ArgumentParser(prog="ergostat", add_help=False, parents=[flags(False)])
    ap.add_argument("-h", "--help", action="store_true")
    ap.add_argument("--version", action="store_true")
    sub = ap.add_subparsers(dest="topic")

    def topic(name, fn, help, named=True, desc=None):
        sp = sub.add_parser(name, parents=[common], help=help, description=desc or help)
        if named:
            sp.add_argument("name", nargs="?")
        sp.set_defaults(fn=fn)
        return sp
    s = topic("system", cmd_system, "Draw a system, or list them",
              desc="Draw a system, or list them. A system is a named selection of the model; systems may overlap.")
    s.add_argument("--all", action="store_true", help="draw everything")
    s.add_argument("--around", metavar="PART", help="one part and what is connected to it (loop/NAME, valve/NAME, ...)")
    s.add_argument("--depth", type=int, default=1, help="how far --around reaches (default 1)")
    s.add_argument("--list", action="store_true", help="the parts as a table")
    s.add_argument("--wiring", action="store_true", help="the agents and how they reach each other")
    s.add_argument("--blocks", action="store_true", help="each loop as a feedback block diagram")
    s.add_argument("--open", action="store_true", help="open it in the web page")
    topic("loop", cmd_loop, "The feedback loops, or one, part by part")
    ch = topic("check", cmd_check, "Is the model whole?", named=False)
    ch.add_argument("--example", action="store_true", help="print an example ergostat.toml")
    topic("agent", cmd_agent, "Who fills which roles, at what rung")
    e = topic("event", cmd_event, "The raw record, or one event with its causes (by id)")
    e.add_argument("-n", type=int, default=30)
    e.add_argument("--type")
    e.add_argument("--item")
    e.add_argument("--source")
    e.add_argument("--follow", "-f", action="store_true")
    i = topic("item", cmd_item, "Events folded by id")
    i.add_argument("-n", type=int, default=30)
    i.add_argument("--all", action="store_true", help="also the parts and agents ergostat's own events are about")
    topic("residual", cmd_residual, "What the model can't explain")
    for t in PART_TOPICS:
        topic(t, cmd_part, f"The {t}s, or one").set_defaults(fn=cmd_part, topic=t)
    r = topic("run", cmd_run, "Start the agents (in the background) and the web page", named=False)
    r.add_argument("--foreground", action="store_true")
    r.add_argument("--stop", action="store_true")
    r.add_argument("--no-web", action="store_true")
    r.add_argument("--port", type=int)
    w = topic("web", cmd_web, "Serve the web page only", named=False)
    w.add_argument("--port", type=int)
    chat = sub.add_parser("chat", parents=[common], help="Talk to the Supervisor")
    chat.add_argument("message", nargs="*")
    chat.add_argument("--print-prompt", action="store_true")
    chat.set_defaults(fn=cmd_chat)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build()
    args = ap.parse_args(argv)
    if args.version:
        print(f"ergostat {__version__}")
        return 0
    if getattr(args, "help", False) and not args.topic:
        print(HELP)
        return 0
    try:
        if not args.topic:
            return cmd_status(args)
        return args.fn(args)
    except DurationError as e:
        print(e, file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0
