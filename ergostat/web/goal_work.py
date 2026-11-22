"""Per-goal background work (a loop's performance, ``control_api.summary``): one table keyed ``(goal, what, window)``
with the time each was worked out. A request is answered at once with what the table holds (``None``: not yet); one
thread fills it goal by goal, the most recently asked first (by the asks' sequence, then the order the goals were
asked in), and among those the never-worked-out before the oldest past its life. A key not asked for in ``forsake``
seconds is no longer worked out (a moment left on the header's slider, a page closed), and of each kind at most
``windows`` windows are wanted at once: the least recently asked are let go. What was worked out and is no longer
wanted is dropped ``idle`` seconds after it was worked out. A pass starts another goal only while the time spent plus
the slowest one seen fits its budget: within ``budget`` unless one goal takes longer than any before it (work under
way is never cut short). The thread rests between passes and ends once nothing is wanted; the next ask starts it
again."""

from __future__ import annotations

import threading
import time

BUDGET = 2.0          # seconds of work in one pass
REST = 2.0            # seconds between passes: the page's other answers are served meanwhile
FORSAKE = 30.0        # a key not asked for this long is no longer worked out (the pages ask every 3 s)
IDLE = 600.0          # a worked-out entry no longer wanted is dropped this long after it was worked out
WINDOWS = 4           # of each kind, the windows (moments) wanted at once: the most recently asked


class GoalWork:
    def __init__(self, budget: float = BUDGET, rest: float = REST, idle: float = IDLE, background: bool = True,
                 forsake: float = FORSAKE, windows: int = WINDOWS):
        self.budget, self.rest, self.idle, self.background = budget, rest, idle, background
        self.forsake, self.windows = forsake, max(1, min(int(windows), 64))
        self.slowest = 0.0                       # the longest one goal's work has taken
        self._lock = threading.Lock()
        self._done: dict = {}                    # (goal, what, window) -> (worked out at, tag, value)
        self._wanted: dict = {}                  # (goal, what, window) -> (asked at, tag, compute, life, (ask, -i))
        self._asks = 0                           # how many asks: their order, never their wall times (lesson-2)
        self._forgotten = 0                      # how many times forget() was called
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def ask(self, what: str, goals, window, tag, compute, life: float) -> dict:
        """Each goal's value for ``tag`` (the model's version), ``None`` if not yet: by ``compute(goal, window)``."""
        now, out = time.time(), {}
        with self._lock:
            self._asks += 1
            for i, g in enumerate(goals):
                k = (g, what, window)
                self._wanted[k] = (now, tag, compute, life, (self._asks, -i))
                got = self._done.get(k)
                out[g] = got[2] if got and got[1] == tag else None
            last: dict = {}                      # this kind's windows, by their latest ask
            for k, w in self._wanted.items():
                if k[1] == what:
                    last[k[2]] = max(last.get(k[2], 0), w[4][0])
            keep = set(sorted(last, key=last.get, reverse=True)[:self.windows])
            for k in [k for k in self._wanted if k[1] == what and k[2] not in keep]:
                del self._wanted[k]
            if self.background and self._thread is None and not self._stop.is_set():
                self._thread = threading.Thread(target=self._run, name="goal-work", daemon=True)
                self._thread.start()
        return out

    def forget(self, what: str | None = None) -> None:
        """Drop what was worked out (of one kind), so it is worked out again: a decision changed what it reads."""
        with self._lock:
            self._forgotten += 1                 # work under way now read what was before: never kept (run_pass)
            for k in [k for k in self._done if what is None or k[1] == what]:
                del self._done[k]

    def stop(self) -> None:
        self._stop.set()

    def _next(self, now: float):
        """The key to work out next: of the most recently asked, one never worked out (or under another tag) first, in
        the order asked, else the oldest past its life."""
        age = lambda k, tag: float("inf") if (got := self._done.get(k)) is None or got[1] != tag else now - got[0]  # noqa: E731
        due = {k: (w[4][0], a == float("inf"), w[4][1] if a == float("inf") else a)
               for k, w in self._wanted.items() if (a := age(k, w[1])) >= w[3]}
        return max(due, key=due.get, default=None)

    def run_pass(self) -> int:
        """Work out goals until the budget would be passed; how many were worked out."""
        start, n = time.monotonic(), 0
        with self._lock:                         # what nobody asks for any more is let go
            now = time.time()
            for k in [k for k, w in self._wanted.items() if now - w[0] > self.forsake]:
                del self._wanted[k]
            for k in [k for k, d in self._done.items() if k not in self._wanted and now - d[0] > self.idle]:
                del self._done[k]
        while not self._stop.is_set():
            if n and time.monotonic() - start + self.slowest > self.budget:
                break
            with self._lock:
                k = self._next(time.time())
                if k is None:
                    break
                _, tag, compute, _life, _order = self._wanted[k]
                seen = self._forgotten
            t0 = time.monotonic()
            try:
                value = compute(k[0], k[2])
            except Exception as e:               # said, never shown as 'being worked out' for ever
                value = {"failed": f"{type(e).__name__}: {e}"}
            with self._lock:
                self.slowest = max(self.slowest, time.monotonic() - t0)
                if seen == self._forgotten:
                    self._done[k] = (time.time(), tag, value)
            n += 1
        return n

    def _run(self) -> None:
        while True:
            self.run_pass()
            with self._lock:
                if not self._wanted or self._stop.is_set():
                    self._thread = None
                    return
            self._stop.wait(self.rest)
