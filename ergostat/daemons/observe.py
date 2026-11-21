"""A sensor daemon's observations, capped (SPEC §9.7): at most ``OBSERVE_PER_S`` lines a sensor in a one-second
window, accepted and refused alike. A window opens at a sensor's first line and closes once a line, the supervisor's
tick or ergostat's stop finds it a second old; lines past the cap are dropped and counted, not recorded and not logged
one by one, and a window's count is said once, by whichever of those comes first (``sensor.refused`` with
``dropped``). The window is read, judged and written under ``Observed.lock``; what is recorded, after it is let go."""

from __future__ import annotations

import threading
import time

OBSERVE_PER_S = 50          # a sensor's observation lines in one second, at most (more are dropped and counted)
_now = time.monotonic       # (a module attribute: tests set the clock)


class Window:
    __slots__ = ("t0", "n", "dropped")

    def __init__(self, t0: float):
        self.t0, self.n, self.dropped = t0, 0, 0


def why(n: int) -> str:
    return f"{n} observations dropped: more than {OBSERVE_PER_S} a second"


class Observed:
    def __init__(self):
        self.lock = threading.Lock()
        self.windows: dict[str, Window] = {}

    @staticmethod
    def _decide(w: Window | None, now: float) -> tuple[bool, bool]:
        """(a new window opened?, this line taken?), from the window as read."""
        fresh = w is None or now - w.t0 >= 1.0
        return fresh, fresh or w.n < OBSERVE_PER_S

    def admit(self, sensor: str, now: float | None = None) -> tuple[bool, int]:
        """One line of ``sensor``'s: whether it is taken, and the drops of its window just closed, to be said now."""
        now = _now() if now is None else now
        with self.lock:
            w = self.windows.get(sensor)
            fresh, ok = self._decide(w, now)
            closed = w.dropped if fresh and w is not None else 0
            if fresh:
                w = self.windows[sensor] = Window(now)
            w.n += 1
            w.dropped += not ok
            return ok, closed

    def flush(self, now: float | None = None, every: bool = False) -> list[tuple[str, int]]:
        """The windows a second old (``every``: all of them) closed: each one's drops, popped, to be said once."""
        now = _now() if now is None else now
        with self.lock:
            done = [s for s, w in self.windows.items() if every or now - w.t0 >= 1.0]
            return [(s, w.dropped) for s in done if (w := self.windows.pop(s)).dropped]
