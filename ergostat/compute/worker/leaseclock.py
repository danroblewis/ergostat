"""The engine's lease renewals turned into its keeper's deadline, on the worker's own clock (SPEC §12s.5). Each engine
message carrying ``sent`` (its monotonic clock as it said it: ``start``'s lease, ``renew``, ``ping``) gives
``heard - sent``, ``heard`` on ``deadline.CLOCK``; ``base`` is the least of them over the last ``WINDOW`` seconds, a
difference only ever compared with others of its kind, never read as a time. ``renew {run, fence, left, sent}`` makes
the run's lease deadline ``sent + base + left``: the engine's expiry on this clock, late by at most the fastest transit
of the window however slow this renewal came. Written whole (``keeper.put``) under ``runs/.lock`` with its ``fence``;
an older fence is ignored, a renewal of the same or a newer one moves it either way. Only a renewal heard writes it."""

import collections
import fcntl
import json
import math
import os

import deadline
import keeper

WINDOW = 600.0


def _finite(v, most: float | None = None) -> bool:
    return (not isinstance(v, bool) and isinstance(v, int | float) and math.isfinite(v)
            and (most is None or abs(v) <= most))


class Clock:
    def __init__(self, root: str, now=deadline.now):
        self.runs, self.now = os.path.join(root, "runs"), now
        self.seen: collections.deque = collections.deque()   # (whole second heard, least heard - sent), rising
        self.fences: dict[str, int] = {}                     # (each run's fence as its start said it)

    def hear(self, sent) -> float | None:
        """``sent`` taken (anything but a finite number ignored); the least ``heard - sent`` of the window, or None."""
        at = self.now()
        if _finite(sent):
            d, sec = at - sent, math.floor(at)
            while self.seen and (self.seen[-1][1] >= d or self.seen[-1][0] == sec):
                d = min(d, self.seen.pop()[1])               # (one a second at most: never more than the window's)
            self.seen.append((sec, d))
        while self.seen and self.seen[0][0] < at - WINDOW - 1:
            self.seen.popleft()
        return self.seen[0][1] if self.seen else None

    def renew(self, req: dict, w) -> None:
        run, fence, left, sent = (req.get(k) for k in ("run", "fence", "left", "sent"))
        if not (type(fence) is int and fence >= 0 and _finite(left, deadline.DAY) and _finite(sent)):
            raise ValueError("renew: fence is a whole number, left and sent seconds (left within a day)")
        base = self.hear(sent)
        d = os.path.join(self.runs, run) if isinstance(run, str) and keeper.RUN.fullmatch(run) else None
        if d is None or not os.path.isdir(d):
            return w.send("refused", id=req["id"], run=run, why="no such run")
        path = os.path.join(d, "deadline")
        with open(os.path.join(self.runs, ".lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)             # (read, judged and written under one lock: two workers)
            held = deadline.read(path)
            if held is None or held[1] is None:          # (unreadable, or a run with no lease: never one made up)
                return w.send("refused", id=req["id"], run=run, why="no lease")
            try:
                with open(path, encoding="utf-8") as f:
                    was = json.load(f).get("fence")
            except (OSError, ValueError, AttributeError, RecursionError):
                was = None
            was = max(x for x in (was, self.fences.get(run), -1) if type(x) is int)
            if fence < was:
                return                                   # an older fence's word: ignored
            keeper.put(path, json.dumps({"wall": held[0], "lease": sent + base + left, "kill": held[2],
                                         "fence": fence}))

    def handlers(self, given: dict) -> dict:
        """``start`` and ``ping`` timed (then given on), and ``renew``."""
        start, ping = given["start"], given["ping"]

        def started(req: dict, w) -> None:
            lease = req.get("lease")
            if isinstance(lease, dict):
                self.hear(lease.get("sent"))
                if type(lease.get("fence")) is int and isinstance(req.get("run"), str) and keeper.RUN.fullmatch(req["run"]):
                    self.fences = {r: f for r, f in self.fences.items() if os.path.isdir(os.path.join(self.runs, r))}
                    self.fences[req["run"]] = lease["fence"]
            start(req, w)

        def pinged(req: dict, w) -> None:
            self.hear(req.get("sent"))
            ping(req, w)

        return {"start": started, "ping": pinged, "renew": self.renew}
