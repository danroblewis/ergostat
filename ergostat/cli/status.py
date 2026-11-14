"""``ergostat`` (the status) and ``ergostat check``."""

from __future__ import annotations

import time

from .. import model as mdl
from .. import show
from .. import state as st
from ..show import c, table
from ..state import fmt
from .common import EXAMPLE, as_of, open_project, out_json, snap_of, window


def cmd_status(args) -> int:
    from ..runner import running_pid, web_url
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
        from .. import history
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
