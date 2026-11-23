"""A run on a node and its keeper (SPEC §12s.3): ``start`` makes the run's folder and starts a detached keeper
(``--keep RUN``), which forks the run in its own process group, waits for it and writes its exit; ``kill`` writes the
stop file the keeper acts on. The run never depends on the worker: a closed session leaves keeper and run going."""

import argparse
import ctypes
import fcntl
import json
import math
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback

RUN = re.compile(r"[0-9a-f]{32}")
HERE = os.path.dirname(os.path.abspath(__file__))      # (the folder, or the zipapp: either runs as ``python3 -I``)
TICK = 0.25
DAY = 86400.0
MOST_PIDS = 32768
MOST_GRACE = 600
MOST_LOG = 1 << 30          # (bytes a stream of the run's output may hold: output.py stops the run past them)


def put(path: str, text: str) -> None:
    """``text`` at ``path`` whole or not at all (a temporary file, then replaced)."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _num(v, most) -> bool:
    return not isinstance(v, bool) and isinstance(v, int | float) and 0 < v <= (most or 0)


def over(limits, said: dict) -> bool:
    """Whether the run's limits are over what the node has: an unknown limit, a non-number, or one the node can't
    say (its CPUs or memory unknown) counts as over (an allowlist; ``network`` is never pretended on this backend)."""
    top = {"cpus": said["cpus"], "memory": said["memory"], "pids": MOST_PIDS, "wall": DAY, "log": MOST_LOG}
    return not isinstance(limits, dict) or any(k not in top or not _num(v, top[k]) for k, v in limits.items())


def _strings(env) -> bool:
    return isinstance(env, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())


def handlers(root: str, said: dict) -> dict:
    runs = os.path.join(root, "runs")

    def claim(run: str) -> str | None:
        """The run's folder made, under one lock with the count of runs going (two workers can't both fill the
        node); a folder with no exit yet counts as going, whatever its keeper's state. Else why not."""
        os.makedirs(runs, mode=0o700, exist_ok=True)
        with open(os.path.join(runs, ".lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            going = sum(1 for n in os.listdir(runs) if RUN.fullmatch(n)
                        and not os.path.exists(os.path.join(runs, n, "exit")))
            if going >= said["slots"]:
                return "full"
            try:
                os.mkdir(os.path.join(runs, run), 0o700)
            except FileExistsError:
                return "bad name"               # (a run of that id is here already: never made again over it)
        return None

    def start(req: dict, w) -> None:
        run, cmd, inp, env = req.get("run"), req.get("command"), req.get("input", ""), req.get("env", {})
        if not (isinstance(cmd, str) and cmd and isinstance(inp, str) and _strings(env)):
            raise ValueError("start: command, input and env are strings")
        limits = req.get("limits", {})
        why = (None if isinstance(run, str) and RUN.fullmatch(run) else "bad name") or \
            ("limits over the node" if over(limits, said) else None) or claim(run)
        if why:
            return w.send("refused", id=req["id"], run=run, why=why)
        d = os.path.join(runs, run)
        try:
            put(os.path.join(d, "run.json"), json.dumps({"run": run, "block": req.get("block"), "backend": "process",
                                                         "command": cmd, "env": env, "limits": limits}))
            put(os.path.join(d, "in"), inp)
            os.mkdir(os.path.join(d, "cwd"))
            with open(os.path.join(d, "keeper.log"), "ab") as log:
                p = subprocess.Popen([sys.executable, "-I", HERE, "--keep", run, "--root", root],
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        except OSError:
            traceback.print_exc(file=sys.stderr)
            shutil.rmtree(d, ignore_errors=True)
            return w.send("refused", id=req["id"], run=run, why="no keeper")
        threading.Thread(target=p.wait, daemon=True).start()      # (reaped when it ends, never a zombie)
        w.send("started", id=req["id"], run=run, keeper=p.pid)

    def kill(req: dict, w) -> None:
        run, grace = req.get("run"), req.get("grace", 10)
        if isinstance(grace, bool) or not isinstance(grace, int | float) or not 0 <= grace <= MOST_GRACE:
            raise ValueError(f"kill: grace is 0 to {MOST_GRACE} seconds")
        if not (isinstance(run, str) and RUN.fullmatch(run) and os.path.isdir(os.path.join(runs, run))):
            return w.send("refused", id=req["id"], run=run, why="no such run")
        put(os.path.join(runs, run, "stop"), json.dumps({"grace": grace, "why": str(req.get("why", ""))}))
        w.send("stopping", id=req["id"], run=run)

    return {"start": start, "kill": kill}


def child(d: str, spec: dict, keeper: int) -> None:
    """In the forked child: its own group, its pgid said, its limits, the death signal; then the run's command."""
    try:
        os.setpgid(0, 0)
        put(os.path.join(d, "pgid"), f"{os.getpid()}\n")
        lim = spec.get("limits") or {}
        for k, r in (("memory", resource.RLIMIT_AS), ("pids", resource.RLIMIT_NPROC)):
            if k in lim:
                resource.setrlimit(r, (int(lim[k]), int(lim[k])))
        if "cpus" in lim and "wall" in lim:
            cpu = math.ceil(lim["cpus"] * lim["wall"])
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        if sys.platform.startswith("linux"):
            if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:   # PR_SET_PDEATHSIG
                raise OSError(ctypes.get_errno(), "prctl PR_SET_PDEATHSIG")
            if os.getppid() != keeper:
                raise OSError("the keeper ended before the death signal was set")
            try:
                with open("/proc/self/oom_score_adj", "w") as f:
                    f.write("500")              # (the run before its keeper; best effort, it is only an order)
            except OSError:
                pass
        for fd, name, mode in ((0, "in", os.O_RDONLY), (1, "out", os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
                               (2, "err", os.O_WRONLY | os.O_CREAT | os.O_TRUNC)):
            os.dup2(os.open(os.path.join(d, name), mode, 0o600), fd)
        os.chdir(os.path.join(d, "cwd"))
        for s in (signal.SIGPIPE, signal.SIGXFSZ, signal.SIGHUP):   # ignored by Python and the keeper; SIG_IGN
            signal.signal(s, signal.SIG_DFL)                        # would pass through exec to the whole run
        os.execve("/bin/sh", ["/bin/sh", "-c", spec["command"]], {**os.environ, **spec.get("env", {})})
    except BaseException:
        traceback.print_exc()
    finally:
        os._exit(127)


def group(pgid: int, sig: int) -> bool:
    """``sig`` to the run's group; whether any process of it was there to take it."""
    try:
        os.killpg(pgid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def grace(path: str) -> float:
    try:
        with open(path, encoding="utf-8") as f:
            g = json.load(f)["grace"]
        return float(g) if not isinstance(g, bool) and 0 <= g <= MOST_GRACE else 10.0
    except (OSError, ValueError, TypeError, KeyError):
        return 10.0                             # (a stop file half read still stops the run, with the usual grace)


def keep(d: str, pid: int) -> tuple[int, str]:
    """Waits for the run; at the stop file, SIGTERM to its group, then SIGKILL to the group past the grace while any
    of it is left. Its exit code (-N for a signal) and how it ended: ``exit``, the signal, or ``TERM``/``KILL``. The
    CPU ``wait4`` gave (the run and every descendant it waited for) is written to ``reaped`` first."""
    code = how = term = None
    stop = os.path.join(d, "stop")
    while True:
        if code is None and (got := os.wait4(pid, os.WNOHANG))[0]:
            code = os.waitstatus_to_exitcode(got[1])
            try:                                # (best effort: without it the CPU is the sampled sum, said so)
                put(os.path.join(d, "reaped"), json.dumps({"user": got[2].ru_utime, "system": got[2].ru_stime}))
            except OSError:
                traceback.print_exc()
        if term is None and code is None and os.path.exists(stop):
            term, how = time.monotonic() + grace(stop), "TERM"
            group(pid, signal.SIGTERM)
        if how == "TERM" and time.monotonic() >= term and group(pid, signal.SIGKILL):
            how = "KILL"
        if code is not None and (how != "TERM" or not group(pid, 0)):
            break
        time.sleep(TICK)
    if how is None:
        how = "exit" if code >= 0 else signal.Signals(-code).name.removeprefix("SIG")
    return code, how


def main(argv: list[str]) -> int:
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    ap = argparse.ArgumentParser(prog="ergostat worker --keep")
    ap.add_argument("--keep", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--day", type=float, default=DAY)
    args = ap.parse_args(argv)
    runs = os.path.realpath(os.path.join(args.root, "runs"))
    d = os.path.join(runs, args.keep)
    if not RUN.fullmatch(args.keep) or not 0 < args.day <= DAY or not os.path.isdir(d):
        print("ergostat worker --keep: no such run", file=sys.stderr)
        return 2
    try:
        with open(os.path.join(d, "run.json"), encoding="utf-8") as f:
            spec = json.load(f)
        me, pid = os.getpid(), os.fork()
        if pid == 0:
            child(d, spec, me)
        try:
            os.setpgid(pid, pid)                # (both sides set it, so a stop can't reach before the group exists)
        except OSError:
            pass
        code, how = keep(d, pid)
    except (OSError, ValueError):
        traceback.print_exc()
        code, how = None, "not started"
    put(os.path.join(d, "exit"), json.dumps({"code": code, "how": how}) + "\n")
    end = time.monotonic() + args.day
    while time.monotonic() < end and not os.path.exists(os.path.join(d, "done")):
        time.sleep(TICK)
    if os.path.dirname(os.path.realpath(d)) == runs and os.path.basename(d) == args.keep:
        shutil.rmtree(d)
    return 0
