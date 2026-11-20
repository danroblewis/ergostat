"""How long a workflow's steps take, hop by hop (docs/proposals/latency.md).

    uv run python scripts/latency_bench.py synth 1 50 100 500 --label before     # a 5-step workflow whose steps do no work
    uv run python scripts/latency_bench.py synth 100 --warm 20 --label warm      # each step a warm daemon (SPEC §9.7)
    uv run python scripts/latency_bench.py synth 50 --intake collector            # arrivals by a polling collector (3 s)
    uv run python scripts/latency_bench.py factory --tickets 3 --label before     # ticket-factory offline (fakes, stand-in)
    uv run python scripts/latency_bench.py calls --label before                   # what one call from a step costs

**synth.** A model with one item kind, ``job``, states s0 → s5, and five program blocks that each take the jobs in
one state (``takes:``) and print the event that moves them to the next; each step is a zsh one-liner that notes when
it began and reads nothing. N jobs arrive at once, by ``--intake``:

- ``record``: written into the record from outside (what ``ergostat event --add`` does, without its model load);
- ``collector``: a collector sensor (``every: 3s``) reads them from a spool file and prints them, as collectors do;
- ``push``: one ``POST /api/events`` to the running engine (when it has one).

Each job's hops, from the record: arrival → recorded (intake) → leased (``ergostat.lease.taken``: dispatch) → the
step's process began (its own clock: spawn) → its event recorded (run) → its lease ended (release; the next step
can take it only then). Per part p50/p95 over every hop, end to end per job, and throughput.

**factory.** examples/ticket-factory, copied and run offline (``TF_OFFLINE=1``: fakes for Jira and GitHub, the
stand-in for the AI, the scripted teammate approving): per step, how long a ticket waits to be taken, each run's
length, how many runs a step took (each ``Wait`` gives the ticket back for ``POLL_EVERY``), and end to end.

**calls.** One ``ergostat act``, ``event --add``, ``lease --renew`` and ``item --json`` from inside a run, timed
(the engine's socket, when it listens, against the command loading the model).

SAFETY. The engine's threads and memory are sampled every 2 s and the run killed above ``--max-threads`` (1,500)
or ``--max-rss`` (6 GB); nothing starts while an earlier benchmark's engine is alive. Items stay at or under 500.
Every result is appended as it comes to ``--out`` (docs/proposals/latency-results.jsonl). Ports 8791-8799."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
OUT = ROOT / "docs/proposals/latency-results.jsonl"
MARK = "ergostat-latency-bench"          # in every engine's environment, so an old one can be found
MAX_ITEMS = 500

STEP = """#!/bin/zsh -f
zmodload zsh/datetime
t=$EPOCHREALTIME
cat >/dev/null
print -r -- "{\\"event\\":\\"job.$1\\",\\"data\\":{\\"started\\":$t}}"
"""

WARM_STEP = """#!/bin/zsh -f
zmodload zsh/datetime
while IFS= read -r line; do
  [[ $line == *'"op": "stop"'* ]] && exit 0
  [[ $line == *'"op": "item"'* && $line =~ '"run": "([^"]+)"' ]] || continue
  print -r -- "{\\"event\\":\\"job.$1\\",\\"run\\":\\"$match[1]\\",\\"data\\":{\\"started\\":$EPOCHREALTIME}}"
  print -r -- "{\\"done\\":0,\\"run\\":\\"$match[1]\\"}"
done
"""

COLLECT = """import json, os, sys
spool, seen = sys.argv[1], sys.argv[1] + ".seen"
n = int(open(seen).read() or 0) if os.path.exists(seen) else 0
lines = open(spool).read().splitlines() if os.path.exists(spool) else []
for line in lines[n:]:
    print(line)
open(seen, "w").write(str(len(lines)))
print(len(lines) - n)
"""


# ---- safety

def others() -> list[int]:
    """Engines an earlier run of this benchmark left alive."""
    r = subprocess.run(["ps", "-axeww", "-o", "pid=,command="], capture_output=True, text=True)
    me = os.getpid()
    return [int(ln.split()[0]) for ln in r.stdout.splitlines() if MARK in ln and int(ln.split()[0]) != me
            and "latency_bench.py" not in ln]


def threads_of(pid: int) -> int:
    r = subprocess.run(["ps", "-M", "-p", str(pid)], capture_output=True, text=True)
    return max(0, len(r.stdout.splitlines()) - 1)


def rss_of(pid: int) -> int:
    r = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip() or 0) * 1024
    except ValueError:
        return 0


def children_of(pgid: int) -> int:
    r = subprocess.run(["pgrep", "-g", str(pgid)], capture_output=True, text=True)
    return len(r.stdout.split())


class Watch:
    """Samples a process every 2 s; kills its group above the limits."""

    def __init__(self, proc: subprocess.Popen, max_threads: int, max_rss: float):
        self.proc, self.max_threads, self.max_rss = proc, max_threads, max_rss
        self.threads = self.rss = self.procs = 0
        self.killed: str | None = None
        self.stop = threading.Event()
        threading.Thread(target=self.run, daemon=True).start()

    def run(self) -> None:
        while not self.stop.is_set() and self.proc.poll() is None:
            t, r, n = threads_of(self.proc.pid), rss_of(self.proc.pid), children_of(self.proc.pid)
            self.threads, self.rss, self.procs = max(self.threads, t), max(self.rss, r), max(self.procs, n)
            if t > self.max_threads or r > self.max_rss:
                self.killed = f"{t} threads, {r / 1e9:.2f} GB"
                print(f"KILLED: {self.killed}", flush=True)
                kill(self.proc)
                return
            self.stop.wait(2.0)


def kill(proc: subprocess.Popen, sig=signal.SIGKILL) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def stop_engine(proc: subprocess.Popen) -> None:
    kill(proc, signal.SIGTERM)
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        kill(proc)
        proc.wait(5)


# ---- the results

def pct(xs: list[float], q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 4)


def summary(xs: list[float]) -> dict:
    return {"p50": pct(xs, 0.5), "p95": pct(xs, 0.95), "max": pct(xs, 1.0), "n": len([x for x in xs if x is not None])}


def write(out: Path, row: dict) -> dict:
    row = {"at": time.time(), "load": round(os.getloadavg()[0], 1), **row}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row)[:1500], flush=True)
    return row


def events_of(home: Path, project: Path) -> list[dict]:
    """Every event in the project's record, read as ergostat reads it."""
    os.environ["ERGOSTAT_HOME"] = str(home)
    from ergostat import model as mdl
    from ergostat.store import Project
    p = Project(mdl.load(project))
    return p.events.query(n=None)


# ---- the synthetic workflow

def synth_model(d: Path, steps: int, pool: int, intake: str, warm: int = 0) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "step.zsh").write_text(WARM_STEP if warm else STEP)
    (d / "collect.py").write_text(COLLECT)
    states = [f"s{i}" for i in range(steps + 1)]
    on = {"job.arrived": "s0", **{f"job.s{i}": f"s{i}" for i in range(1, steps + 1)}}
    y = ["name: latency-bench", "items:", "  job:", "    id: job/*", f"    states: [{', '.join(states)}]", "    on:"]
    y += [f"      {k}: {v}" for k, v in on.items()]
    y += ["    lease: {attempts: 3}", "stocks:"]
    for s in states[:-1]:
        y += [f"  {s}:", f"    sensor: {{items: job, state: {s}, every: 10s}}"]
    y += ["flows:"]
    for i in range(1, steps + 1):
        y += [f"  step{i}:", f"    from: s{i - 1}"] + ([f"    to: s{i}"] if i < steps else []) + \
             [f"    sensor: {{items: job, entering: s{i}, over: 10m}}"]
    if intake == "collector":
        y += ["  arrivals:", "    to: s0", f"    sensor: {{run: {PY} collect.py spool.jsonl, every: 3s}}"]
    y += ["blocks:"]
    for i in range(1, steps + 1):
        run = f"daemon: {{run: zsh -f step.zsh s{i}, warm: true, concurrency: {warm}}}" if warm else \
            f"run: zsh -f step.zsh s{i}"
        y += [f"  step{i}:", "    type: program", f"    {run}",
              f"    takes: {{kind: job, at: s{i - 1}, to: [s{i}]}}", f"    pool: {pool}", f"    out: flow.step{i}"]
    (d / "ergostat.yaml").write_text("\n".join(y) + "\n")


def start_engine(d: Path, home: Path, port: int | None, log: Path, extra_env: dict | None = None) -> subprocess.Popen:
    env = {**os.environ, "ERGOSTAT_HOME": str(home), "ERGOSTAT_AI": "false", "ERGOSTAT_BENCH": MARK, **(extra_env or {})}
    cmd = [PY, "-m", "ergostat", "-C", str(d), "run", "--foreground", *(["--port", str(port)] if port else ["--no-web"])]
    return subprocess.Popen(cmd, cwd=d, env=env, stdout=open(log, "w"), stderr=subprocess.STDOUT, start_new_session=True)


def ready(log: Path, proc: subprocess.Popen, timeout: float = 60.0) -> float:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"the engine ended: {log.read_text()[-2000:]}")
        if "running " in log.read_text():
            return time.monotonic() - t0
        time.sleep(0.1)
    raise RuntimeError("the engine did not start")


def state_dir(home: Path) -> Path:
    got = [p.parent for p in home.rglob("repo.json")]
    if not got:
        raise RuntimeError(f"no state directory under {home}")
    return got[0]


def push(port: int, home: Path, evs: list[dict]) -> dict:
    token = (state_dir(home) / "intake.token").read_text().strip()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/events", data=json.dumps(evs).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def writer(home: Path, d: Path):
    """The record, opened as an outside writer does (before the arrivals: its opening is not theirs)."""
    os.environ["ERGOSTAT_HOME"] = str(home)
    from ergostat import model as mdl
    from ergostat.store import Project
    return Project(mdl.load(d)).events


def arrive(intake: str, d: Path, home: Path, port: int | None, n: int, t0: float, events=None) -> None:
    evs = [{"type": "job.arrived", "item": f"job/{i:04d}", "source": "bench", "data": {"arrived": t0}} for i in range(n)]
    if intake == "record":
        (events or writer(home, d)).add_many(evs, new=True)
    elif intake == "collector":
        with open(d / "spool.jsonl", "a") as f:
            f.writelines(json.dumps({"event": e["type"], "item": e["item"], "data": e["data"]}) + "\n" for e in evs)
    elif intake == "push":
        push(port, home, evs)
    else:
        raise SystemExit(f"--intake {intake}: record, collector or push")


def done_count(home: Path, d: Path, last: str) -> int:
    os.environ["ERGOSTAT_HOME"] = str(home)
    from ergostat import model as mdl
    from ergostat.store import Project
    if not hasattr(done_count, "p"):
        done_count.p = Project(mdl.load(d))
    return len({e["item"] for e in done_count.p.events.query(n=None, type=last)})


def breakdown(evs: list[dict], steps: int) -> dict:
    by: dict[str, list[dict]] = {}
    for e in evs:
        if (e.get("item") or "").startswith("job/"):
            by.setdefault(e["item"], []).append(e)
    parts = {k: [] for k in ("intake", "dispatch", "spawn", "run", "release", "hop")}
    per_step = {f"step{i}": {k: [] for k in ("dispatch", "spawn", "run", "release", "hop")} for i in range(1, steps + 1)}
    e2e, ends = [], []
    t0s = []
    for _item, es in by.items():
        es.sort(key=lambda e: e["seq"])
        arrived = next((e for e in es if e["type"] == "job.arrived"), None)
        if arrived is None:
            continue
        t0 = float(arrived["data"].get("arrived") or arrived["time"])
        t0s.append(t0)
        parts["intake"].append(arrived["time"] - t0)
        entered = arrived["time"]
        released = arrived["time"]
        complete = True
        for i in range(1, steps + 1):
            takes = [e for e in es if e["type"] == "ergostat.lease.taken" and e["data"].get("block") == f"step{i}"]
            moved = next((e for e in es if e["type"] == f"job.s{i}"), None)
            if not takes or moved is None:
                complete = False
                break
            tk = takes[-1]
            ended = next((e for e in es if e["type"] == "ergostat.lease.ended" and e["data"].get("run") == tk["data"]["run"]),
                         None)
            began = float(moved["data"].get("started") or tk["time"])
            got = {"dispatch": tk["time"] - max(entered, released), "spawn": began - tk["time"], "run": moved["time"] - began,
                   "release": (ended["time"] - moved["time"]) if ended else None,
                   "hop": (ended["time"] if ended else moved["time"]) - max(entered, released)}
            for k, v in got.items():
                if v is not None:
                    parts[k].append(v)
                    per_step[f"step{i}"][k].append(v)
            entered, released = moved["time"], ended["time"] if ended else moved["time"]
        if complete:
            e2e.append(released - t0)
            ends.append(released)
    out = {"parts": {k: summary(v) for k, v in parts.items()},
           "per_step": {s: {k: summary(v) for k, v in d.items()} for s, d in per_step.items()},
           "end_to_end": summary(e2e), "completed": len(e2e), "items": len(by)}
    if ends and t0s:
        span = max(ends) - min(t0s)
        out["span"] = round(span, 3)
        out["throughput_items_per_s"] = round(len(e2e) / span, 2) if span > 0 else None
        out["hops_per_s"] = round(len(e2e) * steps / span, 2) if span > 0 else None
    return out


def synth(a, n: int) -> dict | None:
    if n > MAX_ITEMS:
        raise SystemExit(f"{n} items: at most {MAX_ITEMS}")
    alive = others()
    if alive:
        raise SystemExit(f"an earlier benchmark's engine is alive: {alive}; stop it first")
    work = Path(tempfile.mkdtemp(prefix="latbench-", dir=a.work))
    d, home = work / "proj", work / "home"
    pool = a.pool or min(n, 100)
    synth_model(d, a.steps, pool, a.intake, a.warm)
    port = a.port if a.intake == "push" or a.web else None
    log = work / "engine.log"
    proc = start_engine(d, home, port, log)
    watch = Watch(proc, a.max_threads, a.max_rss)
    try:
        startup = ready(log, proc)
        events = writer(home, d) if a.intake == "record" else None
        time.sleep(a.settle)
        t0 = time.time()
        arrive(a.intake, d, home, port, n, t0, events)
        deadline = time.monotonic() + a.timeout
        got = 0
        while time.monotonic() < deadline and proc.poll() is None:
            got = done_count(home, d, f"job.s{a.steps}")
            if got >= n:
                break
            time.sleep(0.5)
        time.sleep(1.5)                                   # the last leases end
    finally:
        watch.stop.set()
        stop_engine(proc)
        done_count.__dict__.pop("p", None)
    res = breakdown(events_of(home, d), a.steps)
    row = write(a.out, {"bench": "synth", "label": a.label, "items": n, "steps": a.steps, "pool": pool, "warm": a.warm, "intake": a.intake,
                        "startup_s": round(startup, 2), "max_threads": watch.threads, "max_rss_mb": round(watch.rss / 1e6),
                        "max_procs": watch.procs, "killed": watch.killed, "timed_out": got < n, **res})
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"kept: {work}")
    return row


# ---- ticket-factory offline

def factory(a) -> dict:
    alive = others()
    if alive:
        raise SystemExit(f"an earlier benchmark's engine is alive: {alive}; stop it first")
    work = Path(tempfile.mkdtemp(prefix="latbench-tf-", dir=a.work))
    d, home = work / "ticket-factory", work / "home"
    shutil.copytree(a.factory, d, ignore=shutil.ignore_patterns("run", "reports", "factory.conf", "__pycache__"))
    if a.auto_gates:                                      # every class promoted: no person in the loop
        f = d / "factory/actions.yaml"
        f.write_text(f.read_text().replace("gate: approve", "gate: auto"))
    env = {"TF_OFFLINE": "1", "TF_MAX_OPEN": str(a.tickets)}
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        env[f"TF_{k}"] = v
    os.environ.update(env)
    log = work / "engine.log"
    proc = start_engine(d, home, a.port, log, env)
    watch = Watch(proc, a.max_threads, a.max_rss)
    t_start = time.time()
    try:
        ready(log, proc, 120)
        deadline = time.monotonic() + a.minutes * 60
        done = 0
        while time.monotonic() < deadline and proc.poll() is None:
            done = done_count(home, d, "ticket.close")
            if done >= a.tickets:
                break
            time.sleep(2)
        time.sleep(2)
    finally:
        watch.stop.set()
        stop_engine(proc)
        done_count.__dict__.pop("p", None)
    evs = events_of(home, d)
    res = factory_breakdown(evs, t_start)
    (work / "events.json").write_text(json.dumps(evs, default=str))
    row = write(a.out, {"bench": "factory", "label": a.label, "tickets": a.tickets, "minutes": a.minutes,
                        "set": a.set or [], "auto_gates": a.auto_gates, "max_threads": watch.threads,
                        "max_procs": watch.procs, "killed": watch.killed,
                        **res})
    if a.keep:
        print(f"kept: {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    return row


def factory_breakdown(evs: list[dict], t_start: float) -> dict:
    """Per step: how long a ticket waits to be taken, each run's length and what it spent asking for gated actions
    (waiting for the approval, for the engine to run it, for the asker to see it ran), the rest of the run (the step's
    own: starting Python, loading the model for ``ergostat item``, git, the fakes), how many runs gave the ticket back
    (``Wait``) and for how long; and the share of all the tickets' time each of those took."""
    by: dict[str, list[dict]] = {}
    for e in evs:
        if (e.get("item") or "").startswith("ticket/"):
            by.setdefault(e["item"], []).append(e)
    runs_by = {e["id"]: e for e in evs if e["type"] == "agent.started"}
    ran_by = {e["causedby"]: e for e in evs if e["type"] in ("agent.ran", "agent.failed")}
    acts: dict[str, dict] = {}
    for e in evs:
        if e["type"].startswith("ergostat.action."):
            a = acts.setdefault(e["item"], {})
            a.setdefault(e["type"].rsplit(".", 1)[1], e)
    by_run: dict[str, list[dict]] = {}
    for a in acts.values():
        if "requested" in a and a["requested"]["data"].get("run"):
            by_run.setdefault(a["requested"]["data"]["run"], []).append(a)
    keys = ("wait", "run", "nacked", "hop", "spawn", "after", "acts", "act_total", "approval", "engine", "asker", "own")
    steps: dict[str, dict[str, list]] = {}
    share = {"waiting to be taken": 0.0, "put off after Wait (POLL_EVERY)": 0.0, "slot or workspace (capacity)": 0.0,
             "gated actions: the approval": 0.0, "gated actions: the engine running it": 0.0,
             "gated actions: the asker seeing it ran": 0.0, "the step's own work": 0.0}
    e2e = []
    put_off: dict[str, float] = {}                         # by the step that gave the ticket back
    for _item, es in by.items():
        es.sort(key=lambda e: e["seq"])
        found = next((e for e in es if e["type"] == "ticket.found"), None)
        free_at = found["time"] if found else es[0]["time"]
        start_at = free_at
        not_before = 0.0
        for e in es:
            if e["type"] == "ergostat.lease.taken":
                s = steps.setdefault(e["data"]["block"], {k: [] for k in keys})
                waited = e["time"] - free_at
                s["wait"].append(waited)
                off = max(0.0, min(waited, not_before - free_at)) if not_before else 0.0
                share["put off after Wait (POLL_EVERY)"] += off
                put_off[e["data"]["block"]] = put_off.get(e["data"]["block"], 0.0) + off
                share["waiting to be taken"] += waited - off
                run = e["data"]["run"]
                st = runs_by.get(run)
                if st:
                    s["spawn"].append(st["time"] - e["time"])
                    share["slot or workspace (capacity)"] += max(0.0, st["time"] - e["time"])
                r = ran_by.get(run)
                mine = by_run.get(run, [])
                tot = appr = eng = ask = 0.0
                for a in mine:
                    rq, ap, rn, dl = (a.get(k) for k in ("requested", "approved", "ran", "delivered"))
                    if rq and dl:
                        tot += dl["time"] - rq["time"]
                    if rq and ap:
                        appr += max(0.0, ap["time"] - rq["time"])
                    if ap and rn:
                        eng += max(0.0, rn["time"] - ap["time"])
                    if rn and dl:
                        ask += max(0.0, dl["time"] - rn["time"])
                s["acts"].append(len(mine))
                s["act_total"].append(tot)
                s["approval"].append(appr)
                s["engine"].append(eng)
                s["asker"].append(ask)
                share["gated actions: the approval"] += appr
                share["gated actions: the engine running it"] += eng
                share["gated actions: the asker seeing it ran"] += ask
                if r:
                    secs = float(r["data"].get("seconds") or 0)
                    s["run"].append(secs)
                    s["own"].append(max(0.0, secs - tot))
                    share["the step's own work"] += max(0.0, secs - tot)
            elif e["type"] == "ergostat.lease.ended":
                d = e["data"]
                blk = next((x["data"]["block"] for x in es if x["type"] == "ergostat.lease.taken"
                            and x["data"].get("run") == d.get("run")), "?")
                s = steps.setdefault(blk, {k: [] for k in keys})
                not_before = 0.0
                if d.get("how") == "nack":
                    s["nacked"].append(1)
                    s["after"].append(float(d.get("after") or 0))
                    not_before = e["time"] + float(d.get("after") or 0)
                else:
                    s["hop"].append(e["time"] - start_at)
                    start_at = e["time"]
                free_at = e["time"]
        close = next((e for e in es if e["type"] == "ticket.close"), None)
        if found and close:
            e2e.append(close["time"] - found["time"])
    out = {}
    for b, s in steps.items():
        out[b] = {"hop": summary(s["hop"]), "wait_to_take": summary(s["wait"]), "spawn": summary(s["spawn"]),
                  "run": summary(s["run"]), "own": summary(s["own"]), "acts_per_run": summary(s["acts"]),
                  "act_total": summary(s["act_total"]), "approval": summary(s["approval"]),
                  "engine": summary(s["engine"]), "asker": summary(s["asker"]),
                  "runs": len(s["wait"]), "nacks": len(s["nacked"]), "put_off_s": summary(s["after"])}
    whole = sum(share.values()) or 1.0
    hops = [h for s in steps.values() for h in s["hop"]]
    return {"hop_all": {**summary(hops), "mean": round(sum(hops) / len(hops), 2) if hops else None},
            "steps": out, "end_to_end": summary(e2e), "tickets_done": len(e2e), "tickets_seen": len(by),
            "time_shares": {k: {"seconds": round(v, 1), "share": round(v / whole, 3)} for k, v in share.items()},
            "put_off_by_step": {k: {"seconds": round(v, 1), "share": round(v / whole, 3)}
                                for k, v in sorted(put_off.items(), key=lambda kv: -kv[1])}}


# ---- calls from a step

def calls(a) -> dict:
    """Times what a step's helper calls cost: ``item --json``, ``event --add``, ``act`` (an auto action) and
    ``lease --renew``, from inside a real run of the bench model, through the CLI and, when the engine listens on its
    socket, through it."""
    alive = others()
    if alive:
        raise SystemExit(f"an earlier benchmark's engine is alive: {alive}; stop it first")
    work = Path(tempfile.mkdtemp(prefix="latbench-calls-", dir=a.work))
    d, home = work / "proj", work / "home"
    d.mkdir(parents=True)
    (d / "probe.py").write_text(PROBE)
    (d / "ergostat.yaml").write_text(CALLS_MODEL.replace("PY", PY))
    log = work / "engine.log"
    proc = start_engine(d, home, None, log)
    watch = Watch(proc, a.max_threads, a.max_rss)
    try:
        ready(log, proc)
        writer(home, d).add_many([{"type": "job.arrived", "item": "job/0001", "source": "bench", "data": {}}])
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not (d / "probe.json").exists():
            time.sleep(0.5)
    finally:
        watch.stop.set()
        stop_engine(proc)
    got = json.loads((d / "probe.json").read_text()) if (d / "probe.json").exists() else {"error": log.read_text()[-2000:]}
    row = write(a.out, {"bench": "calls", "label": a.label, **got})
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    return row


CALLS_MODEL = """name: latency-calls
items:
  job:
    id: job/*
    states: [s0, s1]
    on: {job.arrived: s0, job.s1: s1}
actions:
  noop:
    run: "true"
    gate: auto
blocks:
  probe:
    type: program
    run: PY probe.py
    takes: {kind: job, at: s0, to: [s1]}
    pool: 1
    actions: [noop]
"""

PROBE = """import json, os, shlex, subprocess, sys, time
cmd = shlex.split(os.environ["ERGOSTAT_CMD"])
item = os.environ["ERGOSTAT_ITEM"]
def timed(args, n=5):
    xs = []
    for i in range(n):
        t = time.perf_counter()
        r = subprocess.run(cmd + args(i), capture_output=True, text=True)
        xs.append(time.perf_counter() - t)
        if r.returncode not in (0, 1):
            return {"error": (r.stderr or r.stdout)[-500:]}
    xs.sort()
    return {"p50": round(xs[len(xs) // 2], 4), "min": round(xs[0], 4), "max": round(xs[-1], 4)}
def sock(env):
    return {**os.environ, **env}
out = {"socket": bool(os.environ.get("ERGOSTAT_SOCKET"))}
out["item"] = timed(lambda i: ["item", item, "--json"])
out["event_add"] = timed(lambda i: ["event", "--add", "job.noted", "--item", item, "--data", json.dumps({"n": i})])
out["act"] = timed(lambda i: ["act", "noop", "--json", "--wait", "5s", "--key", f"k{i}"])
out["lease_renew"] = timed(lambda i: ["lease", "--renew"])
t = time.perf_counter(); subprocess.run([sys.executable, "-c", "pass"]); out["python_start"] = round(time.perf_counter() - t, 4)
t = time.perf_counter(); subprocess.run(cmd + ["--version"], capture_output=True)
out["ergostat_version"] = round(time.perf_counter() - t, 4)
json.dump(out, open("probe.json", "w"))
print(json.dumps({"event": "job.s1"}))
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["synth", "factory", "calls", "refactory"])
    ap.add_argument("--events", type=Path, help="refactory: a kept run's events.json, broken down again")
    ap.add_argument("n", nargs="*", type=int, default=[1, 50, 100, 500])
    ap.add_argument("--label", default="")
    ap.add_argument("--steps", type=int, default=5)
    ap.add_argument("--warm", type=int, default=0, help="each step a warm daemon of this many processes (SPEC §9.7)")
    ap.add_argument("--pool", type=int, default=0, help="each step's pool (default: min(N, 100))")
    ap.add_argument("--intake", default="record", choices=["record", "collector", "push"])
    ap.add_argument("--port", type=int, default=8793)
    ap.add_argument("--web", action="store_true", help="run the page too (on --port)")
    ap.add_argument("--settle", type=float, default=2.0, help="seconds after the engine starts before the arrivals")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--work", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--max-threads", type=int, default=1500)
    ap.add_argument("--max-rss", type=float, default=6e9)
    ap.add_argument("--factory", type=Path, default=ROOT / "examples/ticket-factory")
    ap.add_argument("--tickets", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=6.0)
    ap.add_argument("--set", action="append", help="a factory setting, KEY=VALUE (TF_KEY)")
    ap.add_argument("--auto-gates", action="store_true", help="factory: every gated action promoted to auto")
    a = ap.parse_args()
    if not 8791 <= a.port <= 8799:
        raise SystemExit("ports 8791-8799 only")
    if a.what == "synth":
        for n in a.n:
            synth(a, n)
    elif a.what == "factory":
        factory(a)
    elif a.what == "refactory":
        print(json.dumps(factory_breakdown(json.loads(a.events.read_text()), 0.0), indent=1))
    else:
        calls(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
