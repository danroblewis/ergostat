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


def tree() -> dict[int, tuple[int, int]]:
    """Every process: pid → (parent pid, process group)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    got = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and all(x.isdigit() for x in parts):
            got[int(parts[0])] = (int(parts[1]), int(parts[2]))
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
    left (its parent killed, or gone) is still known when the time comes to stop it."""

    def __init__(self, pid: int, every: float = 0.5):
        self.pid, self.every, self.seen = pid, every, set()
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True, name="reap-watch")
        self._t.start()

    def look(self) -> None:
        self.seen |= descendants(self.pid)

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
    pids seen under it before (a ``Watch``'s), stopped too while they live. Returns the pids it signalled."""
    mine = {os.getpgrp()}
    seen: set[int] = set(also or ())
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 1.0)):
        if sig == signal.SIGKILL and seen and not _alive(seen - {os.getpid()}):
            break                                       # all gone: ``pid`` may be another's now, so not looked under again
        procs = tree()
        pids = descendants(pid, procs) | (_alive(seen) if seen else set())
        groups = {procs[p][1] for p in pids if p in procs} - mine
        if also_group and pid in procs and procs[pid][1] not in mine:
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
