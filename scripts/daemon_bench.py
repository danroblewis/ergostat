"""Process starts against a sensor daemon (docs/RUNTIME.md): N command sensors every 3 minutes, read as a process per
reading or by one shared daemon. Watchdogged: killed past 1,500 threads or 6 GB.

    uv run python scripts/daemon_bench.py 20 170 --mode process|daemon --minutes 6.5 --work DIR"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from scale_bench import PY, ROOT, pct, ps

SENSE = "import sys, time\nopen('starts.log', 'a').write('x\\n')\nprint(42 + time.time() % 7)\n"
DAEMON = """import json, sys, time
open('starts.log', 'a').write('d\\n')
for line in sys.stdin:
    m = json.loads(line)
    if m.get("op") == "read":
        print(json.dumps({"reading": 42 + time.time() % 7, "request": m["request"]}), flush=True)
    elif m.get("op") == "stop":
        break
"""
THREADS, MEMORY_MB = 1500, 6 * 1024


def model(d: Path, n: int, mode: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "sense.py").write_text(SENSE)
    (d / "sensed.py").write_text(DAEMON)
    (d / "starts.log").write_text("")
    how = "daemon: sensors" if mode == "daemon" else f"run: {sys.executable} sense.py"
    lines = [f"name: bench{n}{mode}", "stocks:"]
    for i in range(n):
        lines += [f"  s{i}:", "    unit: things", f"    sensor: {{{how}, every: 3m}}"]
    lines += ["goals:"] + [f"  g{i}: {{stock: s{i}, hold: '<= 100'}}" for i in range(n)]
    if mode == "daemon":
        lines += ["daemons:", f"  sensors: {{run: {sys.executable} sensed.py, concurrency: {n}}}"]
    (d / "ergostat.yaml").write_text("\n".join(lines) + "\n")


def run(work: Path, n: int, mode: str, minutes: float) -> dict:
    d = work / f"{mode}{n}"
    model(d, n, mode)
    timings = work / f"timings-{mode}{n}.json"
    timings.unlink(missing_ok=True)
    env = {**os.environ, "ERGOSTAT_HOME": str(work / f"home-{mode}{n}"), "ERGOSTAT_AI": "false",
           "ERGOSTAT_TIMINGS": str(timings)}
    log = open(work / f"engine-{mode}{n}.log", "w")
    proc = subprocess.Popen([PY, str(ROOT / "scripts/scale_probe.py"), "-C", str(d), "run", "--foreground", "--no-web"],
                            cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    t0, samples, killed = time.time(), [], None
    while time.time() < t0 + minutes * 60 and proc.poll() is None:
        time.sleep(5)
        s = ps(proc.pid)
        samples.append(s)
        if s["threads"] > THREADS or (s["rss_mb"] or 0) + s["children_rss_mb"] > MEMORY_MB:
            killed = f"watchdog: {s['threads']} threads, {(s['rss_mb'] or 0) + s['children_rss_mb']:.0f} MB"
            os.killpg(proc.pid, signal.SIGKILL)
            break
    wall = time.time() - t0
    own = samples[-1]["cpu_s"] if samples else None
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
    _, _, ru = os.wait4(proc.pid, 0)                     # the engine and every child it waited for
    log.close()
    starts = len((d / "starts.log").read_text().splitlines())
    count = "from ergostat import model; from ergostat.store import Project; print(Project(model.load()).measurements.count())"
    readings = int(subprocess.run([PY, "-c", count], cwd=d, env=env, capture_output=True, text=True).stdout or 0)
    out = {"n": n, "mode": mode, "minutes": round(wall / 60, 2), "readings": readings, "starts": starts,
           "starts_per_min": round(starts / (3 * (int(wall / 180) + 1)), 1),   # (by the rounds, one every 3 minutes)
           "cpu_total_s": round(ru.ru_utime + ru.ru_stime, 2),
           "cpu_engine_s": own, "cpu_cores": round((ru.ru_utime + ru.ru_stime) / wall, 4),
           "engine_rss_mb_max": max((s["rss_mb"] or 0 for s in samples), default=None),
           "children_rss_mb_max": max((s["children_rss_mb"] for s in samples), default=None),
           "threads_max": max((s["threads"] for s in samples), default=None), **({"killed": killed} if killed else {})}
    if own is not None:
        out["cpu_children_s"] = round(out["cpu_total_s"] - own, 2)
    if timings.exists():                                 # the engine's pass, and its loop's batch (scale_probe.py)
        t = json.loads(timings.read_text())
        xs = t["samples"].get("evaluate") or []
        out["pass_p50_ms"], out["pass_p95_ms"] = (round(1000 * (pct(xs, q) or 0), 2) for q in (0.5, 0.95))
        out["pass_max_ms"] = round(1000 * max(xs or [0]), 2)
        out["batch_max_ms"] = round(1000 * (t["parts"].get("batch") or {}).get("max", 0), 1)
    with open(work / "daemon-results.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    print(json.dumps(out), flush=True)
    return out


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("n", type=int, nargs="+")
    a.add_argument("--mode", choices=("process", "daemon"), default="process")
    a.add_argument("--minutes", type=float, default=6.5)
    a.add_argument("--work", type=Path, default=Path("/tmp/daemon-bench"))
    o = a.parse_args()
    o.work.mkdir(parents=True, exist_ok=True)
    for n in o.n:
        if run(o.work, n, o.mode, o.minutes).get("killed"):
            break                                        # past the watchdog: no larger N


if __name__ == "__main__":
    main()
