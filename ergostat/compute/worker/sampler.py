"""Each run's CPU and memory on the node, as readings (SPEC §12s.3, *Readings*). One thread for every run finds
the runs in the root's ``runs/`` (each folder and its ``pgid``), lists the processes once a sample (``/proc`` on
Linux, one ``ps`` elsewhere) and reads each run's tree: its process group and its descendants by parent. A run is
sampled once a second for its first ten seconds seen, then every ten. Its resources carry the keys a local run's do
(``ergostat/costs/sampler.py``, ``Tracker.result``). The latest is in each ``beat``; once the keeper's exit is
there, the whole is said once in ``ended``. Readings are measurements: nothing here writes an event."""

import json
import os
import re
import subprocess
import sys
import threading
import time

LINUX, MACOS = sys.platform.startswith("linux"), sys.platform == "darwin"
FAST, SLOW, RAMP = 1.0, 10.0, 10.0
TICK = os.sysconf("SC_CLK_TCK") if LINUX else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if LINUX else 4096
RUN = re.compile(r"[0-9a-f]{32}")


class _Ps(subprocess.Popen):
    """``ps``, reaped with ``wait4``, so the CPU it cost is counted as the sampler's own."""
    rusage = None

    def _try_wait(self, flags):
        try:
            pid, sts, ru = os.wait4(self.pid, flags)
        except ChildProcessError:
            return self.pid, 0
        if pid == self.pid:
            self.rusage = ru
        return pid, sts


def _clock(s: str) -> float:
    """``ps``'s CPU time: [[dd-]hh:]mm:ss.cc."""
    days, _, s = s.rpartition("-")
    secs = 0.0
    for x in s.split(":"):
        secs = secs * 60 + float(x)
    return secs + (int(days) * 86400 if days else 0)


def listing() -> tuple[dict, float]:
    """Every process by pid: (parent, group, resident bytes, user, system, reaped children's user and system, or
    None where not read), and what ``ps`` cost. A ``ps`` that fails raises: no sample, never every tree empty."""
    rows = {}
    if LINUX:
        for d in os.listdir("/proc"):
            try:
                with open(f"/proc/{d}/stat", "rb") as f:
                    raw = f.read().decode(errors="replace")
                f = raw[raw.rfind(")") + 2:].split()    # (after the command, which may hold spaces)
                rows[int(d)] = (int(f[1]), int(f[2]), int(f[21]) * PAGE, int(f[11]) / TICK, int(f[12]) / TICK,
                                int(f[13]) / TICK, int(f[14]) / TICK)
            except (OSError, IndexError, ValueError):
                continue
        return rows, 0.0
    p = _Ps(["ps", "-A", "-o", "pid=,ppid=,pgid=,rss=,utime=,stime="], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True)
    try:
        out = p.communicate(timeout=10)[0]
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise
    if p.returncode != 0:
        raise OSError(f"ps ended {p.returncode}")
    for line in out.splitlines():
        f = line.split()
        try:
            rows[int(f[0])] = (int(f[1]), int(f[2]), int(f[3]) * 1024, _clock(f[4]), _clock(f[5]), None, None)
        except (IndexError, ValueError):
            continue
    return rows, (p.rusage.ru_utime + p.rusage.ru_stime) if p.rusage else 0.0


def open_files(pid: int) -> int | None:
    """How many files a process has open where that is cheap (``/proc``; ``libproc`` on macOS); else None."""
    try:
        if LINUX:
            return len(os.listdir(f"/proc/{pid}/fd"))
        if MACOS:
            import ctypes
            lib = ctypes.CDLL("/usr/lib/libproc.dylib")
            size = lib.proc_pidinfo(pid, 1, 0, None, 0)                 # PROC_PIDLISTFDS
            buf = ctypes.create_string_buffer(max(size, 1))
            got = lib.proc_pidinfo(pid, 1, 0, buf, size) if size > 0 else 0
            return got // 8 if got > 0 else None                         # (struct proc_fdinfo is 8 bytes)
    except (OSError, AttributeError):
        pass
    return None


class Run:
    def __init__(self, name: str, now: float):
        self.name, self.first, self.due = name, now, now
        self.pgid = self.keeper = None
        self.cpu: dict[int, tuple[float, float]] = {}     # pid: its last (user, system) seen
        self.reaped = (0.0, 0.0)                          # what its keeper reaped: the run and each descendant waited
        self.memory = self.processes = self.samples = 0
        self.files: int | None = None
        self.overhead, self.kept = 0.0, False

    def see(self, rows: dict, kids: dict) -> bool:
        """One sample of its tree; whether any of it was there."""
        tree = {p for p, r in rows.items() if r[1] == self.pgid}
        todo = [self.pgid] if self.pgid in rows else []
        while todo:                                       # (its descendants, whatever their group)
            tree.add(x := todo.pop())
            todo += [k for k in kids.get(x, ()) if k not in tree]
        if self.keeper is None and LINUX and self.pgid in rows and self._keeper(rows[self.pgid][0]):
            self.keeper = rows[self.pgid][0]
        k = rows.get(self.keeper)
        if k is not None and k[5] is not None:
            self.reaped, self.kept = (max(self.reaped[0], k[5]), max(self.reaped[1], k[6])), True
        if not tree:
            return False
        self.samples += 1
        for p in tree:
            self.cpu[p] = rows[p][3:5]
        self.memory = max(self.memory, sum(rows[p][2] for p in tree))
        self.processes = max(self.processes, len(tree))
        files = [f for p in tree if (f := open_files(p)) is not None]
        if files:
            self.files = max(self.files or 0, sum(files))
        return True

    def _keeper(self, pid: int) -> bool:
        """Whether ``pid`` is this run's keeper (its command line says so), never another that took the parent's
        place (init or a subreaper, once a keeper is gone)."""
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                return f"\0--keep\0{self.name}\0".encode() in f.read()
        except OSError:
            return False

    def result(self) -> dict:
        user = max(sum(u for u, _ in self.cpu.values()), self.reaped[0])
        system = max(sum(s for _, s in self.cpu.values()), self.reaped[1])
        how = ("keeper+sampled" if self.samples else "keeper") if self.kept else ("sampled" if self.samples else "none")
        return {"cpu": round(user + system, 3), "cpu_user": round(user, 3), "cpu_system": round(system, 3),
                "memory_peak": int(self.memory), "processes_peak": max(self.processes, 1),
                **({"open_files_peak": self.files} if self.files is not None else {}),
                "samples": self.samples, "method": how, "sampler_cpu": round(self.overhead, 4)}


class Readings:
    """Every run's readings, kept by one thread (``loop``); ``latest`` for the beat, ``ended`` sent by ``w``."""

    def __init__(self, root: str, w):
        self.runs_dir, self.w = os.path.join(root, "runs"), w
        self.lock = threading.Lock()
        self.runs: dict[str, Run] = {}
        self.said: set[str] = set()                       # (ended already said this session: said once)

    def latest(self) -> dict:
        with self.lock:
            return {n: {"resources": r.result()} for n, r in self.runs.items()}

    def loop(self, stop: threading.Event) -> None:
        while not stop.wait(FAST):
            try:
                for frame in self.look(time.monotonic()):
                    self.w.send("ended", **frame)
            except (OSError, ValueError):                 # (the stream closed: the worker is ending)
                stop.set()
            except Exception:                             # (one look's fault: the next may not have it)
                pass

    def look(self, now: float) -> list[dict]:
        """One look: new runs found, the due and ended ones sampled from one listing; the ``ended`` frames to say."""
        names = {n for n in os.listdir(self.runs_dir) if RUN.fullmatch(n)} if os.path.isdir(self.runs_dir) else set()
        ends = {}
        with self.lock:
            self.said &= names
            for n in names - self.said - self.runs.keys():
                self.runs[n] = Run(n, now)
            for n, r in self.runs.items():
                if r.pgid is None:
                    r.pgid = _read(os.path.join(self.runs_dir, n, "pgid"), int)
                if (e := _read(os.path.join(self.runs_dir, n, "exit"), json.loads)) is not None:
                    ends[n] = e
            due = [r for r in self.runs.values() if r.pgid is not None and (r.due <= now + 0.05 or r.name in ends)]
        if not due and not ends:
            return []
        c0 = time.thread_time()
        rows, cost = listing() if due else ({}, 0.0)
        kids: dict[int, list[int]] = {}
        for p, r in rows.items():
            kids.setdefault(r[0], []).append(p)
        with self.lock:
            seen = [r for r in due if r.see(rows, kids)]
            for r in due:
                r.due = now + (FAST if now - r.first < RAMP else SLOW)
            for r in seen:                                # (its own CPU, the listing's and the trees', shared out)
                r.overhead += (time.thread_time() - c0 + cost) / len(seen)
            out = []
            for n, e in ends.items():
                if isinstance(e, dict) and (r := self.runs.pop(n, None)):
                    self.said.add(n)
                    out.append({"run": n, "code": e.get("code"), "how": e.get("how"), "resources": r.result()})
            return out


def _read(path: str, parse):
    """The file's text parsed, or None while it is not there or not whole (looked at again next time)."""
    try:
        with open(path, encoding="utf-8") as f:
            return parse(f.read())
    except (OSError, ValueError):
        return None
