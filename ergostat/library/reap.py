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
from contextlib import suppress


def tree(started: dict | None = None) -> dict[int, tuple[int, int]]:
    """Every process: pid → (parent pid, process group); each one's start time (``lstart``) put in ``started`` too."""
    started = {} if started is None else started
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
    """Every descendant of ``pid`` seen, with its start time (``ps``'s, to the second): ``still`` names one left behind
    (its parent gone), never a pid used again (but within that second). Looked at after each sample of the runs'
    sampler (``look_all``: no thread of its own), so one started and left between two looks is not seen."""

    def __init__(self, pid: int):
        self.pid, self.seen, self.started, self._lock = pid, set(), {}, threading.Lock()
        with _OPEN_LOCK:
            _OPEN.add(self)

    def look(self, procs: dict | None = None, now: dict | None = None) -> None:
        if procs is None:
            procs = tree(now := {})
        mine = now.get(self.pid)
        with self._lock:                                # (``ps`` failed, or ``pid`` is another's now: nothing to add)
            if mine is not None and self.started.setdefault(self.pid, mine) == mine:
                got = descendants(self.pid, procs)      # (under it now: the run's, whatever held the pid before)
                self.started.update({p: now[p] for p in got if p in now})
                self.seen |= got

    def still(self) -> set[int]:
        """Those seen (``pid`` too) alive now with the start time they were seen with, after one more look."""
        self.look(tree(now := {}), now)
        with self._lock:
            return {p for p, s in self.started.items() if now.get(p) == s}

    def close(self, look: bool = True) -> set[int]:
        with _OPEN_LOCK:
            _OPEN.discard(self)
        if look:
            self.look()
        return self.seen


_OPEN: set[Watch] = set()
_OPEN_LOCK = threading.Lock()


def look_all() -> None:
    with _OPEN_LOCK:
        open_ = list(_OPEN)
    if open_:
        procs = tree(now := {})
        for w in open_:
            w.look(procs, now)


def stop(pid: int, grace: float = 3.0, also_group: bool = False, also=None) -> set[int]:
    """Stop every descendant of ``pid`` and the process groups they lead or share (never this process's own group,
    nor the caller's): SIGTERM, then SIGKILL after ``grace`` seconds for what is left, scanning again for anything
    started meanwhile. With ``also_group``, ``pid``'s own group too (a child started in a session of its own); ``also``,
    pids seen under it before, stopped too while they live; or a function giving the only pids to stop at each round (a
    ``Watch``'s ``still``; ``pid``'s group only while among them). Returns the pids it signalled."""
    mine = {os.getpgrp()}
    seen: set[int] = set() if callable(also) else set(also or ())
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 1.0)):
        if not callable(also) and sig == signal.SIGKILL and seen and not _alive(seen - {os.getpid()}):
            break                                       # all gone: ``pid`` may be another's now, so not looked under again
        procs = tree()
        pids = set(also()) if callable(also) else descendants(pid, procs) | (_alive(seen) if seen else set())
        groups = {procs[p][1] for p in pids if p in procs}
        if also_group and pid in (pids if callable(also) else procs):
            with suppress(OSError):                     # (from the kernel, ``ps`` or not)
                groups.add(os.getpgid(pid))
        groups -= mine | {0}
        seen |= pids
        if not pids and not groups:
            break
        _signal(pids - {os.getpid()}, groups, sig)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and _alive(pids - {os.getpid()}):
            time.sleep(0.05)
    return seen
