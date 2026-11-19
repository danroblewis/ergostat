"""What is handed to the daemons (SPEC §9.7): runs, readings, cancels; and push readings taken from them. A mixin of
the supervisor (``supervise.py``), whose ``slots``, ``draining`` and ``lock`` it reads.

A run is handed over only to the daemon running now under its name, checked and held under the supervisor's lock, so
a restart or a swap between the check and the hold never strands it on a process that is going; and only while its
lease is still its own. A daemon given up takes nothing: a run handed to it is given back at once, uncounted and put
off, and the dispatcher hands its block nothing until it is revived."""

from __future__ import annotations

import time
import uuid

from ..leases.kill import grace
from .proc import Handle, Process

FAILED_AFTER = 60.0            # seconds a run's item given back by a daemon given up is put off
PUSH_EVERY = 1.0               # a push sensor's readings, at most one a second (more are dropped)


class Hands:
    def _procs(self) -> list[Process]:
        with self.lock:
            return [s.proc for s in self.slots.values() if s.proc] + [p for _, p in self.draining]

    def run_item(self, b, run: str, ctx: dict, env: dict, take, timeout: float | None,
                 item: str | None, fence: int | None) -> tuple[int | None, str, dict | None]:
        """One run of ``b`` handed to its daemon, waited for on the run's own thread. Returns its exit (None when it
        never said ``done``), its note, and how its item is given back when that is not by its exit (a nack)."""
        name, h = b.params["daemon"], Handle(take, block=b.name)
        limit = time.monotonic() + (timeout or 300.0)
        line = {"op": "item", "run": run, "item": item, "lease": ctx.get("lease"), "input": ctx,
                "env": {k: v for k, v in env.items() if k.startswith("ERGOSTAT_")}}
        checked = not item
        while True:
            with self.lock:
                slot = self.slots.get(name)
                if slot is None or slot.state == "failed":
                    why = f"its daemon {name} " + ("has given up: " + slot.why if slot else "is not running")
                    return None, why, {"why": why, "count": False, "after": FAILED_AFTER}
                ready = slot.state == "running" and slot.proc is not None and len(slot.proc.runs) < slot.d.concurrency
                if ready and checked:
                    slot.proc.hold(run, h, line)
                    break
            if ready and not checked:                # its lease still its own (read outside the lock), then held
                if not self._leased(item, run, fence):
                    return None, "its lease ended before it was handed over", None
                checked = True
                continue
            if time.monotonic() > limit:
                return None, f"its daemon {name} took no run within its timeout ({slot.state})", {"why": "", "count": False}
            slot.up.wait(min(0.2, max(0.0, limit - time.monotonic())))   # (a restart, a swap, room: looked at again)
            time.sleep(0.02)
        if not h.done.wait(max(0.0, limit - time.monotonic())):
            self.cancel(run, "its timeout")
            h.done.wait(grace() + 7)
            return h.code, h.note or f"stopped after its timeout of {timeout:g}s", self._back(h)
        return h.code, "stopped as the owner asked" if h.asked and h.code else h.note, self._back(h)

    @staticmethod
    def _back(h: Handle) -> dict | None:
        return {"why": h.note, "count": False} if h.requeue else None

    def _leased(self, item: str, run: str, fence: int | None) -> bool:
        from ..leases.fold import held
        from ..spec import items as its
        it = its.one(self.e.p.events, self.e.spec, item)
        lease = held(it.fields) if it else None
        return bool(lease) and lease.get("holder") == run and (fence is None or lease.get("fence") == fence)

    def free(self, name: str) -> int:
        """How many more runs the daemon may hold, whichever block hands them (the dispatcher's room)."""
        with self.lock:
            slot = self.slots.get(name)
            if slot is None or slot.state == "failed":
                return 0
            return slot.d.concurrency - (len(slot.proc.runs) if slot.proc else 0)

    def _held(self, run: str) -> tuple[Process, Handle] | None:
        for p in self._procs():
            with p.lock:
                if run in p.runs:
                    return p, p.runs[run]
        return None

    def cancel(self, run: str, why: str, asked: bool = False, killing: bool = False) -> bool:
        """``cancel`` sent for a run a daemon holds (restarted if it holds it past the grace); False when none does."""
        got = self._held(run)
        if got is None or got[1].done.is_set():
            return False
        p, h = got
        h.asked = h.asked or asked
        if killing:                                  # (its lease expired: the run's note says so, leases/kill.py)
            with self.e.lock:
                self.e.killing[run] = why
        if h.cancelled is None:
            h.cancelled = time.monotonic()
            p.send({"op": "cancel", "run": run})
            p.log.write(f"cancel {run[:8]}: {why}\n")
        return True

    def stop_block(self, block: str) -> bool:
        """The owner's ``block NAME --stop``: each run of that block a daemon holds, cancelled."""
        runs = [r for p in self._procs() for r, h in list(p.runs.items()) if h.block == block]
        return any([self.cancel(r, "the owner's stop", asked=True) for r in runs])

    def read(self, s, answer) -> bool:
        """A reading asked of a sensor's daemon, never waited on: ``answer(value, why)`` is called once, later. False
        (nothing asked, nothing answered) when its daemon has given up: that is said once, by the daemon."""
        with self.lock:
            slot = self.slots.get(s.daemon)
            if slot is not None and slot.state == "failed":
                return False
            p = slot.proc if slot is not None and slot.state == "running" else None
        if p is None:
            answer(None, f"its daemon {s.daemon} is {slot.state if slot else 'not running'}")
            return True
        req = uuid.uuid4().hex[:16]
        p.ask(req, Handle(answer=answer, deadline=time.monotonic() + s.timeout),
              {"op": "read", "sensor": f"{s.of.name}.{s.name}", "request": req})
        return True

    def _pushed(self, daemon: str, sensor, value) -> bool:
        s = self.push.get((daemon, sensor)) if isinstance(sensor, str) else None
        if s is None or isinstance(value, bool) or not isinstance(value, int | float):
            return False
        now = time.monotonic()
        if now - self.pushed_at.get(s.series, 0.0) >= PUSH_EVERY:     # (more than one a second: dropped, not flooding)
            self.pushed_at[s.series] = now
            self.e.results.put((s, float(value), "", time.time(), None))
            self.e.wake.set()
        return True
