"""Measure ergostat at scale on models from scripts/scale_model.py (docs/proposals/scale.md).

    uv run python scripts/scale_bench.py check   10 100 300 1000      # load and compile: time, peak memory, size
    uv run python scripts/scale_bench.py phases  10 100 300 1000      # check's parts: compile, findings, extreme conditions
    uv run python scripts/scale_bench.py tick    10 100 300 1000      # the engine's pass alone, on one thread
    uv run python scripts/scale_bench.py loops   10 100 300 1000      # loop finding: time, loops found, blow-up
    uv run python scripts/scale_bench.py engine  10 --minutes 10      # the engine, headless, with timings
    uv run python scripts/scale_bench.py web     10                   # the page on that record: API and Playwright
    uv run python scripts/scale_bench.py model   10                   # the improver's and the judge's passes
    uv run python scripts/scale_bench.py chart                        # docs/proposals/img/scale-*.png

Models go to WORK/n<N> (WORK: --work, default /tmp/scale), each run's record to WORK/home<N>; every result is
appended to WORK/results.jsonl as one line ({"measure", "n", "load", ...}) with the load average when it was taken,
so a measurement repeated when the machine is quieter sits beside the first. Ports: 8791-8799 only (8790 is the
owner's). No AI: the models' blocks are programs and people, and ERGOSTAT_AI is set to `false` as a guard."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
PORTS = range(8791, 8800)


def load() -> float:
    return round(os.getloadavg()[0], 1)


def record(work: Path, measure: str, n: int, **kw) -> dict:
    row = {"measure": measure, "n": n, "at": time.time(), "load": load(), **kw}
    with open(work / "results.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row)[:600], flush=True)
    return row


def env_for(work: Path, n: int, **kw) -> dict:
    return {**os.environ, "ERGOSTAT_HOME": str(work / f"home{n}"), "ERGOSTAT_AI": "false", **kw}


def model(work: Path, n: int, fresh: bool = False) -> Path:
    d = work / f"n{n}"
    if fresh or not (d / "ergostat.yaml").exists():
        subprocess.run([PY, str(ROOT / "scripts/scale_model.py"), str(n), str(d)], check=True, capture_output=True)
    return d


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


# ---- load and compile


def timed_l(cmd: list[str], cwd: Path, env: dict, timeout: float) -> dict:
    """A command under /usr/bin/time -l: its wall time, peak memory and output (or that it ran out of time)."""
    t = time.time()
    try:
        p = subprocess.run(["/usr/bin/time", "-l", *cmd], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"timeout": timeout, "wall": round(time.time() - t, 2)}
    rss = re.search(r"(\d+)\s+maximum resident set size", p.stderr)
    return {"wall": round(time.time() - t, 2), "rss_mb": round(int(rss.group(1)) / 2**20, 1) if rss else None,
            "exit": p.returncode, "out": p.stdout, "err": p.stderr[-2000:]}


PHASES = r'''
import json, sys, time, resource
from pathlib import Path
def rss():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20, 1)
def say(**kw):
    print(json.dumps(kw), flush=True)
t = time.time()
from ergostat.spec.load import load as load_doc, find
from ergostat.spec.compile import compile_doc
doc = load_doc(find(Path(sys.argv[1])))
say(phase="yaml", s=round(time.time() - t, 2), rss_mb=rss())
t = time.time(); spec, problems = compile_doc(doc)
say(phase="compile", s=round(time.time() - t, 2), rss_mb=rss())
from ergostat.spec import findings
t = time.time(); got = findings.find(spec, extremes=False)
say(phase="findings", s=round(time.time() - t, 2), rss_mb=rss(), found=len(got))
from ergostat.numbers import extremes, simulate as sim
t = time.time(); pl = sim.plan(spec); t_plan = time.time() - t
conds = extremes.conditions(spec, pl, None)
t = time.time(); run = extremes._run(spec, pl, conds[0], None); t_run = time.time() - t
say(phase="extremes-one", plan_s=round(t_plan, 3), replay_s=round(t_run, 3), conditions=len(conds),
    estimate_s=round(len(conds) * (t_plan + t_run), 1), rss_mb=rss())
t = time.time(); got = extremes.failures(spec)
say(phase="extremes", s=round(time.time() - t, 2), rss_mb=rss(), found=len(got))
'''


def cmd_phases(a) -> None:
    """check's parts, one at a time: the YAML read, the compile, the findings, and the extreme-conditions tests (with
    one condition's cost and the number of conditions first, so an estimate is there when the whole runs out of time)."""
    for n in a.n:
        d = model(a.work, n, a.fresh)
        got: dict = {}
        try:
            p = subprocess.run([PY, "-c", PHASES, str(d)], env=env_for(a.work, n), capture_output=True, text=True,
                               timeout=a.timeout)
            out = p.stdout
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            got["timeout"] = a.timeout
        for line in out.splitlines():
            x = json.loads(line)
            got[x.pop("phase")] = x
        record(a.work, "check-phases", n, **got)


def cmd_check(a) -> None:
    for n in a.n:
        d = model(a.work, n, a.fresh)
        size = sum(f.stat().st_size for f in d.rglob("*.yaml"))
        lines = sum(len(f.read_text().splitlines()) for f in d.rglob("*.yaml"))
        got = timed_l([PY, "-m", "ergostat", "check"], d, env_for(a.work, n), a.timeout)
        head = (got.pop("out", "") or "").splitlines()[:1]
        counts = {k: int(v) for v, k in re.findall(r"([\d,]+) (stocks|flows|auxiliaries|sensors|goals|blocks|agents|files)",
                                                   head[0].replace(",", "") if head else "")}
        got.pop("err", None)
        record(a.work, "check", n, yaml_bytes=size, yaml_lines=lines, **counts, **got)


# ---- loop finding

LOOPS = r'''
import json, sys, time
from pathlib import Path
t0 = time.time()
from ergostat import model as mdl
m = mdl.load(Path(sys.argv[1]))
spec = m.spec
t_load = time.time() - t0
from ergostat.spec import causal
t = time.time(); ls = causal.links(spec); t_links = time.time() - t
t = time.time(); capped = causal.loops(spec); t_capped = time.time() - t
out = {"load_s": round(t_load, 2), "links": len(ls), "links_s": round(t_links, 3), "loops_capped": len(capped),
       "loops_capped_s": round(t_capped, 3), "control_loops": len(spec.goals),
       "capped_longest": max((len(l.parts) for l in capped), default=0)}
print(json.dumps(out), flush=True)

class Stop(Exception):
    pass

class Counter(list):
    """found, for causal._from: counts the cycles without keeping them, and stops at the deadline."""
    def __init__(self, deadline):
        self.n, self.deadline, self.lengths, self.marks = 0, deadline, {}, []
    def append(self, cyc):
        self.n += 1
        self.lengths[len(cyc)] = self.lengths.get(len(cyc), 0) + 1
        if self.n & 1023 == 0:
            now = time.time()
            self.marks.append((round(now - t1, 2), self.n))
            if now > self.deadline:
                raise Stop
    def __len__(self):
        return 0

limit = float(sys.argv[2])
nxt = {}
for x in ls:
    nxt.setdefault(x.source, []).append(x)
for v in nxt.values():
    v.sort(key=lambda x: x.target)
nodes = sorted({x.source for x in ls} | {x.target for x in ls})
t1 = time.time()
c = Counter(t1 + limit)
done_starts = 0
try:
    for start in nodes:
        causal._from(start, ls, nxt, 10**6, 10**12, c)
        done_starts += 1
    finished = True
except Stop:
    finished = False
print(json.dumps({"all_loops": c.n, "all_finished": finished, "all_s": round(time.time() - t1, 2),
                  "starts_done": done_starts, "starts": len(nodes), "by_length": c.lengths, "marks": c.marks[-40:]}))
'''


TICK = r'''
import cProfile, io, json, pstats, sys, time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
from ergostat.spec.engine import Engine
t = time.time(); p = Project(mdl.load(Path(sys.argv[1]))); t_load = time.time() - t
e = Engine(p, say=lambda s: None)
e.start = lambda b, why: None                  # nothing runs: the pass alone
e.dispatch.take = lambda *a, **k: None
times, parts = [], {}
for i in range(int(sys.argv[2])):
    t = time.perf_counter(); e.measure(); m = time.perf_counter() - t
    t = time.perf_counter(); e.evaluate(); times.append(time.perf_counter() - t)
    parts.setdefault("measure", []).append(m)
t = time.perf_counter(); e.dispatch.tick(); t_tick = time.perf_counter() - t
t = time.perf_counter(); e.dispatch.watch(); t_watch = time.perf_counter() - t
due = sum(1 for _ in e.machines)
t = time.perf_counter(); [e.command_of(b) for b in e.machines]; t_cmd = time.perf_counter() - t
pr = cProfile.Profile(); pr.enable(); e.evaluate(); pr.disable()
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(8)
times.sort()
print(json.dumps({"load_s": round(t_load, 1), "evaluate_ms": round(1000 * times[len(times) // 2], 2),
                  "evaluate_min_ms": round(1000 * times[0], 2), "measure_ms": round(1000 * sorted(parts["measure"])[len(times) // 2], 2),
                  "command_of_all_ms": round(1000 * t_cmd, 2), "machines": due, "dispatch_tick_ms": round(1000 * t_tick, 2),
                  "dispatch_watch_ms": round(1000 * t_watch, 2), "profile": s.getvalue()[-2500:]}))
'''


def cmd_tick(a) -> None:
    """The engine's pass alone, on one thread, nothing contending: its cost against N (the engine measured live
    pays it after every reading, under one lock)."""
    for n in a.n:
        d = model(a.work, n)
        home = a.work / f"tick{n}"
        try:
            p = subprocess.run([PY, "-c", TICK, str(d), "15"], env={**env_for(a.work, n), "ERGOSTAT_HOME": str(home)},
                               capture_output=True, text=True, timeout=a.timeout)
            got = json.loads(p.stdout.splitlines()[-1]) if p.stdout.strip() else {"error": p.stderr[-800:]}
        except subprocess.TimeoutExpired:
            got = {"timeout": a.timeout}
        record(a.work, "tick", n, **got)


def cmd_loops(a) -> None:
    for n in a.n:
        d = a.work / a.variant if a.variant else model(a.work, n, a.fresh)
        try:
            p = subprocess.run([PY, "-c", LOOPS, str(d), str(a.limit)], env=env_for(a.work, n), capture_output=True,
                               text=True, timeout=a.limit + 900)
            got = {}
            for line in p.stdout.splitlines():
                got.update(json.loads(line))
            if p.returncode:
                got["error"] = p.stderr[-800:]
        except subprocess.TimeoutExpired:
            got = {"timeout": a.limit + 900}
        record(a.work, "loops", n, **got, **({"variant": a.variant} if a.variant else {}))


# ---- the engine


def ps(pid: int) -> dict:
    """The process's RSS and CPU seconds, and its descendants'."""
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss=,time="], capture_output=True, text=True).stdout
    rows = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) == 4:
            rows[int(f[0])] = (int(f[1]), int(f[2]), f[3])

    def secs(t: str) -> float:
        m, s = t.split(":")[-2:]
        h = t.split(":")[0] if t.count(":") == 2 else 0
        return int(h) * 3600 + int(m) * 60 + float(s)
    kids, todo = [], [pid]
    while todo:
        x = todo.pop()
        for k, (pp, _, _) in rows.items():
            if pp == x:
                kids.append(k)
                todo.append(k)
    me = rows.get(pid)
    threads = subprocess.run(["ps", "-M", "-p", str(pid)], capture_output=True, text=True).stdout.count("\n") - 1
    return {"rss_mb": round(me[1] / 1024, 1) if me else None, "cpu_s": secs(me[2]) if me else None, "threads": threads,
            "children": len(kids), "children_rss_mb": round(sum(rows[k][1] for k in kids) / 1024, 1)}


def dir_mb(d: Path) -> float:
    return round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 2**20, 2)


def state_of(work: Path, n: int) -> Path | None:
    got = list((work / f"home{n}").glob("*/repo.json"))
    return got[0].parent if got else None


SEQ = "import sys; from pathlib import Path; from ergostat.storage import Storage, open_events; " \
      "print(open_events(Storage(), Path(sys.argv[1])).last_seq())"


def events_now(sd: Path | None) -> int | None:
    """The record's newest event's number, read through ergostat's own store (no model loaded)."""
    if sd is None:
        return None
    try:
        p = subprocess.run([PY, "-c", SEQ, str(sd)], capture_output=True, text=True, timeout=60)
        return int(p.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        return None


def cmd_engine(a) -> None:
    for n in a.n:
        d = model(a.work, n, a.fresh)
        home = a.work / f"home{n}"
        if home.exists() and not a.keep:
            subprocess.run(["rm", "-rf", str(home)])
        (d / "run").exists() and subprocess.run(["rm", "-rf", str(d / "run")])
        timings = a.work / f"timings{n}.json"
        timings.unlink(missing_ok=True)
        log = open(a.work / f"engine{n}.log", "w")
        t0 = time.time()
        proc = subprocess.Popen([PY, str(ROOT / "scripts/scale_probe.py"), "-C", str(d), "run", "--foreground", "--no-web"],
                                cwd=d, env=env_for(a.work, n, ERGOSTAT_TIMINGS=str(timings)), stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        samples, started_at = [], None
        end = t0 + a.minutes * 60
        while time.time() < end and proc.poll() is None:
            time.sleep(a.every)
            sd = state_of(a.work, n)
            if started_at is None and "running " in (a.work / f"engine{n}.log").read_text():
                started_at = round(time.time() - t0, 1)
            s = {"t": round(time.time() - t0, 1), "load": load(), **ps(proc.pid), "events": events_now(sd),
                 "state_mb": dir_mb(sd) if sd else None}
            samples.append(s)
            print(json.dumps(s), flush=True)
        alive = proc.poll() is None
        if alive:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(60)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        log.close()
        sd = state_of(a.work, n)
        res = {"minutes": a.minutes, "survived": alive, "exit": proc.returncode, "started_after_s": started_at,
               "samples": samples, **summarise(sd, timings, samples, started_at or 0)}
        record(a.work, "engine", n, **res)


def summarise(sd: Path | None, timings: Path, samples: list[dict], started: float) -> dict:
    out: dict = {}
    if timings.exists():
        t = json.loads(timings.read_text())
        span = max(1.0, t["at"] - t["since"])
        out["parts"] = {k: {**v, "cpu_per_s": round(v["cpu"] / span, 4), "wall_per_s": round(v["wall"] / span, 4)}
                        for k, v in t["parts"].items()}
        for k, xs in t["samples"].items():
            out[f"{k}_p50_ms"] = round(1000 * (pct(xs, 0.5) or 0), 2)
            out[f"{k}_p95_ms"] = round(1000 * (pct(xs, 0.95) or 0), 2)
            out[f"{k}_max_ms"] = round(1000 * max(xs or [0]), 2)
    run = [s for s in samples if s["t"] >= started]
    if len(run) >= 2 and run[-1].get("events") is not None and run[0].get("events") is not None:
        dt = run[-1]["t"] - run[0]["t"]
        out["events_per_s"] = round((run[-1]["events"] - run[0]["events"]) / dt, 2)
        out["state_mb_per_h"] = round((run[-1]["state_mb"] - run[0]["state_mb"]) * 3600 / dt, 1)
        cpu = [s for s in run if s.get("cpu_s") is not None]
        out["cpu_cores"] = round((cpu[-1]["cpu_s"] - cpu[0]["cpu_s"]) / dt, 3) if len(cpu) >= 2 else None
    rss = [s["rss_mb"] for s in samples if s.get("rss_mb")]
    out["rss_mb_end"], out["rss_mb_max"] = (rss[-1], max(rss)) if rss else (None, None)
    out["children_max"] = max((s["children"] for s in samples), default=0)
    out["threads_max"] = max((s.get("threads") or 0 for s in samples), default=0)
    if sd is not None:
        out.update(record_stats(sd))
        out["final_state_mb"] = dir_mb(sd)                # after the stop: the write-ahead logs folded in
        if out.get("record_span_s"):
            out["final_mb_per_h"] = round(out["final_state_mb"] * 3600 / out["record_span_s"], 1)
    return out


STATS = r'''
import json, sys
from pathlib import Path
from ergostat.storage import Storage, open_events
ev = open_events(Storage(), Path(sys.argv[1]))
taken = ev.query(n=None, type="ergostat.lease.taken")
cause = {}
for t in taken:
    if t.get("causedby") and (t.get("data") or {}).get("attempt") == 1:
        c = ev.get(t["causedby"])
        if c:
            cause[t["id"]] = t["time"] - c["time"]
every = ev.query(n=None)
types = {}
for e in every:
    types[e["type"]] = types.get(e["type"], 0) + 1
items = {e["item"] for e in every if (e.get("item") or "").startswith("w") and "/" in e["item"]}
done = sum(1 for e in every if e["type"].endswith(".done") or e["type"].endswith("-done"))
print(json.dumps({"lat": sorted(cause.values()), "types": dict(sorted(types.items(), key=lambda x: -x[1])[:25]),
                  "events": len(every), "first": min((e["time"] for e in every), default=0),
                  "last": max((e["time"] for e in every), default=0), "items": len(items), "done": done}))
'''


def record_stats(sd: Path) -> dict:
    """From the record (through ergostat's own store): the dispatch latency (an item reaching a state a block takes
    from, to its first lease there taken: the event that moved it, and the lease's ``causedby``), the items, the
    readings, and the stores' sizes."""
    try:
        p = subprocess.run([PY, "-c", STATS, str(sd)], capture_output=True, text=True, timeout=1800)
        r = json.loads(p.stdout)
    except (subprocess.TimeoutExpired, ValueError) as e:
        return {"stats_error": str(e)[:200]}
    lat = r["lat"]
    out = {"dispatch_n": len(lat), "dispatch_p50_s": round(pct(lat, 0.5), 2) if lat else None,
           "dispatch_p95_s": round(pct(lat, 0.95), 2) if lat else None, "dispatch_max_s": round(max(lat), 2) if lat else None,
           "record_events": r["events"], "record_span_s": round(r["last"] - r["first"], 1), "event_types": r["types"],
           "items_seen": r["items"], "items_moves_done": r["done"],
           "events_mb": dir_mb(sd / "events") if (sd / "events").is_dir() else None,
           "items_index_mb": dir_mb(sd / "items") if (sd / "items").is_dir() else None,
           "measurements_db_mb": round((sd / "measurements.db").stat().st_size / 2**20, 2)}
    try:
        m = sqlite3.connect(f"file:{sd / 'measurements.db'}?mode=ro", uri=True, timeout=30)
        out["readings"] = m.execute("select count(*) from samples").fetchone()[0]
        out["series"] = m.execute("select count(distinct series) from samples").fetchone()[0]
    except sqlite3.Error as e:
        out["readings_error"] = str(e)
    return out


# ---- the page


def free_port() -> int:
    import socket
    for p in PORTS:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit("no port free in 8791-8799")


def get(url: str, timeout: float) -> tuple[float, int, int]:
    t = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read()
            return round(time.time() - t, 3), len(body), r.status
    except Exception as e:                                     # a timeout or a server error, said as such
        return round(time.time() - t, 3), 0, getattr(e, "code", -1)


def serve(work: Path, n: int, port: int) -> subprocess.Popen:
    d = model(work, n)
    proc = subprocess.Popen([PY, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], cwd=d,
                            env=env_for(work, n), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    for _ in range(600):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/static/index.html", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    return proc


APIS = [("status", "status"), ("graph", "graph"), ("graph-dynamics", "graph?view=dynamics"),
        ("graph-blocks", "graph?view=blocks"), ("graph-system", "graph?view=dynamics&system=sys-001"),
        ("graph-opened", "graph?view=dynamics&open=org,area-01,sys-001"),
        ("graph-all-open", "graph?view=dynamics&open=*"), ("loops", "loops"), ("items", "items"),
        ("exercised", "exercised")]
PAGES = [("diagram", "/diagram", True), ("diagram-system", "/diagram?system=sys-001", True),
         ("diagram-opened", "/diagram?open=org,area-01,sys-001", True), ("blocks", "/diagram?view=blocks", True),
         ("diagram-all-open", "/diagram?open=*", True),
         ("loops", "/loops", False), ("items", "/items", False), ("check", "/check", False)]
READY = ("() => typeof S !== 'undefined' && S.layout && S.graphSig && document.querySelectorAll('svg.canvas g.node').length > 0")
ROUTED = ("() => typeof S !== 'undefined' && S.layout && S.graphSig && !S.layout.routing && "
          "document.querySelectorAll('svg.canvas g.node').length > 0")


def cmd_web(a) -> None:
    for n in a.n:
        port = free_port()
        proc = serve(a.work, n, port)
        base = f"http://127.0.0.1:{port}"
        try:
            for name, path in APIS:
                t, size, code = get(f"{base}/api/{path}", a.timeout)
                t2 = get(f"{base}/api/{path}", a.timeout)[0] if code == 200 else None     # again: what a poll costs
                record(a.work, "api", n, api=name, seconds=t, again_s=t2, bytes=size, status=code,
                       server=ps(proc.pid))
            if not a.no_browser:
                browse(a, n, base, proc)
        finally:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(30)


def browse(a, n: int, base: str, proc) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        for name, path, diagram in PAGES:
            ctx = b.new_context(viewport={"width": 1600, "height": 1000})
            pg = ctx.new_page()
            sizes: list[int] = []
            pg.on("response", lambda r, sizes=sizes: sizes.append(int(r.headers.get("content-length") or 0)) if "/api/" in r.url else None)
            row: dict = {"page": name}
            t = time.time()
            try:
                pg.goto(base + path, wait_until="load", timeout=a.timeout * 1000)
                row["load_s"] = round(time.time() - t, 2)
                if diagram:
                    pg.wait_for_function(READY, timeout=a.timeout * 1000, polling=100)
                    row["drawn_s"] = round(time.time() - t, 2)
                    pg.wait_for_function(ROUTED, timeout=a.timeout * 1000, polling=250)
                    row["routed_s"] = round(time.time() - t, 2)
                    row["shapes"] = pg.evaluate("() => [S.graph.nodes.length, S.graph.edges.length]")
                else:
                    pg.wait_for_load_state("networkidle", timeout=a.timeout * 1000)
                    pg.wait_for_function("() => document.querySelector('#main') && document.querySelector('#main').children.length > 0",
                                         timeout=a.timeout * 1000)
                    row["drawn_s"] = round(time.time() - t, 2)
                row["dom_nodes"] = pg.evaluate("() => document.getElementsByTagName('*').length")
                row["heap_mb"] = round(pg.evaluate("() => performance.memory ? performance.memory.usedJSHeapSize : 0") / 2**20, 1)
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                row["gave_up_s"] = round(time.time() - t, 2)
            row["api_bytes"] = sum(sizes)
            record(a.work, "page", n, **row, server=ps(proc.pid))
            ctx.close()
        b.close()


# ---- modelling


def cmd_model(a) -> None:
    for n in a.n:
        d = model(a.work, n)
        e = env_for(a.work, n)
        for name, args in (("fit", ["fit", "--json"]), ("proposals", ["proposals", "--json"]), ("judge", ["judge", "--json"]),
                           ("measure-fit", ["measure", "ergostat.model.fit"])):
            got = timed_l([PY, "-m", "ergostat", *args], d, e, a.timeout)
            out = got.pop("out", "") or ""
            got["out_bytes"] = len(out)
            got["err"] = (got.get("err") or "")[-300:] if got.get("exit") else None
            record(a.work, "modelling", n, step=name, **got)


# ---- charts


def rows(work: Path) -> list[dict]:
    return [json.loads(x) for x in (work / "results.jsonl").read_text().splitlines() if x.strip()]


def cmd_chart(a) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                         "lines.color": "black", "axes.prop_cycle": plt.cycler(color=["black"])})
    rs = rows(a.work)
    img = ROOT / "docs/proposals/img"
    img.mkdir(parents=True, exist_ok=True)
    styles = ["-o", "--s", ":^", "-.v", "-D", "--x", ":+"]

    def best(measure: str, key, where=lambda r: True) -> dict[int, float]:
        """Per N, the measurement taken at the lowest load (a repeat when quieter wins)."""
        got: dict[int, tuple[float, float]] = {}
        for r in rs:
            if r["measure"] == measure and not r.get("variant") and where(r):
                v = key(r)
                if v is None:
                    continue
                if r["n"] not in got or r["load"] < got[r["n"]][0]:
                    got[r["n"]] = (r["load"], v)
        return {n: v for n, (_, v) in sorted(got.items())}

    def chart(name: str, title: str, ylabel: str, series: dict[str, dict[int, float]], logy: bool = True, note: str = ""):
        fig, ax = plt.subplots(figsize=(6, 3.6))
        for (label, pts), st in zip(series.items(), styles, strict=False):
            if pts:
                ax.plot(list(pts), list(pts.values()), st, color="black", label=label, markersize=4, linewidth=1)
        ax.set_xscale("log")
        if logy:
            ax.set_yscale("log")
        ax.set_xlabel("workflows (N)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, which="major", color="0.85", linewidth=0.5)
        if len(series) > 1:
            ax.legend(frameon=False)
        if note:
            fig.text(0.01, 0.01, note, fontsize=7, color="0.3")
        fig.tight_layout()
        fig.savefig(img / f"scale-{name}.png", dpi=150)
        plt.close(fig)

    chart("check", "ergostat check", "seconds", {"wall time": best("check", lambda r: r.get("wall") if not r.get("timeout") else None)})
    chart("check-memory", "ergostat check: peak memory", "MB", {"peak RSS": best("check", lambda r: r.get("rss_mb"))})
    chart("loops", "Feedback loops", "seconds", {
        "find (capped at 300)": best("loops", lambda r: r.get("loops_capped_s")),
        "enumerate all (time limit)": best("loops", lambda r: r.get("all_s"))})
    chart("loops-count", "Feedback loops found", "loops", {
        "simple cycles (all, or at the time limit)": best("loops", lambda r: r.get("all_loops")),
        "reported (cap 300)": best("loops", lambda r: r.get("loops_capped")),
        "control loops (goals)": best("loops", lambda r: r.get("control_loops"))})
    chart("tick", "Engine pass (evaluate)", "ms", {
        "p50": best("engine", lambda r: r.get("evaluate_p50_ms")), "p95": best("engine", lambda r: r.get("evaluate_p95_ms"))})
    parts = sorted({k for r in rs if r["measure"] == "engine" for k in (r.get("parts") or {})})
    chart("engine-cpu", "Engine CPU by part", "CPU seconds per second", {
        k: best("engine", lambda r, k=k: (r.get("parts") or {}).get(k, {}).get("cpu_per_s") or None) for k in
        [p for p in ("evaluate", "sensor.items", "fold.catch_up", "dispatch.tick", "dispatch.watch", "run_block", "judge") if p in parts]})
    chart("engine-rss", "Engine memory", "MB", {"RSS (max)": best("engine", lambda r: r.get("rss_mb_max"))})
    chart("dispatch", "Dispatch latency: item ready to lease taken", "seconds", {
        "p50": best("engine", lambda r: r.get("dispatch_p50_s")), "p95": best("engine", lambda r: r.get("dispatch_p95_s"))})
    chart("storage", "Storage growth", "MB per hour", {"state directory": best("engine", lambda r: r.get("state_mb_per_h"))})
    chart("api", "API answer time", "seconds", {
        k: best("api", lambda r: r.get("seconds") if r.get("status") == 200 else None, lambda r, k=k: r.get("api") == k)
        for k in ("status", "graph-dynamics", "graph-blocks", "graph-system", "loops", "items")})
    chart("api-size", "API answer size", "MB", {
        k: best("api", lambda r: (r.get("bytes") or 0) / 2**20 or None, lambda r, k=k: r.get("api") == k)
        for k in ("status", "graph-dynamics", "graph-blocks", "loops", "items")})
    chart("pages", "Pages: until drawn", "seconds", {
        k: best("page", lambda r: r.get("drawn_s"), lambda r, k=k: r.get("page") == k)
        for k in ("diagram", "diagram-system", "diagram-opened", "blocks", "loops", "items", "check")})
    chart("modelling", "Modelling passes", "seconds", {
        k: best("modelling", lambda r: r.get("wall") if not r.get("timeout") else None, lambda r, k=k: r.get("step") == k)
        for k in ("fit", "proposals", "judge", "measure-fit")})
    print("charts in", img)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=["check", "phases", "tick", "loops", "engine", "web", "model", "chart"])
    ap.add_argument("n", type=int, nargs="*")
    ap.add_argument("--work", type=Path, default=Path("/tmp/scale"))
    ap.add_argument("--fresh", action="store_true", help="generate the models again")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--limit", type=float, default=120, help="loops: seconds to enumerate every loop for")
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--every", type=float, default=15)
    ap.add_argument("--keep", action="store_true", help="engine: keep the record from the last run")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--variant", help="loops: the model in WORK/VARIANT (scale_model.py --handoff ...) instead of WORK/n<N>")
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    {"check": cmd_check, "phases": cmd_phases, "tick": cmd_tick, "loops": cmd_loops, "engine": cmd_engine, "web": cmd_web,
     "model": cmd_model, "chart": cmd_chart}[a.what](a)


if __name__ == "__main__":
    main()
