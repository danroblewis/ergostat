"""Start one demo and leave it running, so a session can look at its pages (scripts/walk.py), then stop it.

    python scripts/demo_up.py start DEMO [--port N]    # one JSON line: {"demo", "url", "copy", "log"}
    python scripts/demo_up.py stop DEMO

DEMO is a folder of examples/ that holds an ergostat.yaml; anything else (a path, ``..``) is refused before anything is
copied. The demo runs from a fresh copy under /tmp (demo_check's fresh_copy), offline against its fakes (OFFLINE), with
an ERGOSTAT_HOME of its own beside the copy. One start at a time per demo: a second is refused while the first runs.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parent.parent)]
from demo_check import DEMOS, ERGOSTAT, OFFLINE, fresh_copy  # noqa: E402

from ergostat.library import reap  # noqa: E402

STATE = Path(os.environ.get("DEMO_UP_STATE") or "/tmp/ergostat-demo-up")   # DEMO.json: what start made, for stop
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
WAIT = 90                                    # seconds for the demo's web to answer
STOP_WAIT = 60                               # seconds a stopping runner is given before what is left is killed
KILL_GRACE = 5                               # seconds between SIGTERM and SIGKILL for what is left
OWNER_PORT = 8790                            # the owner's page: never taken here


def table(started: dict) -> dict[int, tuple[int, int]]:
    """Every live process: pid → (parent, group), its start time put in ``started``. From /proc where there is one
    (a container may have no ps), else ps (reap.tree). Zombies are left out: they have ended."""
    if not Path("/proc/self/stat").is_file():
        return reap.tree(started)
    got = {}
    for d in Path("/proc").iterdir():
        try:
            f = (d / "stat").read_text().rsplit(")", 1)[1].split() if d.name.isdigit() else ["Z"]
        except (OSError, IndexError):
            continue
        if f[0] not in ("Z", "X"):
            got[int(d.name)], started[int(d.name)] = (int(f[1]), int(f[2])), f[19]
    return got


def look(pid: int | None, seen: dict) -> tuple[dict, set[int]]:
    """Add ``pid`` and every descendant of it now to ``seen`` (pid → start time). The table, and those seen alive now
    with the start time they were seen with (never a pid used again)."""
    procs = table(now := {})
    if pid in procs:
        seen.update({p: now[p] for p in reap.descendants(pid, procs) | {pid} if p in now})
    return procs, {p for p, s in seen.items() if now.get(p) == s}


def runner_pid(home: str) -> int | None:
    """The runner's pid from the home this script made for the copy, only while it holds its run.pid's lock (a
    file nobody holds is stale, and its pid may be another's now: as ergostat's runner.running_pid)."""
    for path in Path(home).glob("*/run.pid"):
        with contextlib.suppress(OSError, ValueError), open(path) as f:
            try:
                fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return int(f.read().strip())
    return None


def sweep(pid: int | None, seen: dict) -> set[int]:
    """Stop the runner, everything seen under it (an agent run or daemon is a session of its own, outside the runner's
    group) and the groups they lead: SIGTERM, then SIGKILL. What is left alive is returned."""
    for sig, grace in ((signal.SIGTERM, KILL_GRACE), (signal.SIGKILL, 2)):
        procs, live = look(pid, seen)
        for g in {procs[p][1] for p in live} - {os.getpgrp(), 0}:
            with contextlib.suppress(OSError):
                os.killpg(g, sig)
        for p in live - {os.getpid()}:
            with contextlib.suppress(OSError):
                os.kill(p, sig)
        end = time.monotonic() + grace
        while live and time.monotonic() < end:
            time.sleep(0.1)
            live = look(None, seen)[1]
    return look(None, seen)[1]


def demo_dir(name: str) -> Path:
    d = DEMOS / name
    if not NAME.fullmatch(name) or d.resolve().parent != DEMOS.resolve() or not (d / "ergostat.yaml").is_file():
        raise SystemExit(f"refused: {name!r} is not a demo (a folder of examples/ that holds an ergostat.yaml)")
    return d


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ergostat(st: dict, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **OFFLINE.get(st["demo"], {}), "ERGOSTAT_HOME": st["home"]}
    return subprocess.run([*ERGOSTAT, "-C", st["copy"], *args], capture_output=True, text=True, timeout=60, env=env,
                          cwd=DEMOS.parent)


def running(st: dict) -> bool:
    if not Path(st["copy"], "ergostat.yaml").is_file():
        return False                         # its copy is gone (/tmp cleared): nothing of it can run
    try:
        return bool(json.loads(ergostat(st, "--json").stdout).get("running"))
    except (ValueError, AttributeError, subprocess.TimeoutExpired):
        return True                          # unreadable: counted as running, so no second start goes over it


def answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/status", timeout=10) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def start(name: str, port: int | None) -> int:
    demo = demo_dir(name)
    if port is not None and (not 0 < port < 65536 or port == OWNER_PORT):
        raise SystemExit(f"refused: port {port}")
    port = port or free_port()
    saved = STATE / f"{name}.json"
    if saved.exists() and running(json.loads(saved.read_text())):
        print(f"refused: {name} is already running ({saved.read_text().strip()}); stop it first", file=sys.stderr)
        return 1
    copy = fresh_copy(demo)
    st = {"demo": name, "copy": str(copy), "home": str(copy.parent / "home"), "url": None, "log": None}
    r = ergostat(st, "run", "--port", str(port))
    (copy.parent / "up.log").write_text(r.stdout + r.stderr)
    m = re.search(r"· log (\S+)", r.stdout)
    st["log"] = m.group(1) if m else str(copy.parent / "up.log")
    saved.write_text(json.dumps(st))                 # before the wait: a stop meanwhile finds it
    if r.returncode != 0:                            # (a model with errors: no wait for a web that will not come)
        print(f"{name}: ergostat run failed (rc {r.returncode}). log: {st['log']}\n{r.stdout}{r.stderr}",
              file=sys.stderr)
        stop(name)
        return 1
    end = time.monotonic() + WAIT
    while time.monotonic() < end:
        try:
            st["url"] = json.loads(ergostat(st, "--json").stdout).get("web") or None
        except ValueError:
            st["url"] = None
        if st["url"] and answers(st["url"]):
            saved.write_text(json.dumps(st))
            print(json.dumps({k: st[k] for k in ("demo", "url", "copy", "log")}), flush=True)
            return 0
        time.sleep(0.5)
    print(f"{name}: its web did not answer within {WAIT}s; stopping it. log: {st['log']}\n{r.stdout}{r.stderr}",
          file=sys.stderr)
    stop(name)
    return 1


def stop(name: str) -> int:
    demo_dir(name)
    saved = STATE / f"{name}.json"
    if not saved.exists():
        print(f"{name} was not started here", file=sys.stderr)
        return 1
    st = json.loads(saved.read_text())
    if not table({}):
        print(f"{name}: no process can be listed here (no /proc, no ps), so what it started cannot be found to stop; "
              "nothing done", file=sys.stderr)
        return 1                                      # (not counted as stopped)
    pid, seen = runner_pid(st["home"]), {}
    look(pid, seen)                                 # what runs under it, found while the runner still lives
    r = ergostat(st, "run", "--stop")                 # SIGTERM, waited on for 10 s
    print((r.stdout + r.stderr).strip())
    end = time.monotonic() + STOP_WAIT
    while running(st) and time.monotonic() < end:
        look(pid, seen)
        time.sleep(0.5)
    left = sweep(pid, seen)                           # the runner if still up, and anything of it left behind
    if left or running(st):
        print(f"{name} is still running ({st['copy']}; pids {sorted(left)})", file=sys.stderr)
        return 1
    saved.unlink()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("what", choices=("start", "stop"))
    ap.add_argument("demo")
    ap.add_argument("--port", type=int)
    a = ap.parse_args(argv)
    demo_dir(a.demo)                                  # refused before the state folder or any copy is made
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(STATE / f"{a.demo}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)              # held across read, decide and write: one start or stop at a time
        return start(a.demo, a.port) if a.what == "start" else stop(a.demo)


if __name__ == "__main__":
    sys.exit(main())
