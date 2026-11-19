"""The CPU time and peak memory of each run's whole process tree: one sampler shared by every run, plus the run's own
wait status.

- **The wait status** (``Measured``, a ``Popen`` that reaps its process with ``wait4``): the exact user and system CPU
  of the run's process and of every descendant it waited for, and the largest resident memory of any one of them. A
  descendant left running, or never waited for, is not in it.
- **Sampling** (``Sampler``): one thread for every run at once, never one per run, which every ``INTERVAL`` seconds
  lists the processes once (``/proc`` on Linux; one ``ps`` elsewhere) and finds each run's tree: its process group
  (each run is a session of its own) and its descendants by parent. Per run it keeps each process's last CPU time, the
  most memory the tree held at once (resident, summed over the tree), the most processes and, where it is cheap
  (``/proc``, or ``libproc`` on macOS for the user's own processes), the most open files. A process that lived less
  than an interval between two samples is not seen; memory between samples is not seen.

When the run ends the two are put together: CPU is the larger of the wait status and the sum sampled (each misses what
the other sees: the sampled sum misses the last part of the final interval and short-lived processes; the wait status
misses processes left running); peak memory is the larger of the tree's sampled peak and the largest single process.
Network bytes per process are not measured: macOS gives them only through ``nettop`` (root, or a process per sample)
and Linux only per network namespace.

The sampler measures itself: its thread's CPU and the CPU of the ``ps`` it runs (each reaped with ``wait4``), shared
out among the runs it sampled (``sampler_cpu`` on each run)."""

from __future__ import annotations

import errno
import os
import subprocess
import sys
import threading
import time

INTERVAL = 1.0                 # seconds between samples
LINUX = sys.platform.startswith("linux")
MACOS = sys.platform == "darwin"


class Measured(subprocess.Popen):
    """A process reaped with ``wait4``: ``rusage`` is its resource use, and its waited-for descendants', once it ended."""

    rusage = None

    def _wait4(self, flags: int) -> tuple[int, int]:
        pid, sts, ru = os.wait4(self.pid, flags)
        if pid == self.pid:
            self.rusage = ru
        return pid, sts

    def _try_wait(self, wait_flags):                   # (Popen.wait: its callers hold _waitpid_lock)
        try:
            return self._wait4(wait_flags)
        except ChildProcessError:
            return self.pid, 0

    def _internal_poll(self, _deadstate=None, *args, **kwargs):   # Popen.poll, reaping with wait4 as well
        if self.returncode is None:
            if not self._waitpid_lock.acquire(False):
                return None
            try:
                if self.returncode is not None:
                    return self.returncode
                pid, sts = self._wait4(os.WNOHANG)
                if pid == self.pid:
                    self._handle_exitstatus(sts)
            except OSError as e:
                if _deadstate is not None:
                    self.returncode = _deadstate
                elif e.errno == errno.ECHILD:
                    self.returncode = 0
            finally:
                self._waitpid_lock.release()
        return self.returncode


def _ps() -> tuple[list[tuple[int, int, int, int, float, float]], float]:
    """Every process: (pid, parent, group, resident bytes, user CPU, system CPU), and the CPU the listing cost."""
    if LINUX:
        return _proc(), 0.0
    p = Measured(["ps", "-A", "-o", "pid=,ppid=,pgid=,rss=,utime=,stime="], stdout=subprocess.PIPE,
                 stderr=subprocess.DEVNULL, text=True)
    out, _ = p.communicate(timeout=10)
    cost = (p.rusage.ru_utime + p.rusage.ru_stime) if p.rusage else 0.0
    rows = []
    for line in out.splitlines():
        f = line.split()
        if len(f) < 6:
            continue
        try:
            rows.append((int(f[0]), int(f[1]), int(f[2]), int(f[3]) * 1024, _clock(f[4]), _clock(f[5])))
        except ValueError:
            continue
    return rows, cost


def _clock(s: str) -> float:
    """``ps``'s CPU time: [[dd-]hh:]mm:ss.cc."""
    days, _, s = s.rpartition("-")
    parts = [float(x) for x in s.split(":")]
    secs = 0.0
    for x in parts:
        secs = secs * 60 + x
    return secs + (int(days) * 86400 if days else 0)


_TICK = os.sysconf("SC_CLK_TCK") if LINUX else 100
_PAGE = os.sysconf("SC_PAGE_SIZE") if LINUX else 4096


def _proc() -> list[tuple[int, int, int, int, float, float]]:
    rows = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat", "rb") as f:
                raw = f.read().decode(errors="replace")
        except OSError:
            continue
        f = raw[raw.rfind(")") + 2:].split()        # after the command, which may hold spaces
        try:
            rows.append((int(d), int(f[1]), int(f[2]), int(f[21]) * _PAGE, int(f[11]) / _TICK, int(f[12]) / _TICK))
        except (IndexError, ValueError):
            continue
    return rows


_libproc = None


def open_files(pid: int) -> int | None:
    """How many files a process has open, where that is cheap to know; None where it is not."""
    if LINUX:
        try:
            return len(os.listdir(f"/proc/{pid}/fd"))
        except OSError:
            return None
    if not MACOS:
        return None
    global _libproc
    try:
        import ctypes
        if _libproc is None:
            _libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        size = _libproc.proc_pidinfo(pid, 1, 0, None, 0)             # PROC_PIDLISTFDS: how big a buffer it needs
        if size <= 0:
            return None
        buf = ctypes.create_string_buffer(size)
        got = _libproc.proc_pidinfo(pid, 1, 0, buf, size)
        return got // 8 if got > 0 else None                          # struct proc_fdinfo is 8 bytes
    except (OSError, AttributeError):
        return None


class Tracker:
    """One run's process tree, as sampled."""

    def __init__(self, proc: subprocess.Popen):
        self.proc, self.root, self.started = proc, proc.pid, time.monotonic()
        self.cpu: dict[int, tuple[float, float]] = {}     # pid → its last (user, system) seen
        self.memory = 0                                   # the most the tree held at once, resident bytes
        self.processes = 0
        self.files: int | None = None
        self.samples = 0
        self.overhead = 0.0                               # the sampler's CPU, this run's share

    def see(self, tree: list[tuple], files: int | None, share: float) -> None:
        self.samples += 1
        self.overhead += share
        for pid, _pp, _pg, _rss, u, s in tree:
            self.cpu[pid] = (u, s)
        self.memory = max(self.memory, sum(r[3] for r in tree))
        self.processes = max(self.processes, len(tree))
        if files is not None:
            self.files = max(self.files or 0, files)

    def result(self) -> dict:
        """The run's resources, its wait status and its samples put together."""
        su = sum(u for u, _ in self.cpu.values())
        ss = sum(s for _, s in self.cpu.values())
        ru = getattr(self.proc, "rusage", None)
        wu, ws = (ru.ru_utime, ru.ru_stime) if ru else (0.0, 0.0)
        rss = (ru.ru_maxrss if MACOS else ru.ru_maxrss * 1024) if ru else 0  # bytes on macOS, KiB on Linux
        user, system = max(wu, su), max(ws, ss)
        how = "wait4" + ("+sampled" if self.samples else "") if ru else ("sampled" if self.samples else "none")
        return {"cpu": round(user + system, 3), "cpu_user": round(user, 3), "cpu_system": round(system, 3),
                "memory_peak": int(max(self.memory, rss)), "processes_peak": max(self.processes, 1),
                **({"open_files_peak": self.files} if self.files is not None else {}),
                "samples": self.samples, "method": how, "sampler_cpu": round(self.overhead, 4)}


class Sampler:
    """One thread that samples every run's process tree; it runs only while some run is tracked."""

    def __init__(self, interval: float = INTERVAL, name: str = "ergostat-sampler"):
        self.interval, self.name = interval, name
        self.lock = threading.Lock()
        self.runs: dict[int, Tracker] = {}
        self.thread: threading.Thread | None = None
        self.wake = threading.Event()
        self.cpu = 0.0                 # its own CPU so far: its thread's, and the ps it ran
        self.taken = 0                 # samples taken
        self.busy = 0.0                # wall seconds it spent sampling

    def track(self, proc: subprocess.Popen) -> Tracker:
        t = Tracker(proc)
        with self.lock:
            self.runs[proc.pid] = t
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._loop, name=self.name, daemon=True)
                self.thread.start()
        return t

    def finish(self, t: Tracker) -> dict:
        with self.lock:                # (not while a sample is being taken: it has the lock)
            self.runs.pop(t.root, None)
            return t.result()

    def stats(self) -> dict:
        return {"samples": self.taken, "cpu": round(self.cpu, 4), "busy": round(self.busy, 4), "tracked": len(self.runs),
                "running": bool(self.thread and self.thread.is_alive())}

    def _loop(self) -> None:
        while True:
            with self.lock:
                if not self.runs:
                    self.thread = None
                    return
            self.wake.wait(self.interval)
            self.wake.clear()
            try:
                self.sample()
            except Exception:          # (a listing that failed: the next one may not)
                pass

    def sample(self) -> None:
        t0, c0 = time.monotonic(), time.thread_time()
        rows, ps_cost = _ps()
        kids: dict[int, list[int]] = {}
        by_group: dict[int, list[tuple]] = {}
        by_pid = {}
        for r in rows:
            by_pid[r[0]] = r
            kids.setdefault(r[1], []).append(r[0])
            by_group.setdefault(r[2], []).append(r)
        with self.lock:
            runs = list(self.runs.values())
            trees = []
            for t in runs:
                pids = {r[0] for r in by_group.get(t.root, [])}
                todo = [t.root] if t.root in by_pid else []
                while todo:                                   # its descendants, wherever their group
                    x = todo.pop()
                    pids.add(x)
                    todo += [k for k in kids.get(x, ()) if k not in pids]
                trees.append([by_pid[x] for x in pids if x in by_pid])
            files = [None if not tree else _files(tree) for tree in trees]
            cost = time.thread_time() - c0 + ps_cost
            share = cost / len(runs) if runs else 0.0
            for t, tree, f in zip(runs, trees, files, strict=True):
                if tree:
                    t.see(tree, f, share)
            self.cpu += cost
            self.taken += 1
            self.busy += time.monotonic() - t0


def _files(tree: list[tuple]) -> int | None:
    n, known = 0, False
    for r in tree:
        f = open_files(r[0])
        if f is not None:
            n, known = n + f, True
    return n if known else None


SAMPLER = Sampler()
