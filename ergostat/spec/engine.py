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

The record uses the same stores and event types as before (``valve.opened``, ``loop.off``,
``agent.ran``), so the status, the page and the diagrams show a YAML project like any other."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

from .. import runner as old
from . import blocks as bl
from .ir import Block, Ref, Sensor, Spec
from .legacy import sensor_name, valve_name

TICK = 1.0
JUDGE_EVERY = 30.0          # a judge with no every: passes this often
SOURCE = "ergostat"
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
"""


class Engine:
    def __init__(self, project, say=print):
        self.p, self.say = project, say
        self.spec: Spec = project.model.spec
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.signals: dict[str, float] = {}
        self.builtins = {n: bl.make(self.spec.blocks[n], self.spec) for n in bl.order(self.spec)}
        self.status: dict[str, str] = {}               # goal → holding / off
        self.setpoint: dict[str, float] = {}           # goal → a setpoint a block set (a cascade)
        self.outputs: dict[str, dict[str, float]] = {}   # machine block → port → its last command (held)
        self.commands: dict[str, dict] = {}            # machine block → its last command's detail
        self.running: set[str] = set()
        self.finished: dict[str, float] = {}
        self.asked: dict[str, float] = {}              # advised block → the command it last asked approval for
        self.began: dict[str, float] = {}   # when each machine block's last run began           # machine block → when its last run ended
        self.was_commanded: dict[str, bool] = {}
        self.last_reading = 0.0                        # the time of the newest reading the engine has seen
        self.reading: set[str] = set()                 # sensors whose read is under way
        self.seen: dict[str, float] = {}               # series → the newest reading's time
        self.slots = {a.name: threading.Semaphore(a.at_once) for a in self.spec.agents.values()}
        self.machines = [b for b in self.spec.blocks.values() if b.machine]
        # what caused what, kept so the record can say it (causedby): the event carrying each block's latest
        # output (a built-in's decision, or the run that gave the command), each block's latest run, and the
        # run whose moving a flow made a sensor read at once
        self.cause: dict[str, str] = {}
        self.last_run: dict[str, str] = {}
        self.read_cause: dict[str, str] = {}
        self.testing: dict[str, dict] = {}             # block → the step it moves in an approved step test
        self.held: set[str] = set()                    # blocks held still while a step test runs
        self.moved_by: dict[str, dict[str, float]] = {}  # block → what its last run said it moved, by flow

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

    def measure(self) -> None:
        """Stocks' levels and flows' rates from the record: the newest reading of any of their sensors."""
        m = self.p.measurements
        for kind, table in (("stock", self.spec.stocks), ("flow", self.spec.flows), ("auxiliary", self.spec.auxiliaries)):
            for name, x in table.items():
                best = None
                for s in x.sensors.values():
                    got = m.latest(s.series)
                    if got is None:
                        continue
                    self.signals[f"{kind}.{name}.{s.name}"] = got[1]
                    if self.seen.get(s.series) != got[0]:
                        self.seen[s.series] = got[0]
                        self.last_reading = max(self.last_reading, got[0])
                    if best is None or got[0] > best[0]:
                        best = got
                if best is not None:
                    self.signals[f"{kind}.{name}"] = best[1]
                elif kind == "flow" and x.rate is not None:
                    self.signals[f"flow.{name}"] = x.rate

    def goals(self, now: float, causes: dict | None = None, crossed: dict | None = None) -> None:
        """``causes``: the run behind the reading that started this pass, by what it read; a crossing of a
        goal on that is recorded as caused by it. ``crossed`` collects this pass's crossings, by goal."""
        for name, g in self.spec.goals.items():
            r = self.setpoint.get(name, g.hold.value)
            self.signals[f"goal.{name}"] = r
            y = self.signals.get(str(g.of))
            if y is None:
                self.signals.pop(f"goal.{name}.error", None)
                self.signals.pop(f"goal.{name}.off", None)
                continue
            before = self.status.get(name)
            now_s = g.status(y, before == "off", r)
            e = g.hold.error(y, r)
            self.signals[f"goal.{name}.error"] = e
            self.signals[f"goal.{name}.off"] = 1.0 if now_s == "off" else 0.0
            if now_s != before:
                self.status[name] = now_s
                ev = self.p.events.add(f"loop.{now_s}", item=name, source=SOURCE, causedby=(causes or {}).get(g.of.name),
                                       data={"value": y, "setpoint": f"{g.hold.op} {r:g}", "error": e})
                if crossed is not None:
                    crossed[name] = ev["id"]

    def evaluate(self, causes: dict | None = None) -> None:
        now = time.time()
        crossed: dict[str, str] = {}
        with self.lock:
            self.measure()
            self.goals(now, causes, crossed)
            for name, blk in self.builtins.items():
                before = self.signals.get(f"block.{name}")
                try:
                    v = blk.step(self.get, now)
                except Exception as e:                          # one block failing never stops the others
                    self.say(f"block {name}: {type(e).__name__}: {e}")
                    v = None
                if v is None:
                    self.signals.pop(f"block.{name}", None)
                    continue
                self.signals[f"block.{name}"] = v
                for t in self.spec.blocks[name].targets():
                    if t.kind == "goal":                        # a cascade: an outer block sets an inner setpoint
                        self.setpoint[t.name] = v
                if before != v:
                    self.p.measurements.add(f"block/{name}", v, now)
                    if bool(before) != bool(v):
                        self.decided(self.spec.blocks[name], v, now, crossed)
            if any(t.kind == "goal" for b in self.builtins for t in self.spec.blocks[b].targets()):
                self.goals(now, causes, crossed)                                 # a setpoint just moved: the status follows it
            todo = [b for b in self.machines if self.due(b)]
        for b in todo:
            self.start(b, "command")

    def decided(self, b: Block, v: float, now: float, crossed: dict | None = None) -> None:
        """A built-in's output turning on or off, said as a decision of the goal it serves: caused by that
        goal's crossing, when it crossed in this same pass."""
        served = [r.name for r in b.reads() if r.kind == "goal"] or [b.name]
        cmd = [t.name for t in b.targets() if t.kind == "block"]
        verb = "act" if v else "stop"
        for g in served:
            ev = self.p.events.add("controller.decided", item=g if g in self.spec.goals else b.name, source=b.name,
                                   causedby=(crossed or {}).get(g),
                                   data={"decision": f"{verb}{(': ' + ', '.join(cmd)) if cmd else ''}",
                                         "why": f"{b.type} {b.name} → {v:g}", "block": b.name, "value": v})
            self.cause[b.name] = ev["id"]

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

    def due(self, b: Block) -> bool:
        if b.name in self.running:
            return False
        cmd, _ = self.command_of(b)
        if cmd is None:
            if b.every or b.cron:
                return False                                    # on its own schedule
            data = [r for r in b.inputs.values() if r.kind != "block"]
            return bool(data) and self.last_reading > self.finished.get(b.name, 0.0)
        on = bool(cmd)
        rising = on and not self.was_commanded.get(b.name)
        self.was_commanded[b.name] = on
        if not on:
            self.asked.pop(b.name, None)
            return False
        if b.type == "person" or b.mode == "advise":
            if rising or (b.mode == "advise" and self.asked.get(b.name) != cmd):   # a new command asks again
                self.asked[b.name] = cmd
                self.ask(b, cmd)
            return False
        flows = [t.name for t in b.targets() if t.kind == "flow"]
        if any(s.series in self.reading for s in self.after_acting(flows)):
            return False                                        # its last effect is not read yet: never outrun its sensors
        if b.every and time.time() - self.began.get(b.name, 0.0) < b.every:
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

    def ask(self, b: Block, cmd: float) -> None:
        what = "person.asked" if b.type == "person" else "block.advised"
        self.p.events.add(what, item=b.name, source=SOURCE,
                          data={"command": cmd, "ask": str(b.params.get("ask", "")),
                                "how": f"ergostat block {b.name} --done N" if b.type == "person"
                                else f"ergostat block {b.name} --approve"})
        self.say(f"{b.name}: {'asked' if b.type == 'person' else 'advised, waiting for approval'} (command {cmd:g})")

    def start(self, b: Block, why: str) -> None:
        with self.lock:
            if b.name in self.running or self.stop.is_set():   # stopping: nothing new starts
                return
            if b.name in self.held:                             # a step test holds the loop still: its controller waits
                return
            self.running.add(b.name)
            self.began[b.name] = time.time()
        threading.Thread(target=self._run, args=(b, why), daemon=True).start()

    def _run(self, b: Block, why: str) -> None:
        slot = self.slots.get(b.agent or "")
        moved: list[str] = []
        run = None
        try:
            if slot:
                slot.acquire()
            try:
                moved = self.run_block(b, why)
                run = self.last_run.get(b.name)
            except Exception as e:
                self.say(f"{b.name}: {type(e).__name__}: {e}")
                moved = []
        finally:
            if slot:
                slot.release()
            with self.lock:
                for s in self.after_acting(moved):              # read after acting: the loop sees the effect now
                    if run:
                        self.read_cause[s.series] = run         # (what that reading crosses, this run caused)
                    self.read_soon(s)                           # (marked under way before it may run again)
                self.running.discard(b.name)
                self.finished[b.name] = time.time()
        self.evaluate()

    def after_acting(self, flows) -> list[Sensor]:
        """The sensors of the stocks these flows connect: read at once after a block moves them."""
        out = []
        for f in flows:
            fl = self.spec.flows[f]
            for st in (fl.source, fl.target):
                if st in self.spec.stocks:
                    out += [s for s in self.spec.stocks[st].sensors.values() if s.measured]
        return out

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
            g = self.spec.goals[name]
            goals[name] = {"hold": f"{g.hold.op} {self.signals.get(f'goal.{name}', g.hold.value):g}",
                           "value": self.signals.get(str(g.of)), "error": self.signals.get(f"goal.{name}.error"),
                           "status": self.status.get(name, "unknown")}
        out = {"block": b.name, "type": b.type, "trigger": why, "inputs": inputs, "goals": goals,
               "outputs": {p: [str(r) for r in rs] for p, rs in b.outputs.items()}}
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
        return {g for g in self.spec.goals if b.name in self.spec.loop(g).actuators}

    def program(self, b: Block, ctx: dict) -> tuple[str, str]:
        """The command to run and what to give it on standard input."""
        payload = json.dumps(ctx)
        if b.type != "ai":
            return str(b.params["run"]), payload
        prompt = str(b.params["prompt"])
        path = self.spec.root / prompt
        if "\n" not in prompt and path.is_file():
            prompt = path.read_text(encoding="utf-8")
        cmd = str(b.params.get("run") or AI_COMMAND)
        model = b.params.get("model") or (self.spec.agents[b.agent].model if b.agent in self.spec.agents else None)
        if model and "run" not in b.params and "--model" not in cmd:
            cmd += f" --model {model}"
        return cmd, prompt + AI_FOOTER + payload

    def run_block(self, b: Block, why: str) -> list[str]:
        """One run: give it its inputs and command, record what it says. Returns the flows it moved."""
        ctx = self.context(b, why)
        cmd, stdin = self.program(b, ctx)
        ev = self.p.events
        commander = (ctx.get("command") or {}).get("from")          # caused by the decision or run that commanded it
        begun = ev.add("agent.started", item=b.name, source=SOURCE, causedby=self.cause.get(commander) if commander else None,
                       data={"trigger": why, "command": ctx.get("command")})
        self.last_run[b.name] = begun["id"]
        if "command" in ctx:
            ev.add("block.commanded", item=b.name, source=SOURCE, causedby=begun["id"], data=ctx["command"])
        started = time.time()
        env = {**os.environ, "ERGOSTAT_BLOCK": b.name, "ERGOSTAT_AGENT": b.name, "ERGOSTAT_RUN": begun["id"],
               "ERGOSTAT_PROJECT": self.spec.name, "ERGOSTAT_STATE_DIR": str(self.p.dir),
               "ERGOSTAT_CMD": f"{shlex.quote(sys.executable)} -m ergostat -C {shlex.quote(str(self.spec.root))}"}
        if "command" in ctx:
            env["ERGOSTAT_COMMAND"] = f"{ctx['command']['amount']:g}"
        log = old.log_path(self.p, b.name)
        note, code, lines = "", None, []
        with open(log, "a", encoding="utf-8") as lf:
            lf.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} run {begun['id'][:8]} ({why})\n")
            lf.flush()
            try:
                proc = subprocess.Popen(cmd, shell=True, cwd=self.spec.root, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=lf, text=True, start_new_session=True)
            except OSError as e:
                note = f"could not start: {e}"
            else:
                old.LIVE.add(proc)
                try:
                    out, _ = proc.communicate(stdin, timeout=b.timeout)
                except subprocess.TimeoutExpired:
                    old._kill(proc)
                    out, _ = proc.communicate()
                    note = f"stopped after its timeout of {b.timeout:g}s"
                finally:
                    old.LIVE.discard(proc)
                code = proc.returncode
                lines = out.splitlines()
                for raw in lines:
                    if not raw.strip().startswith("{"):
                        lf.write(raw + "\n")
                if code and not note:
                    note = old.STOPPED_WITH_US if old.STOPPING.is_set() else f"exited {code}"
        said = Said(self, b, begun["id"])
        if code is not None:                                     # what it said it moved counts, even if it then failed
            for raw in lines:
                said.line(raw)
            if code == 0:                                        # a bare number only from a run that finished well
                said.finish()
        if said.proposals:
            said.counts["proposed"] = sum(1 for x in said.proposals if x["status"] != "not-proposed")
            said.counts["not_proposed"] = sum(1 for x in said.proposals if x["status"] == "not-proposed")
        data = {"exit": code, "seconds": round(time.time() - started, 3), "why": why, **said.counts,
                **({"note": note} if note else {}), **({"moved": said.moved} if said.moved else {}),
                **({"commanded": ctx["command"]["amount"]} if "command" in ctx else {})}
        self.moved_by[b.name] = dict(said.moved)
        failed = bool(note) and note != old.STOPPED_WITH_US
        ev.add("agent.failed" if failed else "agent.ran", item=b.name, source=SOURCE, causedby=begun["id"], data=data)
        if failed:
            self.say(f"{b.name}: {note}")
        if said.refused:
            self.say(f"{b.name}: {said.refused[0]}")
        return [f for f, v in said.moved.items() if v]           # moving nothing is not a reason to read again

    def judge(self, b: Block) -> None:
        """One pass of the judge, ergostat's own (no program): recorded as a run, what it moved said on its ports."""
        from ..numbers import judge as jd
        ev = self.p.events
        begun = ev.add("agent.started", item=b.name, source=SOURCE, data={"trigger": "schedule"})
        started = time.time()
        try:
            got = jd.run(self.p, by=b.name)
        except Exception as e:
            ev.add("agent.failed", item=b.name, source=SOURCE, causedby=begun["id"],
                   data={"exit": None, "seconds": round(time.time() - started, 3), "note": f"{type(e).__name__}: {e}"})
            self.say(f"{b.name}: {type(e).__name__}: {e}")
            return
        finally:
            with self.lock:
                self.running.discard(b.name)
        said = Said(self, b, begun["id"])
        for line in jd.lines(self.spec, b.name, got):
            said.take(line)
        ev.add("agent.ran", item=b.name, source=SOURCE, causedby=begun["id"],
               data={"exit": 0, "seconds": round(time.time() - started, 3), "why": "schedule", **said.counts,
                     **{k: got[k] for k in jd.PORTS}, **({"moved": said.moved} if said.moved else {})})

    # ---- sensors

    def read_soon(self, s: Sensor) -> None:
        key = s.series
        with self.lock:
            if key in self.reading:
                return
            self.reading.add(key)
        threading.Thread(target=self._read, args=(s,), daemon=True).start()

    def _read(self, s: Sensor) -> None:
        try:
            name = sensor_name(s.of.name, s.name)

            def observe(seen, refused):
                for o in seen:
                    self.p.events.add(o["type"], item=o["item"], source=name, data=o["data"])
                for why in refused:
                    self.p.events.add("sensor.refused", item=name, source=SOURCE, data={"why": why})
                    self.say(f"sensor {name}: {why}")
            v, why = read_sensor(self.spec, s, self.p.events, observe, self.p.measurements)
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
                cause = self.read_cause.pop(s.series, None)
        self.evaluate({s.of.name: cause} if cause else None)

    # ---- the clock

    def _schedule(self) -> None:
        from ..cron import Cron
        due: dict[str, float] = {}
        timed = [s for s in self.spec.sensors() if s.measured and not s.cron]
        timed_blocks = [b for b in self.machines if (b.every and not b.cron) and not self.spec.commanders_of(b.name)]
        judges = [b for b in self.spec.blocks.values() if b.type == "judge"]
        crons: dict[str, tuple] = {}
        for s in self.spec.sensors():
            if s.measured and s.cron:
                crons[s.series] = (Cron(s.cron), lambda s=s: self.read_soon(s))
        for b in self.machines:
            if b.cron and not self.spec.commanders_of(b.name):
                crons[f"block/{b.name}"] = (Cron(b.cron), lambda b=b: self.start(b, "schedule"))
        nxt = {k: c.next_after(time.time()) for k, (c, _) in crons.items()}
        last_eval = 0.0
        while not self.stop.is_set():
            mono = time.monotonic()
            for s in timed:
                if mono >= due.get(s.series, 0):
                    due[s.series] = mono + (s.every or 60.0)
                    self.read_soon(s)
            for b in timed_blocks:
                k = f"block/{b.name}"
                if mono >= due.get(k, 0):
                    due[k] = mono + b.every
                    self.start(b, "schedule")
            for b in judges:                                     # the judge: built in, on its own clock (SPEC §12e)
                k = f"block/{b.name}"
                if mono >= due.get(k, 0) and b.name not in self.running:
                    due[k] = mono + (b.every or JUDGE_EVERY)
                    with self.lock:
                        self.running.add(b.name)
                    threading.Thread(target=self.judge, args=(b,), daemon=True).start()
            wall = time.time()
            for k, at in list(nxt.items()):
                if at is not None and wall >= at:
                    c, fire = crons[k]
                    nxt[k] = c.next_after(wall)
                    fire()
            if mono - last_eval >= TICK:                         # the clock moves schedules, timers, delays
                last_eval = mono
                try:
                    self.evaluate()
                except Exception as e:
                    self.say(f"evaluating: {type(e).__name__}: {e}")
            self.stop.wait(0.2)

    def _follow(self, seq: int) -> None:
        """Approvals of advised commands, from the CLI."""
        while not self.stop.is_set():
            try:
                new = sorted(self.p.events.query(n=None, after_seq=seq, type="block.approved") +
                             self.p.events.query(n=None, after_seq=seq, type="steptest.approved"), key=lambda e: e["seq"])
            except Exception:
                self.stop.wait(1)
                continue
            for e in new:
                seq = max(seq, e["seq"])
                if e["type"] == "steptest.approved":
                    from ..control import steptest
                    steptest.begin(self, e)
                    continue
                b = self.spec.blocks.get(e.get("item") or "")
                if b and b.machine:
                    cmd, _ = self.command_of(b)
                    if cmd == 0:                                # nothing to approve: its command fell back meanwhile
                        self.say(f"{b.name}: approved, but its command is 0 now; nothing to run")
                        continue
                    self.start(b, "approved")
            try:
                seq = max(seq, self.p.events.last_seq())
            except Exception:
                pass
            self.stop.wait(0.5)

    def _initial(self) -> None:
        for g in self.spec.goals:
            last = self.p.events.query(n=1, item=g, type="loop.*", unvoided=True)
            if last:
                self.status[g] = last[-1]["type"].split(".", 1)[1]

    def start_all(self) -> None:
        from .. import history
        history.note(self.p)
        old.STOPPING.clear()
        self._initial()
        seq = self.p.events.last_seq()
        self.p.events.add("ergostat.started", source=SOURCE,
                          data={"blocks": sorted(self.spec.blocks), "pid": os.getpid(), "format": "yaml"})
        from ..control import steptest
        steptest.resume(self)                                   # a test approved just before, or cut off by a stop
        threading.Thread(target=self._schedule, daemon=True).start()
        threading.Thread(target=self._follow, args=(seq,), daemon=True).start()
        threading.Thread(target=old.Runner._prune, args=(self,), daemon=True).start()   # it reads p, say and stop

    def close(self) -> None:
        self.stop.set()
        old.kill_all()
        deadline = time.monotonic() + 5
        while self.running and time.monotonic() < deadline:
            time.sleep(0.05)
        self.p.events.add("ergostat.stopped", source=SOURCE, data={"pid": os.getpid()})


class Said:
    """A machine block's output lines, recorded: what it moved, what it commanded, what it decided."""

    def __init__(self, eng: Engine, b: Block, run_id: str):
        self.e, self.b, self.run_id = eng, b, run_id
        self.counts = {"openings": 0, "commands": 0, "decisions": 0, "events": 0, "refused": 0}
        self.proposals: list[dict] = []          # what it proposed for the model, and what became of each
        self.moved: dict[str, float] = {}
        self.refused: list[str] = []
        self.bare: float | None = None
        self.json_lines = 0
        self.rx = re.compile(b.params["parse"]) if b.params.get("parse") else None

    def refuse(self, line, why: str) -> None:
        self.counts["refused"] += 1
        self.refused.append(why)
        self.e.p.events.add("agent.refused", item=self.b.name, source=SOURCE, causedby=self.run_id,
                            data={"line": line, "why": why})

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

    def finish(self) -> None:
        if self.bare is not None and not self.json_lines:
            self.take({"value": self.bare}, bare=True)

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
        if "decision" in obj:
            served = sorted(self.e.served(self.b) | {r.name for r in self.b.reads() if r.kind == "goal"}) or [self.b.name]
            for g in served:
                ev.add("controller.decided", item=g, source=self.b.name, causedby=self.run_id,
                       data={"decision": str(obj["decision"]), **({"why": str(obj["why"])} if "why" in obj else {})})
            self.counts["decisions"] += 1
            return
        if "propose" in obj:                          # a change to the model, from any block: validated, then queued
            from ..numbers import improve
            try:
                got = improve.submit(self.e.p, self.b.name, obj["propose"], run=self.run_id)
            except Exception as err:                  # a proposal that cannot even be judged is the block's to read
                got = {"status": "not-proposed", "why": f"{type(err).__name__}: {err}", "title": ""}
            self.proposals.append(got)
            if got["status"] == "not-proposed":
                self.e.say(f"{self.b.name}: not proposed: {got['why']}")
            return
        if "event" in obj:
            t = obj["event"]
            if not isinstance(t, str) or not old.TYPE_NAME.match(t) or t.startswith((*old.OWN_TYPES, "block.", "person.")):
                self.refuse(obj, "an event type is lowercase words joined by dots (backup.verified), and not ergostat's own")
                return
            ev.add(t, item=obj.get("item"), source=self.b.name, causedby=self.run_id,
                   data=obj.get("data") if isinstance(obj.get("data"), dict) else {})
            self.counts["events"] += 1
            return
        r = self.target(obj)
        if r is None:
            self.refuse(obj, f"{self.b.name} has no such output ({obj.get('out')!r}); its outputs: "
                        f"{', '.join(str(t) for t in self.b.targets()) or 'none'}")
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
            if amount < 0 and not self.e.spec.flows[r.name].two_way:
                self.refuse(obj, f"moved must be 0 or more: flow {r.name} runs one way (two-way: true lets it run back)")
                return
            self.moved[r.name] = self.moved.get(r.name, 0.0) + amount
            if amount:
                ev.add("valve.opened", item=valve_name(self.e.spec, self.b.name, r.name), source=self.b.name,
                       causedby=self.run_id, data={"amount": amount, "flow": r.name,
                                                   **({"note": obj["note"]} if "note" in obj else {})})
                self.counts["openings"] += 1
        elif r.kind == "block":
            port = self.port_of(r)
            with self.e.lock:
                self.e.outputs.setdefault(self.b.name, {})[port] = amount
                self.e.commands.setdefault(self.b.name, {})[port] = {**detail, "amount": amount}
                self.e.cause[self.b.name] = self.run_id         # the run that gave the command            self.counts["commands"] += 1
        elif r.kind == "goal":
            with self.e.lock:
                self.e.setpoint[r.name] = amount
            self.counts["commands"] += 1
        elif r.kind == "auxiliary":                         # its value, stated whole: what it was set to is its reading
            self.e.p.measurements.add(f"sensor/{r.name}.set", amount)
            ev.add("auxiliary.set", item=r.name, source=self.b.name, causedby=self.run_id, data={"value": amount})
            self.counts["commands"] += 1


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
        if not isinstance(obj, dict) or "event" not in obj:
            continue
        t, item = obj["event"], obj.get("item")
        if not isinstance(t, str) or not old.TYPE_NAME.match(t) or t.startswith((*old.OWN_TYPES, "block.", "person.", "sensor.")):
            refused.append(f"{str(t)[:60]!r}: an event type is lowercase words joined by dots, and not ergostat's own")
        elif not isinstance(item, str) or "/" not in item:
            refused.append(f"{t}: a sensor's observation names an item (an id with a /, case/logo-3)")
        else:
            seen.append({"type": t, "item": item, "data": obj.get("data") if isinstance(obj.get("data"), dict) else {}})
    return seen, refused


def read_sensor(spec: Spec, s: Sensor, events=None, observe=None, measurements=None) -> tuple[float | None, str]:
    """One reading: the number, or None and why not. Counting items needs the record, and a flow
    read from its stock's changes the measurements. A command's observations (event lines about
    items) go to ``observe``, when given, even with no number."""
    if s.changes is not None:
        if measurements is None:
            return None, "a flow read from its stock's changes needs the stock's readings, and there are none here"
        return changed(spec, s, measurements)
    if s.items is not None:
        if events is None:
            return None, "items are counted from the record, and there is none here"
        from .items import measure
        return measure(events, spec, s)
    if s.query is not None:
        src = spec.sources[s.query["source"]]
        if src.type == "prometheus":
            return prometheus(src.url, str(s.query.get("promql", "")), s.timeout)
        return None, f"source type {src.type} cannot be queried"
    try:
        p = subprocess.run(s.run, shell=True, cwd=spec.root, capture_output=True, text=True, timeout=s.timeout,
                           start_new_session=True)
    except subprocess.TimeoutExpired:
        return None, f"no answer within {s.timeout:g}s"
    if p.returncode != 0:
        return None, f"exited {p.returncode}: {(p.stderr or p.stdout).strip()[:200]}"
    if observe is not None:
        observe(*observations(p.stdout))
    return number_in(p.stdout, s.parse)


def changed(spec: Spec, s: Sensor, measurements, now: float | None = None) -> tuple[float | None, str]:
    """A flow's rate per hour from its stock's successive readings over the window: how much they
    rose (an inflow), fell (an outflow), or both, net, in the flow's direction (a two-way flow). A
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
    total = {"rises": sum(x for x in d if x > 0), "falls": sum(-x for x in d if x < 0), "net": c["sign"] * sum(d)}[c["what"]]
    return round(total * 3600.0 / c["over"], 6), ""


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
