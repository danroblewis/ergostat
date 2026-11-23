"""``ergostat run`` for a YAML model: ergostat closes the loops itself (SPEC §9.1).

- **Sensors** read on their schedules (a command, a query against a source; a person's readings
  arrive through the CLI). Each reading is a measurement.
- After every reading, and every second, the **signals** are worked out again: each stock's level,
  each flow's rate, each goal's setpoint, error and status (with its hysteresis), and every
  **built-in block**, in an order where each comes after what it reads.
- A **machine block** runs when what commands it is nonzero (or on its own schedule when nothing
  commands it). It never runs twice at once; a command that arrives while it runs is held, not
  queued (anti-windup), and it runs again, with the latest command, only after a fresh reading.
  After it moves a flow, the sensors of that flow's stocks read at once, so the loop sees the effect.
- What was **commanded** and what was **moved** are both recorded: the gap is saturation.
- When the model changes, it is **swapped in place** (``swap``), never by killing the runs: a run under way finishes
  under the model it started with (it records that version) and its output is taken against it; new runs start
  under the new model; goals and sensors switch at once, built-ins carry their state over (bumpless).

The record uses the same stores and event types as before (``valve.opened``, ``loop.off``,
``agent.ran``), so the status, the page and the diagrams show a YAML project like any other."""

from __future__ import annotations

import contextlib
import heapq
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

from .. import mirror, store
from .. import runner as old
from ..compute.worker import keeper
from ..costs import ai as costs_ai
from ..costs import budget
from ..costs import record as costs_record
from ..costs.sampler import SAMPLER, Measured
from ..leases import gone as run_gone
from ..library import bounds, reap
from ..reports import crash as reports_crash
from ..reports import lines as report_lines
from . import adopt, runrecord, stream, triggers
from . import blocks as bl
from .ir import Block, Ref, Sensor, Spec
from .legacy import sensor_name, valve_name
from .observer import KEEP, PORTS, RUN, Observer, estimated, opted, stale_age

TICK = 1.0
READERS = 8                 # the fixed pool that runs sensors' commands and queries: no thread per reading (scale.md #1)
BATCH = 0.05                # after a pass, what lands within this long (readings, runs ending) waits for one pass together
MISSING = object()
SLEPT = 30.0                # the wall clock ran this much further than the monotonic one between passes: it slept
JUDGE_EVERY = 30.0          # a judge with no every: passes this often
POOL_FULL_AFTER = 10.0      # seconds an item whose run found its workspace pool full is put off (SPEC §12k)
SWEEP = 5.0                 # how often the owner's messages are swept: left received, or about work since finished
OUTCOMES_EVERY = 30.0       # how often the outcomes of the recipes' uses are found again (SPEC §12j)
SOURCE = "ergostat"
STOPPED_BY_OWNER = "stopped as the owner asked"   # ergostat block NAME --stop: not the block's failure
STOP_ASKED = "block.stop.requested"
RESTART_ASKED = "daemon.restart.requested"
AI_COMMAND = os.environ.get("ERGOSTAT_AI", "claude -p")
AI_FOOTER = """

---
You are a block in an ergostat control system. Your inputs, and the command you were given, are
the JSON below. Answer with JSON lines only, one per output, for example:
{"out": "flow.<name>", "moved": 3}          what you moved along a flow
{"out": "block.<name>", "command": 2}       a command to the block you drive
{"decision": "what you decided", "why": "the reason"}
{"propose": {"kind": "parameter|equation|structure", "parts": ["stock.<name>"], "edit": {...},
             "reasons": [{"says": "...", "evidence": "finding:CODE@PART | fit:total.nmse | residual:stock.<name> |
             path:LINE | URL | rule:NAME"}], "confidence": 0.6}}     a change to the model (SPEC §12e)
{"claim": {"says": "tests pass", "about": "<an item id, stock.<name>, a file, a commit>",
           "check": "tests | changed | state | exit | level"}}   what you did, said plainly: ergostat checks it (SPEC §12g)
{"answer": {"message": "ergostat.message/<id>", "says": "..."}}   your answer to a message the owner sent (SPEC §12h)
Messages the owner sent about this work while it waited are in the JSON under "messages": take them into it.
Gated actions an earlier session of yours asked for, and what became of them, are under "actions" (SPEC §12k).
"""


def every_pass(b: Block) -> bool:
    """Whether a built-in is stepped at every pass: its output can move with time alone, its inputs as they were (an
    ``onoff`` with a ``min-on`` or ``min-off``, an ``alarm`` with a ``for``, a ``counter`` that resets, a ``limit`` with a
    ``rate``, every ``delay``, ``timer`` and ``schedule``), or need not settle in one step (an ``onoff`` with an
    ``until`` other than its goal). The others are functions of their inputs and of their own last output, which a
    step with the same inputs keeps: stepped when what they read changed."""
    p = b.params
    return b.type in ("delay", "timer", "schedule") or \
        (b.type == "onoff" and bool(p.get("min-on") or p.get("min-off") or p.get("until"))) or \
        (b.type == "alarm" and bool(p.get("for"))) or (b.type == "counter" and bool(p.get("reset"))) or \
        (b.type == "limit" and p.get("rate") is not None)


class ShardError(ValueError):
    """A shard the model's plan does not have (SPEC §9.8): at construction, or on a swap to such a plan."""


class Engine:
    incremental = True                                 # a pass works out only what changed (False: everything, each pass)
    lock_wait = 5.0                                    # seconds ``close`` waits for a lock it stops under, at most

    def __init__(self, project, say=print, shard: str | None = None):
        self.p, self.say = project, say
        self.spec: Spec = project.model.spec
        self.shard = shard                             # the shard it works on (SPEC §9.8); None: the whole model
        self._shard_of(self.spec)
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.signals: dict[str, float] = {}
        self.builtins = {n: bl.make(self.spec.blocks[n], self.spec) for n in bl.order(self.spec) if self.own(f"block.{n}")}
        self.status: dict[str, str] = {}               # goal → holding / off
        self.setpoint: dict[str, float] = {}           # goal → a setpoint a block set (a cascade)
        self.per: dict[str, tuple] = {}                # goal held per item or group → (worst, breaking, how many)
        self.per_rows: dict[str, tuple] = {}           # its items as last read, and the record's version then
        self.outputs: dict[str, dict[str, float]] = {}   # machine block → port → its last command (held)
        self.commands: dict[str, dict] = {}            # machine block → its last command's detail
        self.running: set[str] = set()
        self.untrusted_runs: set[str] = set()          # those of them an untrusted library's block began (library/bounds.py)
        self.judge_next: dict[str, float] = {}         # judge block → when its next pass is due (monotonic): it backs off idle
        self.judge_idle: dict[str, int] = {}           # judge block → its passes in a row that moved nothing
        self.finished: dict[str, float] = {}
        self.asked: dict[str, float] = {}              # advised block → the command it last asked approval for
        self.began: dict[str, float] = {}   # when each machine block's last run began           # machine block → when its last run ended
        self.was_commanded: dict[str, bool] = {}
        self.last_reading = 0.0                        # the time of the newest reading the engine has seen
        self.reading: set[str] = set()                 # sensors whose read is under way
        self.seen: dict[str, float] = {}               # series → the newest reading's time
        self.slots = {a.name: threading.Semaphore(a.at_once) for a in self.spec.agents.values()}
        self.machines = [b for b in self.spec.blocks.values() if b.machine and self.own(f"block.{b.name}")]
        # what caused what, kept so the record can say it (causedby): the event carrying each block's latest
        # output (a built-in's decision, or the run that gave the command), each block's latest run, and the
        # run whose moving a flow made a sensor read at once
        self.cause: dict[str, str] = {}
        self.last_run: dict[str, str] = {}
        self.read_cause: dict[str, str] = {}
        self.testing: dict[str, dict] = {}             # block → the step it moves in an approved step test
        self.held: set[str] = set()                    # blocks held still while a step test runs
        self.moved_by: dict[str, dict[str, float]] = {}  # block → what its last run said it moved, by flow
        self._sweeping = threading.Lock()
        self.routes: dict[str, list[dict]] = {}       # block → the route lines its runs printed (a classifier, SPEC §12h)
        self.outcomes_lock = threading.Lock()
        from ..history import version
        self.version = version(project.model)          # the model new runs start under (each run records its own)
        self.procs: dict[str, subprocess.Popen] = {}   # machine block → its run's process, while it runs
        self.stopping_runs: set[str] = set()           # blocks whose run the owner asked to stop
        self.live: dict[str, subprocess.Popen] = {}    # run id → its process, while it runs (leases/kill.py)
        self.killing: dict[str, str] = {}              # run id → why it is being killed (its lease expired)
        self.ingester = None
        self.lease_seq = 0                             # the newest lease event taken to the workspace pools (SPEC §12k)
        self.following = False                         # whether _follow runs: it runs the actions programs ask for
        from ..leases.dispatch import Dispatcher
        self.dispatch = Dispatcher(self)              # blocks that take items: a run per item, each leased (SPEC §9.5)
        from .triggers import Triggers
        self.triggers = Triggers(self)                # blocks started by an event: a run per event (SPEC §9.3)
        from ..daemons.supervise import Supervisor
        self.daemons = Supervisor(self)               # the long-lived runners blocks and sensors hand work to (SPEC §9.7)
        from .joins import Joins
        self.joins = Joins(self)                      # parents moved on by their children (SPEC §5a, Join)
        self.compute = None                           # the sessions with the pools' nodes, once a model has pools (§12s.4)
        # the loop (``_schedule``): readings asked for, taken a batch at a time; commands and queries read by a fixed
        # pool, counts of items from what the fold keeps (counts.py); then one pass over what changed (scale.md #1, #4)
        from .counts import Counts
        self.counts = {False: Counts(False), True: Counts(True)}
        self.wanted: dict[str, Sensor] = {}           # readings asked for and not yet begun, by series, in turn
        self.results: queue.SimpleQueue = queue.SimpleQueue()   # what the pool read: (sensor, value, why, time, error)
        self.wake = threading.Event()
        self.looping = False                           # whether the loop runs: else a reading is a thread, as before
        self.pool: ThreadPoolExecutor | None = None
        self.alarm_pool: ThreadPoolExecutor | None = None   # alarms' sensors: never on the pool an alarm may watch
        self.alarm_pool_out: dict[str, tuple[float, float, float | None]] = {}   # as pool_out, for it
        self.alarm_pool_done_at = time.monotonic()
        self.passing = threading.Lock()                # one pass at a time, whichever thread asks
        self.full = True                               # the next pass works out everything (the first, after a swap)
        self.mark = None                               # the measurements' changes, as of the last pass
        self.measured = False                          # every part's newest reading loaded once (a pool's "no reading")
        self.dirty_keys: set[str] = set()              # signals changed since the last pass (a machine's output, ...)
        self.dirty_goals: set[str] = set()             # goals whose setpoint a run set since
        self.dirty_blocks: set[str] = set()            # machine blocks whose run ended since
        self.dirty_series: set[str] = set()            # series whose reading ended since (read or not)
        self.poked = False
        self.record_moved = False                      # the record was written since the loop last looked (notify.py)
        self.calls = None                              # the socket steps call (calls/server.py), once started
        self.socket: str | None = None
        self.count_last: dict[str, float] = {}         # an items sensor's series → the count last written for it
        self.count_next = 0.0                          # (monotonic) not before: reading every count costs what it costs
        # what the watchdog (watchdog.py) looks at: when a pass last finished, the loop's last round (and which loop
        # is the live one), and the readings handed to the pool and not back, with when the pool last gave one back
        self.passed_at = self.loop_beat = time.monotonic()
        self.loop_gen = 0
        self.pool_lock = threading.Lock()
        self.pool_out: dict[str, tuple[float, float, float | None]] = {}   # series → (handed to the pool, timeout, begun)
        self.pool_done_at = time.monotonic()
        self.wedged: str | None = None                 # set when only a restart of the process can recover it
        self.restart_hard = None                       # the restart itself, when the run loop cannot do it (running.py)
        self.watchdog = None
        # the observer (observer.py, SPEC §9.6): the stale parts a goal or block reads, by signal, with their ages; the
        # goals on a stale part; each stock's estimate between readings (made at the first pass: it reads the record)
        self.stale_parts: dict[str, float] = {}
        self.stale: dict[str, float] = {}
        self.observer: Observer | None = None
        self.observing = True
        self.born = time.time()                        # (or when it last woke: nothing is stale before it could be read)
        self.clock_at = (self.born, time.monotonic())

    # ---- its shard (SPEC §9.8)

    def _shard_of(self, spec: Spec):
        """This engine's ``Shard`` in this model's plan (None: no shard). ShardError when the plan has no such shard:
        it never runs nothing quietly, nor everything."""
        if self.shard is None:
            return None
        from .shards import planned
        got = planned(spec).shards.get(self.shard)
        if got is None:
            raise ShardError(f"no shard {self.shard!r} in this model (its shards: {', '.join(planned(spec).shards)})")
        return got

    @property
    def plan(self):
        from .shards import planned
        return None if self.shard is None else planned(self.spec)

    def own(self, key: str, spec: Spec | None = None) -> bool:
        """Whether a part (a key ``Plan.of`` takes) is this engine's to work on, in ``spec`` (the model now if None):
        every part with no shard; else as ``Plan.of`` says, and by nothing else (a part not in the plan raises)."""
        if self.shard is None:
            return True
        from .shards import planned
        return planned(spec or self.spec).of(key) == self.shard

    def leads(self) -> bool:
        """Whether this engine does what is done once for the whole model: the lead shard's, or the whole's."""
        return self.shard is None or self.shard == self.plan.lead

    def follows(self, key: str, spec: Spec | None = None) -> bool:
        """Whether this engine follows an owner's ask about a part: its owner's, as ``Plan.of`` says. A part ``spec``
        does not have (``KeyError``) is the lead's alone: never no one's, never everyone's."""
        try:
            return self.own(key, spec)
        except (KeyError, ValueError):
            return self.leads()

    def _mine(self, spec: Spec):
        return None if self.shard is None else lambda k: self.own(k, spec)

    def _measured(self, spec: Spec) -> set | None:
        """The stocks, flows and auxiliaries ``measure`` reads: its own, and those its parts read in other shards (a
        goal's ``of``, a block's reads, an equation's refs, an observed stock's flows). None: every one."""
        if self.shard is None:
            return None
        kept, k = spec.lookups().kept, f"engine.measured.{self.shard}"
        if k not in kept:
            tables = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries}
            got = {(kd, n) for kd, t in tables.items() for n in t if self.own(f"{kd}.{n}", spec)}
            refs = [g.of for n, g in spec.goals.items() if self.own(f"goal.{n}", spec)]
            refs += [r for n, b in spec.blocks.items() if self.own(f"block.{n}", spec) for r in b.reads()]
            refs += [Ref.parse(t) for kd, n in sorted(got) if kd != "stock" and tables[kd][n].equation
                     for t in tables[kd][n].equation.refs]
            refs += [Ref("flow", f.name) for n in opted(spec).stocks if ("stock", n) in got for f in spec.flows_of(n)]
            kept[k] = got | {(r.kind, r.name) for r in refs if r is not None and r.name in tables.get(r.kind, ())
                             and not (r.port in PORTS and r.port not in tables[r.kind][r.name].sensors)}  # (an estimate: a wire)
        return kept[k]

    # ---- signals

    def get(self, r: Ref) -> float | None:
        if r.kind == "block" and r.name in self.spec.blocks:
            b = self.spec.blocks[r.name]
            if b.builtin:
                return self.signals.get(f"block.{r.name}")
            outs = self.outputs.get(r.name, {})
            if r.port:
                return outs.get(r.port)
            return outs.get("out", next(iter(outs.values()), None) if len(outs) == 1 else None)
        return self.signals.get(str(r))

    def measure(self, newest: dict | None = None, only: set[str] | None = None) -> set[str]:
        """Stocks' levels and flows' rates from the record: the newest reading of any of their sensors. ``only``: the
        series whose newest reading changed since the last pass (None: every one). Returns the signals that changed."""
        m = self.p.measurements
        if newest is None and hasattr(m, "newest"):
            newest = m.newest()                                # every series' newest, at once (scale.md #3)
        spec, sig, changed = self.spec, self.signals, set()
        tables = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries}
        if only is None:
            parts = [(kind, name) for kind, table in tables.items() for name in table]
        else:
            by = self._wiring()["parts"]
            parts = list(dict.fromkeys(x for sr in only for x in by.get(sr, ())))
        if (read := self._measured(spec)) is not None:          # a shard: its own, and what they read (SPEC §9.8)
            parts = [x for x in parts if x in read]
        for kind, name in parts:
            x = tables[kind].get(name)
            if x is None:
                continue
            best = None
            for s in x.sensors.values():
                got = newest.get(s.series) if newest is not None else m.latest(s.series)
                if got is None:
                    continue
                k = f"{kind}.{name}.{s.name}"
                if sig.get(k, MISSING) != got[1]:
                    sig[k] = got[1]
                    changed.add(k)
                if self.seen.get(s.series) != got[0]:
                    self.seen[s.series] = got[0]
                    self.last_reading = max(self.last_reading, got[0])
                if best is None or got[0] > best[0]:
                    best = got
            v = best[1] if best is not None else x.rate if kind == "flow" and x.rate is not None else MISSING
            if v is not MISSING and sig.get(f"{kind}.{name}", MISSING) != v:
                sig[f"{kind}.{name}"] = v
                changed.add(f"{kind}.{name}")
        self.measured = self.measured or only is None
        return changed

    def _event(self, out: list | None, type: str, **kw) -> dict:
        """An event of the pass: recorded now (``out`` None), or kept in ``out`` to be recorded, in turn, once the
        pass lets go of the lock (its id is its own from now)."""
        if out is None:
            return self.p.events.add(type, **kw)
        ev = {"id": uuid.uuid4().hex, "type": type, "at": time.time(), **kw}
        out.append(ev)
        return ev

    def goals(self, now: float, causes: dict | None = None, crossed: dict | None = None, only=None,
              out: list | None = None) -> set[str]:
        """``causes``: the run behind the reading that started this pass, by what it read; a crossing of a
        goal on that is recorded as caused by it. ``crossed`` collects this pass's crossings, by goal. ``only``: the
        goals to work out again (None: every one); ``out``: see ``_event``. Returns the signals that changed."""
        spec, sig, changed = self.spec, self.signals, set()
        names = spec.goals if only is None else sorted((g for g in only if g in spec.goals), key=self._wiring()["goal_pos"].get)
        for name in (n for n in names if self.own(f"goal.{n}", spec)):
            g = spec.goals[name]
            r = self.setpoint.get(name, g.hold.value)
            if sig.get(f"goal.{name}", MISSING) != r:
                sig[f"goal.{name}"] = r
                changed.add(f"goal.{name}")
            y = sig.get(str(g.of))
            held = self.per.get(name) if g.per else None
            if held is not None and y is not None:
                y = held[0]                                         # the worst item's or group's (SPEC §8, per:)
            if y is None:
                for k in (f"goal.{name}.error", f"goal.{name}.off"):
                    if sig.pop(k, MISSING) is not MISSING:
                        changed.add(k)
                continue
            policy = opted(spec).goals.get(name, "act") if name in self.stale else "act"   # stale: hold, or count as off
            if policy == "hold":
                continue
            before = self.status.get(name)
            now_s = g.status(y, before == "off", r)
            e = g.hold.error(y, r) if policy == "act" else sig.get(f"goal.{name}.error", g.hold.error(y, r))
            for k, v in ((f"goal.{name}.error", e), (f"goal.{name}.off", 1.0 if now_s == "off" or policy == "off" else 0.0)):
                if sig.get(k, MISSING) != v:
                    sig[k] = v
                    changed.add(k)
            if now_s != before and policy == "act":
                self.status[name] = now_s
                ev = self._event(out, f"loop.{now_s}", item=name, source=SOURCE, causedby=(causes or {}).get(g.of.name),
                                 data={"value": y, "setpoint": f"{g.hold.op} {r:g}", "error": e,
                                       **({"breaking": held[1], "breaking_n": held[2]} if held and now_s == "off" else {})})
                if crossed is not None:
                    crossed[name] = ev["id"]
        return changed

    def _per(self, now: float, every: bool, changed) -> set[str]:
        """The goals held per item or group (SPEC §8, ``per:``) worked out again, before the pass takes its lock: each
        (``every``), or those whose stock's sensor read anew. Their items are read from the item index only when the
        record changed since (its newest event, its generation); their hours are worked out again from those kept.
        Returns those whose worst moved."""
        from .goal_per import held, members, sensor_of
        moved, version = set(), None
        for g in self.spec.goals.values():
            s = sensor_of(self.spec, g) if g.per and self.own(f"goal.{g.name}") else None
            if s is None or not (every or s.series in (changed or ())):
                continue
            if version is None:
                ev = self.p.events
                version = (ev.last_seq(), ev.generation()) if hasattr(ev, "last_seq") and hasattr(ev, "generation") else now
            kept = self.per_rows.get(g.name)
            if kept is None or kept[0] != (version, g.per, s.items):
                kept = self.per_rows[g.name] = ((version, g.per, s.items), members(self.spec, g, self.p.events, now))
            got = held(self.spec, g, kept[1], self.setpoint.get(g.name), now)
            if got != self.per.get(g.name):
                self.per[g.name] = got
                moved.add(g.name)
        return moved

    def evaluate(self, causes: dict | None = None, full: bool = False, tick: bool = False) -> None:
        """A pass (SPEC §9.1). The first, and the first after a model swap, works out everything; each after it only what
        is downstream of what changed since the last (scale.md, #1): the series with a new reading and the signals they
        move, the goals on those, the built-ins reading what changed (and those stepped every pass: ``every_pass``), and the
        machine blocks commanded by what changed, bearing on those readings, or whose run or reading ended; on the
        clock's pass (``tick``) also the blocks commanded on and not running (paced by ``every``, held by a step test). The lock is
        held only while the signals are worked out: the readings are read before it, the events and the built-ins'
        outputs written after it, then the blocks due are started."""
        with self.passing:
            m = self.p.measurements
            changed, mark = None, None
            if hasattr(m, "changes"):
                newest, changed, mark = m.changes(self.mark)
            else:
                newest = m.newest() if hasattr(m, "newest") else None
            now, mono = time.time(), time.monotonic()            # (together: a slow pass is no sleep)
            per_moved = self._per(now, full or tick or self.full or changed is None, changed)
            crossed: dict[str, str] = {}
            events: list[dict] = []
            rows: list[tuple[str, float, float]] = []
            with self.lock:
                full = full or self.full or not self.incremental or changed is None
                self.full, self.mark = False, mark
                keys, goals_set, blocks, series = self.dirty_keys, self.dirty_goals, self.dirty_blocks, self.dirty_series
                self.dirty_keys, self.dirty_goals, self.dirty_blocks, self.dirty_series = set(), set(), set(), set()
                was = self.last_reading
                w = self._wiring()
                if full:
                    self.measure(newest)
                    self.observe(now, rows, events)
                    self.staleness(now, events, mono)
                    self.goals(now, causes, crossed, out=events)
                else:
                    keys |= self.measure(newest, changed)
                    keys |= self.observe(now, rows, events) | self.staleness(now, events, mono)
                    series |= changed
                    goals_set |= {g for k in keys for g in w["goals_of"].get(k, ())} | per_moved
                    keys |= self.goals(now, causes, crossed, only=goals_set, out=events)
                out_keys, set_goals, late = self._builtins(now, None if full else keys, crossed, events, rows)
                keys |= out_keys
                if full and any(t.kind == "goal" for b in self.builtins for t in self.spec.blocks[b].targets()):
                    late |= self.goals(now, causes, crossed, out=events)       # a setpoint just moved: the status follows it
                elif set_goals:
                    late |= self.goals(now, causes, crossed, only=set_goals, out=events)
                self.dirty_keys |= late                                     # (read by built-ins before them: the next pass)
                if full:
                    todo = [b for b in self.machines if self.due(b, events)]
                else:
                    names = set(blocks)
                    for k in keys:
                        names |= w["commanded"].get(k, set())
                    for sr in series:
                        names |= w["by_series"].get(sr, set())
                    if self.last_reading > was:
                        names |= w["free"]
                    if tick:
                        names |= {n for n, on in self.was_commanded.items() if on and n not in self.running}
                    pos = w["mpos"]
                    if self.shard is not None:                          # (its shard's: SPEC §9.8)
                        names &= {b.name for b in self.machines}
                    todo = [b for b in sorted((self.spec.blocks[n] for n in names if n in pos), key=lambda b: pos[b.name])
                            if self.due(b, events)]
            if events:
                self.p.events.add_many(events, new=True)
            if rows:
                self.p.measurements.add_many(rows)
            self.passed_at = time.monotonic()
        for b in todo:
            self.start(b, "command")

    def _builtins(self, now: float, keys: set[str] | None, crossed: dict, out: list, rows: list) -> tuple[set, set, set]:
        """The built-ins stepped in their order: every one (``keys`` None), or those reading a signal in ``keys`` or one
        they change, and every one that keeps time. Returns the outputs that changed, the goals whose setpoint changed,
        and the outputs that changed after a built-in reading them was stepped (a delay's loop: seen next pass)."""
        names, pos, readers, timed = self._builtin_wiring()
        if keys is None:
            heap = list(range(len(names)))
        else:
            heap = sorted({pos[n] for n in timed} | {pos[n] for k in keys for n in readers.get(k, ())})
        changed, set_goals, late, done = set(), set(), set(), set()
        while heap:
            i = heapq.heappop(heap)
            if i in done:
                continue
            done.add(i)
            name = names[i]
            blk, key = self.builtins[name], f"block.{name}"
            before = self.signals.get(key)
            get, mode = self.get, self.stale_mode(blk.b)
            if mode == "hold":                              # a stale input: it keeps its output
                continue
            if mode == "off":
                get = self.seeing_off(blk.b)
            try:
                v = blk.step(get, now)
            except Exception as e:                          # one block failing never stops the others
                self.say(f"block {name}: {type(e).__name__}: {e}")
                v = None
            if v is None:
                if before and self.spec.blocks[name].type == "alarm":
                    rows.append((f"block/{name}", now, 0.0))   # failing, or its input unknown: no longer said raised
                if self.signals.pop(key, None) is not None:
                    changed.add(key)
                    self._downstream(key, i, heap, late)
                continue
            self.signals[key] = v
            for t in self.spec.blocks[name].targets():
                if t.kind == "goal":                        # a cascade: an outer block sets an inner setpoint
                    if self.setpoint.get(t.name) != v:
                        set_goals.add(t.name)
                    self.setpoint[t.name] = v
            if before != v:
                rows.append((f"block/{name}", now, v))
                changed.add(key)
                self._downstream(key, i, heap, late)
                if bool(before) != bool(v):
                    self.decided(self.spec.blocks[name], v, now, crossed, out)
        return changed, set_goals, late

    def _downstream(self, key: str, i: int, heap: list, late: set) -> None:
        names, pos, readers, _ = self._builtin_wiring()
        for r in readers.get(key, ()):
            if pos[r] > i:
                heapq.heappush(heap, pos[r])
            else:
                late.add(key)

    def _builtin_wiring(self) -> tuple[list[str], dict[str, int], dict[str, list[str]], list[str]]:
        """The built-ins in order, each one's place, who reads each signal, and those stepped every pass: worked out once per
        set of built-ins (a swap makes another)."""
        got = getattr(self, "_bw", None)
        if got is not None and got[0] is self.builtins:
            return got[1]
        names = list(self.builtins)
        readers: dict[str, list[str]] = {}
        timed = []
        for n in names:
            b = self.builtins[n].b
            keys = {f"block.{r.name}" if r.kind == "block" else str(r) for r in b.reads()}
            if b.goal and b.goal in self.spec.goals:
                g = self.spec.goals[b.goal]
                keys |= {f"goal.{g.name}", f"goal.{g.name}.error", f"goal.{g.name}.off", str(g.of)}
            for k in keys:
                readers.setdefault(k, []).append(n)
            if every_pass(b):
                timed.append(n)
        out = (names, {n: i for i, n in enumerate(names)}, readers, timed)
        self._bw = (self.builtins, out)
        return out

    def _wiring(self) -> dict:
        """What a pass needs to work out only what changed, worked out once per model (``Spec.lookups``): each series'
        parts, each signal's goals, the machine blocks each signal commands, the series each block's start bears on
        (``fresh_for``, ``after_acting``), and those any reading may start (``free``)."""
        spec = self.spec
        kept = spec.lookups().kept
        w = kept.get("engine.wiring")
        if w is not None:
            return w
        parts: dict[str, list[tuple[str, str]]] = {}
        for kind, table in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
            for name, x in table.items():
                for s in x.sensors.values():
                    parts.setdefault(s.series, []).append((kind, name))
        goals_of: dict[str, list[str]] = {}
        for name, g in spec.goals.items():
            goals_of.setdefault(str(g.of), []).append(name)
        machines = [b for b in spec.blocks.values() if b.machine]
        commanded: dict[str, set[str]] = {}
        by_series: dict[str, set[str]] = {}
        free: set[str] = set()
        for b in machines:
            if b.takes:
                continue
            cs = spec.commanders_of(b.name)
            for c in cs:
                commanded.setdefault(f"block.{c.name}", set()).add(b.name)
            if not cs:
                if not (b.every or b.cron) and any(r.kind != "block" for r in b.inputs.values()):
                    free.add(b.name)
                continue
            flows = [t.name for t in b.targets() if t.kind == "flow"]
            ser = {x.series for x in self.after_acting(flows)}
            fresh = set()
            for g in self.served(b) | {r.name for r in b.reads() if r.kind == "goal"}:
                gg = spec.goals.get(g)
                t = spec.measured(gg.of.kind).get(gg.of.name) if gg else None
                fresh |= {x.series for x in t.sensors.values()} if t else set()
            if not ser and not fresh:
                free.add(b.name)                             # it bears on any reading
            for sr in ser | fresh:
                by_series.setdefault(sr, set()).add(b.name)
        w = {"parts": parts, "goal_pos": {g: i for i, g in enumerate(spec.goals)}, "goals_of": goals_of,
             "commanded": commanded, "by_series": by_series, "free": free,
             "mpos": {b.name: i for i, b in enumerate(machines) if not b.takes}}
        kept["engine.wiring"] = w
        return w

    def decided(self, b: Block, v: float, now: float, crossed: dict | None = None, out: list | None = None) -> None:
        """A built-in's output turning on or off, said as a decision of the goal it serves: caused by that
        goal's crossing, when it crossed in this same pass."""
        served = [r.name for r in b.reads() if r.kind == "goal"] or [b.name]
        cmd = [t.name for t in b.targets() if t.kind == "block"]
        verb = "act" if v else "stop"
        for g in served:
            ev = self._event(out, "controller.decided", item=g if g in self.spec.goals else b.name, source=b.name,
                             causedby=(crossed or {}).get(g),
                             data={"decision": f"{verb}{(': ' + ', '.join(cmd)) if cmd else ''}",
                                   "why": f"{b.type} {b.name} → {v:g}", "block": b.name, "value": v})
            self.cause[b.name] = ev["id"]

    # ---- the observer (observer.py, SPEC §9.6)

    def history(self, spec: Spec, n: str) -> list[tuple[float, float]]:
        pts = sorted(p for s in spec.stocks[n].sensors.values() for p in self.p.measurements.range(s.series, 0, None, last=KEEP + 1))
        return pts[-(KEEP + 1):]

    def observe(self, now: float, rows: list, out: list) -> set[str]:
        """Each estimated stock's estimate moved to now, once a pass, and its new readings blended in; their innovations
        are recorded, and a run of large ones says the model disagrees. Returns the estimates and uncertainties that
        changed. Nothing for a model that estimates no stock."""
        if not self.observing or not opted(self.spec).stocks:
            return set()
        ob = self.observer
        if ob is None:
            ob = self.observer = Observer(self.spec, lambda n: self.history(self.spec, n), mine=self._mine(self.spec))
        ob.advance(now, self.signals)
        new = []
        for n, tr in ob.tracks.items():
            got = max(((self.seen[s.series], s.name) for s in self.spec.stocks[n].sensors.values() if s.series in self.seen),
                      default=None)
            y = self.signals.get(f"stock.{n}.{got[1]}") if got else None
            if isinstance(y, int | float) and (tr.last is None or got[0] > tr.last):
                new.append((got[0], n, float(y)))
        changed = set()
        for t, n, y in sorted(new):
            tr = ob.tracks[n]
            got = tr.read(t, y, ob.rate.get(n, 0.0) * max(ob.t - t, 0.0) / 3600.0)   # (against its estimate then)
            if got is not None:
                rows.append((f"observer/{n}/innovation", t, got[0]))
                if tr.run == RUN:
                    self._event(out, "ergostat.model.disagrees", item=f"stock.{n}", source=SOURCE,
                                data={"stock": n, "innovation": got[0], "sd": got[1], "run": RUN})
        for n, tr in ob.tracks.items():
            for port, v in (("estimate", tr.x), ("uncertainty", tr.uncertainty(now))):
                k = f"stock.{n}.{port}"
                if v is not None and port not in self.spec.stocks[n].sensors and self.signals.get(k) != v:
                    self.signals[k] = v
                    changed.add(k)
        return changed

    def staleness(self, now: float, out: list, mono: float | None = None) -> set[str]:
        """Which parts the watched goals and blocks read are stale now (never before the engine has run long enough to
        read them: since it started, or woke from a sleep); a watched goal going stale or reading again is recorded.
        Returns the parts whose staleness changed. Nothing for a model that watches nothing."""
        o = opted(self.spec)
        if not o.parts:
            return set()
        mono = time.monotonic() if mono is None else mono
        slept = (now - self.clock_at[0]) - (mono - self.clock_at[1])
        if slept > SLEPT:                                  # the wall clock jumped: asleep (the page hears of it too)
            self.born = now
            self._event(out, "ergostat.engine.woke", source=SOURCE, data={"slept": round(slept, 1)})
        self.clock_at = (now, mono)
        ages = {}
        for r in o.parts:
            t = self.spec.measured(r.kind).get(r.name)
            last = max((self.seen[s.series] for s in t.sensors.values() if s.series in self.seen), default=None) if t else None
            age = stale_age(self.spec, r, last, now, self.born)
            if age is not None:
                ages[str(r)] = age
        changed = set(ages) ^ set(self.stale_parts)
        self.stale_parts = ages
        for name, policy in ((n, x) for n, x in o.goals.items() if self.own(f"goal.{n}")):
            g = self.spec.goals[name]
            age = ages.get(str(Ref(g.of.kind, g.of.name)))
            if (age is None) != (name not in self.stale):
                self._event(out, "ergostat.goal.fresh" if age is None else "ergostat.goal.stale", item=name, source=SOURCE,
                            data={"part": str(g.of), "age": age, "on_stale": policy})
            if age is None:
                self.stale.pop(name, None)
            else:
                self.stale[name] = age
        return changed

    def stale_in(self, b: Block) -> dict[str, float]:
        """What it reads that is stale (a watched part, or a watched goal on one), with its reading's age."""
        out = {}
        for r in b.reads():
            age = self.stale.get(r.name) if r.kind == "goal" else \
                None if estimated(self.spec, r) else self.stale_parts.get(f"{r.kind}.{r.name}")
            if age is not None:
                out[str(r)] = age
        return out

    def stale_mode(self, b: Block) -> str | None:
        """What a stale input makes it do: ``hold`` (keep its output), ``off`` (see its stale goals as off), or None (as
        usual): its own ``on-stale:``, else the strictest of its stale goals'."""
        if not self.stale_parts or not self.stale_in(b):
            return None
        if b.on_stale in ("hold", "off"):
            return b.on_stale
        pols = {opted(self.spec).goals.get(r.name) for r in b.reads() if r.kind == "goal" and r.name in self.stale}
        return "hold" if "hold" in pols else "off" if "off" in pols else None

    def seeing_off(self, b: Block):
        """Its ``get``, with each stale goal it reads seen as off, and the goal's stale value not read (so an ``until``
        does not release it on a value that is no longer true)."""
        gone = {r.name for r in b.reads() if r.kind == "goal" and r.name in self.stale}
        ofs = {self.spec.goals[g].of for g in gone}

        def get(r):
            if r.kind == "goal" and r.port == "off" and r.name in gone:
                return 1.0
            return None if r in ofs else self.get(r)
        return get

    def touch(self, *keys: str, goals=()) -> None:
        """Signals that changed outside a pass (a run's command, a setpoint it set): the next pass works them out."""
        with self.lock:
            self.dirty_keys.update(keys)
            self.dirty_goals.update(goals)
            self.poked = True
        self.wake.set()

    def poke(self, *blocks: str, now: bool = True) -> None:
        """A run ended: a pass soon (the loop's next), with these blocks looked at again; at once when no loop runs
        (``now``: else at the next pass, whenever that is)."""
        with self.lock:
            self.dirty_blocks.update(blocks)
            self.poked = True
        if self.looping:
            self.wake.set()
        elif now:
            self.evaluate()

    # ---- machine blocks

    def command_of(self, b: Block) -> tuple[float | None, dict]:
        """What commands it now: the largest of its commanders' outputs (None: nothing commands it)."""
        vals, detail = [], {}
        for c in self.spec.commanders_of(b.name):
            port = next((p for p, rs in c.outputs.items() if Ref("block", b.name) in rs), None)
            v = self.get(Ref("block", c.name, port if port and port != "out" else None))
            if v is None:
                r = next((r for r in b.inputs.values() if r.kind == "block" and r.name == c.name), None)
                v = self.get(r) if r else None
            if v is not None:
                vals.append(v)
                detail = {**self.commands.get(c.name, {}).get(port or "out", {}), "from": c.name}
        if not self.spec.commanders_of(b.name):
            return None, {}
        return (max(vals) if vals else 0.0), detail

    def due(self, b: Block, out: list | None = None) -> bool:
        if b.name in self.running or b.takes or b.on:         # started by the items it takes, or by its events
            return False
        cmd, _ = self.command_of(b)
        gap = bounds.pace(self.spec, b, b.every)                # (an untrusted library's: never under its floor)
        if cmd is None:
            if b.every or b.cron:
                return False                                    # on its own schedule
            data = [r for r in b.inputs.values() if r.kind != "block"]
            if gap and time.time() - self.began.get(b.name, 0.0) < gap:
                return False
            return bool(data) and self.last_reading > self.finished.get(b.name, 0.0)
        on = bool(cmd)
        rising = on and not self.was_commanded.get(b.name)
        self.was_commanded[b.name] = on
        if not on:
            self.asked.pop(b.name, None)
            return False
        if self.stale_mode(b) == "hold":
            return False                                        # a stale reading: it keeps its last command
        if b.type == "person" or b.mode == "advise":
            if rising or (b.mode == "advise" and self.asked.get(b.name) != cmd):   # a new command asks again
                self.asked[b.name] = cmd
                self.ask(b, cmd, out)
            return False
        flows = [t.name for t in b.targets() if t.kind == "flow"]
        if any(s.series in self.reading for s in self.after_acting(flows)):
            return False                                        # its last effect is not read yet: never outrun its sensors
        if gap and time.time() - self.began.get(b.name, 0.0) < gap:
            return False                                        # paced: a commanded block runs at most every `every`
        return rising or self.fresh_for(b, flows) > self.finished.get(b.name, 0.0)

    def fresh_for(self, b: Block, flows: list[str]) -> float:
        """The newest reading that bears on this block: of the stocks its flows touch, and of what
        its goals are about (any reading, when it has neither)."""
        series = {s.series for s in self.after_acting(flows)}
        for g in self.served(b) | {r.name for r in b.reads() if r.kind == "goal"}:
            of = self.spec.goals[g].of
            t = self.spec.measured(of.kind).get(of.name)
            series |= {s.series for s in t.sensors.values()} if t else set()
        if not series:
            return self.last_reading
        return max((self.seen.get(x, 0.0) for x in series), default=0.0)

    def ask(self, b: Block, cmd: float, out: list | None = None) -> None:
        what = "person.asked" if b.type == "person" else "block.advised"
        self._event(out, what, item=b.name, source=SOURCE,
                          data={"command": cmd, "ask": str(b.params.get("ask", "")),
                                "how": f"ergostat block {b.name} --done N" if b.type == "person"
                                else f"ergostat block {b.name} --approve"})
        self.say(f"{b.name}: {'asked' if b.type == 'person' else 'advised, waiting for approval'} (command {cmd:g})")

    def start(self, b: Block, why: str, extra: dict | None = None, cause: str | None = None) -> bool:
        """A run of it, in a thread of its own; False when none started."""
        with self.lock:
            if b.name in self.running or self.stop.is_set():   # stopping: nothing new starts
                return False
            if b.name in self.held:                             # a step test holds the loop still: its controller waits
                return False
            b = self.spec.blocks.get(b.name)                    # a new run starts under the model as it is now
            if b is None or not b.machine:                      # (removed, or no longer a machine: no more runs)
                return False
            if not self.own(f"block.{b.name}"):                 # another shard's block: never run here (SPEC §9.8)
                self.say(f"{b.name}: not started here, it is shard {self.plan.of(f'block.{b.name}')}'s")
                return False
            if not bounds.room(self, b):                        # an untrusted library's runs at once: counted and
                return False                                    # added under this one lock (SPEC §2a)
            bounds.hold(self, b.name, b)
            self.began[b.name] = time.time()
            spec, version = self.spec, self.version
        threading.Thread(target=self._run, args=(b, why, spec, version, extra, cause), daemon=True).start()
        return True

    def _run(self, b: Block, why: str, spec: Spec | None = None, version: str | None = None, extra: dict | None = None,
             cause: str | None = None) -> None:
        slot = self.slots.get(b.agent or "")                    # the one it takes is the one it gives back
        moved: list[str] = []
        run = None
        try:
            if slot:
                slot.acquire()
            try:
                moved = self.run_block(b, why, extra=extra, spec=spec, version=version, cause=cause)
                run = self.last_run.get(b.name)
            except Exception as e:
                self.say(f"{b.name}: {type(e).__name__}: {e}")
                moved = []
        finally:
            if slot:
                slot.release()
            with self.lock:
                self._read_moved(moved, run)                    # read after acting: the loop sees the effect now
                self.running.discard(b.name)
                self.finished[b.name] = time.time()
        self.poke(b.name)

    def after_acting(self, flows, spec: Spec | None = None) -> list[Sensor]:
        """The sensors of the stocks these flows connect: read at once after a block moves them (a flow the model
        no longer has, moved by a run that started before it changed, has none)."""
        spec, out = spec or self.spec, []
        for f in flows:
            fl = spec.flows.get(f)
            if fl is None:
                continue
            for st in (fl.source, fl.target):
                if st in spec.stocks:
                    out += [s for s in spec.stocks[st].sensors.values() if s.measured]
        return out

    def _read_moved(self, flows, cause: str | None, spec: Spec | None = None) -> None:
        """The sensors after_acting names that are in this engine's shard (``Plan.of``; all, with no shard), each read
        at once, its reading caused by the run ``cause``. Another shard's are read by their owner (``_moved``)."""
        with self.lock:
            for s in self.after_acting(flows, spec):
                try:
                    if not self.own(f"{s.of.kind}.{s.of.name}.{s.name}", spec):
                        continue
                except (KeyError, ValueError):                  # (in no shard of this model: not read here)
                    continue
                if cause:
                    self.read_cause[s.series] = cause           # (what that reading crosses, this run caused)
                self.read_soon(s)                               # (marked under way before it may run again)

    def _moved(self, e: dict) -> None:
        """A run's ended event that moved flows (``data.moved``), followed by seq (``_follow``): the moved stocks' sensors
        in this shard read at once, caused by that run. None with no shard, nor for a block this engine follows under
        the model now: its own runs were read by ``_run``. So a swap that moves the block between its run and this
        leaves the new owner's stocks to their schedule: read at once by neither, never twice. A ``moved`` not a
        mapping, a flow moved by 0, NaN or not a number, a flow or stock this model lacks: no read."""
        spec, d = self.spec, e.get("data")
        moved = d.get("moved") if isinstance(d, dict) else None
        if self.shard is None or not isinstance(moved, dict) or self.follows(f"block.{e.get('item') or ''}", spec):
            return
        flows = [f for f, v in moved.items() if type(v) in (int, float) and v == v and v]
        self._read_moved(flows, e["causedby"] if isinstance(e.get("causedby"), str) else None, spec)

    def context(self, b: Block, why: str) -> dict:
        cmd, detail = self.command_of(b)
        amount = cmd
        if amount is not None and b.max is not None:
            amount = min(amount, b.max)
        if amount is not None and b.min is not None and amount:
            amount = max(amount, b.min)
        inputs = {str(r): self.get(r) for r in b.inputs.values()}
        goals = {}
        for name in {r.name for r in b.reads() if r.kind == "goal"} | self.served(b):
            g = self.spec.goals.get(name)
            if g is None:                                         # (a goal gone from the model as the run began)
                continue
            held = self.per.get(name) if g.per else None          # held per item or group: the worst, and who (SPEC §8)
            goals[name] = {"hold": f"{g.hold.op} {self.signals.get(f'goal.{name}', g.hold.value):g}",
                           "value": held[0] if held else self.signals.get(str(g.of)),
                           "error": self.signals.get(f"goal.{name}.error"), "status": self.status.get(name, "unknown"),
                           **({"per": g.per, "breaking": held[1], "breaking_n": held[2]} if held else {})}
            if name in self.stale:                                # its reading is stale: it knows (SPEC §9.6)
                goals[name]["stale"] = round(self.stale[name], 1)
                if self.stale_mode(b) == "off":
                    goals[name]["status"] = "off"
        out = {"block": b.name, "type": b.type, "trigger": why, "inputs": inputs, "goals": goals,
               "outputs": {p: [str(r) for r in rs] for p, rs in b.outputs.items()}}
        if stale := self.stale_in(b):
            out["stale"] = {k: round(v, 1) for k, v in stale.items()}
        if self.spec.improve.reviewed and b.type in ("ai", "person"):   # an author: the reviewer's verdicts on its changes
            from ..numbers import reviewer as rv
            if said := rv.memory(self.p, b.name):
                out["reviewer"] = said
        law = {k: b.params[k] for k in ("gain", "integral-time", "deadband", "resolution", "limits") if b.params.get(k) is not None}
        if law:
            out["params"] = law                                   # its control law's constants, as the model writes them
        test = self.testing.get(b.name)
        if why == "step-test" and test:                           # a step test the owner approved: move exactly this
            out["command"] = {"amount": test["amount"], "test": test["id"], "from": "step-test",
                              **({"to": test["to"]} if test.get("to") is not None else {})}
            return out
        if cmd is not None:
            out["command"] = {**{k: v for k, v in detail.items() if k != "amount"}, "amount": amount}
            if amount != cmd:
                out["command"]["asked"] = cmd
        return out

    def served(self, b: Block) -> set[str]:
        """The goals whose loop it acts in (as an actuator): worked out once per model (docs/proposals/scale.md)."""
        spec = self.spec
        kept = spec.lookups().kept
        by = kept.get("engine.served")
        if by is None:
            by = {}
            for g in spec.goals:
                for a in spec.loop(g).actuators:
                    by.setdefault(a, set()).add(g)
            kept["engine.served"] = by
        return set(by.get(b.name, ()))

    def program(self, b: Block, ctx: dict, spec: Spec | None = None) -> tuple[str, str]:
        """The command to run and what to give it on standard input."""
        spec = spec or self.spec
        payload = json.dumps(ctx)
        if b.type != "ai":
            return str(b.params.get("run") or ""), payload    # (a daemon's block has none: SPEC §9.7)
        prompt = str(b.params["prompt"])
        path = spec.root / prompt
        if "\n" not in prompt and path.is_file():
            prompt = path.read_text(encoding="utf-8")
        cmd = str(b.params.get("run") or AI_COMMAND)
        model = b.params.get("model") or (spec.agents[b.agent].model if b.agent in spec.agents else None)
        if model and "run" not in b.params and "--model" not in cmd:
            cmd += f" --model {model}"
        if "run" not in b.params and "--output-format" not in cmd and costs_ai.is_claude(cmd):
            cmd += " --output-format json"                # its result as JSON: its text, and its cost (SPEC §9.1)
        if "run" not in b.params and spec.budget is not None and costs_ai.is_claude(cmd):   # T1: its reserve, ours wins
            cmd = re.sub(r"\s--max-budget-usd(?:=|\s+)\S+", "", cmd) + f" --max-budget-usd {budget.reserve_of(spec, b)}"
        return cmd, prompt + AI_FOOTER + payload

    def run_block(self, b: Block, why: str, extra: dict | None = None, spec: Spec | None = None,
                  version: str | None = None, item: str | None = None, fence: int | None = None,
                  run_id: str | None = None, cause: str | None = None, outcome: dict | None = None) -> list[str]:
        """One run: give it its inputs and command, record what it says. Returns the flows it moved. ``extra``: more
        for its input (a classifier's message and candidates; a leased item and its lease). ``spec`` and ``version``:
        the model it started under (the one loaded now, by default); it finishes under it, whatever the model becomes
        meanwhile. ``item``, ``fence``: the item it holds a lease on (SPEC §9.5), and the lease's fencing number;
        ``run_id``, the run's id, named by the lease before it starts; ``cause``, what started it; ``outcome`` is filled
        with how it ended (exit, note, nack)."""
        if b.takes and item is None:                             # a block that takes items runs on one, leased (SPEC §9.5)
            return self.dispatch.once(b, why, outcome)
        spec, version = spec or self.spec, version or self.version
        ctx = {**self.context(b, why), **(extra or {})}
        ev = self.p.events
        commander = (ctx.get("command") or {}).get("from")          # caused by the decision or run that commanded it
        cause = cause or (self.cause.get(commander) if commander else None)
        data = {"trigger": why, "command": ctx.get("command"), "model": version,
                **({"event_seq": ctx["event"].get("seq")} if isinstance(ctx.get("event"), dict) else {}),
                **self.triggers.of_run(b, ctx, cause),          # what led to it, carried (SPEC §9.3)
                **({"timeout": b.timeout} if b.timeout else {}),
                **({"item": item, "lease": fence} if item else {})}

        def write(more: dict | None = None) -> dict:
            return ev.add("agent.started", item=b.name, source=SOURCE, id=run_id, causedby=cause, data={**data, **(more or {})})
        if spec.budget is None or item is not None:          # (a leased run reserved at its take: not again)
            begun = write()
        else:                                                # the permissive (SPEC §9.9)
            run_id = run_id or uuid.uuid4().hex
            begun, no = budget.permit(self.p, spec, b, write, run_id)
            if begun is None:
                if outcome is not None:
                    outcome["refused"] = no
                self.say(f"{b.name}: refused: budget: {no}")
                return []
        try:
            return self._ran(b, why, spec, version, item, fence, ctx, begun, outcome)
        except BaseException:
            if begun["id"] in budget.OPEN:                   # raised out of before its end: its reserve stays charged
                with contextlib.suppress(Exception):
                    budget.close(self.p, b.name, begun["id"], None, "the run raised before its end")
            raise
        finally:
            budget.OPEN.discard(begun["id"])
            budget.remove(self.p.dir, begun["id"])          # its sessions' ledger (T1): its own file only

    def _ran(self, b: Block, why: str, spec: Spec, version: str | None, item: str | None, fence: int | None, ctx: dict,
             begun: dict, outcome: dict | None) -> list[str]:
        """The run, once started (its ``agent.started`` written): to its end."""
        ev = self.p.events
        if outcome is not None:
            outcome["run"] = begun["id"]
        self.last_run[b.name] = begun["id"]
        if "command" in ctx:
            ev.add("block.commanded", item=b.name, source=SOURCE, causedby=begun["id"], data=ctx["command"])
        if why != "message":                                     # the owner's messages that waited for it (SPEC §12h)
            try:
                from ..messages import deliver
                msgs = deliver.for_context(self.p, spec, b, begun["id"], item=item)
            except Exception as e:                               # a message never stops a run
                self.say(f"{b.name}: messages: {type(e).__name__}: {e}")
                msgs = []
            if msgs:
                ctx["messages"] = msgs
        cmd, stdin = self.program(b, ctx, spec)
        started = time.time()
        env = {**os.environ, "ERGOSTAT_BLOCK": b.name, "ERGOSTAT_AGENT": b.name, "ERGOSTAT_RUN": begun["id"],
               "ERGOSTAT_PROJECT": spec.name, "ERGOSTAT_STATE_DIR": str(self.p.dir), "ERGOSTAT_MODEL_VERSION": version,
               "ERGOSTAT_CMD": f"{shlex.quote(sys.executable)} -m ergostat -C {shlex.quote(str(spec.root))}"}
        if self.socket:                                          # its calls answered by this engine (calls/)
            env["ERGOSTAT_SOCKET"] = self.socket
        else:
            env.pop("ERGOSTAT_SOCKET", None)
        if "command" in ctx:
            env["ERGOSTAT_COMMAND"] = f"{ctx['command']['amount']:g}"
        env.pop("ERGOSTAT_EVENT", None)
        env.pop("ERGOSTAT_JOURNAL", None)                        # (a kept run's own, below: never one inherited)
        reserve = budget.reserve_of(spec, b) if spec.budget is not None else None
        env.pop("ERGOSTAT_MAX_COST", None)                       # its cap (T1, SPEC §9.9), never one inherited
        if reserve is not None:
            env["ERGOSTAT_MAX_COST"] = str(reserve)
        if isinstance(ctx.get("event"), dict):                   # the event that started it (SPEC §9.3)
            env["ERGOSTAT_EVENT"] = str(ctx["event"].get("id"))
        if item:                                                 # the item it holds, and its lease (SPEC §9.5)
            lease = ctx.get("lease") or {}
            env.update({"ERGOSTAT_ITEM": item, "ERGOSTAT_LEASE": str(fence or ""),
                        "ERGOSTAT_LEASE_TTL": f"{float(lease.get('ttl') or 0):g}",
                        "ERGOSTAT_LEASE_EXPIRES": f"{float(lease.get('expires') or 0):.3f}"})
        else:                                                    # none: not one inherited from where ergostat was started
            for k in ("ERGOSTAT_ITEM", "ERGOSTAT_LEASE", "ERGOSTAT_LEASE_TTL", "ERGOSTAT_LEASE_EXPIRES"):
                env.pop(k, None)
        if (ctx.get("command") or {}).get("review"):             # a review asked of it: the ask is answered by this run
            with self.lock:
                frm = ctx["command"].get("from")
                if frm in self.outputs:
                    self.outputs[frm][f"review-{b.name}"] = 0.0
                    self.touch(f"block.{frm}")
        given = self.start_context(b, ctx, begun["id"], env, spec, item) if b.params.get("context") else None
        ready, refused = self.place(b, ctx, begun["id"], env, given, spec)   # its folder, and what its session may use
        cmd, stdin = self.program(b, ctx, spec)                   # (its input, with the context it was given)
        if given and b.type == "ai" and "run" not in b.params:   # claude -p itself: the context after its own prompt
            cmd += f" --append-system-prompt-file {shlex.quote(given['file'])}"
        if ready.cfg and "run" not in b.params:                  # claude -p itself: in its folder, gated when it is
            from ..actions import sandbox
            cmd += " " + sandbox.command_line(ready.cfg)
        cwd = ready.workdir if ready.workdir and "run" not in b.params else spec.root
        note, code, resources = "", None, None
        said = Said(self, b, begun["id"], spec, version, item=item, fence=fence)

        usage = costs_ai.Usage(b.params.get("model") or (spec.agents[b.agent].model if b.agent in spec.agents else None))
        from .. import runlog
        try:                                                     # its own log, or it does not start (SPEC §4b)
            seq = begun.get("seq")
            seq = seq if seq is not None else (ev.get(begun["id"]) or {}).get("seq")
            rl = runlog.open_run(self.p, b.name, seq, begun["id"])
        except Exception as e:
            rl, note = None, f"could not start: its run log: {e}"

        trip: list[bool] = []

        def logged(got: list[str], n: int) -> None:             # (after its AI usage was taken: it had n parts before)
            if reserve is not None and len(usage.parts) > n and budget.tripped(usage.parts, reserve):
                from ..leases import kill as lease_kill
                trip.append(True)                               # T1: its process group stopped (SPEC §9.9)
                lease_kill.kill(self, begun["id"], budget.T1, item, fence, b.name)
            for raw in got:
                if not raw.strip().startswith("{"):
                    lf.write(raw if raw.endswith("\n") else raw + "\n")
            lf.flush()

        def take(got: list[str]) -> None:                       # its lines, as they arrive (SPEC §9.1)
            n = len(usage.parts)
            got = costs_ai.expand(usage, got)                   # (what its AI sessions cost, taken as they say it)
            logged(got, n)
            said.lines(got)
        lf, back, tail, unread = rl.file if rl else None, None, "", ""
        kept_end = None                                          # a kept run's files and keeper, let go once it ended
        try:
            if rl is None:                                       # (no log of its own: not started)
                pass
            elif b.params.get("daemon") and not refused:            # handed to its daemon (SPEC §9.7): wall time only
                code, note, back, resources = self.daemons.run_item(b, begun["id"], ctx, env, take, b.timeout, item,
                                                                     fence)
                with self.lock:
                    killed = self.killing.pop(begun["id"], None)
                note = f"killed: {killed}" if killed else note or (f"exited {code}" if code else "")
            else:
                kept = spec.outlive_engine                   # held by a keeper, never stopped with us (SPEC §9.1)
                name = begun["id"] if not kept or keeper.RUN.fullmatch(begun["id"]) else uuid.uuid4().hex
                # its input, output, exit, record; kept: its output its journal, appended, and the offset read to
                files, proc = (adopt.files if kept else runrecord.files)(self.p.dir, name), None
                if kept:
                    env["ERGOSTAT_JOURNAL"] = str(files["out"])
                try:
                    if refused:
                        raise OSError(refused)
                    if kept:
                        os.close(os.open(files["out"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600))
                        proc = keeper.launch(str(self.p.dir.resolve()), name,
                                             "exec " + shlex.join(runrecord.command(cmd, files)), stdin or "",
                                             str(cwd), env, str(files["out"]), lf.fileno(), b.timeout)
                    else:
                        files["in"].write_text(stdin or "", encoding="utf-8")
                        with open(files["in"], "rb") as fin, open(files["out"], "wb") as fout:
                            proc = Measured(runrecord.command(cmd, files), cwd=cwd, env=env, stdin=fin, stdout=fout,
                                            stderr=lf, start_new_session=True)
                    runrecord.write(files, proc.pid, begun["id"], b.name, item, fence, {
                        "log": rl.rel, "given": (given or {}).get("item"),
                        "workspace": {"item": ready.item, "lease": ready.lease} if ready.workspace else None,
                    } if kept else None)
                except OSError as e:
                    note = refused or f"could not start: {e}"
                    if proc is not None:                         # started, but its record not written: stopped
                        old._kill(proc)
                        proc.wait()
                        if kept:
                            proc.release()
                    runrecord.remove(files)
                else:
                    if not kept:                                 # (kill_all's: a kept run is left going)
                        old.LIVE.add(proc)
                    elif item:                                   # (and its lease with it, as we stop)
                        self.dispatch.keeping.add(begun["id"])
                    with self.lock:
                        self.procs[b.name] = proc
                        self.live[begun["id"]] = proc
                        stopping = self.stop.is_set()            # (set under this lock: close's kill missed this run;
                    if stopping:                                 # not STOPPING: process-wide)
                        old._kill(proc)
                    tracked, left = SAMPLER.track(proc), False      # its process tree's CPU and memory, sampled
                    try:
                        proc.watch = reap.Watch(proc.pid)            # what it starts, for a lease kill (leases/kill.py)
                        got = (stream.follow(proc, files["out"], b.timeout,
                                             adopt.taker(said, usage, files["offset"], logged), self.stop, start=0)
                               if kept else stream.follow(proc, files["out"], b.timeout, take))   # (off: as before)
                        left = got is None                           # we stop, it goes on: its end is not ours
                        if got or kept and not left and proc.how() == "timeout":   # (its keeper's, should that
                            note = f"stopped after its timeout of {b.timeout:g}s"     # come first)
                    finally:
                        if kept and not left:                        # (kept till its end is recorded: SPEC §9.1)
                            kept_end = (files, proc)
                        elif not left:
                            runrecord.remove(files)                  # read to its end: nothing left to take again
                        resources = SAMPLER.finish(tracked)
                        if getattr(proc, "watch", None):
                            proc.watch.close(look=False)         # (its run is over: no last ps)
                        old.LIVE.discard(proc)
                        with self.lock:
                            if self.procs.get(b.name) is proc:
                                del self.procs[b.name]
                            asked = b.name in self.stopping_runs
                            self.stopping_runs.discard(b.name)
                            self.live.pop(begun["id"], None)
                            killed = self.killing.pop(begun["id"], None)
                    if left:                                     # no agent.ran: its journal and its keeper's exit
                        self.say(f"{b.name}: its run {begun['id'][:8]} goes on without us ({files['out']})")
                        if outcome is not None:                  # are what is left of it, for the next engine to
                            outcome["left"] = True               # take up, its lease still held (SPEC §9.1)
                        return []
                    code = proc.returncode
                    if killed:                                       # its lease expired: stopped (leases/kill.py)
                        note = f"killed: {killed}"
                    elif code and not note:
                        note = (old.STOPPED_WITH_US if old.STOPPING.is_set() or self.stop.is_set()
                                else STOPPED_BY_OWNER if asked else f"exited {code}")
        finally:                                                 # its entry in the block's log, whole, as it ends
            if rl is not None:
                from ..repair.capture import TAIL, clip
                try:                                             # (read first, whatever the block log's fate)
                    tail = clip(rl.tail(TAIL + 1)) if note or (code == 0 and "ergostat.failure" in spec.items) else ""
                except Exception as e:
                    tail = f"(its run log {rl.rel} could not be read: {type(e).__name__}: {e})\n"
                    unread = f"its run log could not be read: {type(e).__name__}: {e}"
                try:
                    runlog.finish(rl, begun["time"], why, self.p.storage.logs["block"])
                except Exception as e:
                    self.say(f"{b.name}: its log: {type(e).__name__}: {e}")
                finally:
                    rl.close()
                try:
                    runlog.prune(self.p, b.name, self.p.storage.logs.get("runs"))
                except Exception as e:
                    self.say(f"{b.name}: its run logs: {type(e).__name__}: {e}")
        if trip and (not note or note.startswith(("exited", f"killed: {budget.T1}"))):   # (ended past its cap, either way)
            note = budget.T1
        if code == 0 and not note:                              # a bare number only from a run that finished well
            said.finish()
        said.tally()
        data = {"exit": code, "seconds": round(time.time() - started, 3), "why": why, **said.counts,
                **({"daemon": b.params["daemon"]} if b.params.get("daemon") else {}),
                **({"log": rl.rel} if rl else {}),
                **({"item": item} if item else {}),
                **({"note": note} if note else {}), **({"moved": said.moved} if said.moved else {}),
                **({"commanded": ctx["command"]["amount"]} if "command" in ctx else {}), "model": version,
                **({"model_now": self.version} if self.version != version else {}),   # it ran across a change
                **({"resources": resources} if resources else {}), **({"ai": ai} if (ai := usage.record()) else {})}
        self.moved_by[b.name] = dict(said.moved)
        if ready.workspace:                                      # its run was its lease, when it had none: released
            try:
                from ..workspaces import leases
                leases.run_ended(self.p, spec, ready.item, begun["id"], ready.lease)
            except Exception as e:
                self.say(f"{b.name}: workspace: {type(e).__name__}: {e}")
        failed = bool(note) and note not in (old.STOPPED_WITH_US, STOPPED_BY_OWNER) and not ready.full
        if outcome is not None:
            outcome.update({"exit": code, "note": note, "nack": said.nack, "stopped": note in (old.STOPPED_WITH_US, STOPPED_BY_OWNER)})
            if back:                                             # its daemon restarted for another's fault, or gave up
                outcome["nack"] = {**back, "why": back.get("why") or note}
            if ready.full:                                       # no workspace free: given back, put off, not counted
                outcome["nack"] = {"why": note, "after": POOL_FULL_AFTER, "count": False}
        ended = ev.add("agent.failed" if failed else "agent.ran", item=b.name, source=SOURCE, causedby=begun["id"], data=data,
                       id=adopt.end_id(begun["id"]) if kept_end else None)   # (a kept run's: one end, SPEC §9.1)
        budget.OPEN.discard(begun["id"])                          # (ended: nothing after this closes it again)
        if kept_end and item and outcome is not None:            # its files go once its lease's end is written too
            outcome["done"] = lambda: adopt.let_go(*kept_end)
        try:                                                     # its numbers as series of its block (SPEC §9.1)
            costs_record.write_series(self.p, b.name, data, ended["time"])
        except Exception as e:
            self.say(f"{b.name}: its costs: {type(e).__name__}: {e}")
        self.after_end(b, spec, begun, data, said, failed, given, stdin, tail, unread, logged=rl is not None)
        if kept_end:                                             # (its end's steps done: not again by the next engine)
            adopt.settled(kept_end[0])
            if not (item and outcome is not None):
                adopt.let_go(*kept_end)
        return [f for f, v in said.moved.items() if v]           # moving nothing is not a reason to read again

    def after_end(self, b: Block, spec: Spec, begun: dict, data: dict, said: Said, failed: bool, given: dict | None,
                  stdin: str, tail: str, unread: str = "", logged: bool = True) -> None:
        """What follows a run's end, once its ``agent.ran`` or ``agent.failed`` is written: its failure triaged, its
        claims checked, its recipes' outcomes, its review. A run taken up has the same (``adopt.settle``, SPEC §9.1)."""
        code, note = data.get("exit"), data.get("note") or ""
        if failed:
            self.say(f"{b.name}: {note}")
            if spec.items.get("ergostat.failure"):               # triaged, one failure a signature (SPEC §12r)
                try:
                    from ..repair import capture
                    capture.failed(self.p, spec, b, begun, data, stdin, tail)   # (its own file's, only)
                except Exception as e:
                    self.say(f"{b.name}: its failure: {type(e).__name__}: {e}")
        elif code == 0 and not note and logged and b.type in ("program", "ai") and spec.items.get("ergostat.failure"):
            try:                                                 # an error it caught and printed (SPEC §12r)
                if unread:                                       # (unread: nothing recorded, and said)
                    raise OSError(unread)
                from ..repair import capture
                capture.swallowed(self.p, spec, b, begun, tail, stdin)
            except Exception as e:
                self.say(f"{b.name}: its swallowed check: {type(e).__name__}: {e}")
        if said.refused:
            self.say(f"{b.name}: {said.refused[0]}")
        if said.claims:                                          # what it said it did, checked by ergostat (SPEC §12g)
            from ..claims import checks
            for c in checks.check_all(self.p, spec, said.claims):
                if c["state"] == "contradicted":
                    self.say(f"{b.name}: claim contradicted: {c['says']!r}: {c['why']}")
        if spec.contexts:                                        # how the work each recipe started turned out
            self.outcomes()
        if not failed and b.params.get("review"):                # who reviews its work, and how deeply, by its trust
            self.review(b, begun["id"], given)

    def place(self, b: Block, ctx: dict, run: str, env: dict, given: dict | None, spec: Spec | None = None):
        """An ``ai`` block's folder and what its session may use (SPEC §12k): a workspace from its pool for the item it
        works on, or its workdir:; its read:, tools: and actions:; a ``program`` block's workspace: and actions:.
        Returns what was made ready, and why the run cannot start (no workspace to give it), or None."""
        from ..actions import prepare as pr
        if b.type not in ("ai", "program"):
            return pr.Prepared(), None
        try:
            ready = pr.prepare(self.p, spec or self.spec, b, ctx, run, env, given,
                               runner="ergostat" if self.following else "here")
        except Exception as e:                                   # no workspace for it: the run does not start
            from ..workspaces.pool import PoolError, PoolFull
            why = str(e) if isinstance(e, PoolError) else f"{type(e).__name__}: {e}"
            return pr.Prepared(full=isinstance(e, PoolFull)), why
        if b.params.get("actions"):                              # what its sessions asked for and were not answered
            from ..actions import gate
            got = gate.for_context(self.p, b.name, run, item=env.get("ERGOSTAT_ITEM") or None)
            if got:
                ctx["actions"] = got
        return ready, None

    def start_context(self, b: Block, ctx: dict, run: str, env: dict, spec: Spec | None = None,
                      leased: str | None = None) -> dict | None:
        """The block's recipe rendered for this run's item (SPEC §12j): written to a file in the state directory,
        recorded as a use (``ergostat.context.used``), named in its input (``context``) and its environment
        (``ERGOSTAT_CONTEXT``, the file; ``_RECIPE``, ``_HASH``, ``_ITEM``) for the session it starts."""
        from ..recipes import render as rd
        from ..recipes import uses
        want = b.params["context"]
        spec = spec or self.spec
        try:
            item = rd.item_for(self.p, spec, want.get("item"), leased or (ctx.get("command") or {}).get("item"), b.name, run)
            r = rd.render(self.p, spec, want["recipe"], item, b.name, run)
        except Exception as e:                                   # a context that cannot be rendered: the run goes on without
            self.p.events.add("agent.refused", item=b.name, source=SOURCE, causedby=run,
                              data={"why": f"context {want['recipe']}: {type(e).__name__}: {e}"})
            self.say(f"{b.name}: context {want['recipe']}: {type(e).__name__}: {e}")
            return None
        d = self.p.dir / "contexts"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{b.name}-{run[:8]}.md"
        f.write_text(r.text, encoding="utf-8")
        uses.used(self.p, r, b.name, run, str(f))
        given = {"recipe": r.recipe, "version": r.version, "tag": r.tag, "hash": r.hash, "chars": len(r.text),
                 "item": r.item, "file": str(f)}
        ctx["context"] = given
        env.update({"ERGOSTAT_CONTEXT": str(f), "ERGOSTAT_CONTEXT_RECIPE": r.tag, "ERGOSTAT_CONTEXT_HASH": r.hash,
                    "ERGOSTAT_CONTEXT_ITEM": r.item or ""})
        return given

    def outcomes(self) -> None:
        from ..recipes import uses
        if not self.outcomes_lock.acquire(blocking=False):      # one pass at a time; one under way will see it
            return
        try:
            uses.refresh(self.p, self.spec)
        except Exception as e:                                   # the next pass tries again
            self.say(f"contexts: outcomes: {type(e).__name__}: {e}")
        finally:
            self.outcomes_lock.release()

    def review(self, b: Block, run: str, given: dict | None) -> None:
        """After a run that ended well: whether its work is reviewed, by whom and how deeply (SPEC §12j)."""
        from ..recipes import review as rv
        d = rv.decide(self.p, b)
        if d is None:
            return
        item = (given or {}).get("item")
        if item is None:
            from ..claims import record
            item = next((c["about"]["item"] for c in record.of_run(self.p, run) if (c.get("about") or {}).get("item")), None)
        data = {**d, "of": run, **({"item": item} if item else {})}
        if not d["by"]:
            self.p.events.add("review.skipped", item=b.name, source=SOURCE, causedby=run, data=data)
            return
        ev = self.p.events.add("review.required", item=b.name, source=SOURCE, causedby=run, data=data)
        port = f"review-{d['by']}"
        with self.lock:
            self.outputs.setdefault(b.name, {})[port] = 1.0
            self.commands.setdefault(b.name, {})[port] = {"amount": 1.0, **({"item": item} if item else {}),
                                                          "review": {"of": run, "depth": d["depth"], "why": d["why"]}}
            self.cause[b.name] = ev["id"]
        self.touch(f"block.{b.name}")
        self.say(f"{b.name}: review by {d['by']} ({d['depth']}): {d['why']}")   # (it starts at the next pass)

    def judge(self, b: Block) -> None:
        """One pass of the judge, ergostat's own (no program): recorded as a run, what it moved said on its ports. A
        judge of changes to the model (SPEC §12e), or the intent judge of finished work (``judge: intent``, §12i)."""
        if b.judge_mode == "intent":
            from ..intent import judge as jd
        else:
            from ..numbers import judge as jd
        ev = self.p.events
        spec, version = self.spec, self.version
        begun = ev.add("agent.started", item=b.name, source=SOURCE, data={"trigger": "schedule", "model": version, **(
            {"reserve": 0.0, "pid": os.getpid()} if spec.budget else {})})   # (its calls reserve, SPEC §9.9)
        started, within = time.time(), budget.WITHIN.set((begun["id"], True))   # (its end sums its calls' costs)
        try:
            got = jd.run(self.p, spec, by=b.name) if b.judge_mode == "intent" else jd.run(self.p, by=b.name)
        except Exception as e:
            ev.add("agent.failed", item=b.name, source=SOURCE, causedby=begun["id"],
                   data={"exit": None, "seconds": round(time.time() - started, 3), "note": f"{type(e).__name__}: {e}"})
            self.say(f"{b.name}: {type(e).__name__}: {e}")
            return
        finally:
            budget.WITHIN.reset(within)
            with self.lock:
                self.running.discard(b.name)
        if got.get("refused"):
            self.say(f"{b.name}: refused: {got['refused']}")
        if b.judge_mode != "intent":                   # nothing new to judge: it backs off (judge.pause)
            every = bounds.pace(spec, b, b.every or JUDGE_EVERY)
            wait = jd.pause(got, every, self.judge_idle.get(b.name, 0))
            self.judge_idle[b.name] = 0 if wait <= every else self.judge_idle.get(b.name, 0) + 1
            self.judge_next[b.name] = time.monotonic() + wait
        said = Said(self, b, begun["id"], spec, version)
        for line in jd.lines(spec, b.name, got):
            said.take(line)
        said.flush()
        ev.add("agent.ran", item=b.name, source=SOURCE, causedby=begun["id"],
               data={"exit": 0, "seconds": round(time.time() - started, 3), "why": "schedule", "model": version,
                     **said.counts,
                     **{k: got[k] for k in getattr(jd, "PORTS", ())},
                     **({k: got[k] for k in ("judged", "met", "held", "missed", "cost_usd")} if b.judge_mode == "intent" else {}),
                     **({"moved": said.moved} if said.moved else {})})
        if b.judge_mode == "intent":
            for v in got.get("verdicts") or []:
                if v["verdict"] in ("unmet", "contradicted"):
                    self.say(f"{b.name}: {v['work']} not done as meant ({v['verdict']}): {v['why'][:200]}")

    # ---- sensors

    def read_soon(self, s: Sensor) -> None:
        """A reading asked for now (its schedule, or a run that moved its stock): marked under way at once; the loop
        takes it with the others asked meanwhile. Without a loop (an engine not started), a thread reads it."""
        key = s.series
        with self.lock:
            if key in self.reading:
                return
            self.reading.add(key)
            if self.looping:
                self.wanted[key] = s
        if self.looping:
            self.wake.set()
            return
        threading.Thread(target=self._read, args=(s,), daemon=True).start()

    def _observer(self, name: str):
        """Where a command's observations go: events about items, or the owner's messages it relays."""
        def observe(seen, refused):
            from ..store import ChangesetError
            for o in seen:
                if "message" in o:                       # the owner's words, relayed by a sensor (SPEC §12h)
                    from ..messages import route
                    m = o["message"]
                    try:
                        route.send(self.p, self.spec, m.get("text"), by=str(m.get("by") or "owner"),
                                   about=m.get("about"), via=f"sensor {name}")
                    except Exception as err:
                        refused.append(f"message: {err}")
                    continue
                why = "id" in o and mirror.valid(o["id"], name)     # a cite only of its own log (mirror.py)
                if why:
                    refused.append(why)
                    continue
                try:
                    self.p.events.add(o["type"], item=o["item"], source=name, data=o["data"], patch=o.get("patch"),
                                      set=o.get("set"), id=o.get("id"))
                except ChangesetError as err:
                    refused.append(f"{o['type']}: {err}")
            for why in refused:
                self.p.events.add("sensor.refused", item=name, source=SOURCE, data={"why": why})
                self.say(f"sensor {name}: {why}")
        return observe

    def _read(self, s: Sensor) -> None:
        """One reading on a thread of its own, then a pass: for an engine whose loop is not running."""
        try:
            v, why = read_sensor(self.spec, s, self.p.events, self._observer(sensor_name(s.of.name, s.name)), self.p.measurements,
                                   env=callback_env(self.spec, self.p.dir, self.socket))
            if v is None:
                self.p.events.add("sensor.failed", item=sensor_name(s.of.name, s.name), source=SOURCE, data={"why": why})
                self.say(f"sensor {s.of.name}.{s.name}: {why}")
            else:
                self.p.measurements.add(s.series, v)
        except Exception as e:
            self.say(f"sensor {s.of.name}.{s.name}: {type(e).__name__}: {e}")
        finally:
            with self.lock:
                self.reading.discard(s.series)
                self.dirty_series.add(s.series)
                cause = self.read_cause.pop(s.series, None)
        self.evaluate({s.of.name: cause} if cause else None)

    def _alarmed(self) -> set[str]:
        """The series of the sensors an alarm block reads."""
        kept = self.spec.lookups().kept
        if "engine.alarmed" not in kept:
            kept["engine.alarmed"] = {x.series for b in self.spec.blocks.values() if b.type == "alarm"
                                      for r in b.reads() if (t := self.spec.measured(r.kind).get(r.name))
                                      for x in t.sensors.values()}
        return kept["engine.alarmed"]

    def _read_one(self, s: Sensor, which: str = "", handed: float = 0.0) -> None:
        """One reading of a command or a query, on the pool (``which``: ``alarm_`` for the alarms' own), handed to it at
        ``handed``: its result posted to the loop. A late one from a pool since replaced touches nothing of the new."""
        out = getattr(self, f"{which}pool_out")
        with self.pool_lock:                                  # begun: only now may its timeout lengthen the wedge limit
            if out.get(s.series, (None,))[0] == handed:
                out[s.series] = (*out[s.series][:2], time.monotonic())
        try:
            v, why = read_sensor(self.spec, s, self.p.events, self._observer(sensor_name(s.of.name, s.name)), self.p.measurements,
                                   env=callback_env(self.spec, self.p.dir, self.socket))
            got = (s, v, why, time.time(), None)
        except Exception as e:
            got = (s, None, "", time.time(), e)
        with self.pool_lock:
            if out.get(s.series, (None,))[0] == handed:
                out.pop(s.series, None)
                setattr(self, f"{which}pool_done_at", time.monotonic())
        self.results.put(got)
        self.wake.set()

    def _item_sensors(self) -> tuple[dict[bool, list[Sensor]], dict[str, bool]]:
        """The model's sensors that count items, by the fold they count from; and each one's fold."""
        spec = self.spec
        kept = spec.lookups().kept
        got = kept.get(f"engine.item_sensors.{self.shard}")
        if got is None:
            from .counts import transcript_of
            by: dict[bool, list[Sensor]] = {False: [], True: []}
            flag = {}
            for s in spec.sensors():
                if s.items is not None and self.own(f"{s.of.kind}.{s.of.name}.{s.name}", spec):
                    flag[s.series] = transcript_of(spec, s)
                    by[flag[s.series]].append(s)
            got = kept[f"engine.item_sensors.{self.shard}"] = (by, flag)
        return got

    def _read_here(self, sensors: list[Sensor]) -> list[tuple]:
        """Readings ergostat takes itself, at once: counts of items (each fold followed once, then every count read
        from what it keeps), and flows read from their stock's changes."""
        spec = self.spec
        by, flag = self._item_sensors()
        counts = {}
        for tr in {flag.get(s.series, False) for s in sensors if s.items is not None}:
            try:
                if self.counts[tr].follow(self.p.events, spec, by[tr]):
                    counts[tr] = self.counts[tr]
            except Exception as e:                       # counted from the index as before, this time
                self.say(f"counting items: {type(e).__name__}: {e}")
        out = []
        for s in sensors:
            try:
                c = counts.get(flag.get(s.series, False)) if s.items is not None else None
                v, why = read_sensor(spec, s, self.p.events, None, self.p.measurements, counts=c)
                out.append((s, v, why, time.time(), None))
            except Exception as e:
                out.append((s, None, "", time.time(), e))
        return out

    def _readings(self, tick: bool) -> bool:
        """The loop's batch: every reading asked for since the last is begun (ergostat's own read here, commands and
        queries handed to the pool), what the pool read meanwhile is gathered, all of it written at once, and one pass
        follows (when anything was read or ended, or on the clock's tick). True when a pass ran.

        When the record was written since, every count of items is read too (they cost nothing to read), and those
        that changed are written and worked out with the rest: a goal on a queue sees its first item at once, not at
        its sensor's next reading (docs/proposals/latency.md)."""
        with self.lock:
            asked, self.wanted = list(self.wanted.values()), {}
            poked, self.poked = self.poked, False
            moved = self.record_moved and time.monotonic() >= self.count_next   # (at most a fifth of the loop's time)
            if moved:
                self.record_moved = False
        handed: set[str] = set()
        try:
            return self._begin(asked, moved, poked, tick, handed)
        finally:
            with self.lock:                                   # a reading begun here is never left under way for good
                for s in asked:
                    if s.series not in handed:
                        self.reading.discard(s.series)

    def _begin(self, asked: list, moved: bool, poked: bool, tick: bool, handed: set) -> bool:
        """``_readings``' first half: the counts the record's writes call for added, commands and queries handed to the
        pool (named in ``handed``: the pool lets go of them), and ergostat's own taken here (``_take``)."""
        here = [s for s in asked if s.items is not None or s.changes is not None]
        extra: set[str] = set()
        began = time.monotonic()
        if moved:
            mine = {s.series for s in here}
            by, _ = self._item_sensors()
            for s in by[False] + by[True]:
                if s.series not in mine:
                    mine.add(s.series)
                    extra.add(s.series)
                    here.append(s)
        for s in asked:
            if s.daemon is not None:                          # asked of its daemon: no process, no pool thread (SPEC §9.7)
                if self.daemons.read(s, lambda v, why, s=s: (self.results.put((s, v, why, time.time(), None)),
                                                             self.wake.set())):
                    handed.add(s.series)                      # (a daemon given up: not asked, its failure said once)
            elif s.items is None and s.changes is None:
                which = "alarm_" if s.series in self._alarmed() else ""
                with self.pool_lock:
                    if getattr(self, f"{which}pool") is None:
                        setattr(self, f"{which}pool", ThreadPoolExecutor(max_workers=2 if which else READERS,
                                                                         thread_name_prefix=f"ergostat-{which}read"))
                    pool, at = getattr(self, f"{which}pool"), time.monotonic()
                    getattr(self, f"{which}pool_out")[s.series] = (at, float(s.timeout or 30.0), None)
                try:
                    pool.submit(self._read_one, s, which, at)
                    handed.add(s.series)
                except RuntimeError:                          # (a pool the watchdog just replaced: asked again next time)
                    with self.pool_lock:
                        getattr(self, f"{which}pool_out").pop(s.series, None)
        return self._take(here, extra, began, poked, tick)

    def _take(self, here: list, extra: set, began: float, poked: bool, tick: bool) -> bool:
        """``_readings``' second half: ergostat's own read here, what the pool read gathered, all of it written, and
        each one's reading let go of even when writing it failed; then the pass."""
        got = self._read_here(here) if here else []
        if extra:                                         # read on a change of the record: kept only when it moved
            self.count_next = time.monotonic() + 4 * (time.monotonic() - began)
            got = [g for g in got if g[0].series not in extra or (g[4] is None and g[1] is not None
                                                                   and g[1] != self.count_last.get(g[0].series))]
        for s, v, *_ in got:
            if s.items is not None and v is not None:
                self.count_last[s.series] = v
        while True:
            try:
                got.append(self.results.get_nowait())
            except queue.Empty:
                break
        rows = []
        causes = {}
        try:
            for s, v, why, t, err in got:
                name = sensor_name(s.of.name, s.name)
                if err is not None:
                    self.say(f"sensor {s.of.name}.{s.name}: {type(err).__name__}: {err}")
                elif v is None:
                    self.p.events.add("sensor.failed", item=name, source=SOURCE, data={"why": why})
                    self.say(f"sensor {s.of.name}.{s.name}: {why}")
                else:
                    rows.append((s.series, t, v))
            if rows:
                self.p.measurements.add_many(rows)
        finally:                                              # (written or not: each is read again when next due)
            with self.lock:
                for s, *_ in got:
                    self.reading.discard(s.series)
                    self.dirty_series.add(s.series)
                    cause = self.read_cause.pop(s.series, None)
                    if cause:
                        causes[s.of.name] = cause
        if got or poked or tick:
            self.evaluate(causes or None, tick=tick)
            return True
        return False

    # ---- the clock

    def _plan(self, spec: Spec, crons: dict, nxt: dict) -> tuple[list, list, list, dict, dict]:
        """What the clock reads, from this model: its timed sensors and blocks, its judges and its crons. A cron
        already counting down, and written the same, keeps its next time (a model change moves no schedule)."""
        from ..cron import Cron
        sensors = [s for s in spec.sensors() if self.own(f"{s.of.kind}.{s.of.name}.{s.name}", spec)]   # (its shard's)
        timed = [s for s in sensors if s.measured and not s.cron]
        machines = [b for b in spec.blocks.values() if b.machine and self.own(f"block.{b.name}", spec)]
        timed_blocks = [b for b in machines if (b.every and not b.cron) and not spec.commanders_of(b.name)]
        judges = [b for b in spec.blocks.values() if b.type == "judge" and self.own(f"block.{b.name}", spec)]
        new: dict[str, tuple] = {}
        for s in sensors:
            if s.measured and s.cron:
                new[s.series] = (Cron(s.cron), lambda s=s: self.read_soon(s), s.cron)
        for b in machines:
            if b.cron and not spec.commanders_of(b.name):
                new[f"block/{b.name}"] = (Cron(b.cron), lambda b=b: self.start(b, "schedule"), b.cron)
        now = time.time()
        times = {k: nxt[k] if k in crons and crons[k][2] == x[2] and k in nxt else x[0].next_after(now)
                 for k, x in new.items()}
        return timed, timed_blocks, judges, new, times

    def _schedule(self, gen: int = 0) -> None:
        """The loop: timed readings from a heap of when each is due, timed blocks, judges and crons; each round the
        readings asked for are taken as one batch and one pass follows (``_readings``). It sleeps until the next
        reading is due, the clock's tick, or something wakes it (a reading the pool finished, a run that ended)."""
        due: dict[str, float] = {}
        spec = self.spec
        timed, timed_blocks, judges, crons, nxt = self._plan(spec, {}, {})
        heap = [(0.0, i) for i in range(len(timed))]             # every sensor reads at once (by its place: two of a
                                                                 # series, the first in the model's order reads)
        last_eval = last_sweep = 0.0
        while not self.stop.is_set() and gen == self.loop_gen:   # (a loop the watchdog replaced stops)
            self.loop_beat = time.monotonic()
            self.wake.clear()
            if spec is not self.spec:                            # the model was swapped: its schedules from now on
                spec = self.spec
                try:
                    timed, timed_blocks, judges, crons, nxt = self._plan(spec, crons, nxt)
                except Exception as e:
                    self.say(f"schedules: {type(e).__name__}: {e}")
                mono = time.monotonic()                          # a shorter every holds from now; a longer, from the next
                for k, every in [(s.series, bounds.pace(spec, s, s.every or 60.0)) for s in timed] + [
                        (f"block/{b.name}", bounds.pace(spec, b, b.every)) for b in timed_blocks]:
                    if k in due:
                        due[k] = min(due[k], mono + every)
                heap = [(due.get(s.series, 0.0), i) for i, s in enumerate(timed)]
                heapq.heapify(heap)
            mono = time.monotonic()
            while heap and heap[0][0] <= mono:
                at, i = heapq.heappop(heap)
                s = timed[i]
                if due.get(s.series, 0.0) > mono:               # another sensor of its series just read: due with it
                    heapq.heappush(heap, (due[s.series], i))
                    continue
                due[s.series] = mono + bounds.pace(spec, s, s.every or 60.0)
                heapq.heappush(heap, (due[s.series], i))
                self.read_soon(s)
            for b in timed_blocks:
                k = f"block/{b.name}"
                if mono >= due.get(k, 0):
                    due[k] = mono + bounds.pace(spec, b, b.every)
                    self.start(b, "schedule")
            for b in judges:                                     # the judge: built in, on its own clock (SPEC §12e)
                k = f"block/{b.name}"
                if mono >= due.get(k, 0) and mono >= self.judge_next.get(b.name, 0) and b.name not in self.running:
                    due[k] = mono + bounds.pace(spec, b, b.every or JUDGE_EVERY)
                    with self.lock:
                        if not bounds.room(self, b):             # (an untrusted library's judge counts as a run)
                            continue
                        bounds.hold(self, b.name, b)
                    threading.Thread(target=self.judge, args=(b,), daemon=True).start()
            if self.spec.contexts and mono >= due.get("contexts", 0):   # outcomes found later (an item kept, reopened)
                due["contexts"] = mono + OUTCOMES_EVERY
                threading.Thread(target=self.outcomes, daemon=True).start()
            wall = time.time()
            for k, at in list(nxt.items()):
                if at is not None and wall >= at:
                    c, fire, _ = crons[k]
                    nxt[k] = c.next_after(wall)
                    fire()
            if mono - last_sweep >= SWEEP:                       # the owner's messages: routed, finished work followed up
                last_sweep = mono
                threading.Thread(target=self._sweep, daemon=True).start()
            try:
                self.joins.look()                                # parents their children moved on: what was written since
            except Exception as e:
                self.say(f"joins: {type(e).__name__}: {e}")
            try:
                self.triggers.look()                             # blocks started by an event: what was written since
            except Exception as e:
                self.say(f"triggers: {type(e).__name__}: {e}")
            tick = mono - last_eval >= TICK                      # the clock moves schedules, timers, delays
            if tick:
                last_eval = mono
            try:
                passed = self._readings(tick)
            except Exception as e:
                passed = False
                self.say(f"evaluating: {type(e).__name__}: {e}")
                reports_crash.noted(self.p, e, "engine")         # drafted as a report for the owner (SPEC §12m)
            if passed:
                self.stop.wait(BATCH)                            # what lands meanwhile is the next batch
            now = time.monotonic()
            self.wake.wait(max(0.0, min(0.2, last_eval + TICK - now, (heap[0][0] - now) if heap else 0.2)))

    def _sweep(self) -> None:
        if self._sweeping.locked() or not self.leads():          # (the lead's alone: SPEC §9.8)
            return
        with self._sweeping:
            try:
                from ..messages import deliver
                deliver.sweep(self.p, self.spec)
            except Exception as e:
                self.say(f"messages: {type(e).__name__}: {e}")
            if self.spec.workspaces:                             # leases ended: workspaces held, or cleaned (SPEC §12k)
                try:
                    from ..workspaces import leases
                    self.lease_seq = leases.sweep(self.p, self.spec, self.lease_seq)
                except Exception as e:
                    self.say(f"workspaces: {type(e).__name__}: {e}")
            if self.spec.actions:                                # approved actions no one ran
                try:
                    from ..actions import gate
                    gate.sweep(self.p, self.spec)
                except Exception as e:
                    self.say(f"actions: {type(e).__name__}: {e}")
            if getattr(self.spec, "notify", None):              # what newly waits on a person, sent (SPEC §12o)
                from ..inbox import deliver
                deliver.start(self.p, self.spec, self.say)

    def _follow(self, seq: int) -> None:
        """Approvals of advised commands, and the owner's asks to stop a run, from the CLI: looked for when the record is
        written (``notify.py``), and every half second besides."""
        from ..notify import of
        board = of(self.p.events)
        mark = board.n if board else 0
        while not self.stop.is_set():
            try:
                seq = self._follow_once(seq)
            except Exception:
                self.stop.wait(1)
                continue
            if board is None:
                self.stop.wait(0.5)
            else:
                mark = board.wait(mark, 0.5)

    def _follow_once(self, seq: int) -> int:
        """One look at what was written after ``seq``, each event in seq order; returns the seq looked to. A shard
        engine follows the runs that moved flows too (``_moved``): their ended events, failed or not."""
        top = self.p.events.last_seq()                        # (what is written while it looks is looked at next time)
        runs = "agent.ran,agent.failed" if self.shard is not None else None
        new = sorted([e for t in ("block.approved,block.denied,trigger.reset", "ergostat.action.approved",
                                  "steptest.approved", STOP_ASKED, RESTART_ASKED, runs) if t
                      for e in self.p.events.query(n=None, after_seq=seq, type=t)], key=lambda e: e["seq"])
        for e in new:
            seq = max(seq, e["seq"])
            try:                                              # (one event's fault never stops the rest, nor repeats them)
                self._moved(e) if e["type"] in ("agent.ran", "agent.failed") else self._ask(e)
            except Exception as x:
                self.say(f"following {e['type']}: {type(x).__name__}: {x}")
        return max(seq, top)

    def _ask(self, e: dict) -> None:
        """One owner's ask, followed only by the engine whose shard owns what it names (SPEC §9.8), judged and acted on
        under the one model read for it. A run it approves still starts only under the model as it is then: when a
        swap has moved the block meanwhile, ``start`` refuses it here and the owner approves it again."""
        spec, t, name = self.spec, e["type"], e.get("item") or ""
        if t == STOP_ASKED:                                   # (and by an engine holding its run, itself or in a daemon,
            if self.follows(f"block.{name}", spec) or name in self.procs or self.daemons.holds(name):  # whoever owns it)
                self.stop_run(name)
        elif t == RESTART_ASKED:                              # the owner reviving a daemon (SPEC §9.7)
            if self.follows(f"daemon.{name}", spec):
                self.daemons.revive(name)
        elif t == "ergostat.action.approved":                 # a program's action, run here, never by it (SPEC §12k)
            if self.follows(f"block.{self._asker(name)}", spec):
                threading.Thread(target=self.run_action, args=(name, spec), daemon=True).start()
        elif t == "steptest.approved":
            if self.follows(f"goal.{(e.get('data') or {}).get('goal') or name}", spec):
                from ..control import steptest
                steptest.begin(self, e, spec)
        elif self.follows(f"block.{name}", spec):
            b = spec.blocks.get(name)
            if t == "trigger.reset":                          # a block's breaker, reset by the owner (SPEC §9.3)
                self.triggers.reset(name)
            elif b and b.machine and b.on is not None:        # an ask about an event (SPEC §9.3): it, or the next
                self.triggers.answered(b, t == "block.approved", (e.get("data") or {}).get("ask"))
            elif b and b.machine and t == "block.approved":
                cmd, _ = self.command_of(b)
                if cmd == 0:                                # nothing to approve: its command fell back meanwhile
                    self.say(f"{b.name}: approved, but its command is 0 now; nothing to run")
                    return
                if not self.start(b, "approved") and not self.follows(f"block.{name}"):
                    self.say(f"{b.name}: approved before it moved to another shard; not run, approve it again")

    def _asker(self, aid: str) -> str:
        """The block whose run asked for an action ("" when it cannot be read: then the lead's, as an unknown block)."""
        from ..actions import record
        try:
            return (record.get(self.p, aid) or {}).get("block") or ""
        except Exception:
            return ""

    def run_action(self, aid: str, spec: Spec | None = None) -> None:
        """An approved action a program block's run asked for: run by ergostat, with its environment, once."""
        from ..actions import gate, record
        try:
            a = record.get(self.p, aid)
            if a is not None and a.get("asker") == "program":
                gate.run_once(self.p, spec or self.spec, aid)
        except Exception as e:
            self.say(f"actions: {aid}: {type(e).__name__}: {e}")

    def _initial(self) -> None:
        for g in (g for g in self.spec.goals if self.own(f"goal.{g}")):
            last = self.p.events.query(n=1, item=g, type="loop.*", unvoided=True)
            if last:
                self.status[g] = last[-1]["type"].split(".", 1)[1]

    def start_all(self) -> None:
        from .. import history
        lead = self.leads()                                      # what is done once for the model: by the lead (SPEC §9.8)
        if lead:
            history.note(self.p)
        if self.shard is None:                                   # (process-wide: never a shard's, SPEC §9.8)
            old.STOPPING.clear()
        self._initial()
        seq = self.p.events.last_seq()
        if lead:
            self.p.events.add("ergostat.started", source=SOURCE, data={"blocks": sorted(self.spec.blocks),
                              "pid": os.getpid(), "format": "yaml", "shard": self.shard})
        try:                                                    # runs whose process is gone hold no reserve open
            budget.recover(self.p, self.spec, every=0)
        except Exception as e:
            self.say(f"budget: recovery: {type(e).__name__}: {e}")
        from ..control import steptest
        steptest.resume(self)                                   # a test approved just before, or cut off by a stop
        self.adopted = adopt.scan(self)                          # runs the engine before left going: taken up, their
        self._listen()                                           # leases kept, before any run starts or lease is looked at
        self.daemons.sync(self.spec)                             # (after the socket: its path is in their environment)
        self._connect()
        self.looping = True                                      # readings go to the loop from now (no thread each)
        threading.Thread(target=self._schedule, name="ergostat-loop", daemon=True).start()
        threading.Thread(target=self._follow, args=(seq,), daemon=True).start()
        self.following = True                                    # it runs the actions programs ask for (SPEC §12k)
        if lead:
            threading.Thread(target=old.Runner._prune, args=(self,), daemon=True).start()   # it reads p, say and stop
        self.dispatch.holding = True                             # leases held when it last stopped are watched at once
        threading.Thread(target=self.dispatch.run, daemon=True).start()   # blocks that take items, their leases (SPEC §9.5)
        threading.Thread(target=self._record_follow, name="ergostat-record", daemon=True).start()
        self._ingest()
        from .watchdog import Watchdog
        self.watchdog = Watchdog(self)                           # a pass or the pool wedged: found, and recovered
        self.watchdog.start()

    def _listen(self) -> None:
        """Calls from a step (``ergostat act``, ``event --add``, ``lease``, ``item``) answered here, over a socket in the
        state directory (``calls/``), each without loading the model; ``ERGOSTAT_SOCKET`` names it in every run."""
        from ..calls.server import Server
        try:
            self.calls = Server(self)
            self.socket = self.calls.start()
        except OSError as e:                                     # the commands do what they did before
            self.calls, self.socket = None, None
            self.say(f"socket: {type(e).__name__}: {e}")

    def _connect(self) -> None:
        """The sessions with the model's compute nodes (SPEC §12s.4): one per node per engine process, so the lead's."""
        pools = self.spec.compute if self.leads() else {}
        if self.compute is None and pools:
            from ..compute.connection import Pools
            self.compute = Pools(self.p, self.say)
        if self.compute is not None:
            self.compute.sync(pools)

    def _record_follow(self) -> None:
        """The loop woken when the record is written (``notify.py``): counts of items read at once (``_readings``)."""
        from ..notify import of
        board = of(self.p.events)
        if board is None:
            return
        mark = board.n
        while not self.stop.is_set():
            was, mark = mark, board.wait(mark, 1.0)
            if mark != was:
                with self.lock:
                    self.record_moved = True
                self.wake.set()
                self.stop.wait(BATCH)                     # (a burst of writes: one batch)

    def _ingest(self) -> None:
        from .. import transcripts
        if not self.leads():                                     # (the lead's alone: SPEC §9.8)
            return
        if self.ingester is not None:
            self.ingester.spec = self.spec                       # (swapped: it reads the new model's item kinds)
            return
        ing = transcripts.Ingester(self.p, self.spec)
        if ing.kinds():                                          # sessions whose transcripts become events (SPEC §5a)
            self.ingester = ing
            threading.Thread(target=ing.run, args=(self.stop, self.say), daemon=True).start()

    def stop_run(self, name: str) -> bool:
        """The owner's ask to stop a block's run under way (``ergostat block NAME --stop``): a removed block's last run,
        or one whose command changed, is otherwise left to finish. Recorded as stopped, not as its failure."""
        with self.lock:
            proc = self.procs.get(name)
            if proc is None:
                return self.daemons.stop_block(name)               # (runs its daemon holds: each cancelled)
            self.stopping_runs.add(name)
        old._kill(proc)
        self.say(f"{name}: its run stopped, as the owner asked")
        return True

    def swap(self, model) -> dict:
        """Take a changed model in place (SPEC §9.1): never a restart, never a run killed. Each run under way
        carries on under the model it started with, and records it; new runs start under this one. Goals switch at
        once (a new setpoint holds from the next pass), sensors at their next reading, and a built-in whose law is
        written the same keeps itself; one changed takes over its state (bumpless). A block removed, or whose
        command changed, starts no more runs under its old definition. Records ``model.changed`` with the runs that
        carried over; returns what it said."""
        from .. import history
        from ..numbers.version import _hash, _plain
        new: Spec = model.spec
        same = lambda a, b: a is not None and b is not None and _hash(_plain(a)) == _hash(_plain(b))   # noqa: E731
        began = time.monotonic()
        with self.lock:
            before, was = self.spec, self.version
            # all of it worked out first, nothing of the running model touched: a change that cannot be taken (a
            # built-in that will not make, a version that will not hash) leaves the last one running as it was
            self._shard_of(new)                          # its shard gone from the new plan: refused, nothing taken
            goals = {n for n in new.goals if self.own(f"goal.{n}", new)}     # what it works on under the new model
            blocks = {n for n in new.blocks if self.own(f"block.{n}", new)}
            read = self._measured(new)
            builtins, kept_as = {}, []
            for n in (n for n in bl.order(new) if n in blocks):
                b, kept = new.blocks[n], self.builtins.get(n)
                if kept is not None and same(kept.b, b):
                    kept_as.append((kept, b))
                    builtins[n] = kept
                    continue
                x = bl.make(b, new)
                if kept is not None and type(kept) is type(x):  # bumpless: the new law starts from the old one's state
                    for k, v in vars(kept).items():
                        if k not in ("b", "spec", "p", "tree"):
                            setattr(x, k, v)
                builtins[n] = x
            version = history.version(model)
            observer = Observer(new, lambda n: self.history(new, n), carry=self.observer, mine=self._mine(new)) \
                if self.observer and opted(new).stocks else None
            carried = sorted(n for n in self.running if n.split(" ", 1)[0] in before.blocks)   # ("block item": a leased run)
            blk = lambda n: n.split(" ", 1)[0]                                                    # noqa: E731
            finishing = {"removed": [n for n in carried if blk(n) not in new.blocks],
                         "changed": [n for n in carried if blk(n) in new.blocks
                                     and not same(before.blocks[blk(n)], new.blocks[blk(n)])]}
            worked = time.monotonic() - began
            # then taken, all at once (nothing below raises)
            for kept, b in kept_as:
                kept.b, kept.spec, kept.p = b, new, b.params
            for n in set(self.builtins) - set(builtins):
                self.signals.pop(f"block.{n}", None)
            self.builtins = builtins
            for g in set(self.status) - goals:                   # (a goal removed, or moved to another shard)
                self.status.pop(g, None)
            for d in (self.per, self.per_rows):
                for g in set(d) - goals:
                    d.pop(g, None)
            o = opted(new)                                       # what the new model no longer asks the observer for
            for g in set(self.stale) - (set(o.goals) & goals):
                self.stale.pop(g, None)
            self.stale_parts = {k: v for k, v in self.stale_parts.items() if k in {str(r) for r in o.parts}}
            for k in [k for k in self.signals if k.endswith((".estimate", ".uncertainty")) and k.startswith("stock.")]:
                st, n = new.stocks.get(k.split(".")[1]), k.split(".")[1]
                if st is None or k.split(".")[2] not in st.sensors and (n not in o.stocks or not self.own(f"stock.{n}", new)):
                    self.signals.pop(k, None)
            if read is not None:                                 # a part it no longer reads: its readings forgotten
                for k in [k for k in self.signals if k.split(".")[0] in ("stock", "flow", "auxiliary")]:
                    if tuple(k.split(".")[:2]) not in read and not k.endswith((".estimate", ".uncertainty")):
                        self.signals.pop(k, None)
            self.observer = observer
            for k in [k for k in self.signals if k.startswith("goal.") and k.split(".")[1] not in goals]:
                self.signals.pop(k, None)
            setters = {t.name for b in new.blocks.values() for t in b.targets() if t.kind == "goal"}
            for g in set(self.setpoint) - (setters & goals):     # a cascade removed: its goal holds what is written
                self.setpoint.pop(g, None)
            for a in new.agents.values():
                if a.name not in self.slots or before.agents.get(a.name) is None or \
                        before.agents[a.name].at_once != a.at_once:
                    self.slots[a.name] = threading.Semaphore(a.at_once)   # (a run holding the old one gives it back)
            for n in list(self.outputs):
                if n not in blocks and n not in self.running:
                    self.outputs.pop(n, None)
                    self.commands.pop(n, None)
            self.machines = [b for b in new.blocks.values() if b.machine and b.name in blocks]
            self.spec = new
            self.p.model = model
            self.version = version
            self.full = True                                     # the next pass works out everything, under the new model
        self.daemons.sync(new)                                   # a daemon whose definition changed: drained, replaced
        self._connect()                                          # a pool changed or removed: its sessions closed
        self.wake.set()
        self._ingest()
        finishing = {k: v for k, v in finishing.items() if v}   # what runs once more, under its old definition
        said = {"reload": "in place", "carried": len(carried), "runs": carried, "version_before": was,
                **({"finishing": finishing} if finishing else {})}
        took = time.monotonic()
        try:
            if self.leads():                                     # (the lead's alone: SPEC §9.8)
                history.note(self.p, said)
        except Exception as e:                                   # the record of it never undoes the change
            self.say(f"recording the change: {type(e).__name__}: {e}")
        return {**said, "version": self.version, "seconds": {"swap": round(worked, 3),
                                                             "record": round(time.monotonic() - took, 3)}}

    def shut(self, wait: float) -> None:
        """Dispatch closed: the stop set under the lock a take checks it under, so a lease taken past this waits in
        ``running``. Never waited on for good (at most ``wait``: a lock held by something wedged, as the watchdog
        allows); a take past its check without it sees the stop again after its write, and gives the item back."""
        got = self.lock.acquire(timeout=wait)
        try:
            self.stop.set()
        finally:
            if got:
                self.lock.release()

    def close(self) -> None:
        self.shut(self.lock_wait)
        self.wake.set()
        if self.calls is not None:
            self.calls.close()
        for pool in (self.pool, self.alarm_pool):
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)
        if self.shard is None:
            old.kill_all()
        else:                                   # a shard's: only its own runs, never STOPPING (SPEC §9.8); a run
            got = self.lock.acquire(timeout=self.lock_wait)   # started past the stop kills itself (self.stop is
            try:                                 # set); a lock held for good is waited on at most lock_wait
                mine = []
                for _ in range(100):             # (without the lock: a run registering mid-copy, copied again)
                    try:
                        mine = list(self.live.values())
                        break
                    except RuntimeError:
                        continue
            finally:
                if got:
                    self.lock.release()
            for proc in mine:
                if not isinstance(proc, keeper.Kept):    # (one its keeper holds goes on: SPEC §9.1)
                    old._kill(proc)
        self.daemons.close()
        if self.compute is not None:
            self.compute.close()                # every session ended: no ssh or worker child left
        deadline = time.monotonic() + 5
        while self.running and time.monotonic() < deadline:
            time.sleep(0.05)
        # A run still going: its lease given back, not counted (SPEC §9.5). Its process outlived kill_all (or a daemon
        # still holds it): once its lease has ended, the fence refuses any line it still writes about the item, so a
        # new engine in this same process (tests, a reload) that leases the item again is not moved by it.
        self.dispatch.give_back()                # (and every lease still held here, its run's own end failed)
        run_gone.closed(self.dispatch)              # (its leases' owner gone now: leases/gone.py)
        self.p.events.add("ergostat.stopped", source=SOURCE, data={"pid": os.getpid(), "shard": self.shard})


class Said:
    """A machine block's output lines, recorded as they arrive (``lines``, in the order printed): what it moved, what it
    commanded, what it decided. A run that holds a lease on an item (``item``, ``fence``): its event lines are about
    that item unless they name another, refused once its lease has ended (fencing), and it may give the item back
    (``{"nack": ...}``). Event lines in a row are recorded together, in one write, before anything after them."""

    def __init__(self, eng: Engine, b: Block, run_id: str, spec: Spec | None = None, version: str | None = None,
                 item: str | None = None, fence: int | None = None):
        self.e, self.b, self.run_id = eng, b, run_id
        self.spec, self.version = spec or eng.spec, version or eng.version   # the model its run started under
        self.item, self.fence = item, fence
        self.nack: dict | None = None
        self.counts = {"openings": 0, "commands": 0, "decisions": 0, "events": 0, "refused": 0}
        self.proposals: list[dict] = []          # what it proposed for the model, and what became of each
        self.claims: list[dict] = []             # what it said it did, recorded, to be checked after the run
        self.moved: dict[str, float] = {}
        self.refused: list[str] = []
        self.bare: float | None = None
        self.json_lines = 0
        self.rx = re.compile(b.params["parse"]) if b.params.get("parse") else None
        self.pending: list[dict] = []            # event lines in a row, not yet recorded
        self.fence_seen = False                  # its lease looked at for this batch of lines
        self.fence_why: str | None = None        # why its lease has ended: once it has, it stays ended
        self.fence_at: int | None = None         # the newest lease event about its item when it was last folded
        self.at: float | None = None             # when the line being taken was printed, when known (else now)

    def lines(self, raws: list[str], ends: list[int] | None = None, ats: list[float | None] | None = None) -> None:
        """A batch of its lines, as they arrived: each taken in turn, the events among them recorded by the end of it.
        One bad line never leaves the rest untaken. ``ends``: where each line ends in its journal (a kept run's, SPEC
        §9.1): the events a line makes have ids of that place (``store.line_id``), so a line taken again adds none.
        ``ats``: when each was printed (its keeper's stamps, a run taken up): its events and readings at that time."""
        self.fence_seen = False
        seed = [None, 0]
        token = store.LINE.set(seed) if ends is not None else None
        try:
            for i, raw in enumerate(raws):
                if ends is not None and seed[0] != f"{self.run_id}:{ends[i]}":
                    seed[:] = [f"{self.run_id}:{ends[i]}", 0]
                if ats is not None:
                    self.at = ats[i]
                try:
                    self.line(raw)
                except Exception as err:
                    self.refuse(raw.strip()[:200], f"could not record it ({type(err).__name__}: {err})")
            try:
                self.flush()
            except Exception as err:             # (the record could not take them: said, and the run goes on)
                self.refuse(f"{len(raws)} lines", f"could not record them ({type(err).__name__}: {err})")
        finally:
            if token is not None:
                store.LINE.reset(token)

    def flush(self) -> None:
        """The event lines waiting, recorded, in one write."""
        if not self.pending:
            return
        rows, self.pending = self.pending, []
        from ..store import ChangesetError
        try:                                     # (ids of a journal's lines: looked for, kept once)
            self.e.p.events.add_many(rows, new=not any(r.get("id") for r in rows))
        except ChangesetError:                   # (each was checked when taken: one by one, each refused alone)
            for r in rows:
                try:
                    self.e.p.events.add(r["type"], item=r.get("item"), source=r["source"], causedby=r["causedby"],
                                        data=r.get("data"), patch=r.get("patch"), set=r.get("set"), id=r.get("id"),
                                        at=r.get("at"))
                except ChangesetError as err:
                    self.counts["events"] -= 1
                    self.refuse({k: r.get(k) for k in ("type", "item")}, str(err))

    def refuse(self, line, why: str) -> None:
        self.flush()                             # what came before it is recorded before it
        self.counts["refused"] += 1
        self.refused.append(why)
        self.e.p.events.add("agent.refused", item=self.b.name, source=SOURCE, causedby=self.run_id,
                            data={"line": line, "why": why}, at=self.at)

    def line(self, raw: str) -> None:
        raw = raw.strip()
        if not raw:
            return
        if raw.startswith("{"):
            try:
                obj = json.loads(raw)
            except ValueError:
                self.refuse(raw[:200], "a line starting with { that is not JSON")
                return
            if isinstance(obj, dict):
                self.json_lines += 1
                self.take(obj)
            return
        if self.rx is not None:
            m = self.rx.search(raw)
            if m:
                try:
                    self.bare = float(m.group(1))
                except ValueError:
                    pass
            return
        try:
            self.bare = float(raw)
        except ValueError:
            pass

    def fenced(self) -> str | None:
        """Why this run may no longer say anything about its item: its lease ended (it expired), and the item's lease
        is another's, or none. Looked at once per batch of lines, the item folded again only when a lease event about
        it was recorded since (a lease ends only by one); once ended, ended."""
        if self.fence_why is not None or self.fence_seen:
            return self.fence_why
        self.fence_seen = True
        from ..leases import PREFIX
        newest = self.e.p.events.query(n=1, item=self.item, type=PREFIX + "*")
        at = newest[-1]["seq"] if newest else 0
        if at != self.fence_at:
            self.fence_at = at
            self.fence_why = self._fenced()
        return self.fence_why

    def _fenced(self) -> str | None:
        from ..leases.fold import held
        from .items import one
        it = one(self.e.p.events, self.e.spec, self.item)
        lease = held(it.fields) if it else None
        if lease and lease.get("holder") == self.run_id and lease.get("fence") == self.fence:
            return None
        now = (it.fields.get("lease") or {}).get("fence") if it else None
        return (f"its lease on {self.item} (fence {self.fence}) has ended; the lease now is {now or 'none'}: "
                f"refused, not applied (fencing)")

    def finish(self) -> None:
        if self.bare is not None and not self.json_lines:
            self.take({"value": self.bare}, bare=True)

    def tally(self) -> None:
        """Its proposals, counted for its end: those proposed, and those not."""
        if self.proposals:
            self.counts["proposed"] = sum(1 for x in self.proposals if x.get("status") != "not-proposed")
            self.counts["not_proposed"] = sum(1 for x in self.proposals if x.get("status") == "not-proposed")

    def target(self, obj: dict) -> Ref | None:
        outs = self.b.targets()
        name = obj.get("out")
        if name is None:
            if len(outs) == 1:
                return outs[0]
            want = "flow" if "moved" in obj else "block" if "command" in obj else None
            pick = [r for r in outs if r.kind == want]
            return pick[0] if len(pick) == 1 else None
        if name in self.b.outputs and len(self.b.outputs[name]) == 1:
            return self.b.outputs[name][0]
        r = Ref.parse(name)
        return r if r in outs else None

    def port_of(self, r: Ref) -> str:
        return next((p for p, rs in self.b.outputs.items() if r in rs), "out")

    def take(self, obj: dict, bare: bool = False) -> None:
        ev = self.e.p.events
        if "event" not in obj:                        # anything else: the events before it are recorded first
            self.flush()
        if "decision" in obj:
            served = sorted(self.e.served(self.b) | {r.name for r in self.b.reads() if r.kind == "goal"}) or [self.b.name]
            for g in served:
                ev.add("controller.decided", item=g, source=self.b.name, causedby=self.run_id, at=self.at,
                       data={"decision": str(obj["decision"]), **({"why": str(obj["why"])} if "why" in obj else {})})
            self.counts["decisions"] += 1
            return
        if "propose" in obj:                          # a change to the model, from any block: validated, then queued
            from ..numbers import improve
            try:
                got = improve.submit(self.e.p, self.b.name, obj["propose"], run=self.run_id, at=self.at)
            except Exception as err:                  # a proposal that cannot even be judged is the block's to read
                got = {"status": "not-proposed", "why": f"{type(err).__name__}: {err}", "title": ""}
            self.proposals.append(got)
            if got["status"] != "not-proposed":       # a change to judge: the judge looks at once, however idle it was
                self.e.judge_next.clear()
            if got["status"] == "not-proposed":
                self.e.say(f"{self.b.name}: not proposed: {got['why']}")
            return
        if "claim" in obj:                            # what it says it did: recorded now, checked after the run (SPEC §12g)
            from ..claims import record
            try:
                self.claims.append(record.made(self.e.p, self.spec, self.b.name, obj["claim"], run=self.run_id,
                                               n=len(self.claims), at=self.at))
            except record.ClaimError as err:
                self.refuse(obj, str(err))
                return
            self.counts["claims"] = self.counts.get("claims", 0) + 1
            return
        if "route" in obj:                            # a classifier's answer: where a message goes (SPEC §12h)
            r = obj["route"]
            if not isinstance(r, dict) or not isinstance(r.get("message"), str) or not isinstance(r.get("to", []), list):
                self.refuse(obj, "a route line: {\"route\": {\"message\": ID, \"to\": [item ids, block.NAME], \"why\": ...}}")
                return
            self.e.routes.setdefault(self.b.name, []).append(r)
            self.counts["routes"] = self.counts.get("routes", 0) + 1
            flows = [t for t in self.b.targets() if t.kind == "flow"]
            if len(flows) == 1 and r.get("to"):          # a classifier with one flow: it moves a message along it
                self.moved[flows[0].name] = self.moved.get(flows[0].name, 0.0) + 1
            return
        if "answer" in obj:                           # an answer to a message the owner sent (SPEC §12h)
            from ..messages import deliver, record
            a = obj["answer"]
            try:
                if not isinstance(a, dict):
                    raise record.MessageError("an answer line: {\"answer\": {\"message\": ID, \"says\": \"...\"}}")
                deliver.answered(self.e.p, str(a.get("message") or ""), a.get("says"), by=self.b.name, run=self.run_id,
                                 session=a.get("session"))
            except record.MessageError as err:
                self.refuse(obj, str(err))
                return
            self.counts["answers"] = self.counts.get("answers", 0) + 1
            return
        if "report" in obj:                           # something ergostat cannot express or do: a report for the owner (SPEC §12m)
            return report_lines.take(self, obj)
        if "nack" in obj:                             # it gives its item back (SPEC §9.5)
            got = nack_of(obj["nack"])
            if self.item is None or got is None:
                self.refuse(obj, "a nack line gives back the item the run holds a lease on: {\"nack\": \"why\"}, or "
                                 "{\"nack\": {\"why\": ..., \"after\": \"30m\", \"count\": false}}" if self.item else
                            "a nack line gives back a leased item, and this run holds none")
                return
            self.nack = got
            return
        if "event" in obj:
            t = obj["event"]
            if self.item and not obj.get("item"):     # a run on a leased item: its lines are about it by default
                obj = {**obj, "item": self.item}
            if self.item and obj.get("item") == self.item:
                why = self.fenced()
                if why:
                    self.refuse(obj, why)
                    return
            if isinstance(t, str) and t.startswith(("ergostat.decision.", "ergostat.correction.")):
                self.flush()
                from ..decisions import acts  # a proposal of the owner's intent: checked like any
                try:
                    acts.take_line(self.e.p, t, obj.get("item"), obj.get("data") if isinstance(obj.get("data"), dict) else {},
                                   self.b.name, causedby=self.run_id)
                    self.counts["events"] += 1
                except acts.ActError as err:
                    self.refuse(obj, str(err))
                return
            if not isinstance(t, str) or not old.TYPE_NAME.match(t) or t.startswith((*old.OWN_TYPES, "block.", "person.")):
                self.refuse(obj, "an event type is lowercase words joined by dots (backup.verified), and not ergostat's own")
                return
            if self.b.on is not None and not triggers.declared(self.b, t):   # the trigger graph holds (SPEC §9.3)
                self.refuse(obj, f"{t} is not among what {self.b.name} emits: (on.emits: {self.b.on.emits or 'none'})")
                return
            from ..store import ChangesetError, changeset
            data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
            try:                                       # it changes its item by data, a patch or the whole of it (SPEC §5a)
                if changeset(data, obj.get("patch"), obj.get("set")) and \
                        (not isinstance(obj.get("item"), str) or "/" not in obj["item"]):
                    raise ChangesetError("a patch or a set changes an item: name it (an id with a /, ticket/12)")
            except ChangesetError as err:
                self.refuse(obj, str(err))
                return
            self.pending.append({"type": t, "item": obj.get("item"), "source": self.b.name, "causedby": self.run_id,
                                 "data": data, "id": store.line_id(), "at": self.at,
                                 **{k: obj[k] for k in ("patch", "set") if obj.get(k) is not None}})
            self.counts["events"] += 1
            return
        r = self.target(obj)
        if r is None:
            self.refuse(obj, f"{self.b.name} has no such output ({obj.get('out')!r}); its outputs: "
                        f"{', '.join(str(t) for t in self.b.targets()) or 'none'}")
            return
        now = self.e.spec
        if not {"flow": now.flows, "block": now.blocks, "goal": now.goals, "auxiliary": now.auxiliaries}.get(r.kind, {}).get(r.name):
            self.refuse(obj, f"{r} is no longer in the model: this run started under version {self.version}, "
                        f"and the model changed to {self.e.version} while it ran")
            return
        amount = obj.get("moved", obj.get("command", obj.get("value")))
        detail = amount if isinstance(amount, dict) else {}
        if isinstance(amount, dict):
            amount = amount.get("amount")
        if not old._number(amount):
            self.refuse(obj, "an output needs a number: moved, command, or value")
            return
        amount = float(amount)
        if r.kind == "flow":
            if amount < 0 and not self.spec.flows[r.name].two_way:
                self.refuse(obj, f"moved must be 0 or more: flow {r.name} runs one way (two-way: true lets it run back)")
                return
            self.moved[r.name] = self.moved.get(r.name, 0.0) + amount
            if amount:
                ev.add("valve.opened", item=valve_name(self.spec, self.b.name, r.name), source=self.b.name,
                       causedby=self.run_id, at=self.at, data={"amount": amount, "flow": r.name,
                                                   **({"note": obj["note"]} if "note" in obj else {})})
                self.counts["openings"] += 1
        elif r.kind == "block":
            port = self.port_of(r)
            with self.e.lock:
                self.e.outputs.setdefault(self.b.name, {})[port] = amount
                self.e.commands.setdefault(self.b.name, {})[port] = {**detail, "amount": amount}
                self.e.cause[self.b.name] = self.run_id         # the run that gave the command
            self.e.touch(f"block.{self.b.name}")
            self.counts["commands"] += 1
        elif r.kind == "goal":
            with self.e.lock:
                self.e.setpoint[r.name] = amount
            self.e.touch(goals=(r.name,))
            self.counts["commands"] += 1
        elif r.kind == "auxiliary":                         # its value, stated whole: what it was set to is its reading
            self.e.p.measurements.add(f"sensor/{r.name}.set", amount, at=self.at)
            ev.add("auxiliary.set", item=r.name, source=self.b.name, causedby=self.run_id, data={"value": amount},
                   at=self.at)
            self.counts["commands"] += 1


def nack_of(raw) -> dict | None:
    """``{"nack": "why"}``, or ``{"nack": {"why": ..., "after": "30m", "count": false, "news": true}}``: the item given
    back, why, not taken again before ``after`` (a duration) or, with ``news``, before something new is recorded about
    it from outside its own runs, whichever is first; and whether the attempt counts (by default it does)."""
    if isinstance(raw, str):
        return {"why": raw}
    if not isinstance(raw, dict):
        return None
    out: dict = {"why": str(raw.get("why") or "given back")}
    if raw.get("after") is not None:
        from ..durations import DurationError, parse_duration
        try:
            out["after"] = parse_duration(raw["after"], "after")
        except DurationError:
            return None
    if raw.get("count") is not None:
        out["count"] = bool(raw["count"])
    if raw.get("news"):                                  # or taken again as soon as there is news of it (SPEC §9.5)
        out["news"] = True
    return out


def observations(text: str) -> tuple[list[dict], list[str]]:
    """What a sensor's command observed besides its number: event lines about items
    ({"event": "case.met", "item": "case/logo-3", "data": {...}}). An observation records what was
    seen, never a command: it names an item (an id with a /) and none of ergostat's own types."""
    seen, refused = [], []
    for x in text.splitlines():
        x = x.strip()
        if not x.startswith("{"):
            continue
        try:
            obj = json.loads(x)
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("message"), dict):   # the owner's words, relayed (SPEC §12h)
            if isinstance(obj["message"].get("text"), str) and obj["message"]["text"].strip():
                seen.append({"message": obj["message"]})
            else:
                refused.append("a message line says something: {\"message\": {\"text\": \"...\", \"by\": \"me\"}}")
            continue
        if not isinstance(obj, dict) or "event" not in obj:
            continue
        t, item = obj["event"], obj.get("item")
        if not isinstance(t, str) or not old.TYPE_NAME.match(t) or t.startswith((*old.OWN_TYPES, "block.", "person.", "sensor.")):
            refused.append(f"{str(t)[:60]!r}: an event type is lowercase words joined by dots, and not ergostat's own")
        elif not isinstance(item, str) or "/" not in item:
            refused.append(f"{t}: a sensor's observation names an item (an id with a /, case/logo-3)")
        else:
            cited = isinstance(obj.get("id"), str) and obj["id"].startswith(mirror.PREFIX)   # any other id: a fresh one
            seen.append({"type": t, "item": item, "data": obj.get("data") if isinstance(obj.get("data"), dict) else {},
                         **{k: obj[k] for k in ("patch", "set") if obj.get(k) is not None},
                         **({"id": obj["id"]} if cited else {})})
    return seen, refused


def callback_env(spec: Spec, state: os.PathLike | str, socket: str | None = None) -> dict[str, str]:
    """How a sensor's command calls ergostat back, as a block's run is told: ``ERGOSTAT_CMD``, ``ERGOSTAT_PROJECT``,
    ``ERGOSTAT_STATE_DIR``, and ``ERGOSTAT_SOCKET`` when the engine answers calls (none inherited otherwise)."""
    env = {**os.environ, "ERGOSTAT_PROJECT": spec.name, "ERGOSTAT_STATE_DIR": str(state),
           "ERGOSTAT_CMD": f"{shlex.quote(sys.executable)} -m ergostat -C {shlex.quote(str(spec.root))}"}
    if socket:
        env["ERGOSTAT_SOCKET"] = socket
    else:
        env.pop("ERGOSTAT_SOCKET", None)
    return env


def read_sensor(spec: Spec, s: Sensor, events=None, observe=None, measurements=None, counts=None,
                env: dict[str, str] | None = None) -> tuple[float | None, str]:
    """One reading: the number, or None and why not. Counting items needs the record (or ``counts``, what the
    engine keeps of it as it folds: counts.py), and a flow read from its stock's changes the measurements. A
    command's observations (event lines about items) go to ``observe``, when given, even with no number. A command
    runs with ``env`` (``callback_env``: how to call ergostat back), else with the project's own worked out."""
    if s.changes is not None:
        if measurements is None:
            return None, "a flow read from its stock's changes needs the stock's readings, and there are none here"
        return changed(spec, s, measurements)
    if s.items is not None:
        if counts is not None and not s.items.get("sum"):     # a field summed is read from the index itself
            return counts.value(spec, s)
        if events is None:
            return None, "items are counted from the record, and there is none here"
        from .items import measure
        return measure(events, spec, s)
    if s.daemon is not None:
        return None, f"read by its daemon {s.daemon} while ergostat runs"
    if s.query is not None:
        src = spec.sources[s.query["source"]]
        if src.type == "prometheus":
            return prometheus(src.url, str(s.query.get("promql", "")), s.timeout)
        if src.type == "ergostat":                           # a remote ergostat's reading (SPEC §4c)
            from ..remote.readings import read
            return read(spec, src, s)
        return None, f"source type {src.type} cannot be queried"
    from ..library import runs
    from ..store import state_dir
    if env is None:
        env = callback_env(spec, state_dir(spec.name, spec.root))
    if runs.sandboxed(s):                                # not proven the owner's or ergostat's (library/runs.py)
        out, why = runs.read(spec, s, env.get("ERGOSTAT_STATE_DIR") or state_dir(spec.name, spec.root))
        if out is None:
            return None, why
        if observe is not None:
            seen, refused = observations(out)
            said = [o for o in seen if "message" in o]
            observe([o for o in seen if "message" not in o],
                    refused + ["message: a sandboxed run cannot relay a message"] * bool(said))
        return number_in(out, s.parse)
    try:
        env = {**env, "ERGOSTAT_SENSOR": sensor_name(s.of.name, s.name)}      # who a mirror cites as (mirror.py)
        p = subprocess.run(s.run, shell=True, cwd=spec.root, capture_output=True, text=True, timeout=s.timeout,
                           start_new_session=True, env=env)
    except subprocess.TimeoutExpired:
        return None, f"no answer within {s.timeout:g}s"
    if p.returncode != 0:
        return None, f"exited {p.returncode}: {(p.stderr or p.stdout).strip()[:200]}"
    if observe is not None:
        observe(*observations(p.stdout))
    return number_in(p.stdout, s.parse)


def changed(spec: Spec, s: Sensor, measurements, now: float | None = None) -> tuple[float | None, str]:
    """A flow's rate per hour from its stock's successive readings over the window: how much they
    rose (an inflow), fell (an outflow), or both, net, in the flow's direction (a two-way flow), or that net
    less what the stock's other measured flows moved (``rest``: the residual flow). A
    sudden drop is a big outflow: what the stock's sensor sees is what some process did."""
    c = s.changes
    st = spec.stocks[c["stock"]]
    src = st.sensors.get("main") or next((x for x in st.sensors.values() if x.measured or x.manual), None)
    if src is None:
        return None, f"stock {st.name} has no sensor to read changes from"
    now = time.time() if now is None else now
    since = now - c["over"]
    pts = measurements.range(src.series, since, now)
    before = measurements.latest(src.series, since)
    if before is not None and (not pts or before[0] < pts[0][0]):
        pts = [before, *pts]                             # the level the window started from
    if len(pts) < 2:
        return 0.0, ""
    d = [b[1] - a[1] for a, b in zip(pts, pts[1:], strict=False)]
    total = {"rises": sum(x for x in d if x > 0), "falls": sum(-x for x in d if x < 0)}.get(c["what"], c["sign"] * sum(d))
    rate = total * 3600.0 / c["over"]
    if c["what"] == "rest":                              # less what its stock's other flows moved, as each last read it
        for g in spec.flows.values():
            o = g.sensors.get("main") or next(iter(g.sensors.values()), None)
            if g.name != s.of.name and st.name in (g.source, g.target) and o is not None and o.measured:
                got = measurements.latest(o.series, now)
                if got is not None and got[0] >= since:
                    rate -= c["sign"] * (1 if g.target == st.name else -1) * got[1]
    return round(rate, 6), ""


def number_in(text: str, parse: str | None) -> tuple[float | None, str]:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if parse:
        rx = re.compile(parse)
        for x in reversed(lines):
            m = rx.search(x)
            if m:
                try:
                    return float(m.group(1)), ""
                except ValueError:
                    pass
        return None, f"no line matches parse: {parse}"
    for x in reversed(lines):
        if x.startswith("{"):
            try:
                v = json.loads(x).get("value")
                if old._number(v):
                    return float(v), ""
            except (ValueError, AttributeError):
                pass
            continue
        try:
            return float(x.split()[0]), ""
        except (ValueError, IndexError):
            continue
    return None, "it printed no number (a bare number, or {\"value\": n})" + (f": {lines[-1][:80]!r}" if lines else "")


def prometheus(url: str, promql: str, timeout: float) -> tuple[float | None, str]:
    q = urllib.parse.urlencode({"query": promql})
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/v1/query?{q}", timeout=timeout) as r:  # noqa: S310
            body = json.loads(r.read().decode())
    except Exception as e:
        return None, f"prometheus at {url}: {type(e).__name__}: {e}"
    if body.get("status") != "success":
        return None, f"prometheus: {body.get('error', 'failed')}"
    data = body.get("data", {})
    res = data.get("result")
    if data.get("resultType") == "scalar":
        return float(res[1]), ""
    if not isinstance(res, list) or len(res) != 1:
        return None, f"the query returned {len(res) if isinstance(res, list) else 'no'} series; it must return one (sum(...))"
    try:
        return float(res[0]["value"][1]), ""
    except (KeyError, IndexError, ValueError, TypeError):
        return None, "prometheus: no value in the answer"
