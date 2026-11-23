"""A run on a node and its keeper (SPEC §12s.3): ``start`` makes the run's folder and starts a detached keeper
(``--keep RUN``), which forks the run in its own process group, waits for it and writes its exit; ``kill`` writes the
stop file the keeper acts on. The run never depends on the worker: a closed session leaves keeper and run going.

The engine keeps its own machine blocks' runs the same way when ``runs: outlive_engine`` is on (SPEC §9.1, ``launch``,
``Kept``): the run's standard output appended to its journal, ``runs/RUN.jsonl`` in the state folder, so stopping or
killing the engine leaves the run going and its exit written."""

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

if not __package__:     # the worker's and the keeper's process (by bare name, __main__.py): only they hold deadlines
    import deadline

RUN = re.compile(r"[0-9a-f]{32}")
HERE = os.path.dirname(os.path.abspath(__file__))      # (the folder, or the zipapp: either runs as ``python3 -I``)
TICK = 0.25
DAY = 86400.0
MOST_PIDS = 32768
MOST_GRACE = 600
MOST_LOG = 1 << 30          # (bytes a stream of the run's output may hold: output.py stops the run past them)
APPEND = os.O_WRONLY | os.O_CREAT | os.O_APPEND
WALL_GRACE = 2.0            # seconds from SIGTERM to SIGKILL when a run's own deadline stops it
MARGIN = 5.0                # seconds a kept run's deadline is after its engine's: the engine's timeout first while up


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
        lease = req.get("lease")
        if lease is not None and not (isinstance(lease, dict) and _num(lease.get("left"), DAY)
                                      and _num(lease.get("ttl"), DAY)):
            raise ValueError("start: lease is {left, ttl}, seconds within a day")
        limits = req.get("limits", {})
        why = (None if isinstance(run, str) and RUN.fullmatch(run) else "bad name") or \
            ("limits over the node" if over(limits, said) else None) or claim(run)
        if why:
            return w.send("refused", id=req["id"], run=run, why=why)
        d = os.path.join(runs, run)
        try:
            put(os.path.join(d, "run.json"), json.dumps({"run": run, "block": req.get("block"), "backend": "process",
                                                         "command": cmd, "env": env, "limits": limits,
                                                         "deadlines": True}))
            at = deadline.now()             # (no wall limit: a day, the most a run may have; never unbounded)
            deadline.write(os.path.join(d, "deadline"), at + limits.get("wall", DAY),
                           None if lease is None else at + lease["left"],
                           WALL_GRACE if lease is None else deadline.kill_after(lease["ttl"]))
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
            got = spec.get(name) if fd else None      # (an engine's run: its journal, appended to; its log's descriptor)
            if type(got) is int:
                os.dup2(got, fd)
            else:
                os.dup2(os.open(got or os.path.join(d, name), APPEND if got else mode, 0o600), fd)
        if type(spec.get("err")) is int and spec["err"] > 2:
            os.close(spec["err"])
        os.chdir(spec.get("cwd") or os.path.join(d, "cwd"))
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


def keep(d: str, pid: int, wall: float | None = None, held: "deadline.Held | None" = None) -> tuple[int, str]:
    """Waits for the run; at the stop file, at ``wall`` seconds on (an engine's run: its own deadline, or none), or
    at the earlier of a node run's ``held`` deadlines (taken again each tick), SIGTERM to its group, then SIGKILL to
    the group past the grace (a deadline's: ``WALL_GRACE``, or the held ``kill``) while any of it is left. Its exit
    code (-N for a signal) and how it ended: ``exit``, the signal, ``TERM``/``KILL``, or the deadline that stopped
    it, ``timeout`` (an engine's run), ``wall`` or ``lease``. Timed on ``deadline.CLOCK``, never the time of day."""
    code = how = term = timed = None
    stop, late = os.path.join(d, "stop"), None if wall is None else deadline.now() + wall
    while True:
        if code is None and (got := os.waitpid(pid, os.WNOHANG))[0]:
            code = os.waitstatus_to_exitcode(got[1])
        if held is not None and term is None:
            held.look()
        at = deadline.now()
        due = held.due(at) if held is not None else "timeout" if late is not None and at >= late else None
        if term is None and code is None and (os.path.exists(stop) or due):
            timed = None if os.path.exists(stop) else due
            term = at + (grace(stop) if timed is None else held.kill if held is not None else WALL_GRACE)
            how = "TERM"
            group(pid, signal.SIGTERM)
        if how == "TERM" and deadline.now() >= term and group(pid, signal.SIGKILL):
            how = "KILL"
        if code is not None and (how != "TERM" or not group(pid, 0)):
            break
        nxt = None if term is not None else held.next() if held is not None else late   # (woken at a nearer one)
        time.sleep(0.05 if how == "TERM" else max(0.01, min(TICK, TICK if nxt is None else nxt - deadline.now())))
    if how is None:
        how = "exit" if code >= 0 else signal.Signals(-code).name.removeprefix("SIG")
    return code, timed or how


# ---- a machine block's run on this machine, under its keeper (SPEC §9.1, *A run outlives its engine*)

def ended(d: str) -> int | None:
    """The run's exit as its keeper wrote it, or None while it has written none. A run that never started (its code
    unknown) reads 127, never 0: an exit unknown is never taken for success."""
    try:
        with open(os.path.join(d, "exit"), encoding="utf-8") as f:
            code = json.load(f).get("code")
    except FileNotFoundError:
        return None
    except (OSError, ValueError, AttributeError):
        return 127                              # (written whole by put: unreadable is not a run still going)
    return code if isinstance(code, int) and not isinstance(code, bool) else 127


class Kept:
    """A run its keeper holds, as the engine that started it sees it: what it uses of a ``Popen``. ``pid`` is the
    run's own, the id of its process group (a stop, a lease's kill, a timeout signal the whole group, as before); its
    exit is the keeper's ``exit`` file. ``rusage`` is None: no ``wait4`` here, its CPU and memory are the sampler's."""

    rusage = None

    def __init__(self, d: str, keeper, pid: int):
        self.dir, self.keeper, self.pid, self.returncode = d, keeper, pid, None

    def poll(self) -> int | None:
        if self.returncode is None:
            got = ended(self.dir)
            if got is None and self.keeper.poll() is not None:
                got = ended(self.dir)           # (looked at again: written just before it ended)
                got = -signal.SIGKILL if got is None else got   # its keeper gone with no exit: the run with it
            self.returncode = got
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        end = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if end is not None and time.monotonic() >= end:
                raise subprocess.TimeoutExpired("keeper", timeout)
            time.sleep(0.02)
        return self.returncode

    def how(self) -> str | None:
        """How its keeper says it ended (``timeout``: its own deadline stopped it), or None when unsaid."""
        try:
            with open(os.path.join(self.dir, "exit"), encoding="utf-8") as f:
                return json.load(f).get("how")
        except (OSError, ValueError, AttributeError):
            return None

    def kill(self) -> None:
        put(os.path.join(self.dir, "stop"), json.dumps({"grace": 0, "why": "killed"}))

    def release(self) -> None:
        """Read to its end: its keeper may remove its folder and end (within a tick; reaped by a thread meanwhile, so
        the run's end is never held up for it)."""
        put(os.path.join(self.dir, "done"), "")
        threading.Thread(target=self.keeper.wait, daemon=True, name="keeper-reap").start()


def launch(root: str, run: str, command: str, inp: str, cwd: str, env: dict, out: str, err: int,
           timeout: float | None = None, wait: float = 30.0) -> Kept:
    """The run started under a detached keeper in its own session: ``root/runs/RUN/`` made (its record and its input),
    its standard output appended to ``out`` (its journal), its errors to the descriptor ``err`` (passed down), ``env``
    given to the keeper's process (never written to disk). A ``timeout`` is the keeper's own too: ``MARGIN`` seconds
    after it the keeper stops the run's group itself, so a run whose engine is gone still ends by it. Returns once the run's group
    exists; OSError when it does not within ``wait``, and the keeper is told to stop it should it start later."""
    if not RUN.fullmatch(run):
        raise OSError("a run's keeper needs a run id of 32 hex digits")
    d = os.path.join(root, "runs", run)
    os.makedirs(os.path.dirname(d), mode=0o700, exist_ok=True)
    os.mkdir(d, 0o700)
    try:
        put(os.path.join(d, "run.json"), json.dumps({"run": run, "backend": "process", "command": command, "out": out,
                                                     "err": err, "cwd": cwd, "limits": {},
                                                     "wall": timeout + MARGIN if timeout else None}))
        put(os.path.join(d, "in"), inp)
        with open(os.path.join(d, "keeper.log"), "ab") as log:
            p = subprocess.Popen([sys.executable, "-I", HERE, "--keep", run, "--root", root], env=env,
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                                 pass_fds=(err,))
    except OSError:
        shutil.rmtree(d, ignore_errors=True)
        raise
    end = time.monotonic() + wait
    while True:
        try:
            with open(os.path.join(d, "pgid"), encoding="utf-8") as f:
                return Kept(d, p, int(f.read()))
        except (OSError, ValueError):
            pass
        if p.poll() is not None or os.path.exists(os.path.join(d, "exit")) or time.monotonic() > end:
            put(os.path.join(d, "stop"), json.dumps({"grace": 0, "why": "not started in time"}))
            put(os.path.join(d, "done"), "")
            raise OSError(f"its keeper did not start it (see {os.path.join(d, 'keeper.log')})")
        time.sleep(0.005)


def stop_all(root: str, grace: float) -> list[str]:
    """``ergostat run --stop --runs``: each run a keeper holds in ``root/runs`` and not yet ended is told to stop (its
    stop file: SIGTERM to its group, SIGKILL past ``grace``), whether or not any engine is up. Returns their ids."""
    runs, asked = os.path.join(root, "runs"), []
    try:
        names = sorted(os.listdir(runs))
    except FileNotFoundError:
        return []
    for n in names:
        d = os.path.join(runs, n)
        if RUN.fullmatch(n) and os.path.isfile(os.path.join(d, "run.json")) and ended(d) is None:
            put(os.path.join(d, "stop"), json.dumps({"grace": grace, "why": "ergostat run --stop --runs"}))
            asked.append(n)
    return asked


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
        wall = spec.get("wall")
        if wall is not None and (isinstance(wall, bool) or not isinstance(wall, int | float) or not 0 < wall < math.inf):
            raise ValueError(f"its deadline is not a number of seconds: {wall!r}")   # (not started, never unbounded)
        held = deadline.Held(os.path.join(d, "deadline")) if spec.get("deadlines") is True else None
        me, pid = os.getpid(), os.fork()
        if pid == 0:
            child(d, spec, me)
        try:
            os.setpgid(pid, pid)                # (both sides set it, so a stop can't reach before the group exists)
        except OSError:
            pass
        code, how = keep(d, pid, wall, held)
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
