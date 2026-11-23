"""The daemons' supervisor (SPEC §9.7): one thread, never the engine's loop, that keeps each daemon running. A daemon
that exits, goes silent past its heartbeat, or stops reading its standard input (an alarm) is restarted after a
back-off; one that holds a cancelled run past the grace too. More than ``restart: max`` restarts within ``within`` and
it is given up (``ergostat.daemon.failed``, an intervention) until the owner revives it (``block NAME --restart``,
recorded as ``daemon.restart.requested``, or any model change). Every process it ends, its whole process group goes
with it. What it hands out (runs, readings) is ``work.py``'s. Its state goes to ``<state>/daemons.json``, a shard
engine's to ``<state>/daemons.SHARD.json`` (SPEC §9.8); ``read_status`` merges them."""

from __future__ import annotations

import json
import os
import re
import signal
import threading
import time
from collections import deque
from dataclasses import replace

from .. import runner as old
from ..costs.sampler import Sampler
from ..leases.kill import grace
from . import proc
from .config import WARM_ALL
from .observe import Observed
from .proc import Process
from .work import Hands

SOURCE = "ergostat"
TICK = 0.2
WRITE_EVERY = 2.0
SAMPLER = Sampler(30.0, "ergostat-daemon-sampler", floor=1.0)   # the daemons' CPU and memory: about 1 s after a
                                                                # start, then at doubling gaps to every 30 s; one ps


class Slot:
    """A daemon by name: its definition, its process now, its restarts."""

    def __init__(self, d):
        self.d, self.proc, self.tracked = d, None, None
        self.state, self.why, self.next_at = "starting", "", 0.0
        self.restarts: deque[float] = deque()
        self.total, self.alarm = 0, None
        self.spawning = False                        # one _start at a time: sync's and the loop's never both spawn
        self.up = threading.Event()


def killpg(pgid: int, wait: float) -> None:
    """Its whole process group (it leads a session of its own): TERM, then KILL after ``wait`` for what is left. Once
    gone (or sent KILL, which it cannot outlive) it leaves ``proc.GROUPS``: no id kept that the OS could reuse."""
    try:
        for sig, then in ((signal.SIGTERM, wait), (signal.SIGKILL, 0.0)):
            try:
                os.killpg(pgid, sig)
            except OSError:                          # (none left)
                return
            end = time.monotonic() + then
            while time.monotonic() < end:
                try:
                    os.killpg(pgid, 0)
                except OSError:
                    return
                time.sleep(0.05)
    finally:
        with proc.GROUPS_LOCK:
            proc.GROUPS.discard(pgid)


def _signal(pgid: int, sig: int) -> bool:
    """False when the group cannot be signalled: none left, or (EPERM) it cannot be ours any more."""
    try:
        return os.killpg(pgid, sig) is None
    except OSError:
        return False


def collect() -> set[int]:
    """``end_all``'s first step: new groups closed off (each kills itself) and the live ones taken, under the one
    lock ``Process`` checks and adds under, so a group spawned meanwhile is in this snapshot or killed by itself."""
    with proc.GROUPS_LOCK:
        proc.CLOSING = True
        return set(proc.GROUPS)


def end_all(wait: float) -> list[int]:
    """Every daemon's group ended before ergostat starts itself again in place, with no ``Supervisor`` lock taken (what
    is wedged may hold it): TERM to each, one shared deadline ``wait`` (clamped to 0..3 s) for all, then KILL to what
    is left. A group that cannot be signalled (gone, EPERM) is dropped, never retried. A group ``killpg`` ended after
    the snapshot may still be signalled from it: harmless while its leader is unreaped, a small window otherwise.
    A group with only unreaped processes left counts as present, so it is waited for to the deadline, then KILLed.
    The groups that were sent TERM, returned."""
    wait = min(max(float(wait), 0.0), 3.0)
    groups = collect()
    sent = [g for g in sorted(groups) if _signal(g, signal.SIGTERM)]
    left, deadline = set(sent), time.monotonic() + wait
    while left and time.monotonic() < deadline:
        time.sleep(0.05)
        left = {g for g in left if _signal(g, 0)}
    for g in left:
        _signal(g, signal.SIGKILL)
    with proc.GROUPS_LOCK:
        proc.GROUPS.difference_update(groups)
    return sent


class Supervisor(Hands):
    def __init__(self, eng):
        self.e = eng
        self.lock = threading.RLock()
        self.slots: dict[str, Slot] = {}
        self.draining: list[tuple[Slot, Process]] = []
        self.dying: list[Process] = []               # (warm) restarted, its group being killed: counted until it ends
        self.push: dict[tuple[str, str], object] = {}
        self.pushed_at: dict[str, float] = {}
        self.observers: dict[tuple[str, str], object] = {}   # (daemon, STOCK.SENSOR) → a sensor it serves
        self.observed = Observed()
        self.put_off: dict[str, str] = {}                # item → the daemon given up that gave it back, put off
        self.thread: threading.Thread | None = None
        self.written = 0.0

    # ---- the model's daemons

    def sync(self, spec) -> None:
        """The daemons this model uses: a new one started, one changed or no longer used drained, one given up and
        written the same revived. Of the engine's shard only (SPEC §9.8), by the plan of ``spec`` itself: never read
        again from the engine, which a later swap may have moved on."""
        mine = lambda n: self.e.own(f"daemon.{n}", spec)          # noqa: E731
        used = {b.params["daemon"] for b in spec.blocks.values() if b.params.get("daemon")}
        used = {n for n in used | {s.daemon for s in spec.sensors() if s.daemon} if mine(n)}
        want = {}                                    # a warm one: a process of its own per run held at once, NAME#i
        for n in used:
            d = spec.daemons[n]
            want |= {f"{n}#{i}": replace(d, name=f"{n}#{i}", concurrency=1) for i in range(1, d.concurrency + 1)} \
                if d.warm else {n: d}
        start = []
        with self.lock:
            for n, slot in list(self.slots.items()):
                if n not in want or want[n] != slot.d or slot.state == "failed":
                    if slot.state == "failed":
                        self._release(n)
                    self._drain(slot, "its definition changed" if n in want else "nothing uses it now")
                    del self.slots[n]
            for n in sorted(set(want) - set(self.slots)):
                self.slots[n] = slot = Slot(want[n])
                if slot.d.warm and self._warm_live() >= WARM_ALL:
                    continue                         # (the loop starts it once a warm process ends: WARM_ALL at most)
                slot.spawning = True                 # claimed before the loop runs: spawned here, never by its tick
                start.append(slot)
            self.push = {(s.daemon, f"{s.of.name}.{s.name}"): s for s in spec.sensors() if s.daemon in used and s.push}
            self.observers = {(s.daemon, f"{s.of.name}.{s.name}"): s for s in spec.sensors() if s.daemon in used}
            if self.slots and (self.thread is None or not self.thread.is_alive()):
                self.thread = threading.Thread(target=self._loop, name="ergostat-daemons", daemon=True)
                self.thread.start()
        for slot in start:                           # at once, before sync returns: the first readings asked find it
            self._spawn_claimed(slot)                # running (not "starting", a failure until the sensor is next due)

    def revive(self, name: str) -> bool:
        """The owner's ``block NAME --restart``: a daemon given up (or any) started afresh, its restarts forgotten."""
        with self.lock:
            fresh = []
            subs = self.subs(name)
            for old_slot in subs:
                self._drain(old_slot, "the owner asked for a restart")
                slot = self.slots[old_slot.d.name] = Slot(old_slot.d)
                self._release(old_slot.d.name)
                if not slot.d.warm or self._warm_live() < WARM_ALL:
                    slot.spawning = True             # (as in sync: spawned here, before revive returns; else by the
                    fresh.append(slot)               # loop once the processes draining end: WARM_ALL at most)
        if not subs:
            return False
        self.e.say(f"daemon {name}: restarted, as the owner asked")
        for slot in fresh:
            self._spawn_claimed(slot)
        return True

    def _warm_live(self) -> int:
        """(under the lock) Warm processes running, being started, draining or being killed: never more than
        WARM_ALL."""
        self.dying = [p for p in self.dying if p.proc.poll() is None]
        return sum(1 for s in self.slots.values() if s.d.warm and (s.proc or s.spawning)) + \
            sum(1 for s, _ in self.draining if s.d.warm) + len(self.dying)

    def subs(self, name: str) -> list[Slot]:
        """(under the lock) The daemon of that name: its one slot, or a warm one's process slots (NAME#i)."""
        return [s for n, s in self.slots.items() if n == name or n.rpartition("#")[0] == name]

    def _recycle(self, slot: Slot, why: str) -> None:
        """(under the lock) A warm process replaced, uncounted: drained, a new one started at the next tick."""
        new = self.slots[slot.d.name] = Slot(slot.d)
        new.restarts, new.total = slot.restarts, slot.total
        self._drain(slot, why)

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
            for slot in list(self.slots.values()):
                if slot.state in ("starting", "backoff") and now >= slot.next_at and not slot.spawning:
                    if slot.d.warm and self._warm_live() + sum(s.d.warm for s, w in todo if w is None) >= WARM_ALL:
                        continue
                    todo.append((slot, None))
                elif slot.state == "running" and (why := self._trouble(slot, now)):
                    todo.append((slot, why))
                elif slot.state == "running" and slot.proc.recycle and not slot.proc.runs:
                    why, counted = slot.proc.recycle  # (warm) misbehaved: restarted, counted; else replaced
                    todo.append((slot, (why, False))) if counted else self._recycle(slot, why)
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
        self.flush_observed()                        # (a burst's drops said within about a second, nothing after it)
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
        with self.lock:                              # claimed before spawning: a second caller spawns nothing
            if self.slots.get(slot.d.name) is not slot or slot.state not in ("starting", "backoff") or slot.spawning:
                return
            slot.spawning = True
        self._spawn_claimed(slot)

    def _spawn_claimed(self, slot: Slot) -> None:
        """A slot this caller claimed (``spawning``, set under the lock) spawned, and the claim let go."""
        try:
            self._spawn(slot)
        finally:
            with self.lock:
                slot.spawning = False

    def _spawn(self, slot: Slot) -> None:
        log = open(old.log_path(self.e.p, f"daemon-{slot.d.name}"), "a", encoding="utf-8")
        from ..spec.engine import callback_env
        try:
            p = Process(slot.d, self.e.spec.root, callback_env(self.e.spec, self.e.p.dir, self.e.socket), log,
                        lambda s, v, n=slot.d.name: self._pushed(n, s, v),
                        lambda s, o, t, n=slot.d.name: self._observed(n, s, o, t))
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
            if p is not None and d.warm:
                self.dying.append(p)
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
            base = d.name.rpartition("#")[0] if d.warm else d.name     # (warm: one alarm for the daemon, not each)
            said = failed and any(s is not slot and s.state == "failed" for s in self.subs(base))
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
            if not said:
                self.e.p.events.add("ergostat.daemon.failed", item=base, source=SOURCE,
                                    data={**data, "intervention": True, "class": f"alarm:daemon:{base}",
                                          "users": self.users(base)})
            self.e.say(f"daemon {d.name}: given up after {n} restarts within {d.within:g}s ({why}): alarm raised; "
                       f"ergostat block {base} --restart when its cause is fixed")
            return
        self.e.p.events.add("ergostat.daemon.restarted", item=d.name, source=SOURCE,
                            data={**data, "wait": wait, **({"alarm": True} if alarm else {})})
        self.e.say(f"daemon {d.name}: {why}: restarting in {wait:g}s" + (" (alarm raised)" if alarm else ""))

    # ---- what is seen of them

    def failed(self, name: str | None) -> bool:
        with self.lock:
            subs = self.subs(name or "")
        return bool(subs) and all(s.state == "failed" for s in subs)

    def users(self, name: str) -> list[str]:
        spec, name = self.e.spec, name.split("#")[0]
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
        shard = getattr(self.e, "shard", None)       # (a shard's own file and temporary file: SPEC §9.8)
        f = self.e.p.dir / ("daemons.json" if shard is None else f"daemons.{shard}.json")
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
        deadline = time.monotonic() + 1.0            # (its reader's last lines counted, unless something it started
        while any(not p.ended.is_set() for p in procs) and time.monotonic() < deadline:   # still holds its output)
            time.sleep(0.02)
        self.flush_observed(every=True)              # (each window's drops said, open or not; a line after: the log's)
        if self.slots or self.draining:
            self.write(final=True)


def of_daemon(daemons: dict, name: str) -> dict:
    """One daemon's status as the pages show it: a warm one's processes (NAME#i) together, how many in each state,
    a partial give-up said, its latest alarm; each process's own under ``processes``."""
    subs = {k: v for k, v in sorted(daemons.items()) if k.rpartition("#")[0] == name}
    if name in daemons or not subs:
        return daemons.get(name, {})
    states = {}
    for v in subs.values():
        states[v["state"]] = states.get(v["state"], 0) + 1
    alarms = [v["alarm"] for v in subs.values() if v.get("alarm")]
    lines = [v["last_line"] for v in subs.values() if v.get("last_line")]
    return {"state": ", ".join(f"{n} {s}" for s, n in states.items()) + f" (of {len(subs)} warm processes)",
            "failed": states.get("failed", 0), "restarts": sum(v.get("restarts") or 0 for v in subs.values()),
            "alarm": max(alarms, key=lambda a: a["at"]) if alarms else None, "last_line": max(lines, default=None),
            "why": next((v["why"] for v in subs.values() if v.get("why")), ""), "processes": subs}


SHARD_FILE = re.compile(r"daemons\.([a-z0-9][a-z0-9-]{0,63})\.json")


def _alive(pid) -> bool:
    """Whether the writer ``pid`` is a live process (EPERM: alive, not ours); not an int, or none such: not alive."""
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, OverflowError) as err:
        return isinstance(err, PermissionError)
    return True


def _stopped(x) -> bool:
    return not isinstance(x, dict) or x.get("state") == "stopped"


def read_status(state_dir) -> dict:
    """``<state>/daemons.json`` and each shard's ``daemons.SHARD.json``, as their engines last wrote them, merged
    (none: {}). A file that cannot be read adds nothing; a shard file whose writer is dead gives its daemons stopped,
    pid null. A daemon in two files is given once: the entry not stopped, else the first file by name."""
    out: dict = {}
    for f in sorted(state_dir.glob("daemons*.json")):
        m = SHARD_FILE.fullmatch(f.name)
        try:
            got = json.loads(f.read_text()) if m or f.name == "daemons.json" else None
        except (OSError, ValueError, RecursionError):
            continue
        got = got if isinstance(got, dict) else {}
        daemons, dead = got.get("daemons") or {}, m is not None and not _alive(got.get("pid"))
        for n, x in daemons.items() if isinstance(daemons, dict) else ():
            if dead and isinstance(x, dict):
                x = {**x, "state": "stopped", "pid": None}
            if n not in out or _stopped(out[n]) and not _stopped(x):
                out[n] = x
    return out
