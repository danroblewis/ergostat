"""``ergostat`` (the status) and ``ergostat check``."""

from __future__ import annotations

import time

from .. import model as mdl
from .. import show
from .. import state as st
from ..show import ago, c, table
from ..state import fmt
from .common import EXAMPLE, EXAMPLE_CRON, as_of, open_project, out_json, parts_of, snap_of, window


def cmd_status(args) -> int:
    if getattr(args, "watch", False):
        return watch(args)
    return status(args)


def watch(args, every: float = 2.0) -> int:
    """``ergostat --watch``: the status, redrawn every two seconds until Ctrl-C."""
    import contextlib
    import io
    import sys
    try:
        while True:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                status(args)
            sys.stdout.write("\033[H\033[2J" + buf.getvalue() + c(f"\nredrawn every {every:g}s · Ctrl-C to stop", "dim") + "\n")
            sys.stdout.flush()
            time.sleep(every)
    except KeyboardInterrupt:
        return 0


def status(args) -> int:
    from ..runner import running_pid, web_url
    p = open_project(args)
    m, snap = p.model, snap_of(p, args)
    pid = running_pid(p)
    att = st.attention(snap, running=bool(pid) and snap["live"], model=m)
    loops = snap["loops"]
    if args.system:                                       # only what is in that system
        parts = parts_of(args, m)
        agents = {x.agent for t in (m.sensors, m.controllers, m.valves) for x in t.values() if x.name in parts}
        loops = {n: lp for n, lp in loops.items() if n in parts}
        att = [a for a in att if a["what"].split(" ", 1)[-1] in parts | agents or a["what"] == "the record"]
    trouble = any(a["level"] in ("bad", "warn") for a in att)
    code = 1 if (getattr(args, "exit_code", False) and trouble) else 0
    if args.json:
        out_json({"running": bool(pid), "web": web_url(p) if pid else None, "attention": att,
                  "loops": loops, "counts": counts(p), "ok": not trouble})
        return code
    run = c("running", "ok") + (f" · {web_url(p)}" if web_url(p) else "") if pid else c("not running", "warn") + " · start: ergostat run"
    print(f"{c('ergostat', 'bold')} · {m.name} · {run}{as_of(snap)}")
    if not m.stocks and not m.agents:
        print("the model is empty. describe your system with `ergostat chat`.")
        return 0
    print()
    problems = [a for a in att if a["level"] != "hint"]
    hints = [a for a in att if a["level"] == "hint"]
    for a in problems:
        print(f"  {c('●', a['level'])} {a['what']}: {a['says']}")
    if not problems:
        print(f"  {c('●', 'ok')} nothing needs you")
    if hints:
        print(c(f"\n  suggestions ({len(hints)}): ergostat loop NAME shows the evidence", "dim"))
        for a in hints:
            print(f"  {c('○', 'accent')} {a['what']}: {a['says']}")
    print()
    if args.since:
        from .. import history
        ch = history.changes(p, time.time() - window(args))
        print(c(f"the model, since {args.since} ago: " + (f"{len(ch)} change{'' if len(ch) == 1 else 's'}" if ch else "no changes"), "dim"))
        for e in ch:
            d = e["data"]
            what = [f"+{x}" for x in d["added"]] + [f"-{x}" for x in d["removed"]] + [f"~{x}" for x in d["changed"]]
            more = f"  and {len(what) - 6} more" if len(what) > 8 else ""
            when = time.strftime("%a %H:%M" if time.time() - e["time"] > 86400 else "%H:%M:%S", time.localtime(e["time"]))
            print(f"  {when}  " + "  ".join(what[:6] if more else what) + c(more, "dim"))
        print()
    if loops and not pid and snap["live"]:
        last = max((lp["last_read"] for lp in loops.values() if lp.get("last_read")), default=None)
        if last:
            print(c(f"not running: these are the last readings, from {ago(last)}; nothing is measuring now", "warn"))
    if loops:
        print(table(["LOOP", "STATUS", "HOLDS", "NOW", "SETPOINT", "TIME OFF"],
                    [[n, show.status_word(lp["status"]), lp["stock"], fmt(lp["value"]), st.setpoint_text(lp),
                      (c(f"{round(lp['off_share'] * 100)}%", "bad" if lp["off_share"] >= 0.5 else "warn") if lp.get("off_share")
                       else ("0%" if lp.get("observed") else "-"))]
                     for n, lp in loops.items()]))
        print()
    k = counts(p)
    print(c(f"{k['loops']} loops · {k['stocks']} stocks · {k['flows']} flows · {k['agents']} agents · "
            f"{k['events']} events · {k['measurements']} measurements", "dim"))
    return code

def counts(p) -> dict:
    m = p.model
    return {"loops": len(m.controllers), "stocks": len(m.stocks), "flows": len(m.flows), "agents": len(m.agents),
            "events": p.events.count(), "measurements": p.measurements.count()}

def cmd_check(args) -> int:
    if args.example:
        print(EXAMPLE_CRON if args.example == "cron" else EXAMPLE)
        return 0
    p = open_project(args)
    found = mdl.check(p.model)
    m = p.model
    errors = [x for x in found if x[0] == "error"]
    if args.json:
        return out_json({"ok": not errors, "errors": len(errors), "warnings": len(found) - len(errors),
                         "found": [{"level": lv, "message": msg} for lv, msg in found]}) or (1 if errors else 0)

    def n(k, word):
        return f"{k} {word}" + ("" if k == 1 else "s")
    head = " · ".join([n(len(m.stocks), "stock"), n(len(m.flows), "flow"), n(len(m.sensors), "sensor"),
                       n(len(m.controllers), "controller"), n(len(m.valves), "valve"), n(len(m.agents), "agent"),
                       n(len(m.system_names()), "system")])
    print(f"{c('error', 'bad') if errors else c('ok', 'ok')}   {head}")
    for lv, msg in found:
        print(f"{c(lv, {'error': 'bad', 'warn': 'warn'}.get(lv, 'dim')):<5}  {msg}")
    return 1 if errors else 0
