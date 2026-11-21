"""Stopping everything a process started: its descendants, each in whatever process group or session it made for
itself (a block's run is a session of its own; a Claude session started by it is in that run's group), found while
their parents still live, so nothing is orphaned past reach. Used by ``try_use``'s trial (``trial.py``), and by
``author.trial`` around it."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time


def tree(started: dict | None = None) -> dict[int, tuple[int, int]]:
    """Every process: pid → (parent pid, process group); with ``started``, each one's start time put in it too
    (pid → ``ps``'s ``lstart``), from the same look, so a pid used again by another process is told apart."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid=,lstart="], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    got = {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and all(x.isdigit() for x in parts[:3]):
            got[int(parts[0])] = (int(parts[1]), int(parts[2]))
            if started is not None:
                started[int(parts[0])] = parts[3].strip()
    return got


def descendants(pid: int, procs: dict | None = None) -> set[int]:
    procs = tree() if procs is None else procs
    kids: dict[int, list[int]] = {}
    for p, (pp, _) in procs.items():
        kids.setdefault(pp, []).append(p)
    out, todo = set(), [pid]
    while todo:
        for k in kids.get(todo.pop(), []):
            if k not in out:
                out.add(k)
                todo.append(k)
    return out


def _signal(pids: set[int], groups: set[int], sig) -> None:
    for g in groups:
        try:
            os.killpg(g, sig)
        except OSError:
            pass
    for p in pids:
        try:
            os.kill(p, sig)
        except OSError:
            pass


def _alive(pids: set[int]) -> set[int]:
    left = set()
    for p in pids:
        try:
            os.kill(p, 0)
        except OSError:
            continue
        left.add(p)
    return left


class Watch:
    """Every descendant of ``pid`` seen, looked for every ``every`` seconds while it runs: what a run started and then
    left (its parent killed, or gone) is still known when the time comes to stop it. Each is kept with its start time
    as first seen (``pid`` too), so ``still`` names only those that are still the process seen, never a pid used again.
    One that started and was left within a single look (``EVERY``) is not seen. Every watch open shares one thread and
    one ``ps`` a look (a run costs no thread of its own)."""

    def __init__(self, pid: int):
        self.pid, self.seen, self.started, self._lock = pid, set(), {}, threading.Lock()
        _looker(self)

    def look(self, procs: dict | None = None, now: dict | None = None) -> None:
        if procs is None:
            now = {}
            procs = tree(now)
        got = descendants(self.pid, procs)
        with self._lock:
            for p in (got | {self.pid}) & now.keys():   # (under it now: its own, whatever held the pid before)
                self.started[p] = now[p] if p in got else self.started.get(p, now[p])
            self.seen |= got

    def still(self) -> set[int]:
        """Those seen (and ``pid``) that live now with the start time they were seen with."""
        now: dict[int, str] = {}
        tree(now)
        with self._lock:
            return {p for p, s in self.started.items() if s and now.get(p) == s}

    def close(self, look: bool = True) -> set[int]:
        with _OPEN_LOCK:
            _OPEN.discard(self)
        if look:
            self.look()
        return self.seen


EVERY = 0.5                     # seconds between the shared looks
_OPEN: set[Watch] = set()
_OPEN_LOCK = threading.Lock()
_LOOKER: list[threading.Thread] = []


def _looker(w: Watch) -> None:
    with _OPEN_LOCK:                                    # (open once the looker runs: a failed start leaves none open)
        if not (_LOOKER and _LOOKER[0].is_alive()):
            _LOOKER[:] = [threading.Thread(target=_look_all, daemon=True, name="reap-watch")]
            _LOOKER[0].start()
        _OPEN.add(w)


def _look_all() -> None:
    while True:
        time.sleep(EVERY)
        with _OPEN_LOCK:
            open_ = list(_OPEN)
            if not open_:
                _LOOKER.clear()                         # (the next watch starts it again, under the same lock)
                return
        now: dict[int, str] = {}
        procs = tree(now)
        for w in open_:
            w.look(procs, now)


def stop(pid: int, grace: float = 3.0, also_group: bool = False, also: set[int] | None = None) -> set[int]:
    """Stop every descendant of ``pid`` and the process groups they lead or share (never this process's own group,
    nor the caller's): SIGTERM, then SIGKILL after ``grace`` seconds for what is left, scanning again for anything
    started meanwhile. With ``also_group``, ``pid``'s own group too (a child started in a session of its own); ``also``,
    pids seen under it before (a ``Watch``'s), stopped too while they live; or a function asked for them at each round
    (a ``Watch``'s ``still``: only those still the process seen), and then ``pid`` is looked under only while it is
    among them. Returns the pids it signalled."""
    mine = {os.getpgrp()}
    seen: set[int] = set() if callable(also) else set(also or ())
    stamps: dict[int, str] = {}                         # (callable: those signalled, with the start times they had)
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 1.0)):
        now: dict[int, str] = {}
        procs = tree(now)
        if callable(also):                              # (and those the last round found, while the same process)
            known = set(also()) | {p for p, s in stamps.items() if now.get(p) == s}
            under = pid in known                        # (``pid`` used again by another: not looked under)
        else:
            if sig == signal.SIGKILL and seen and not _alive(seen - {os.getpid()}):
                break                                   # all gone: ``pid`` may be another's now, so not looked under again
            known, under = (_alive(seen) if seen else set()), True
        pids = (descendants(pid, procs) if under else set()) | known
        groups = {procs[p][1] for p in pids if p in procs}
        if also_group and under:                        # (from the kernel when ``ps`` failed)
            try:
                groups.add(procs[pid][1] if pid in procs else os.getpgid(pid))
            except OSError:
                pass
        groups -= mine | {0}
        seen |= pids
        stamps.update({p: now[p] for p in pids if p in now})
        if not pids and not groups:
            break
        _signal(pids - {os.getpid()}, groups, sig)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and _alive(pids - {os.getpid()}):
            time.sleep(0.05)
    return seen
