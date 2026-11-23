"""A node run's two deadlines, as its keeper holds them (SPEC §12s.5): the wall (its start plus ``limits.wall``) and its
lease's expiry, both read from ``runs/RUN/deadline`` every quarter second. The file is
``{"wall": T, "lease": T or null, "kill": K}``: ``T`` seconds on ``CLOCK`` (the same on every process of the machine),
``K`` the seconds from SIGTERM to SIGKILL. ``start`` writes the first; the lease's renewals rewrite it.

``CLOCK`` counts suspend, so a machine asleep past a deadline ends the run when it wakes, and the time of day is never
read: ``CLOCK_BOOTTIME`` on Linux; elsewhere ``CLOCK_MONOTONIC``, which on macOS is the continuous clock
(``mach_continuous_time``, counting sleep; Python's own ``time.monotonic`` there is not)."""

import json
import math
import os
import time

CLOCK = getattr(time, "CLOCK_BOOTTIME", time.CLOCK_MONOTONIC)
CLOCK_NAME = "CLOCK_BOOTTIME" if hasattr(time, "CLOCK_BOOTTIME") else "CLOCK_MONOTONIC"
DAY = 86400.0
MOST_KILL = 600.0


def now() -> float:
    return time.clock_gettime(CLOCK)


def kill_after(ttl: float) -> float:
    """K for a lease of ``ttl`` seconds: grace(ttl)/4, grace(ttl) = max(1, min(0.1 ttl, 30)) (leases/terms.py)."""
    return max(1.0, min(0.1 * ttl, 30.0)) / 4


def _at(v, at: float) -> bool:
    return not isinstance(v, bool) and isinstance(v, int | float) and math.isfinite(v) and v <= at + DAY


def read(path: str) -> tuple[float, float | None, float] | None:
    """``(wall, lease, kill)`` from the file, or None when it can't be read or is not that shape: a time that is not
    a finite number within a day from now, a ``kill`` not 0 to 600 seconds."""
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(got, dict):
        return None
    wall, lease, kill, at = got.get("wall"), got.get("lease"), got.get("kill"), now()
    if not (_at(wall, at) and (lease is None or _at(lease, at)) and _at(kill, 0) and 0 <= kill <= MOST_KILL):
        return None
    return float(wall), None if lease is None else float(lease), float(kill)


def write(path: str, wall: float, lease: float | None, kill: float) -> None:
    """The file whole or not at all (a temporary file, then replaced)."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps({"wall": wall, "lease": lease, "kill": kill}))
    os.replace(tmp, path)


class Held:
    """The deadlines a keeper holds. ``look`` takes the file again: the wall never moves later, whatever the file
    says; the lease moves to a well-formed file's (its renewals are the engine's word), but a ``null`` there never
    drops one held. A file that can't be read, or is garbage, keeps the last values."""

    def __init__(self, path: str):
        got = read(path)
        if got is None:
            raise ValueError("its deadline file is unreadable")     # (not started: never a run with no deadline)
        self.path, (self.wall, self.lease, self.kill) = path, got

    def look(self) -> None:
        got = read(self.path)
        if got is not None:
            self.wall = min(self.wall, got[0])
            self.lease = self.lease if got[1] is None else got[1]
            self.kill = got[2]

    def next(self) -> float:
        return self.wall if self.lease is None else min(self.wall, self.lease)

    def due(self, at: float) -> str | None:
        """``wall`` or ``lease``, whichever is the earlier, once it has passed; None before."""
        if at < self.next():
            return None
        return "wall" if self.lease is None or self.wall <= self.lease else "lease"
