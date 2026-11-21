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
    One that started and was left within a single look (``every``) is not seen."""

    def __init__(self, pid: int, every: float = 0.5):
        self.pid, self.every, self.seen, self.started = pid, every, set(), {}
        self._lock, self._stop = threading.Lock(), threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True, name="reap-watch")
        self._t.start()

    def look(self) -> None:
        now: dict[int, str] = {}
        got = descendants(self.pid, tree(now))
        with self._lock:
            for p in (got | {self.pid}) & now.keys():
                self.started.setdefault(p, now[p])
            self.seen |= got

    def still(self) -> set[int]:
        """Those seen (and ``pid``) that live now with the start time they were seen with."""
        now: dict[int, str] = {}
        tree(now)
        with self._lock:
            return {p for p, s in self.started.items() if s and now.get(p) == s}

    def _loop(self) -> None:
        while not self._stop.wait(self.every):
            self.look()

    def close(self) -> set[int]:
        self._stop.set()
        self.look()
        return self.seen


def stop(pid: int, grace: float = 3.0, also_group: bool = False, also: set[int] | None = None) -> set[int]:
    """Stop every descendant of ``pid`` and the process groups they lead or share (never this process's own group,
    nor the caller's): SIGTERM, then SIGKILL after ``grace`` seconds for what is left, scanning again for anything
    started meanwhile. With ``also_group``, ``pid``'s own group too (a child started in a session of its own); ``also``,
    pids seen under it before (a ``Watch``'s), stopped too while they live; or a function asked for them at each round
    (a ``Watch``'s ``still``: only those still the process seen), and then ``pid`` is looked under only while it is
    among them. Returns the pids it signalled."""
    mine = {os.getpgrp()}
    seen: set[int] = set() if callable(also) else set(also or ())
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 1.0)):
        if callable(also):
            known = set(also())
            under = pid in known                        # (``pid`` used again by another: not looked under)
        else:
            if sig == signal.SIGKILL and seen and not _alive(seen - {os.getpid()}):
                break                                   # all gone: ``pid`` may be another's now, so not looked under again
            known, under = (_alive(seen) if seen else set()), True
        procs = tree()
        pids = (descendants(pid, procs) if under else set()) | known
        groups = {procs[p][1] for p in pids if p in procs} - mine
        if also_group and under and pid in procs and procs[pid][1] not in mine:
            groups.add(procs[pid][1])
        groups.discard(0)
        seen |= pids
        if not pids and not groups:
            break
        _signal(pids - {os.getpid()}, groups, sig)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and _alive(pids - {os.getpid()}):
            time.sleep(0.05)
    return seen
