"""The daemons' supervisor (SPEC §9.7): one thread, never the engine's loop, that keeps each daemon running. A daemon
that exits, goes silent past its heartbeat, or stops reading its standard input (an alarm) is restarted after a
back-off; one that holds a cancelled run past the grace too. More than ``restart: max`` restarts within ``within`` and
it is given up (``ergostat.daemon.failed``, an intervention) until the owner revives it (``block NAME --restart``,
recorded as ``daemon.restart.requested``, or any model change). Every process it ends, its whole process group goes
with it. What it hands out (runs, readings) is ``work.py``'s. Its state goes to ``<state>/daemons.json``."""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from collections import deque

from .. import runner as old
from ..costs.sampler import Sampler
from ..leases.kill import grace
from .proc import Process
from .work import Hands

SOURCE = "ergostat"
TICK = 0.2
WRITE_EVERY = 2.0
SAMPLER = Sampler(30.0, "ergostat-daemon-sampler")   # the daemons' CPU and memory, every 30 s: one ps for all


class Slot:
    """A daemon by name: its definition, its process now, its restarts."""

    def __init__(self, d):
        self.d, self.proc, self.tracked = d, None, None
        self.state, self.why, self.next_at = "starting", "", 0.0
        self.restarts: deque[float] = deque()
        self.total, self.alarm = 0, None
        self.up = threading.Event()


def killpg(pgid: int, wait: float) -> None:
    """Its whole process group (it leads a session of its own): TERM, then KILL after ``wait`` for what is left."""
    for sig, then in ((signal.SIGTERM, wait), (signal.SIGKILL, 0.0)):
        try:
            os.killpg(pgid, sig)
        except OSError:                              # (none left)
            return
        end = time.monotonic() + then
        while time.monotonic() < end:
            try:
                os.killpg(pgid, 0)
            except OSError:
                return
            time.sleep(0.05)


class Supervisor(Hands):
    def __init__(self, eng):
        self.e = eng
        self.lock = threading.RLock()
        self.slots: dict[str, Slot] = {}
        self.draining: list[tuple[Slot, Process]] = []
        self.push: dict[tuple[str, str], object] = {}
        self.pushed_at: dict[str, float] = {}
        self.put_off: dict[str, str] = {}                # item → the daemon given up that gave it back, put off
        self.thread: threading.Thread | None = None
        self.written = 0.0

    # ---- the model's daemons

    def sync(self, spec) -> None:
        """The daemons this model uses: a new one started, one changed or no longer used drained, one given up and
        written the same revived."""
        used = {b.params["daemon"] for b in spec.blocks.values() if b.params.get("daemon")}
        used |= {s.daemon for s in spec.sensors() if s.daemon}
        start = []
        with self.lock:
            for n, slot in list(self.slots.items()):
                if n not in used or spec.daemons.get(n) != slot.d or slot.state == "failed":
                    if slot.state == "failed":
                        self._release(n)
                    self._drain(slot, "its definition changed" if n in used else "nothing uses it now")
                    del self.slots[n]
            for n in used - set(self.slots):
                self.slots[n] = Slot(spec.daemons[n])
                start.append(self.slots[n])
            self.push = {(s.daemon, f"{s.of.name}.{s.name}"): s for s in spec.sensors() if s.daemon and s.push}
            if self.slots and (self.thread is None or not self.thread.is_alive()):
                self.thread = threading.Thread(target=self._loop, name="ergostat-daemons", daemon=True)
                self.thread.start()
        for slot in start:                           # at once: the first readings asked find it there
            self._start(slot)

    def revive(self, name: str) -> bool:
        """The owner's ``block NAME --restart``: a daemon given up (or any) started afresh, its restarts forgotten."""
        with self.lock:
            slot = self.slots.get(name)
            if slot is None:
                return False
            self._drain(slot, "the owner asked for a restart")
            slot = self.slots[name] = Slot(slot.d)
            self._release(name)
        self.e.say(f"daemon {name}: restarted, as the owner asked")
        self._start(slot)
        return True

    def _release(self, name: str) -> None:
        """(under the lock) The items a daemon given up gave back, put off: due again at once, now it runs."""
        mine = {i for i, d in self.put_off.items() if d == name}
        for i in mine:
            del self.put_off[i]
        self.e.dispatch.due_now |= mine

    def _drain(self, slot: Slot, why: str) -> None:
        """(under the lock) Its process sent ``stop``, kept until it holds nothing and the grace has passed."""
        slot.up.clear()
        slot.state = "stopped"
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
        todo, gone = [], []
        with self.lock:                              # what to do worked out under the lock; done outside it
            for slot in self.slots.values():
                if slot.state in ("starting", "backoff") and now >= slot.next_at:
                    todo.append((slot, None))
                elif slot.state == "running" and (why := self._trouble(slot, now)):
                    todo.append((slot, why))
            for slot, p in list(self.draining):
                if p.ended.is_set() or p.proc.poll() is not None:   # (ended, even while a child holds its output)
                    self.draining.remove((slot, p))
                    gone.append((slot, p))
                elif (late := self._late(p, now)) or (p.idle_since is not None and now - p.idle_since > grace()):
                    if late:                         # its other runs given back, uncounted, as when running
                        p.fail_all(f"its daemon {slot.d.name} still held run {late[:8]} after it was cancelled", True)
                    self._kill(p)
        for slot, p in gone:
            p.fail_all(f"its daemon {slot.d.name} ended while draining", False)
            self._finished(slot, p)
            self._kill(p)                            # (what it started, left in its group)
        for slot, why in todo:
            self._start(slot) if why is None else self._restart(slot, *why)
        if now - self.written >= WRITE_EVERY:
            self.write()

    def _trouble(self, slot: Slot, now: float) -> tuple[str, bool] | None:
        """Why a running daemon must be restarted, and whether that raises an alarm; None while it is well."""
        p, d = slot.proc, slot.d
        if p.ended.is_set() or p.proc.poll() is not None:   # (ended, even while something it started holds its output)
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
            p = Process(slot.d, self.e.spec.root, callback_env(self.e.spec, self.e.p.dir, self.e.socket), log,
                        lambda s, v, n=slot.d.name: self._pushed(n, s, v))
        except OSError as err:
            log.close()
            self._restart(slot, f"could not start: {err}", False)
            return
        with self.lock:
            if self.slots.get(slot.d.name) is not slot or slot.state not in ("starting", "backoff"):
                stale = True                         # (replaced or drained meanwhile: not wanted)
            else:
                stale = False
                slot.proc, slot.tracked = p, SAMPLER.track(p.proc)
                slot.state, slot.why = "running", ""
                slot.up.set()
        if stale:
            p.stop()
            self._kill(p)
            return
        self.e.p.events.add("ergostat.daemon.started", item=slot.d.name, source=SOURCE,
                            data={"daemon": slot.d.name, "pid": p.pid, "restarts": len(slot.restarts)})

    def _finished(self, slot: Slot, p: Process) -> dict:
        p.log.close()
        return SAMPLER.finish(slot.tracked) if slot.tracked is not None and slot.tracked.proc is p.proc else {}

    def _kill(self, p: Process) -> None:
        """Its process group ended (TERM, then KILL after the grace), on a thread of its own: never the loop's wait."""
        if not getattr(p, "killing", False):
            p.killing = True
            threading.Thread(target=killpg, args=(p.pid, grace()), daemon=True).start()

    def _restart(self, slot: Slot, why: str, alarm: bool) -> None:
        now = time.monotonic()
        with self.lock:
            if self.slots.get(slot.d.name) is not slot:
                return
            p, d = slot.proc, slot.d
            slot.proc = None
            slot.up.clear()
            slot.restarts.append(now)
            while slot.restarts and now - slot.restarts[0] > d.within:
                slot.restarts.popleft()
            slot.total, slot.why, n = slot.total + 1, why, len(slot.restarts)
            failed = n > d.restarts
            wait = min(d.backoff[0] * 2 ** (n - 1), d.backoff[1])
            slot.state, slot.next_at = ("failed", 0.0) if failed else ("backoff", now + wait)
            if alarm or failed:
                slot.alarm = {"why": f"given up after {n} restarts within {d.within:g}s: {why}" if failed else why,
                              "at": time.time()}
        res = {}
        if p is not None:
            crashed = p.ended.is_set() or p.proc.poll() is not None
            p.fail_all(f"its daemon {d.name} {why}", requeue=not crashed)
            self._kill(p)                            # its group, crashed or not: nothing it started is left behind
            res = self._finished(slot, p)
        data = {"daemon": d.name, "why": why, "pid": p.pid if p else None, "restarts": n, "within": d.within,
                **({"exit": p.proc.returncode} if p and p.proc.returncode is not None else {}),
                **({"resources": res} if res else {})}
        if failed:
            self.e.p.events.add("ergostat.daemon.failed", item=d.name, source=SOURCE,
                                data={**data, "intervention": True, "class": f"alarm:daemon:{d.name}",
                                      "users": self.users(d.name)})
            self.e.say(f"daemon {d.name}: given up after {n} restarts within {d.within:g}s ({why}): alarm raised; "
                       f"ergostat block {d.name} --restart when its cause is fixed")
            return
        self.e.p.events.add("ergostat.daemon.restarted", item=d.name, source=SOURCE,
                            data={**data, "wait": wait, **({"alarm": True} if alarm else {})})
        self.e.say(f"daemon {d.name}: {why}: restarting in {wait:g}s" + (" (alarm raised)" if alarm else ""))

    # ---- what is seen of them

    def failed(self, name: str | None) -> bool:
        slot = self.slots.get(name or "")
        return slot is not None and slot.state == "failed"

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
                          "last_line": time.time() - time.monotonic() + p.last_out if p else None,
                          "restarts": len(slot.restarts), "restarts_total": slot.total,
                          "in_flight": len(p.runs) if p else 0, "served": p.served if p else 0,
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
        """Ergostat stopping: each daemon asked to stop, its group killed if it has not ended within the grace."""
        with self.lock:
            procs = self._procs()
            for s in self.slots.values():
                s.up.clear()
                s.state = "stopped"
        for p in procs:
            p.stop()
        deadline = time.monotonic() + min(grace(), 3.0)
        while any(not p.ended.is_set() for p in procs) and time.monotonic() < deadline:
            time.sleep(0.05)
        for p in procs:
            p.fail_all(old.STOPPED_WITH_US, True)
            killpg(p.pid, 1.0)                       # (ended or not: what it started goes too)
        if self.slots or self.draining:
            self.write(final=True)


def read_status(state_dir) -> dict:
    """``<state>/daemons.json``, as the engine last wrote it (none: {})."""
    try:
        return json.loads((state_dir / "daemons.json").read_text()).get("daemons") or {}
    except (OSError, ValueError):
        return {}
