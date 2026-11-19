"""Run a test suite under a watchdog: sample its whole process tree (the pytest workers, the engines and page
servers they start, the browsers) and kill it past the machine's limits; report the peaks.

    uv run python scripts/suite_watch.py [--threads 1500] [--rss-mb 6144] [--worker-mb 2048] [--every 1] -- CMD ...

A process is the run's if it descends from CMD or carries the run's tag in its environment
(``ERGOSTAT_SUITE_WATCH``), so a server a test left behind, reparented when its parent died, still counts, and is
stopped (by its pid) when CMD ends. ``--worker-mb`` caps each pytest-xdist worker's own tree (the worker, its browser,
its servers): one past it is killed alone, and xdist reports its test as crashed. Prints one JSON line at the end;
exits with CMD's code, or 3 if the whole run was killed."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid

TAG = "ERGOSTAT_SUITE_WATCH"
WORKER = "exec(eval(sys.stdin.readline()))"     # (how execnet starts an xdist worker)


def members(root: int, tag: str) -> tuple[dict[int, int], list[set[int]]]:
    """The run's processes (pid -> RSS in KB), and each xdist worker's own tree."""
    out = subprocess.run(["ps", "-A", "-E", "-ww", "-o", "pid=,ppid=,rss=,command="], capture_output=True, text=True).stdout
    rows, kids = {}, {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        pid, ppid, rss, cmd = int(parts[0]), int(parts[1]), int(parts[2]), parts[3] if len(parts) > 3 else ""
        rows[pid] = (rss, f"{TAG}={tag}" in cmd, WORKER in cmd)
        kids.setdefault(ppid, []).append(pid)

    def tree(top: int) -> set[int]:
        mine, todo = set(), [top]
        while todo:
            p = todo.pop()
            if p in rows and p not in mine:
                mine.add(p)
                todo.extend(kids.get(p, []))
        return mine
    mine = tree(root) | {p for p, (_, tagged, _) in rows.items() if tagged}
    return {p: rows[p][0] for p in mine}, [tree(p) for p in mine if rows[p][2]]


def threads(pids) -> int:
    if not pids:
        return 0
    out = subprocess.run(["ps", "-M", "-p", ",".join(map(str, pids))], capture_output=True, text=True).stdout
    return max(0, len(out.splitlines()) - 1)


def kill(pids, sig=signal.SIGKILL):
    for p in pids:
        try:
            os.kill(p, sig)
        except OSError:
            pass


def _interrupted(*_):
    raise KeyboardInterrupt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=1500)
    ap.add_argument("--rss-mb", type=int, default=6144)
    ap.add_argument("--worker-mb", type=int, default=2048)
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    tag = uuid.uuid4().hex[:12]
    t0 = time.time()
    proc = subprocess.Popen(cmd, env={**os.environ, TAG: tag})
    peak = {"threads": 0, "rss_mb": 0.0, "procs": 0, "worker_mb": 0.0}
    killed, workers_killed = None, 0
    signal.signal(signal.SIGTERM, _interrupted)
    try:
        while proc.poll() is None:
            m, workers = members(proc.pid, tag)
            for w in workers:
                wmb = sum(m.get(p, 0) for p in w) / 1024
                peak["worker_mb"] = round(max(peak["worker_mb"], wmb), 1)
                if wmb > a.worker_mb:
                    print(f"suite_watch: a worker's tree past {a.worker_mb} MB ({wmb:.0f} MB); killing it", file=sys.stderr, flush=True)
                    kill(w)
                    workers_killed += 1
            n, mb = threads(m), sum(m.values()) / 1024
            peak.update(threads=max(peak["threads"], n), rss_mb=round(max(peak["rss_mb"], mb), 1), procs=max(peak["procs"], len(m)))
            if n > a.threads or mb > a.rss_mb:
                killed = f"{n} threads, {mb:.0f} MB"
                print(f"suite_watch: past the limits ({killed}); killing {len(m)} processes", file=sys.stderr, flush=True)
                kill(m)
                break
            time.sleep(a.every)
    except KeyboardInterrupt:                           # the watchdog stopped: nothing of the run outlives it
        killed = "interrupted"
        kill(members(proc.pid, tag)[0])
    rc = proc.wait()
    left = members(proc.pid, tag)[0]
    left.pop(proc.pid, None)
    kill(left)
    print(json.dumps({"rc": rc, "wall_s": round(time.time() - t0, 1), "peak": peak, "killed": killed, "workers_killed": workers_killed,
                      "left_behind": len(left)}), flush=True)
    sys.exit(3 if killed else rc)


if __name__ == "__main__":
    main()
