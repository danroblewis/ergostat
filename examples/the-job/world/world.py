"""The job's world, simulated: everything outside ergostat that a senior engineer's day is made of.

Teammates open pull requests and ask for reviews, chat channels talk, the pager fires, teams ask to
ramp feature flags, secrets age toward expiry, the CI server releases new versions, customers file
tickets, changes move through their paper trail, outages happen and leave postmortem actions. And
"me", the owner, decides and performs (world/me.py): faster on what was prepared for them.

Nothing here talks to ergostat. The world keeps its state in run/world/state.json and appends what
happens to run/world/feed.jsonl, the way a real system has an API and a stream of changes; the
watchers (bin/watch.py) read it, as they would read the code host, the chat, the pager or the
tracker. Whoever reads it first advances it to now: the world is a function of the clock.

Time: one working day is JOB_DAY seconds (default 60), so a five-minute run is a working week.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import random
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "run" / "world"
OUTBOX = ROOT / "outbox"
DAY = float(os.environ.get("JOB_DAY", "60"))
GH = os.environ.get("JOB_GH") == "1"              # the code host is read for real (bin/codehost.py): no simulated PRs
STEP = DAY / 24                                    # the world moves in steps of a third of a working hour


def days(n: float) -> float:
    """n working days, in seconds."""
    return n * DAY


def u(a: float, b: float) -> float:
    """A duration between a and b working days, in seconds."""
    return days(random.uniform(a, b))


def draft(item: str) -> Path:
    """Where a preparer leaves its draft for an item: outbox/review-2041.md."""
    return OUTBOX / (item.replace("/", "-") + ".md")


def drafted_at(item: str) -> float | None:
    p = draft(item)
    return p.stat().st_mtime if p.exists() else None


class World:
    """The state, and the feed it appends to while it moves."""

    def __init__(self, state: dict):
        self.s = state
        self.out: list[dict] = []

    @property
    def now(self) -> float:
        return self.s["now"]

    def next_id(self, kind: str, start: int) -> int:
        n = self.s["ids"].get(kind, start) + 1
        self.s["ids"][kind] = n
        return n

    def emit(self, kind: str, item: str, type: str, **data) -> None:
        self.out.append({"t": self.now, "kind": kind, "item": item, "type": type, "data": data})

    def things(self, kind: str) -> dict:
        return self.s["things"].setdefault(kind, {})

    def add(self, kind: str, item: str, type: str, **data) -> dict:
        thing = {"t": self.now, **data}
        self.things(kind)[item] = thing
        self.emit(kind, item, type, **{k: v for k, v in data.items() if not k.startswith("_")})
        return thing

    # the calendar: working days from the first, Monday to Friday
    def day_index(self, t: float | None = None) -> int:
        return int(((self.now if t is None else t) - self.s["t0"]) // DAY)

    def date(self, k: int | None = None) -> str:
        k = self.day_index() if k is None else k
        d = dt.date.fromisoformat(self.s["start"])
        while k > 0:
            d += dt.timedelta(days=1)
            if d.weekday() < 5:
                k -= 1
        return d.isoformat()

    def clock(self, t: float | None = None) -> str:
        """The working time of t: 2026-11-16 10:30 (a working day runs 09:00 to 17:00)."""
        t = self.now if t is None else t
        k = self.day_index(t)
        frac = (t - self.s["t0"]) / DAY - k
        mins = int(9 * 60 + frac * 8 * 60)
        return f"{self.date(k)} {mins // 60:02d}:{mins % 60:02d}"

    def busy(self) -> float:
        """How stretched I am: an outage I am in takes most of me."""
        return 3.0 if any(o.get("declared") and not o.get("resolved") for o in self.things("outage").values()) else 1.0


def first_monday() -> str:
    """The simulated week starts on this week's Monday (next week's, at a weekend)."""
    d = dt.date.today()
    d += dt.timedelta(days=7 - d.weekday()) if d.weekday() >= 5 else -dt.timedelta(days=d.weekday())
    return d.isoformat()


@contextmanager
def advanced(now: float | None = None):
    """The world, moved on to now (under a lock): yields it, then saves it and appends what happened to the feed."""
    from world import me, traffic
    RUN.mkdir(parents=True, exist_ok=True)
    OUTBOX.mkdir(exist_ok=True)
    now = time.time() if now is None else now
    with open(RUN / ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = RUN / "state.json"
        fresh = not path.exists()
        state = json.loads(path.read_text()) if not fresh else {
            "t0": now, "now": now, "start": first_monday(), "ids": {}, "things": {}, "log": []}
        w = World(state)
        if fresh:
            traffic.seed(w)
        t = state["now"]
        while t < now:
            step = min(STEP, now - t)
            t += step
            state["now"] = t
            traffic.step(w, step / DAY)
            me.step(w)
        state["now"] = now
        yield w
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(path)
        if w.out:
            with open(RUN / "feed.jsonl", "a") as f:
                for e in w.out:
                    f.write(json.dumps(e) + "\n")
            w.out = []


def feed(after: int) -> tuple[list[dict], int]:
    """What the feed has said since byte offset `after`, and the new offset."""
    path = RUN / "feed.jsonl"
    if not path.exists():
        return [], 0
    with open(path, "rb") as f:
        f.seek(after)
        data = f.read()
    end = data.rfind(b"\n") + 1
    return [json.loads(x) for x in data[:end].splitlines() if x.strip()], after + end
