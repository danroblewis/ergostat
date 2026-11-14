"""``ergostat agent``: who fills which roles, at what rung."""

from __future__ import annotations

import sys
import time

from ..durations import human
from ..show import ago, c, table
from .common import open_project, out_json, snap_of


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
    from ..runner import log_path
    log = log_path(p, a.name)
    if log.exists():
        tail = log.read_text(errors="replace").splitlines()[-6:]
        if tail:
            print(c("\nend of its log (" + str(log) + ")", "dim"))
            print("\n".join("  " + x for x in tail))
    return 0
