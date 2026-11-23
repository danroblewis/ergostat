"""A queue's shared environment (SPEC §9.5, *Faults*): ``takes: {..., faults: {healthy: R}}``. While R does not read
healthy the block takes no new item; a run that fails while it is not, or after it was not since the run was taken, is
given back uncounted with the cause on the item; the queue resumes by itself when R reads healthy again.

R is a part's reading (``sensor.NAME``: the stock, flow or auxiliary NAME that a sensor reads; or ``stock.``,
``flow.``, ``auxiliary.NAME``), healthy above 0; a goal (``goal.NAME``), healthy while it holds (its ``.off`` is 0); or
a command (``block.NAME[.PORT]``: what that block outputs), healthy above 0. Unknown (no reading, not a number, a stale
reading, a goal whose part is stale) is never healthy: it holds the queue as an outage does, and says so (for
``QUIET`` after the engine's start, while a first reading may still be coming: held, unsaid).

The hold is an event about the block, ``ergostat.queue.held`` (``block``, ``healthy``, ``cause``: unhealthy or
unknown, ``why``, ``since``), and its end ``ergostat.queue.resumed`` (the same, with ``until`` and ``held``, seconds,
caused by the hold). A hold an earlier engine left open is taken up from the record, so it is ended once."""

from __future__ import annotations

import re
import time

from ..spec.ir import Ref
from ..spec.observer import stale_age
from .poolnow import unread

HELD, RESUMED = "ergostat.queue.held", "ergostat.queue.resumed"
SENSOR = re.compile(r"^sensor\.([a-z][a-z0-9-]*)$")
PARTS = ("stock", "flow", "auxiliary")
SOURCE = "ergostat"
QUIET = 30.0          # seconds after the engine starts (or wakes) that an unknown holds unsaid: its first reading due


# ---- the model: compiled and checked

def compile_healthy(c, raw, what: str) -> Ref | None:
    """``faults: {healthy: R}`` in a block's ``takes:`` (None without it). ``sensor.NAME`` is resolved by ``check``."""
    f = raw.get("faults")
    if f is None:
        return None
    w = f"{what}.takes.faults"
    if not isinstance(f, dict) or "healthy" not in f:
        c.err(f"{w}: a map with healthy: (a sensor, goal or command; faults: {{healthy: sensor.NAME}})", raw.at("faults"),
              "bad-takes")
        return None
    c.keys(f, {"healthy"}, w)
    x = f["healthy"]
    m = SENSOR.match(x) if isinstance(x, str) else None
    if m:
        return Ref("sensor", m.group(1))
    return c.ref(x, raw.at("faults"), f"{w}.healthy", (*PARTS, "goal", "block"))


def check(c, spec, b) -> None:
    """The part ``healthy:`` names exists (a ``sensor.NAME`` a part that a sensor reads); else it is refused."""
    r, what = b.takes.healthy, f"block {b.name}.takes.faults.healthy"
    if r is None:
        return
    if r.kind == "sensor":
        got = [k for k in PARTS if getattr(spec.measured(k).get(r.name), "sensors", None)]
        if got:
            b.takes.healthy = Ref(got[0], r.name)
            return
        names = [n for k in PARTS for n, t in spec.measured(k).items() if t.sensors]
        bad = f"{r.name!r} is not a stock, flow or auxiliary that a sensor reads" + c.suggest(r.name, names)
    elif r.kind in PARTS:
        bad = (f"{r}: the {r.kind}'s reading itself (no port)" if r.port else "" if r.name in spec.measured(r.kind)
               else f"{r} is not a {r.kind} of the model" + c.suggest(r.name, spec.measured(r.kind)))
    elif r.kind == "goal":
        bad = (f"{r}: the goal itself (no port; it is healthy while it holds)" if r.port else "" if r.name in spec.goals
               else f"{r} is not a goal of the model" + c.suggest(r.name, spec.goals))
    else:
        bad = (f"{r}: not its own command" if r.name == b.name else "" if r.name in spec.blocks
               else f"{r} is not a block of the model" + c.suggest(r.name, spec.blocks))
    if bad:
        c.err(f"{what}: {bad}", b.where, "unknown-ref")
        b.takes.healthy = None


# ---- the reading

def _stale(e, r: Ref, now: float) -> float | None:
    t = e.spec.measured(r.kind).get(r.name)
    seen = getattr(e, "seen", {})
    last = max((seen[s.series] for s in t.sensors.values() if s.series in seen), default=None) if t else None
    return stale_age(e.spec, Ref(r.kind, r.name), last, now, getattr(e, "born", None))


def read(e, r: Ref, now: float | None = None) -> tuple[bool | None, str]:
    """(True: healthy, False: not, None: unknown) and what was read, as the engine last read it (no sensor runs)."""
    now = time.time() if now is None else now
    try:
        if r.kind == "goal":
            g = e.spec.goals.get(r.name)
            age = _stale(e, g.of, now) if g is not None and g.of.kind in PARTS else None
            if g is None or r.name in getattr(e, "stale", {}) or age is not None:
                return None, f"{r}: its reading is stale" if g is not None else f"{r}: not in the model now"
            v = e.signals.get(f"goal.{r.name}.off")
            if unread(v):
                return None, f"{r}: not worked out yet"
            return v == 0, f"{r} {'holds' if v == 0 else 'is off'}"
        v = e.get(r)
        if unread(v):
            return None, f"{r} has no reading"
        age = _stale(e, r, now) if r.kind in PARTS else None
        if age is not None:
            return None, f"{r}: its reading is stale ({age:.0f}s old)"
        return v > 0, f"{r} reads {v:g}"
    except Exception as x:                                   # unreadable: unknown, never healthy
        return None, f"{r}: unreadable ({type(x).__name__}: {x})"


# ---- the hold, in the dispatcher

class Holds:
    """Each block's hold on its queue while its ``healthy`` is not healthy, and a count of the looks that found it so
    (a run whose block's count moved since it was taken ran through an outage)."""

    def __init__(self, eng):
        self.e = eng
        self.on: dict[str, dict] = {}       # block → its open hold (the event)
        self.bad: dict[str, int] = {}       # block → the looks that found it not healthy
        self.taken_up: set[str] = set()     # blocks whose open hold in the record was looked for

    def open(self, b) -> bool:
        """Whether the block may take now; a hold begun or ended is recorded. Before the engine's first pass has loaded
        the readings, and while an unknown is within ``QUIET`` of the engine's start, it takes nothing, records nothing."""
        r = b.takes.healthy if b.takes else None
        if r is None:
            if b.name in self.on:                              # (its faults: taken out of the model while it held)
                self.resume(b.name, self.on[b.name], "no healthy: in the model now")
                self.on.pop(b.name, None)
            return True
        ok, why = read(self.e, r)
        if not ok:
            self.bad[b.name] = self.bad.get(b.name, 0) + 1
        if not getattr(self.e, "measured", True) or (ok is None and b.name not in self.on
                                                     and time.time() - float(getattr(self.e, "born", 0.0)) < QUIET):
            return False                                       # (not read yet since it started or woke: held, unsaid)
        self.take_up(b.name)
        was = self.on.get(b.name)
        if ok and was is not None:
            self.resume(b.name, was, why)
            self.on.pop(b.name, None)
        elif not ok and was is None:
            cause = "unknown" if ok is None else "unhealthy"
            self.on[b.name] = self.e.p.events.add(HELD, item=b.name, source=SOURCE, data={
                "block": b.name, "healthy": str(r), "cause": cause, "why": why, "since": time.time()})
            self.e.say(f"{b.name}: {why} ({cause}): it takes nothing new until it reads healthy")
        return bool(ok)

    def resume(self, block: str, was: dict, why: str) -> None:
        now = time.time()
        since = float(was["data"].get("since") or was["time"])
        self.e.p.events.add(RESUMED, item=block, source=SOURCE, causedby=was["id"],
                            data={"block": block, "healthy": was["data"].get("healthy"), "why": why, "since": since,
                                  "until": now, "held": round(max(0.0, now - since), 1)})
        self.e.say(f"{block}: {why}: it takes again (held {(now - since) / 60:.1f} min)")

    def take_up(self, block: str) -> None:
        """Once a block: a hold an earlier engine recorded and never ended is this one's to end."""
        if block in self.taken_up:
            return
        got = self.e.p.events.query(n=1, item=block, type="ergostat.queue.*")
        self.taken_up.add(block)
        if got and got[-1]["type"] == HELD:
            self.on[block] = got[-1]

    def mark(self, block: str) -> int:
        return self.bad.get(block, 0)

    def fault(self, b, mark: int | None) -> str | None:
        """Why a run of ``b`` taken at ``mark`` is not to count: its ``healthy`` does not read healthy now, or did not
        at some look since it was taken (``mark`` None: not known, only now is read). None: healthy throughout."""
        r = b.takes.healthy if b is not None and b.takes else None
        if r is None:
            return None
        ok, why = read(self.e, r)
        if not ok:
            return f"{'unknown' if ok is None else 'unhealthy'}: {why}"
        if mark is not None and self.mark(b.name) != mark:
            return f"{r} was not healthy during the run"
        return None
