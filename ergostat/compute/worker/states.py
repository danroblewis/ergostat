"""The runs a starting worker finds in its root, each ``running``, ``gone`` or ``unknown``, and the sweep of their
folders by name (SPEC §12s.6). ``gone`` is said only on a reading made (an allowlist): the keeper's ``exit`` written,
another boot recorded, the run's pid another process's (its start time differs), or its pid absent and its process
group read as empty. Every other case is ``unknown``, never gone and never fine, and is stopped by name: its ``stop``
written, and SIGTERM then SIGKILL to its group only while its leader is shown to be the run. The keeper writes
``proc`` (``record``): the boot, the run's pid and start time, its own."""

import json
import os
import re
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
BOOT_ID = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")    # a per-boot UUID, nothing else
# A start time's one form: /proc's clock ticks since boot, else ps's lstart printed under PS_ENV ("Mon Nov 23 10:00:00
# 2026"). ps prints lstart by the caller's LANG/LC_TIME and TZ, so every ps here runs with those fixed: the keeper's
# record and a later worker's reading then have one text. A start of any other form is no reading.
START = {True: re.compile(r"^[0-9]+$"),
         False: re.compile(r"^[A-Z][a-z]{2} [A-Z][a-z]{2} [ 0-9][0-9] [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}$")}
PS_ENV = {"LC_ALL": "C", "LANG": "C", "TZ": "UTC"}     # (over the caller's own, at each call)


def _start_form(text: str) -> bool:
    return bool(START[LINUX].match(text))


class Unread(Exception):
    """A reading that could not be made (a failed ``ps``, ``/proc`` unreadable): never taken as an answer."""


def _ps(argv: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env={**os.environ, **PS_ENV})


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
        if len(rest) < 20 or not _start_form(rest[19]):
            raise Unread("a short /proc stat")
        return rest[0], rest[19]
    try:
        out = _ps(["ps", "-o", "state=,lstart=", "-p", str(pid)], 5)
    except (OSError, subprocess.SubprocessError) as e:
        raise Unread(str(e)) from None
    got = out.stdout.split(None, 1)
    if out.returncode == 0 and len(got) == 2:
        if not _start_form(got[1].strip()):
            raise Unread("a start time of another form")
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


def boot() -> str:
    """This boot's id, a UUID made at each boot (``/proc/sys/kernel/random/boot_id``; ``sysctl kern.bootsessionuuid``
    elsewhere, never ``kern.boottime``, a time of day the clock moves); Unread when not read or not of that form."""
    try:
        if LINUX:
            with open("/proc/sys/kernel/random/boot_id", encoding="utf-8") as f:
                got = f.read().strip()
        else:
            out = _ps(["sysctl", "-n", "kern.bootsessionuuid"], 5)
            got = out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError) as e:
        raise Unread(str(e)) from None
    if not BOOT_ID.match(got):
        raise Unread("no boot id")
    return got


def record(d: str, pid: int) -> None:
    """In the keeper, after its fork: ``proc``, the boot, the run's pid and start time and the keeper's (best effort:
    without it the run reads ``unknown``, never gone)."""
    try:
        run, me = _stat(pid), _stat(os.getpid())
        if run and me:
            keeper.put(os.path.join(d, "proc"), json.dumps({"pid": pid, "start": run[1], "keeper": os.getpid(),
                                                            "keeper_start": me[1], "boot": boot()}))
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
        out = _ps(["ps", "-A", "-o", "pgid=,state="], 10)
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


def _proc(d: str) -> dict | None:
    """The keeper's ``proc`` record, None when missing or not of its shape (a start time not of ``START``'s form)."""
    rec = _read(os.path.join(d, "proc"), json.loads)
    ok = (isinstance(rec, dict) and _pid(rec.get("pid")) and _pid(rec.get("keeper"))
          and all(isinstance(rec.get(k), str) for k in ("start", "keeper_start", "boot"))
          and BOOT_ID.match(rec["boot"]) and _start_form(rec["start"]) and _start_form(rec["keeper_start"]))
    return rec if ok else None


def _ended(d: str, how: str) -> dict:
    """The run and its keeper both gone: the exit written here, never success (``code`` null, read as 127)."""
    if keeper.ended(d) is None:
        keeper.put(os.path.join(d, "exit"), json.dumps({"code": None, "how": how}) + "\n")
    return {"state": "gone", "code": keeper.ended(d), "how": how}


def state(d: str, table: list) -> dict:
    """One run folder's state now. ``table``: the process groups, read once a look (``[set]``, ``[None]`` to read).
    The run leads its own group (keeper.py: pgid == pid), and a pid number is not given again while any process has
    it as its pid or its group: so a pid now another process's means the run's group is empty."""
    code = keeper.ended(d)
    if code is not None:
        return {"state": "gone", "code": code, "how": (_read(os.path.join(d, "exit"), json.loads) or {}).get("how")}
    rec = _proc(d)
    if rec is None:
        return {"state": "unknown", "why": "record unreadable"}
    try:
        if rec["boot"] != boot():
            return _ended(d, "rebooted")                          # (two boot UUIDs differ: that boot has ended)
        run_start = start_of(rec["pid"])
        keeper_alive = start_of(rec["keeper"]) == rec["keeper_start"]
    except Unread:
        return {"state": "unknown", "why": "ps failed"}
    if run_start == rec["start"]:
        return {"state": "running"} if keeper_alive else {"state": "unknown", "why": "keeper gone"}
    if run_start is None:                                         # its pid free or a zombie: its group may be left
        try:
            if table[0] is None:
                table[0] = groups()
        except Unread:
            return {"state": "unknown", "why": "group not read"}
        if rec["pid"] in table[0]:
            return {"state": "unknown", "why": "group not empty"}
    if keeper_alive:
        return {"state": "gone", "code": None, "how": None}       # (its keeper writes the exit within a tick)
    return _ended(d, "keeper gone")


def shown(rec: dict | None) -> bool:
    """Whether the run's group is shown to be the run's now: the same boot, its leader alive with the start recorded."""
    try:
        return rec is not None and rec["boot"] == boot() and start_of(rec["pid"]) == rec["start"]
    except Unread:
        return False


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
        """Each run stopped by name: its ``stop`` written (its keeper, if any, acts on it), and its group (its pid)
        signalled here, SIGTERM then SIGKILL after ``GRACE``, each only when ``shown`` just before it is sent, else
        not at all; never this worker's own group."""
        try:
            recs = []
            for n in names:
                d = os.path.join(self.runs, n)
                try:
                    if not os.path.exists(os.path.join(d, "stop")):
                        keeper.put(os.path.join(d, "stop"), json.dumps({"grace": GRACE, "why": "unknown"}))
                except OSError:
                    pass
                rec = _proc(d)
                if rec is not None and rec["pid"] != os.getpgid(0):
                    recs.append(rec)
            for sig in (signal.SIGTERM, signal.SIGKILL):
                if sig == signal.SIGKILL:
                    time.sleep(GRACE)
                for rec in recs:
                    if shown(rec):
                        keeper.group(rec["pid"], sig)
        finally:
            self.stopping.release()


def sweeps(root: str, stop: threading.Event, every: float = HOUR) -> None:
    while not stop.wait(every):
        try:
            sweep(root)
        except Exception as e:                    # (one sweep's fault: said, and the next tried)
            print(f"sweep: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
