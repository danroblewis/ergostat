"""Restarts of the engine's process that did not help, backed off (SPEC §9.1). The watchdog, the startup deadline and
the outer watcher (``watcher.py``) each ask ``wait`` before they restart the engine, and ``note`` when they do. The
last restart is kept in ``<state>/restarts.json``, so the back-off outlives the process it restarts: a restart is
taken as having helped when the next is wanted more than ``HELPED`` (or twice its own wait) after it. The first
restart is at once; after one that did not help, the next waits ``FIRST`` from it, then twice as long each time, at
most ``MOST``: 60 s, 2 m, 4 m, ... 30 m."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

FIRST = 60.0
MOST = 1800.0
HELPED = 600.0
FILE = "restarts.json"


def _gap(n: int) -> float:
    """How long after restart ``n - 1`` restart ``n`` (counted from 1 in a run of restarts that did not help) waits."""
    return 0.0 if n <= 1 else min(FIRST * 2 ** (n - 2), MOST)


def _last(d: Path) -> dict:
    try:
        got = json.loads((Path(d) / FILE).read_text())
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _next(last: dict, now: float) -> int:
    if not last:
        return 1
    n = int(last.get("n", 1))
    return n + 1 if now - float(last.get("at", 0)) <= max(HELPED, 2 * _gap(n + 1)) else 1


def wait(d: Path, now: float | None = None) -> tuple[float, int]:
    """(seconds still to wait before the next restart, which restart it would be in this run of them)."""
    now = time.time() if now is None else now
    last = _last(d)
    n = _next(last, now)
    return (max(0.0, _gap(n) - (now - float(last.get("at", 0)))) if n > 1 else 0.0), n


def note(d: Path, why: str, by: str, now: float | None = None) -> int:
    """A restart done now: which it is in its run (1: the first, or the last one helped)."""
    now = time.time() if now is None else now
    n = _next(_last(d), now)
    path = Path(d) / FILE
    tmp = path.with_name(f"{FILE}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps({"at": now, "n": n, "why": why, "by": by}))
        os.replace(tmp, path)
    except OSError:
        pass
    return n
