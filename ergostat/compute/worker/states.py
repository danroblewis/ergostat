"""The runs a starting worker finds in its root, each ``running``, ``gone`` or ``unknown``, and the sweep of their
folders by name (SPEC §12s.6). ``gone`` is said only on a reading made (an allowlist): the keeper's ``exit`` written,
or the run's pid absent or another process's (its start time differs) and its process group read as empty. Every
other case is ``unknown``, never gone and never fine, and is stopped by name: its ``stop`` written, SIGTERM then
SIGKILL to the group in its ``pgid``. The keeper writes ``proc`` (``record``): the run's pid and start time, its own."""

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

import keeper

LINUX = sys.platform.startswith("linux")
GRACE = 2.0                 # seconds from the worker's SIGTERM to its SIGKILL for an unknown run
HOUR = 3600.0


class Unread(Exception):
    """A reading that could not be made (a failed ``ps``, ``/proc`` unreadable): never taken as an answer."""


def _stat(pid: int) -> tuple[str, str] | None:
    """(state letter, start time) of ``pid``, None when there is no such process; Unread when it can't be told."""
    if LINUX:
        try:
            with open(f"/proc/{pid}/stat", "rb") as f:
                text = f.read().decode(errors="replace")
        except (FileNotFoundError, ProcessLookupError):
            return None
        except OSError as e:
            raise Unread(str(e)) from None
        rest = text[text.rfind(")") + 2:].split()                 # (the name in brackets may hold spaces)
        if len(rest) < 20:
            raise Unread("a short /proc stat")
        return rest[0], rest[19]
    try:
        out = subprocess.run(["ps", "-o", "state=,lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        raise Unread(str(e)) from None
    got = out.stdout.split(None, 1)
    if out.returncode == 0 and len(got) == 2:
        return got[0][:1], got[1].strip()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except OSError:
        pass
    raise Unread(f"ps ended {out.returncode}")


def start_of(pid: int) -> str | None:
    """When ``pid`` started; None when no process has it or it has ended (a zombie); Unread when not read."""
    got = _stat(pid)
    return None if got is None or got[0] in ("Z", "X") else got[1]


def record(d: str, pid: int) -> None:
    """In the keeper, after its fork: ``proc``, the run's pid and start time and the keeper's (best effort: without
    it the run reads ``unknown``, never gone)."""
    try:
        run, me = _stat(pid), _stat(os.getpid())
        if run and me:
            keeper.put(os.path.join(d, "proc"), json.dumps({"pid": pid, "start": run[1], "keeper": os.getpid(),
                                                            "keeper_start": me[1]}))
    except (OSError, Unread):
        pass


def groups() -> set[int]:
    """Every process group with a process in it that has not ended; Unread when the table can't be read whole."""
    if LINUX:
        try:
            names = os.listdir("/proc")
        except OSError as e:
            raise Unread(str(e)) from None
        got = set()
        for n in names:
            if n.isdigit():
                try:
                    with open(f"/proc/{n}/stat", "rb") as f:
                        rest = f.read().decode(errors="replace").rsplit(")", 1)[1].split()
                except OSError:
                    continue                                      # (ended meanwhile)
                except IndexError:
                    raise Unread(f"/proc/{n}/stat unreadable") from None
                if len(rest) < 3 or not rest[2].lstrip("-").isdigit():
                    raise Unread(f"/proc/{n}/stat unreadable")
                if rest[0] not in ("Z", "X"):
                    got.add(int(rest[2]))
        return got
    try:
        out = subprocess.run(["ps", "-A", "-o", "pgid=,state="], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        raise Unread(str(e)) from None
    if out.returncode != 0:
        raise Unread(f"ps ended {out.returncode}")
    return {int(f[0]) for f in map(str.split, out.stdout.splitlines()) if len(f) == 2 and f[1][:1] != "Z"}


def _read(path: str, parse):
    try:
        with open(path, encoding="utf-8") as f:
            return parse(f.read())
    except (OSError, ValueError):
        return None


def _pid(v) -> bool:
    return type(v) is int and v > 1


def state(d: str, table: list) -> dict:
    """One run folder's state now. ``table``: the process groups, read once a look (``[set]``, ``[None]`` to read)."""
    code = keeper.ended(d)
    if code is not None:
        return {"state": "gone", "code": code, "how": (_read(os.path.join(d, "exit"), json.loads) or {}).get("how")}
    rec = _read(os.path.join(d, "proc"), json.loads)
    if not (isinstance(rec, dict) and _pid(rec.get("pid")) and _pid(rec.get("keeper"))
            and all(isinstance(rec.get(k), str) for k in ("start", "keeper_start"))):
        return {"state": "unknown", "why": "record unreadable"}
    try:
        run_alive = start_of(rec["pid"]) == rec["start"]
        keeper_alive = start_of(rec["keeper"]) == rec["keeper_start"]
    except Unread:
        return {"state": "unknown", "why": "ps failed"}
    if run_alive:
        return {"state": "running"} if keeper_alive else {"state": "unknown", "why": "keeper gone"}
    pgid = _read(os.path.join(d, "pgid"), int)
    try:
        if table[0] is None:
            table[0] = groups()
        empty = _pid(pgid) and pgid not in table[0]
    except Unread:
        return {"state": "unknown", "why": "group not read"}
    if not empty:
        return {"state": "unknown", "why": "group not empty" if _pid(pgid) else "record unreadable"}
    if keeper_alive:
        return {"state": "gone", "code": None, "how": None}       # (its keeper writes the exit within a tick)
    if keeper.ended(d) is None:                                   # its keeper gone with it: the exit recorded here
        keeper.put(os.path.join(d, "exit"), json.dumps({"code": None, "how": "keeper gone"}) + "\n")
    return {"state": "gone", "code": keeper.ended(d), "how": "keeper gone"}


def _folders(runs: str) -> list[str]:
    """The run folders under ``runs``: names of 32 hex digits, real folders (never a link) resolved inside it."""
    try:
        names = sorted(os.listdir(runs))
    except OSError:
        return []
    real = os.path.realpath(runs)
    return [n for n in names if keeper.RUN.fullmatch(n) and not os.path.islink(os.path.join(runs, n))
            and os.path.isdir(os.path.join(runs, n)) and os.path.realpath(os.path.join(runs, n)) ==
            os.path.join(real, n)]


def sweep(root: str, day: float = keeper.DAY, now: float | None = None) -> list[str]:
    """Removes each run folder (``_folders``) whose run has ended (its ``exit`` there) and that has ``done`` or
    ended ``day`` ago or more; nothing else, never all-but-a-list. Returns the names removed."""
    runs, gone, now = os.path.join(root, "runs"), [], time.time() if now is None else now
    if os.path.commonpath([os.path.realpath(runs), os.path.realpath(root)]) != os.path.realpath(root):
        return []
    for n in _folders(runs):
        d = os.path.join(runs, n)
        try:
            ended_at = os.lstat(os.path.join(d, "exit")).st_mtime
        except OSError:
            continue
        if os.path.exists(os.path.join(d, "done")) or now - ended_at >= day:
            shutil.rmtree(d, onexc=lambda f, p, e: None if isinstance(e, FileNotFoundError) else print(
                f"sweep: {p}: {e}", file=sys.stderr))
            gone.append(n)
    return gone


class States:
    """The runs found at start, their states read again for each beat until their folder is removed; each unknown
    one stopped by name each time it is read so (one stopping thread at a time)."""

    def __init__(self, root: str):
        self.runs = os.path.join(root, "runs")
        self.names = _folders(self.runs)
        self.stopping = threading.Lock()
        self.now = self.look()

    def look(self) -> dict:
        table: list = [None]
        got = {}
        for n in self.names:
            d = os.path.join(self.runs, n)
            if os.path.isdir(d):
                try:
                    got[n] = state(d, table)
                except Exception as e:            # (a reading not made: unknown, said, never gone)
                    print(f"states: {n}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                    got[n] = {"state": "unknown", "why": "not read"}
        self.names = list(got)
        unknown = [n for n, s in got.items() if s["state"] == "unknown"]
        if unknown and self.stopping.acquire(blocking=False):
            threading.Thread(target=self.stop, args=(unknown,), daemon=True, name="ergostat-worker-stop").start()
        return got

    def hello(self) -> list:
        return [{"run": n, **s} for n, s in self.now.items()]

    def stop(self, names: list[str]) -> None:
        """Each run stopped by name: its ``stop`` written (its keeper, if any, acts on it) and its group signalled
        here, SIGTERM then SIGKILL after ``GRACE``; never this worker's own group."""
        try:
            pgids = []
            for n in names:
                d = os.path.join(self.runs, n)
                try:
                    if not os.path.exists(os.path.join(d, "stop")):
                        keeper.put(os.path.join(d, "stop"), json.dumps({"grace": GRACE, "why": "unknown"}))
                except OSError:
                    pass
                pg = _read(os.path.join(d, "pgid"), int)
                if _pid(pg) and pg != os.getpgid(0):
                    pgids.append(pg)
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if sig == signal.SIGKILL:
                    time.sleep(GRACE)
                for pg in pgids:
                    keeper.group(pg, sig)
        finally:
            self.stopping.release()


def sweeps(root: str, stop: threading.Event, every: float = HOUR) -> None:
    while not stop.wait(every):
        try:
            sweep(root)
        except Exception as e:                    # (one sweep's fault: said, and the next tried)
            print(f"sweep: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
