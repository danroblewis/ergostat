"""``ergostat agent``: who fills which roles, at what rung."""

from __future__ import annotations

import json
import sys
import time

from .. import model as mdl
from .. import show
from ..durations import human
from ..show import ago, c, table
from ..state import fmt
from .common import open_project, out_json, snap_of


def cmd_agent(args) -> int:
    if getattr(args, "now", False):
        return run_now(args)
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
            if a["kind"] == "person":
                state_txt = c("–", "dim")
            elif a.get("running_since"):
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
    from ..costs import record as costs
    use = costs.of_block(p, a.name, snap["at"] - snap["window"], snap["at"])
    if args.json:
        return out_json({"agent": a.__dict__, **s, "use": use})
    print(f"{c('agent', 'dim')} {a.name} · rung {a.rung} {a.kind}" + (f" · {a.description}" if a.description else ""))
    if a.command:
        print(f"  command  {a.command}")
    print("  runs     " + (a.schedule or "not run by ergostat"))
    print("  fills    " + (", ".join(f"{r['kind']} {r['name']}" for r in s["roles"]) or "nothing"))
    loads = [f.name for f in m.flows.values() if f.disturbance and f.agent == args.name]
    if loads:
        print("  the load " + ", ".join(f"disturbance {x}" for x in loads))
    every = [e for e in p.events.query(n=400, item=a.name, type="agent.*") if e["type"] in ("agent.ran", "agent.failed")]
    runs = every[-8:]
    if len(every) > 2:
        secs = [float(e["data"].get("seconds") or 0) for e in every[-40:]]
        failed = sum(1 for e in every[-40:] if e["type"] == "agent.failed")
        print(f"  durations {show.spark(list(enumerate(secs)), 40)}  {fmt(min(secs))}s to {fmt(max(secs))}s over the last "
              f"{len(secs)} runs" + (c(f", {failed} failed", "bad") if failed else ""))
    for line in cost_lines(use, human(snap["window"])):
        print(line)
    print()
    print(table(["WHEN", "RESULT", "READINGS", "OPENINGS", "DECISIONS", "SECONDS", "COST", "TOKENS", "CPU", "MEMORY"],
                [[ago(e["time"]), c("failed: " + e["data"].get("note", ""), "bad") if e["type"] == "agent.failed" else "ok",
                  str(e["data"].get("readings", 0)), str(e["data"].get("openings", 0)), str(e["data"].get("decisions", 0)),
                  str(e["data"].get("seconds", "")), *run_costs(costs.numbers(e))] for e in runs], "no runs yet"))
    from ..runner import log_path
    log = log_path(p, a.name)
    if log.exists():
        tail = log.read_text(errors="replace").splitlines()[-6:]
        if tail:
            print(c("\nend of its log (" + str(log) + ")", "dim"))
            print("\n".join("  " + x for x in tail))
    return 0


def usd(x) -> str:
    return "–" if x is None else "$0" if x == 0 else f"${x:.4f}" if x < 0.01 else f"${x:,.2f}"


def tokens(n) -> str:
    return "–" if not n else f"{n / 1e6:.3g}M" if n >= 1e6 else f"{n / 1e3:.3g}k" if n >= 1e4 else str(n)


def cpu(x) -> str:
    return "–" if x is None else f"{x:.2g}s" if x < 60 else human(x)


def mem(b) -> str:
    return "–" if not b else f"{b / 1e9:.3g} GB" if b >= 1e9 else f"{b / 1e6:.3g} MB"


def run_costs(n: dict) -> list[str]:
    """A run's cost, tokens, CPU and peak memory, as a row's last cells (SPEC §9.1)."""
    return [usd(n["cost_usd"]) + (" est." if n["cost"] and n["cost"] != "reported" else ""), tokens(n["tokens"]),
            cpu(n["cpu"]), mem(n["memory"])]


def cost_lines(use: dict, window: str) -> list[str]:
    """What an agent's runs cost over the window: totals, and a spark line of each number run by run."""
    t = use["totals"]
    if not t["runs"]:
        return []
    est = f" ({t['cost']})" if t["cost"] and t["cost"] != "reported" else ""
    out = [f"  cost     {usd(t['cost_usd'])}{est} · {tokens(t['tokens'])} tokens · {cpu(t['cpu'])} CPU · at most "
           f"{mem(t['memory_peak'])} in one run, over {t['runs']} runs in {window}"]
    for key, name, f in (("cost_usd", "cost", usd), ("cpu", "CPU", cpu), ("memory", "memory", mem)):
        xs = [(r["time"], r[key]) for r in use["runs"] if r[key] is not None]
        if len(xs) > 2:
            vs = [v for _, v in xs]
            out.append(f"  {name:<8} {show.spark(list(enumerate(vs[-40:])), 40)}  {f(min(vs))} to {f(max(vs))} a run")
    return out


def run_now(args) -> int:
    """``ergostat agent NAME --now``: run it once, at once, recorded like any run; say what it said."""
    from ..runner import log_path, run_agent
    p = open_project(args)
    a = p.model.agents.get(args.name or "")
    if a is None:
        print(f"no agent {args.name!r}" if args.name else "name the agent: ergostat agent NAME --now", file=sys.stderr)
        return 2
    if not a.command or a.kind == "person":
        print(f"{a.name} has no command for ergostat to run" + (" (a person)" if a.kind == "person" else ""), file=sys.stderr)
        return 2
    errors = [msg for lv, msg in mdl.check(p.model, warnings=False) if lv == "error"]
    if errors:
        many = "s" if len(errors) > 1 else ""
        print(c(f"the model has {len(errors)} error{many} (ergostat check); running it anyway, to try it", "warn"))
    seq = p.events.last_seq()
    began = time.time()
    r = run_agent(p, a, why="by hand")
    said = p.events.query(n=None, after_seq=seq)
    if args.json:
        return out_json({"run": r, "events": said})
    ok = not r.get("note")
    def n(k, word):
        return f"{k} {word}" + ("" if k == 1 else "s")
    print(f"{c('ran', 'ok') if ok else c(r.get('note'), 'bad')} in {r['seconds']}s: {n(r['readings'], 'reading')}, "
          f"{n(r['openings'], 'opening')}, {n(r['decisions'], 'decision')}, {n(r['events'], 'event')}" +
          (c(f", {r['refused']} refused", "warn") if r["refused"] else ""))
    from .record import event_line
    for e in said:
        if e["type"] not in ("agent.started", "agent.ran", "agent.failed"):
            print("  " + event_line(e))
    for s_ in p.model.sensors.values():
        if s_.agent == a.name:
            got = p.measurements.latest(f"sensor/{s_.name}")
            if got and got[0] >= time.time() - r["seconds"] - 1:
                print(f"  {c('reading', 'dim')}  {s_.name} = {fmt(got[1])}")
    if r.get("unread"):
        print(c(f"{r['unread']} line{'s' if r['unread'] > 1 else ''} not understood (broken JSON, or naming no part or event):", "warn"))
        for line in r.get("unread_lines", []):
            print(f"  {line}")
    # the roles it fills that it said nothing for: the likeliest thing missing from a new agent
    decided = {e.get("item") for e in said if e["type"] == "controller.decided"}
    opened = {e.get("item") for e in said if e["type"] == "valve.opened"}
    silent = []
    for role in p.model.roles_of(a.name):
        if role.kind == "sensor":
            got = p.measurements.latest(f"sensor/{role.name}")
            if not got or got[0] < began:
                silent.append(f"sensor {role.name}")
        elif role.kind == "controller" and role.name not in decided and not role.open_loop:   # a timer never says
            silent.append(f"controller {role.name}")
        elif role.kind == "valve" and role.name not in opened:
            silent.append(f"valve {role.name}")
    sensors = [x for x in silent if x.startswith("sensor ")]
    if sensors:
        print(c("no reading from: " + ", ".join(sensors) + " (a sensor should read every run)", "warn"))
    if silent and r.get("printed") and "took" not in r and a.parse and not r["readings"] + r["openings"]:
        print(c(f"it printed {r['printed']} line{'s' if r['printed'] != 1 else ''}, but none matched its parse ({a.parse})", "warn"))
    elif silent and r.get("printed") and "took" not in r and not (r["readings"] or r["openings"] or r["decisions"] or r["events"]):
        # it printed, but nothing ergostat could take: the likeliest mistake with a script that talks to people
        print(c(f"it printed {r['printed']} line{'s' if r['printed'] != 1 else ''} but nothing was recorded: print the number "
                f"alone (`... | wc -l`), JSON lines (ergostat help blocks), or give the agent "
                f"parse = \"cleaned up (\\\\d+)\" to take the number from its own words", "warn"))
    elif len(silent) > len(sensors):
        print(c("said nothing for: " + ", ".join(x for x in silent if x not in sensors) + " (fine when there was nothing to do)", "dim"))
    lines = log_path(p, a.name).read_text(errors="replace").splitlines() if log_path(p, a.name).exists() else []
    starts = [i for i, x in enumerate(lines) if x.startswith("--- ")]
    tail = lines[starts[-1] + 1:][-12:] if starts else []                 # this run's section only
    if tail:
        print(c("this run's log", "dim"))
        print("\n".join("  " + x for x in tail))
    if r["refused"]:
        for e in said:
            if e["type"] == "agent.refused":
                print(c("refused: ", "warn") + e["data"]["why"] + f"  {json.dumps(e['data']['line'])[:200]}")
    return 0 if ok and not r["refused"] else 1
