"""``ergostat run``: runs each agent that has a command, on its schedule (``every``) or when an
event it listens for arrives (``on``), and records what it says.

An agent's run gets a JSON object on stdin: who it is, the roles it fills, the current state, each
of its controllers' setpoints and errors, and the event that triggered it (if any). It answers on
stdout, one JSON object per line, naming the part each line is for:

    {"sensor": "disk-usage", "value": 71}                     a reading (a measurement)
    {"valve": "delete-old-files", "amount": 3.1}              an opening (an event; amount moves its flow)
    {"controller": "disk-under-80", "decision": "wait"}       a decision (an event)
    {"event": "backup.verified", "item": "nightly", "data": {}}   anything else that happened

A line naming a part the agent does not fill is refused and recorded as refused: every agent acts
only through the roles it fills. Other output is kept in the agent's log. After each reading,
a loop that crosses its setpoint (holding to off, or back) is recorded as ``loop.off`` or
``loop.holding``: the edge detector, the one place a measurement becomes an event."""

from __future__ import annotations

import fnmatch
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import state as st

RUN_TIMEOUT = 300.0
OWN_TYPES = ("agent.", "loop.", "valve.", "controller.", "model.", "ergostat.", "auxiliary.", "variable.")   # no agent may publish these
LIVE: set = set()          # the runs in progress, so stopping ergostat stops them too
STOPPING = threading.Event()  # set when ergostat itself stops: a run killed then is not the agent's failure
STOPPED_WITH_US = "stopped with ergostat"
RELOADED = threading.Event()  # this process is a runner restarted in place for a new model, not a fresh start


def _kill(p) -> None:
    """The run and everything it started: each run is its own process group."""
    import signal
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            p.kill()
        except OSError:
            pass


def kill_all() -> None:
    STOPPING.set()
    for p in list(LIVE):
        _kill(p)
TICK = 0.25
SOURCE = "ergostat"


def log_path(project, agent: str) -> Path:
    d = project.dir / "logs"
    d.mkdir(exist_ok=True)
    return d / f"{agent}.log"


def context(project, agent, trigger: dict | None) -> dict:
    """What an agent's run is given: cheap to make (no full snapshot), since every run makes one."""
    m = project.model
    roles = m.roles_of(agent.name)
    values = {name: st.stock_value(project, name)["value"] for name in m.stocks}
    ctls = {}
    for c in roles:
        if c.kind == "controller":
            v = values.get(c.holds)
            closes = bool(m.loop(c.name) and m.loop(c.name).closes)
            last = project.events.query(n=1, item=c.name, type="loop.*", unvoided=True)
            op, target = c.target()
            ctls[c.name] = {"holds": c.holds, "setpoint": c.setpoint, "op": op, "target": target, "tolerance": c.tolerance,
                            "value": v, "drives": c.drives,
                            "error": c.error(v) if v is not None and closes else None,
                            "status": (c.status(v, bool(last and last[-1]["type"] == "loop.off")) if v is not None and closes
                                       else "open" if not closes else "unknown")}
    return {"agent": agent.name, "kind": agent.kind, "roles": [{"kind": p.kind, "name": p.name} for p in roles],
            "state": values, "controllers": ctls, "trigger": trigger}


def matches(pattern: str, ev: dict) -> bool:
    """An ``on`` pattern: an event-type glob, optionally ``@item`` (also a glob): ``loop.off@backup-fresh``."""
    t, _, item = pattern.partition("@")
    return fnmatch.fnmatchcase(ev.get("type", ""), t) and (not item or fnmatch.fnmatchcase(str(ev.get("item") or ""), item))


TYPE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$")


def _number(v) -> bool:
    import math
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


class Recorder:
    """Turns an agent's output lines into measurements and events, refusing what it may not say or
    says badly. Lines that look meant for ergostat but cannot be read are counted, never lost quietly."""

    def __init__(self, project, agent, run_id: str):
        self.p, self.agent, self.run_id = project, agent, run_id
        self.fills = {(r.kind, r.name) for r in project.model.roles_of(agent.name)}   # as the model was when it began
        measured = [f for f in self.fills if f[0] in ("sensor", "valve")]
        self.bare = measured[0] if len(measured) == 1 else None   # where a bare number goes: a plain program's output
        self.counts = {"readings": 0, "openings": 0, "decisions": 0, "events": 0, "refused": 0, "unread": 0}
        self.unread: list[str] = []
        self.said = 0                    # JSON lines it printed: an agent that speaks JSON has no bare number
        self.printed = 0                 # lines of any kind: a run that printed text but said nothing is told so
        self.parsed_from: str | None = None
        self.took: float | None = None   # the bare number, once recorded (or 0: nothing moved)
        self.rx = re.compile(agent.parse) if getattr(agent, "parse", None) else None
        self.pending: float | None = None    # the last bare number, taken when the run ends

    def refuse(self, line: dict, why: str) -> None:
        self.counts["refused"] += 1
        self.p.events.add("agent.refused", item=self.agent.name, source=SOURCE, causedby=self.run_id,
                          data={"line": line, "why": why})

    def not_read(self, raw: str) -> None:
        self.counts["unread"] += 1
        if len(self.unread) < 5:
            self.unread.append(raw[:200])

    def take(self, raw: str) -> bool:
        """True when the line was handled (recorded or refused); False when it goes to the log."""
        if raw.strip():
            self.printed += 1
        if self.bare and self.rx is not None and not raw.lstrip().startswith("{"):   # its own words, by its own pattern
            m = self.rx.search(raw)
            if m:
                try:
                    self.pending = float(m.group(1))
                    self.parsed_from = raw.strip()[:80]
                except ValueError:
                    pass
            return False
        if self.bare:
            try:
                self.pending = float(raw)                # `.50` from bc, `007` from printf: a number all the same
                return False                             # to the log; recorded at the end if nothing spoke JSON
            except ValueError:
                pass
        try:
            line = json.loads(raw)
        except ValueError:
            if raw.lstrip().startswith("{"):             # meant for ergostat, but not JSON
                self.not_read(raw)
            return False
        if not isinstance(line, dict):
            return False
        self.said += 1
        return self.take_line(line)

    def finish(self) -> str | None:
        """A plain program's bare number (the last it printed), when it printed no JSON line: the
        reading of its one sensor, or what its one valve moved (0: no opening). What became of it,
        for the log."""
        if not self.bare or self.pending is None or self.said:
            return None
        kind, name = self.bare                   # `du -sm dir | cut -f1`, `find ... -delete -print | wc -l`
        if kind == "valve" and self.pending == 0:
            self.took = 0.0
            return "0: nothing moved, no opening"
        before = dict(self.counts)
        self.take_line({kind: name, ("value" if kind == "sensor" else "amount"): self.pending})
        if self.counts["refused"] > before["refused"]:
            return f"{self.pending:g}: refused (see ergostat agent {self.agent.name})"
        self.took = self.pending
        return f"{self.pending:g} → {kind} {name}" + (f" (from \"{self.parsed_from}\")" if self.parsed_from else "")

    def take_line(self, line: dict) -> bool:
        ev = self.p.events
        for kind in ("sensor", "valve", "controller"):
            if kind not in line:
                continue
            name = line[kind]
            if not isinstance(name, str) or (kind, name) not in self.fills:
                self.refuse(line, f"{self.agent.name} does not fill {kind} {name}")
                return True
            if kind == "sensor":
                if not _number(line.get("value")):
                    self.refuse(line, "a reading needs a number: value")
                    return True
                self.p.measurements.add(f"sensor/{name}", float(line["value"]))
                self.counts["readings"] += 1
                edges(self.p, self.run_id, sensor=name)
            elif kind == "valve":
                if "position" not in line and "amount" not in line:
                    self.refuse(line, "a valve line says amount (what it moved) or position (how far it is open)")
                    return True
                if "position" in line and not _number(line["position"]):
                    self.refuse(line, "position must be a number")
                    return True
                if "amount" in line and (not _number(line["amount"]) or line["amount"] < 0):
                    self.refuse(line, "amount must be a number, 0 or more (a flow runs one way)")
                    return True
                if "position" in line:                   # how far it is open: a setting, kept as a measurement
                    self.p.measurements.add(f"valve/{name}", float(line["position"]))
                if "amount" in line:
                    valve = self.p.model.valves.get(name)
                    if valve is None:                    # removed while the run went on: said, and refused
                        self.refuse(line, f"valve {name} is no longer in the model: it changed while this run went on")
                        return True
                    ev.add("valve.opened", item=name, source=self.agent.name, causedby=self.run_id,
                           data={"amount": float(line["amount"]), "flow": valve.flow,
                                 **({"note": line["note"]} if "note" in line else {})})
                    self.counts["openings"] += 1
            else:
                if not isinstance(line.get("decision"), str) or not line["decision"].strip():
                    self.refuse(line, "a decision needs words: decision")
                    return True
                ev.add("controller.decided", item=name, source=self.agent.name, causedby=self.run_id,
                       data={"decision": line["decision"], **({"why": line["why"]} if "why" in line else {})})
                self.counts["decisions"] += 1
            return True
        if "event" in line:
            t = line["event"]
            if not isinstance(t, str) or not TYPE_NAME.match(t):
                self.refuse(line, "an event type is lowercase words joined by dots, like backup.requested")
                return True
            if t.startswith(OWN_TYPES):
                self.refuse(line, f"{t}: types under {', '.join(OWN_TYPES)} are ergostat's own")
                return True
            if "data" in line and not isinstance(line["data"], dict):
                self.refuse(line, "data must be an object")
                return True
            if line.get("item") is not None and not isinstance(line["item"], str):
                self.refuse(line, "item must be a string: what the event is about")
                return True
            from .store import ChangesetError
            try:
                ev.add(t, item=line.get("item"), source=self.agent.name, causedby=self.run_id, data=line.get("data") or {},
                       patch=line.get("patch"), set=line.get("set"))
            except ChangesetError as e:
                self.refuse(line, str(e))
                return True
            self.counts["events"] += 1
            return True
        self.not_read(json.dumps(line))                      # an object that names no part and no event
        return False


EDGES = threading.Lock()      # two readings at once never record the same crossing twice


def edges(project, causedby: str | None = None, sensor: str | None = None) -> list[dict]:
    """The edge detector: for each loop whose status changed since it was last recorded, record
    ``loop.off`` or ``loop.holding``. With ``sensor``, only the loops that sensor serves."""
    with EDGES:
        return _edges(project, causedby, sensor)


def _edges(project, causedby, sensor) -> list[dict]:
    out = []
    for lp in project.model.loops():
        if not lp.closes or (sensor is not None and sensor not in lp.sensors):
            continue
        value = st.stock_value(project, lp.stock)["value"]
        if value is None:
            continue
        error = lp.controller.error(value)
        last = project.events.query(n=1, item=lp.name, type="loop.*", unvoided=True)
        before = last[0]["type"].split(".", 1)[1] if last else None
        now = lp.controller.status(value, was_off=before == "off")
        if before != now:
            out.append(project.events.add(f"loop.{now}", item=lp.name, source=SOURCE, causedby=causedby,
                                          data={"value": value, "setpoint": lp.controller.setpoint, "error": error}))
    return out


def run_agent(project, agent, trigger: dict | None = None, why: str = "schedule", version: str | None = None) -> dict:
    """One run: start the command, feed it its context, record its lines, and record the run. ``version``: the
    model it starts under (recorded on the run; it finishes under that agent's definition whatever changes)."""
    if version is None:
        from .history import version as model_version
        version = model_version(project.model)
    started = time.time()
    begun = project.events.add("agent.started", item=agent.name, source=SOURCE,
                               causedby=trigger.get("id") if trigger else None,
                               data={"trigger": trigger["type"] if trigger else why, "model": version})
    rec = Recorder(project, agent, begun["id"])
    log = log_path(project, agent.name)
    try:                                                # a log is kept to its last megabyte once it passes five
        if log.stat().st_size > 5 * 2**20:
            with open(log, "rb") as f:
                f.seek(-2**20, 2)
                tail = f.read()
            log.write_bytes(tail[tail.find(b"\n") + 1:])
    except OSError:
        pass
    env = {**os.environ, "ERGOSTAT_AGENT": agent.name, "ERGOSTAT_RUN": begun["id"], "ERGOSTAT_PROJECT": project.model.name,
           "ERGOSTAT_STATE_DIR": str(project.dir)}
    code, note = None, ""
    with open(log, "a", encoding="utf-8") as lf:
        lf.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} run {begun['id'][:8]} "
                 f"({trigger['type'] if trigger else why})\n")
        lf.flush()
        try:
            p = subprocess.Popen(agent.command, shell=True, cwd=project.repo, env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=lf, text=True, start_new_session=True)
            LIVE.add(p)
        except OSError as e:
            note = f"could not start: {e}"
        else:
            killed = threading.Event()

            def kill():
                killed.set()
                _kill(p)
            timer = threading.Timer(agent.timeout or RUN_TIMEOUT, kill)     # before stdin: a full pipe cannot dodge it
            timer.daemon = True
            timer.start()

            def feed(text: str) -> None:
                try:
                    p.stdin.write(text)
                    p.stdin.close()
                except (OSError, ValueError):
                    pass
            threading.Thread(target=feed, args=(json.dumps(context(project, agent, trigger)),), daemon=True).start()
            crashed = None                                   # the first line that could not be recorded
            try:
                for raw in p.stdout:
                    try:
                        if not rec.take(raw.strip()):
                            lf.write(raw)
                    except Exception as e:                       # one bad line never leaves the run half done
                        crashed = crashed or f"{type(e).__name__}: {e}"
                        rec.refuse({"raw": raw[:200]}, f"could not record it ({type(e).__name__})")
            finally:
                code = p.wait()
                timer.cancel()
                LIVE.discard(p)
            if killed.is_set():
                from .durations import human
                note = f"stopped after its timeout of {human(agent.timeout)}"
            elif code != 0 and STOPPING.is_set():
                note = STOPPED_WITH_US
            elif code != 0:
                note = f"exited {code}"
            if code == 0 and not killed.is_set():             # a bare number from a run that finished well, only
                try:
                    became = rec.finish()
                    if became:
                        lf.write(f"[ergostat] the bare number {became}\n")
                except Exception as e:
                    crashed = crashed or f"{type(e).__name__}: {e}"
    data = {"exit": code, "seconds": round(time.time() - started, 3), **rec.counts, "why": trigger["type"] if trigger else why,
            **({"unread_lines": rec.unread} if rec.unread else {}), **({"note": note} if note else {}), "printed": rec.printed,
            **({"took": rec.took} if rec.took is not None else {}), "model": version}
    failed = bool(note) and note != STOPPED_WITH_US      # cut short by our own stop: not the agent's failure
    project.events.add("agent.failed" if failed else "agent.ran", item=agent.name, source=SOURCE, causedby=begun["id"],
                       data=data)
    return data


def _runs(agent) -> bool:
    return agent is not None and bool(agent.command) and agent.kind != "person"


class Runner:
    def __init__(self, project, say=print):
        from .history import version
        self.p, self.say = project, say
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.queues = {a.name: queue.Queue() for a in project.model.agents.values() if _runs(a)}
        self.workers: set[str] = set()   # agents with a worker thread
        self.waiting: set[str] = set()
        self.busy: set[str] = set()       # agents whose run is under way
        self.version = version(project.model)

    def _worker(self, name: str) -> None:
        with self.lock:
            if name in self.workers:
                return
            self.workers.add(name)
        threading.Thread(target=self._work, args=(name,), daemon=True).start()

    def _work(self, name: str) -> None:
        q = self.queues[name]
        while not self.stop.is_set():
            with self.lock:                              # each run under the agent as the model has it now
                agent = self.p.model.agents.get(name)
                if not _runs(agent):                     # removed (its last run finished): no more runs
                    self.workers.discard(name)
                    self.queues.pop(name, None)
                    self.waiting.discard(name)
                    return
            try:
                trig = q.get(timeout=TICK)
            except queue.Empty:
                continue
            self.waiting.discard(name)
            if self.stop.is_set():
                break
            with self.lock:
                agent = self.p.model.agents.get(name)
                if not _runs(agent):
                    continue
                version = self.version
                self.busy.add(name)
            try:
                r = run_agent(self.p, agent, trig, version=version)
            except Exception as e:                       # one agent failing never stops the rest
                self.say(f"{name}: {type(e).__name__}: {e}")
                continue
            finally:
                self.busy.discard(name)
            if r.get("note") or r.get("refused"):
                self.say(f"{name}: {r.get('note') or ''} {r.get('refused') and str(r['refused']) + ' refused' or ''}".strip())

    def _plan(self, model, crons: dict, next_cron: dict) -> tuple[list, dict, dict]:
        """The timed agents and the crons, from this model; a cron written the same keeps its next time."""
        from .cron import Cron
        timed = [a for a in model.agents.values() if _runs(a) and a.every]
        new = {a.name: (Cron(a.cron), a.cron) for a in model.agents.values() if _runs(a) and a.cron}
        times = {}
        for n, (c, text) in new.items():
            if n in crons and crons[n][1] == text and n in next_cron:
                times[n] = next_cron[n]
                continue
            try:
                times[n] = c.next_after(time.time())
            except Exception as e:
                self.say(f"{n}: its cron never matches ({e}); it will not run")
                times[n] = None
        return timed, new, times

    def _schedule(self) -> None:
        due: dict[str, float] = {}
        model = self.p.model
        timed, crons, next_cron = self._plan(model, {}, {})
        while not self.stop.is_set():
            if model is not self.p.model:                    # swapped: the new model's schedules from now
                model = self.p.model
                timed, crons, next_cron = self._plan(model, crons, next_cron)
            now = time.monotonic()
            for a in timed:
                if now >= due.get(a.name, 0):
                    due[a.name] = now + a.every
                    self._due(a.name)
            wall = time.time()
            for n, at in list(next_cron.items()):
                if at is not None and wall >= at:
                    try:
                        next_cron[n] = crons[n][0].next_after(wall)
                    except Exception as e:                      # one agent's schedule never stops the others
                        self.say(f"{n}: its cron no longer matches ({e}); it will not run again")
                        next_cron[n] = None
                    self._due(n)
            self.stop.wait(TICK)

    def _due(self, name: str) -> None:
        q = self.queues.get(name)
        if q is not None and name not in self.waiting:      # its last scheduled run has not started: skip
            self.waiting.add(name)
            q.put(None)

    def _prune(self) -> None:
        """Every ``storage: rollup: every`` (an hour): roll items' old events up into snapshots, forget
        what is older than the model's ``keep`` (default 30 days), and roll the measurements into their
        tiers (``rollup.upkeep``)."""
        from .rollup import upkeep
        while not self.stop.wait(60):                      # not at once: a start is busy enough
            try:
                got = upkeep(self.p)
                ro, me = got["rollup"], got.get("measurements") or {}
                if ro["items"] or got["pruned"] or me.get("forgot"):
                    self.say(f"rolled up {ro['events']} events of {ro['items']} items; kept {self.p.model.keep / 86400:g} days: "
                             f"forgot {got['pruned']} events; measurements: {me.get('rolled', 0)} buckets made, "
                             f"{me.get('forgot', 0)} rows forgotten")
            except Exception as e:
                self.say(f"rolling up: {type(e).__name__}: {e}")
            if self.stop.wait(getattr(self.p, "storage", None).every if getattr(self.p, "storage", None) else 3600):
                return

    def _follow(self, seq: int) -> None:
        """From ``seq``, taken before any thread started, so no event that lands meanwhile is missed."""
        model = None
        while not self.stop.is_set():
            if model is not self.p.model:                     # (swapped: who listens, from now)
                model = self.p.model
                listening = [a for a in model.agents.values() if _runs(a) and a.on]
            try:
                new = self.p.events.query(n=None, after_seq=seq)
            except Exception as e:                              # the follower outlives a busy database
                self.say(f"following events: {type(e).__name__}: {e}")
                self.stop.wait(1)
                continue
            for ev in new:
                seq = ev["seq"]
                for a in listening:
                    own = ev.get("source") == a.name or (ev.get("item") == a.name and ev["type"].startswith("agent."))
                    q = self.queues.get(a.name)
                    if q is not None and not own and any(matches(pat, ev) for pat in a.on):
                        q.put(ev)
            self.stop.wait(TICK)

    def start(self) -> None:
        from . import history
        history.note(self.p)
        STOPPING.clear()
        seq = self.p.events.last_seq()
        if not RELOADED.is_set():
            self._still_off()
        for name in list(self.queues):
            self._worker(name)
        threading.Thread(target=self._schedule, daemon=True).start()
        threading.Thread(target=self._follow, args=(seq,), daemon=True).start()
        threading.Thread(target=self._prune, daemon=True).start()
        self.p.events.add("ergostat.started", source=SOURCE, data={"agents": sorted(self.queues), "pid": os.getpid()})


    def swap(self, model) -> dict:
        """Take a changed model in place, never killing a run: one under way finishes as the agent it began as, and
        records the model it began under; new runs are the new model's. An agent removed runs no more once its run
        is done; one added starts at once. Records ``model.changed`` with the runs that carried over."""
        from . import history
        with self.lock:
            before, was = self.p.model, self.version
            carried = sorted(self.busy)
            self.p.model = model
            self.version = history.version(model)
            for a in model.agents.values():
                if _runs(a) and a.name not in self.queues:
                    self.queues[a.name] = queue.Queue()
            fresh = [a for a in model.agents if _runs(model.agents[a]) and a not in self.workers]
        for name in fresh:
            self._worker(name)
        changed = [n for n in carried if n in model.agents and history._hash(before.agents[n]) != history._hash(model.agents[n])]
        said = {"reload": "in place", "carried": len(carried), "runs": carried, "version_before": was,
                **({"finishing": {k: v for k, v in (("removed", [n for n in carried if n not in model.agents]),
                                                    ("changed", changed)) if v}}
                   if changed or any(n not in model.agents for n in carried) else {})}
        try:
            history.note(self.p, said)
        except Exception as e:
            self.say(f"recording the change: {type(e).__name__}: {e}")
        return {**said, "version": self.version}

    def _still_off(self) -> None:
        """A loop off when ergostat starts is said again: what its crossing set off may have been lost
        with the last run (a stop, a crash), and an agent listening for loop.off would wait forever.
        Only on a fresh start (not a reload), only on a recent reading, before any agent runs."""
        from .state import snapshot
        with EDGES:
            snap = snapshot(self.p)
            for name, lp in snap["loops"].items():
                fresh = lp.get("last_read") and snap["at"] - lp["last_read"] < 600
                if lp["status"] == "off" and fresh:
                    self.p.events.add("loop.off", item=name, source=SOURCE,
                                      data={"value": lp["value"], "setpoint": lp["setpoint"], "error": lp["error"], "still": True})

    def close(self) -> None:
        self.stop.set()
        kill_all()
        deadline = time.monotonic() + 5                  # let the killed runs record how they ended
        while self.busy and time.monotonic() < deadline:
            time.sleep(0.05)
        self.p.events.add("ergostat.stopped", source=SOURCE, data={"pid": os.getpid()})


# ---- in the background

def pid_file(project) -> Path:
    return project.dir / "run.pid"


_LOCK = None     # the open, locked pid file of the runner in this process


def take_lock(project) -> bool:
    """Lock ``run.pid`` for this process's life and write its pid: one runner per repository. A
    pid file whose lock nobody holds is stale (a crash, a reboot), whatever pid it names.

    A process restarted in place (a reload) inherits the locked file through ``ERGOSTAT_LOCK_FD``, so
    the lock is never let go between the two. A reader's brief shared lock (``running_pid``) is
    waited out for a moment rather than taken for another runner."""
    import fcntl
    global _LOCK
    fd = os.environ.pop("ERGOSTAT_LOCK_FD", "")
    if fd.isdigit():
        try:
            f = os.fdopen(int(fd), "a+")
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)  # already ours: a no-op that proves it
            os.set_inheritable(f.fileno(), False)
            _LOCK = f
            RELOADED.set()                               # the same runner, restarted with a new model
            return True
        except OSError:
            pass
    f = open(pid_file(project), "a+")
    deadline = time.monotonic() + 1.0
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() > deadline or running_pid(project, wait=False):
                f.close()
                return False
            time.sleep(0.02)
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    _LOCK = f
    return True


def keep_lock_across_exec() -> dict:
    """The environment that hands this process's lock to the program it ``execv``s into."""
    if _LOCK is None:
        return {}
    os.set_inheritable(_LOCK.fileno(), True)
    return {"ERGOSTAT_LOCK_FD": str(_LOCK.fileno())}


def running_pid(project, wait: bool = True) -> int | None:
    """The runner's pid, when one holds the lock on ``run.pid``. A file locked but still empty (a
    runner between locking and writing it) is read again for a moment."""
    import fcntl
    for _ in range(25 if wait else 1):
        try:
            with open(pid_file(project)) as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:                     # held: a runner is there, or another reader
                    try:
                        pid = int(f.read().strip() or 0)
                    except ValueError:
                        pid = 0
                    if pid:
                        return pid
                    if not wait:
                        return None
                    time.sleep(0.02)
                    continue
                fcntl.flock(f, fcntl.LOCK_UN)
                return None                                 # nobody holds it: stale
        except FileNotFoundError:
            return None
    return None


def web_url(project) -> str | None:
    try:
        return json.loads((project.dir / "web.json").read_text())["url"]
    except (FileNotFoundError, ValueError, KeyError):
        return None


def start_background(project, args: list[str]) -> int:
    log = project.dir / "run.log"
    try:
        if log.stat().st_size > 5_000_000:              # kept to two: this one and the one before
            log.replace(log.with_suffix(".log.1"))
    except OSError:
        pass
    with open(log, "a") as lf:
        p = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(project.repo), "run", "--foreground", *args],
                             stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    return p.pid
