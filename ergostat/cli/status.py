"""``ergostat`` (the status) and ``ergostat check``."""

from __future__ import annotations

import time
from pathlib import Path

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


def _edited(args, err: Exception) -> int | None:
    """The model's files do not load: when a runner runs here, it still runs the last good version, and that is said
    with every error (not the status, which needs a model). None: no runner here (the error is said as everywhere)."""
    from pathlib import Path
    from types import SimpleNamespace

    from .. import reload as rl
    from ..calls.client import state_of
    from ..runner import running_pid, web_url
    here = Path(args.C).resolve() if getattr(args, "C", None) else Path.cwd()
    d = state_of(here)
    pid = running_pid(SimpleNamespace(dir=d)) if d is not None else None
    if not pid:
        return None
    lines = [x.strip() for x in str(err).splitlines()[1:] if x.strip()] or [str(err)]
    known = rl.read_state(d) or {}
    if getattr(args, "json", False):
        out_json({"running": True, "web": web_url(SimpleNamespace(dir=d)), "edited": {"errors": lines,
                  "banner": rl.banner(lines), "running": known.get("running")}, "ok": False})
        return 1
    print(f"{c('ergostat', 'bold')} · {c('running', 'ok')} ({pid})" + (f" · {web_url(SimpleNamespace(dir=d))}"
                                                                       if web_url(SimpleNamespace(dir=d)) else ""))
    print()
    print(f"  {c('●', 'bad')} {rl.banner(lines)}" + (f" ({known['running']})" if known.get("running") else "") + ":")
    for x in lines:
        print(f"      {x}")
    print(c("\n  the status shows again once the files load (ergostat check)", "dim"))
    return 1


def status(args) -> int:
    from ..goodmodel import fallback
    from ..runner import running_pid, web_url
    from ..store import Project
    here, broken = Path(args.C).resolve() if getattr(args, "C", None) else Path.cwd(), None
    try:
        p = Project(mdl.load(here))
    except mdl.ModelError as e:                           # shown with the engine's last good model, when one is kept
        p, broken = fallback(here, e), e
        if p is None:
            got = _edited(args, e)                        # (else: a runner still runs the last good version)
            if got is not None:
                return got
            p = open_project(args)                        # (which says it, as everywhere)
    except Exception:
        p = open_project(args)
    m, snap = p.model, snap_of(p, args)
    pid = running_pid(p)
    att = st.attention(snap, running=bool(pid) and snap["live"], model=m)
    edited = None
    if pid:                                               # loads, but the runner refused it (errors the check finds)
        from ..reload import read_state
        edited = read_state(p.dir)
    if broken is not None:
        from .. import reload as rl
        lines = [x.strip() for x in str(broken).splitlines()[1:] if x.strip()] or [str(broken)]
        edited = {"banner": rl.banner(lines) if pid else rl.banner(lines).replace("still running", "shown with"),
                  "errors": lines}
    if edited:
        att.insert(0, {"level": "bad", "what": "the model", "says": edited["banner"]})
    spec = getattr(m, "spec", None)
    if spec is not None and not getattr(args, "at", None):   # the YAML model's findings: from the record, and missing loops
        from ..spec import watch
        for f in watch.find(p, spec):
            att.append({"level": "warn", "what": f.about or "the model", "says": f.message.split(": ", 1)[-1]})
        for f in m.problems:
            if f.code == "missing-feedback":
                att.append({"level": "bad" if "(critical)" in f.message else "hint", "what": f.about,
                            "says": f.message.split(": ", 1)[-1]})
    loops = snap["loops"]
    if spec is not None and not getattr(args, "at", None):   # an off loop names the open items about it (SPEC §5a)
        for n, says in off_about(p, spec, loops).items():
            loops[n]["about"] = says
            for a in att:
                if a["what"] == f"loop {n}" and a["level"] != "hint":   # its attention line, not its suggestion
                    a["says"] += f" · items about it: {says}"
    if args.system:                                      # only what is in that system
        parts = parts_of(args, m)
        agents = {x.agent for t in (m.sensors, m.controllers, m.valves) for x in t.values() if x.name in parts}
        loops = {n: lp for n, lp in loops.items() if n in parts}
        att = [a for a in att if a["what"].split(" ", 1)[-1] in parts | agents or a["what"] == "the record"]
    trouble = any(a["level"] in ("bad", "warn") for a in att)
    code = 1 if (getattr(args, "exit_code", False) and trouble) else 0
    said = None
    if spec is not None and not getattr(args, "at", None):    # the modelling loop, never silent: what it waits for
        try:
            from ..numbers import modelling_status as mst
            said = mst.of(p)
        except Exception as e:
            said = {"on": None, "says": f"modelling: cannot say ({type(e).__name__}: {e})"}
    if args.json:
        out_json({"running": bool(pid), "web": web_url(p) if pid else None, "attention": att,
                  **({} if pid else {"last_seen": last_seen(p, snap)}),
                  "loops": loops, "goals_off": st.goals_off(snap),
                  "counts": counts(p), "ok": not trouble, **({"modelling": said} if said else {})})
        return code
    seen = last_seen(p, snap) if not pid else None
    run = c("running", "ok") + (f" · {web_url(p)}" if web_url(p) else "") if pid else \
        c("engine not running", "warn") + (f" (last seen {ago(seen)})" if seen else "") + " · start: ergostat run"
    print(f"{c('ergostat', 'bold')} · {m.name} · {run}{as_of(snap)}")
    if not m.stocks and not m.agents:
        print("the model is empty. describe your system with `ergostat chat`.")
        return 0
    g = st.goals_off(snap)                                # the one count, as the page's header and `ergostat projects`
    print(c(st.goals_said(g), "bad" if g["system"] else "dim"))
    print()
    problems = [a for a in att if a["level"] != "hint"]
    hints = [a for a in att if a["level"] == "hint"]
    for a in problems:
        print(f"  {c('●', a['level'])} {a['what']}: {a['says']}")
        if edited and a["says"] == edited["banner"]:
            for x in edited["errors"]:
                print(f"      {x}")
    if not problems:
        print(f"  {c('●', 'ok')} nothing needs you")
    if said:
        print(f"  {c('◆', 'accent')} modelling: {said['says']}")
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
            what = [f"+{x}" for x in d["added"]] + [f"-{x}" for x in d["removed"]] + [f"~{x}" for x in d["changed"]] + [
                f"~interface:{x}" for x in d.get("interfaces_changed", [])]
            more = f"  and {len(what) - 6} more" if len(what) > 8 else ""
            when = time.strftime("%a %H:%M" if time.time() - e["time"] > 86400 else "%H:%M:%S", time.localtime(e["time"]))
            print(f"  {when}  " + "  ".join(what[:6] if more else what) + c(more, "dim"))
        print()
    dead = not pid and snap["live"] and bool(seen)
    if loops and dead:
        print(c(f"engine not running: these are the loops as last seen, {ago(seen)}; nothing is measuring now", "warn"))
    if loops:
        print(table(["LOOP", "STATUS", "HOLDS", "NOW", "SETPOINT", "TIME OFF"],
                    [[n + (c(" ⏲", "dim") if lp.get("open_loop") else ""),
                      (c(f"was {lp['status']}", "dim") if dead else show.status_word(lp["status"]))
                      + (c(f" ({lp['about']})", "dim") if lp.get("about") else ""), lp["stock"],
                      fmt(lp["value"]), st.setpoint_text(lp),
                      (c(f"{round(lp['off_share'] * 100)}%", "bad" if lp["off_share"] >= 0.5 else "warn") if lp.get("off_share")
                       else ("0%" if lp.get("observed") else "-"))]
                     for n, lp in loops.items()]))
        print()
    k = counts(p)
    def n(x, word):
        return f"{x} {word}{'' if x == 1 else 's'}"
    print(c(" · ".join(n(k[w + "s"], w) for w in ("loop", "stock", "flow", "agent", "event", "measurement")), "dim"))
    return code

def off_about(p, spec, loops: dict) -> dict[str, str]:
    """Per loop that is off with open items about its goal or its measured value: their ids (at most 3, "+N"), or
    that they are unknown when the item index cannot be read. No lookup when none is off or no kind declares about:."""
    from ..spec import about as ab
    off = {n: [f"goal.{n}", str(spec.goals[n].of)] for n, lp in loops.items() if lp.get("status") == "off" and n in spec.goals}
    if not off or not ab.declared(spec):
        return {}
    try:
        got = ab.open_about(p.events, spec, {x for ps in off.values() for x in ps})
    except ab.Unknown:
        return dict.fromkeys(off, "unknown (the item index could not be read)")
    ids = {n: list(dict.fromkeys(i for i, _, _ in sorted((y for x in ps for y in got.get(x, [])), key=lambda y: -y[2])))
           for n, ps in off.items()}                     # the latest first, whichever part each is about
    return {n: ab.short(v) for n, v in ids.items() if v}


def last_seen(p, snap: dict) -> float | None:
    """When the engine was last seen alive: its last heartbeat, else its last reading."""
    from ..watcher import beat
    hb = beat(p.dir) or {}
    return hb.get("written") or max((lp["last_read"] for lp in snap["loops"].values() if lp.get("last_read")), default=None)


def counts(p) -> dict:
    m = p.model
    return {"loops": len(m.controllers), "stocks": len(m.stocks), "flows": len(m.flows), "agents": len(m.agents),
            "events": p.events.count(), "measurements": p.measurements.count()}

def cmd_check(args) -> int:
    if args.example:
        print(EXAMPLE_CRON if args.example == "cron" else EXAMPLE)
        return 0
    from .spec_cmds import check_yaml, here
    path = mdl.find(here(args))
    if path is not None and path.name == mdl.YAML:
        return check_yaml(args, path)
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
