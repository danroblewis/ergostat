"""The daemons' supervisor (SPEC §9.7): one thread, never the engine's loop, that keeps each daemon running. A daemon
that exits, goes silent past its heartbeat, or stops reading its standard input (an alarm) is restarted after a
back-off; one that holds a cancelled run past the grace too. More than ``restart: max`` restarts within ``within`` and
it is given up (``ergostat.daemon.failed``, an intervention). A crash fails its runs in flight, counted; a restart
for anything else gives them back uncounted. On a model swap a changed daemon is sent ``stop`` and drained. Its state
goes to ``<state>/daemons.json`` for the page."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque

from .. import runner as old
from ..costs.sampler import Sampler
from ..leases.kill import grace
from ..library import reap
from .proc import Handle, Process

SOURCE = "ergostat"
TICK = 0.2
WRITE_EVERY = 2.0
SAMPLER = Sampler(30.0)        # the daemons' CPU and memory, sampled every 30 s: one ps for all, not one a second


class Slot:
    """A daemon by name: its definition, its process now, its restarts."""

    def __init__(self, d):
        self.d, self.proc, self.tracked = d, None, None
        self.state, self.why, self.next_at = "starting", "", 0.0
        self.restarts: deque[float] = deque()
        self.total, self.alarm = 0, None
        self.room = threading.Semaphore(d.concurrency)
        self.up = threading.Event()


class Supervisor:
    def __init__(self, eng):
        self.e = eng
        self.lock = threading.RLock()
        self.slots: dict[str, Slot] = {}
        self.draining: list[tuple[Slot, Process]] = []
        self.push: dict[tuple[str, str], object] = {}
        self.thread: threading.Thread | None = None
        self.written = 0.0

    # ---- the model's daemons

    def sync(self, spec) -> None:
        """The daemons this model uses: a new one started, one changed or no longer used drained."""
        used = {b.params["daemon"] for b in spec.blocks.values() if b.params.get("daemon")}
        used |= {s.daemon for s in spec.sensors() if s.daemon}
        with self.lock:
            for n, slot in list(self.slots.items()):
                if n not in used or spec.daemons.get(n) != slot.d:
                    self._drain(slot, "its definition changed" if n in used else "nothing uses it now")
                    del self.slots[n]
            for n in used - set(self.slots):
                self.slots[n] = Slot(spec.daemons[n])
                self._start(self.slots[n])                # at once: the first readings asked find it there
            self.push = {(s.daemon, f"{s.of.name}.{s.name}"): s for s in spec.sensors() if s.daemon and s.push}
            if self.slots and (self.thread is None or not self.thread.is_alive()):
                self.thread = threading.Thread(target=self._loop, name="ergostat-daemons", daemon=True)
                self.thread.start()

    def _drain(self, slot: Slot, why: str) -> None:
        slot.up.clear()
        if slot.proc is not None:
            self.e.say(f"daemon {slot.d.name}: {why}: stopping once it finishes what it holds")
            slot.proc.stop()
            slot.proc.idle_since = time.monotonic() if not slot.proc.runs else None
            self.draining.append((slot, slot.proc))

    # ---- the loop

    def _loop(self) -> None:
        while not self.e.stop.is_set():
            try:
                self.tick()
            except Exception as err:                 # the supervisor never stops for one daemon's trouble
                self.e.say(f"daemons: {type(err).__name__}: {err}")
            self.e.stop.wait(TICK)

    def tick(self) -> None:
        now = time.monotonic()
        with self.lock:
            for slot in list(self.slots.values()):
                if slot.state in ("starting", "backoff") and now >= slot.next_at:
                    self._start(slot)
                elif slot.state == "running" and (why := self._trouble(slot, now)):
                    self._restart(slot, *why)
            for slot, p in list(self.draining):
                if p.ended.is_set():
                    p.fail_all(f"its daemon {slot.d.name} ended while draining", False)
                    self._finished(slot, p)
                    self.draining.remove((slot, p))
                elif (p.idle_since is not None and now - p.idle_since > grace()) or self._late(p, now):
                    self._kill(p)
        if now - self.written >= WRITE_EVERY:
            self.write()

    def _trouble(self, slot: Slot, now: float) -> tuple[str, bool] | None:
        """Why a running daemon must be restarted, and whether that raises an alarm; None while it is well."""
        p, d = slot.proc, slot.d
        if p.ended.is_set():
            return f"exited {p.proc.returncode}", False
        if p.full or (p.writing_since is not None and now - p.writing_since > d.stdin_timeout):
            return f"did not read its standard input for {d.stdin_timeout:g}s", True
        if d.heartbeat and now - p.last_out > d.heartbeat:
            return f"silent for {now - p.last_out:.0f}s (heartbeat {d.heartbeat:g}s)", False
        with p.lock:
            expired = [(r, h) for r, h in p.requests.items() if h.deadline is not None and now > h.deadline]
            for r, _ in expired:
                p.requests.pop(r, None)
        for _, h in expired:
            h.answer(None, "no answer from its daemon in time")
        if late := self._late(p, now):
            return f"still held run {late[:8]} {grace():g}s after it was cancelled", False
        return None

    def _late(self, p: Process, now: float) -> str | None:
        """A run it still holds past the grace after it was cancelled."""
        with p.lock:
            return next((r for r, h in p.runs.items() if h.cancelled is not None and now - h.cancelled > grace()), None)

    def _start(self, slot: Slot) -> None:
        log = open(old.log_path(self.e.p, f"daemon-{slot.d.name}"), "a", encoding="utf-8")
        from ..spec.engine import callback_env
        try:
            slot.proc = Process(slot.d, self.e.spec.root, callback_env(self.e.spec, self.e.p.dir, self.e.socket), log,
                                lambda s, v, n=slot.d.name: self._pushed(n, s, v))
        except OSError as err:
            slot.proc = None
            log.close()
            self._restart(slot, f"could not start: {err}", False)
            return
        slot.tracked = SAMPLER.track(slot.proc.proc)
        slot.state, slot.why = "running", ""
        slot.up.set()
        self.e.p.events.add("ergostat.daemon.started", item=slot.d.name, source=SOURCE,
                            data={"daemon": slot.d.name, "pid": slot.proc.pid, "restarts": len(slot.restarts)})

    def _finished(self, slot: Slot, p: Process) -> dict:
        p.log.close()
        return SAMPLER.finish(slot.tracked) if slot.tracked is not None and slot.tracked.proc is p.proc else {}

    def _kill(self, p: Process) -> None:
        if not getattr(p, "killing", False):
            p.killing = True
            threading.Thread(target=reap.stop, args=(p.pid,), kwargs={"grace": grace(), "also_group": True,
                                                                      "also": {p.pid}}, daemon=True).start()

    def _restart(self, slot: Slot, why: str, alarm: bool) -> None:
        p, d, now = slot.proc, slot.d, time.monotonic()
        slot.proc = None
        slot.up.clear()
        res = {}
        if p is not None:
            crashed = p.ended.is_set()
            p.fail_all(f"its daemon {d.name} {why}", requeue=not crashed)
            if not crashed:
                self._kill(p)
            res = self._finished(slot, p)
        slot.restarts.append(now)
        while slot.restarts and now - slot.restarts[0] > d.within:
            slot.restarts.popleft()
        slot.total, slot.why = slot.total + 1, why
        n = len(slot.restarts)
        data = {"daemon": d.name, "why": why, "pid": p.pid if p else None, "restarts": n, "within": d.within,
                **({"exit": p.proc.returncode} if p and p.ended.is_set() else {}), **({"resources": res} if res else {})}
        if alarm:
            slot.alarm = {"why": why, "at": time.time()}
        if n > d.restarts:
            slot.state = "failed"
            slot.alarm = {"why": f"given up after {n} restarts within {d.within:g}s: {why}", "at": time.time()}
            self.e.p.events.add("ergostat.daemon.failed", item=d.name, source=SOURCE,
                                data={**data, "intervention": True, "class": f"alarm:daemon:{d.name}",
                                      "users": self.users(d.name)})
            self.e.say(f"daemon {d.name}: given up after {n} restarts within {d.within:g}s ({why}): alarm raised")
            return
        wait = min(d.backoff[0] * 2 ** (n - 1), d.backoff[1])
        slot.state, slot.next_at = "backoff", now + wait
        self.e.p.events.add("ergostat.daemon.restarted", item=d.name, source=SOURCE,
                            data={**data, "wait": wait, **({"alarm": True} if alarm else {})})
        self.e.say(f"daemon {d.name}: {why}: restarting in {wait:g}s" + (" (alarm raised)" if alarm else ""))

    # ---- work handed to it

    def run_item(self, b, run: str, ctx: dict, env: dict, take, timeout: float | None,
                 item: str | None, fence: int | None) -> tuple[int | None, str, bool]:
        """One run of ``b`` handed to its daemon, waited for on the run's own thread. Returns its exit (None when it
        never said ``done``), its note, and whether its item is given back uncounted."""
        name = b.params["daemon"]
        with self.lock:
            slot = self.slots.get(name)
        if slot is None:
            return None, f"its daemon {name} is not running", True
        limit = time.monotonic() + (timeout or 300.0)
        if not slot.up.wait(max(0.0, limit - time.monotonic())) or not slot.room.acquire(
                timeout=max(0.0, limit - time.monotonic())):
            return None, f"its daemon {name} is {slot.state}" + (f": {slot.why}" if slot.why else ""), slot.state != "failed"
        try:
            h = Handle(take, block=b.name)
            p = slot.proc
            if p is None:
                return None, f"its daemon {name} is {slot.state}: {slot.why}", True
            p.hold(run, h, {"op": "item", "run": run, "item": item, "lease": ctx.get("lease"), "input": ctx,
                            "env": {k: v for k, v in env.items() if k.startswith("ERGOSTAT_")}})
            if not h.done.wait(max(0.0, limit - time.monotonic())):
                self.cancel(run, "its timeout")
                h.done.wait(grace() + 10 * TICK + 5)
                return h.code, h.note or f"stopped after its timeout of {timeout:g}s", h.requeue
            note = "stopped as the owner asked" if h.asked and h.code else h.note
            return h.code, note, h.requeue
        finally:
            slot.room.release()

    def _procs(self) -> list[Process]:
        with self.lock:
            return [s.proc for s in self.slots.values() if s.proc] + [p for _, p in self.draining]

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

    def read(self, s, answer) -> None:
        """A reading asked of a sensor's daemon, never waited on: ``answer(value, why)`` is called once, later."""
        with self.lock:
            slot = self.slots.get(s.daemon)
            p = slot.proc if slot is not None and slot.state == "running" else None
        if p is None:
            answer(None, f"its daemon {s.daemon} is {slot.state if slot else 'not running'}")
            return
        req = uuid.uuid4().hex[:16]
        p.ask(req, Handle(answer=answer, deadline=time.monotonic() + s.timeout),
              {"op": "read", "sensor": f"{s.of.name}.{s.name}", "request": req})

    def _pushed(self, daemon: str, sensor, value) -> bool:
        s = self.push.get((daemon, sensor)) if isinstance(sensor, str) else None
        if s is None or isinstance(value, bool) or not isinstance(value, int | float):
            return False
        self.e.results.put((s, float(value), "", time.time(), None))
        self.e.wake.set()
        return True

    # ---- what is seen of them

    def users(self, name: str) -> list[str]:
        spec = self.e.spec
        return [f"block.{b.name}" for b in spec.blocks.values() if b.params.get("daemon") == name] + \
            [f"sensor.{s.of.name}.{s.name}" for s in spec.sensors() if s.daemon == name]

    def status(self) -> dict:
        out = {}
        with self.lock:
            for n, slot in self.slots.items():
                p, t = slot.proc, slot.tracked
                res = t.result() if t is not None and p is not None and t.proc is p.proc else {}
                out[n] = {"state": slot.state, "pid": p.pid if p else None, "why": slot.why, "alarm": slot.alarm,
                          "last_line": time.time() - time.monotonic() + p.last_out if p else None, "restarts": len(slot.restarts),
                          "restarts_total": slot.total, "in_flight": len(p.runs) if p else 0, "served": p.served if p else 0,
                          "concurrency": slot.d.concurrency, "users": self.users(n), "cpu": res.get("cpu"),
                          "memory": res.get("memory_peak"), "run": slot.d.run}
        return out

    def write(self, final: bool = False) -> None:
        self.written = time.monotonic()
        got = self.status()
        if final:
            for x in got.values():
                x["state"], x["pid"] = "stopped", None
        f = self.e.p.dir / "daemons.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps({"at": time.time(), "pid": os.getpid(), "daemons": got}))
        os.replace(tmp, f)

    def close(self) -> None:
        """Ergostat stopping: each daemon asked to stop, killed if it has not within the grace."""
        procs = self._procs()
        for p in procs:
            p.stop()
        deadline = time.monotonic() + min(grace(), 3.0)
        while any(not p.ended.is_set() for p in procs) and time.monotonic() < deadline:
            time.sleep(0.05)
        for p in procs:
            if not p.ended.is_set():
                reap.stop(p.pid, grace=1.0, also_group=True, also={p.pid})
            p.fail_all(old.STOPPED_WITH_US, True)
        if self.slots or self.draining:
            self.write(final=True)


def read_status(state_dir) -> dict:
    """``<state>/daemons.json``, as the engine last wrote it (none: {})."""
    try:
        return json.loads((state_dir / "daemons.json").read_text()).get("daemons") or {}
    except (OSError, ValueError):
        return {}
