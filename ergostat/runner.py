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
OWN_TYPES = ("agent.", "loop.", "valve.", "controller.", "model.", "ergostat.")   # no agent may publish these
LIVE: set = set()          # the runs in progress, so stopping ergostat stops them too


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
            last = project.events.query(n=1, item=c.name, type="loop.*")
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
        self.fills = {(r.kind, r.name) for r in project.model.roles_of(agent.name)}
        self.counts = {"readings": 0, "openings": 0, "decisions": 0, "events": 0, "refused": 0, "unread": 0}
        self.unread: list[str] = []

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
        try:
            line = json.loads(raw)
        except ValueError:
            if raw.lstrip().startswith("{"):             # meant for ergostat, but not JSON
                self.not_read(raw)
            return False
        if not isinstance(line, dict):
            return False
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
                if "position" in line:                   # how far it is open: a setting, kept as a measurement
                    if not _number(line["position"]):
                        self.refuse(line, "position must be a number")
                        return True
                    self.p.measurements.add(f"valve/{name}", float(line["position"]))
                if "amount" in line:
                    if not _number(line["amount"]) or line["amount"] < 0:
                        self.refuse(line, "amount must be a number, 0 or more (a flow runs one way)")
                        return True
                    ev.add("valve.opened", item=name, source=self.agent.name, causedby=self.run_id,
                           data={"amount": float(line["amount"]), "flow": self.p.model.valves[name].flow,
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
            ev.add(t, item=line.get("item"), source=self.agent.name, causedby=self.run_id, data=line.get("data") or {})
            self.counts["events"] += 1
            return True
        self.not_read(raw)                                   # an object that names no part and no event
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
        last = project.events.query(n=1, item=lp.name, type="loop.*")
        before = last[0]["type"].split(".", 1)[1] if last else None
        now = lp.controller.status(value, was_off=before == "off")
        if before != now:
            out.append(project.events.add(f"loop.{now}", item=lp.name, source=SOURCE, causedby=causedby,
                                          data={"value": value, "setpoint": lp.controller.setpoint, "error": error}))
    return out


def run_agent(project, agent, trigger: dict | None = None, why: str = "schedule") -> dict:
    """One run: start the command, feed it its context, record its lines, and record the run."""
    started = time.time()
    begun = project.events.add("agent.started", item=agent.name, source=SOURCE,
                               causedby=trigger.get("id") if trigger else None,
                               data={"trigger": trigger["type"] if trigger else why})
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
            elif code != 0:
                note = f"exited {code}"
    data = {"exit": code, "seconds": round(time.time() - started, 3), **rec.counts, "why": trigger["type"] if trigger else why,
            **({"unread_lines": rec.unread} if rec.unread else {}), **({"note": note} if note else {})}
    project.events.add("agent.ran" if not note else "agent.failed", item=agent.name, source=SOURCE, causedby=begun["id"],
                       data=data)
    return data


class Runner:
    def __init__(self, project, say=print):
        self.p, self.say = project, say
        self.stop = threading.Event()
        self.queues = {a.name: queue.Queue() for a in project.model.agents.values() if a.command and a.kind != "person"}
        self.waiting: set[str] = set()

    def _work(self, name: str) -> None:
        agent = self.p.model.agents[name]
        q = self.queues[name]
        while not self.stop.is_set():
            try:
                trig = q.get(timeout=TICK)
            except queue.Empty:
                continue
            self.waiting.discard(name)
            if self.stop.is_set():
                break
            try:
                r = run_agent(self.p, agent, trig)
            except Exception as e:                       # one agent failing never stops the rest
                self.say(f"{name}: {type(e).__name__}: {e}")
                continue
            if r.get("note") or r.get("refused"):
                self.say(f"{name}: {r.get('note') or ''} {r.get('refused') and str(r['refused']) + ' refused' or ''}".strip())

    def _schedule(self) -> None:
        from .cron import Cron
        due: dict[str, float] = {}
        timed = [a for a in self.p.model.agents.values() if a.name in self.queues and a.every]
        crons = {a.name: Cron(a.cron) for a in self.p.model.agents.values() if a.name in self.queues and a.cron}
        next_cron = {}
        for n, c in crons.items():
            try:
                next_cron[n] = c.next_after(time.time())
            except Exception as e:
                self.say(f"{n}: its cron never matches ({e}); it will not run")
                next_cron[n] = None
        while not self.stop.is_set():
            now = time.monotonic()
            for a in timed:
                if now >= due.get(a.name, 0):
                    due[a.name] = now + a.every
                    self._due(a.name)
            wall = time.time()
            for n, at in list(next_cron.items()):
                if at is not None and wall >= at:
                    try:
                        next_cron[n] = crons[n].next_after(wall)
                    except Exception as e:                      # one agent's schedule never stops the others
                        self.say(f"{n}: its cron no longer matches ({e}); it will not run again")
                        next_cron[n] = None
                    self._due(n)
            self.stop.wait(TICK)

    def _due(self, name: str) -> None:
        if name not in self.waiting:                        # its last scheduled run has not started: skip
            self.waiting.add(name)
            self.queues[name].put(None)

    def _prune(self) -> None:
        """Hourly: forget what is older than the model's ``keep`` (default 30 days)."""
        while not self.stop.is_set():
            before = time.time() - self.p.model.keep
            try:
                gone = self.p.events.prune(before), self.p.measurements.prune(before)
                if any(gone):
                    self.say(f"kept {self.p.model.keep / 86400:g} days: forgot {gone[0]} events and {gone[1]} measurements")
            except Exception as e:
                self.say(f"pruning: {type(e).__name__}: {e}")
            self.stop.wait(3600)

    def _follow(self, seq: int) -> None:
        """From ``seq``, taken before any thread started, so no event that lands meanwhile is missed."""
        listening = [a for a in self.p.model.agents.values() if a.name in self.queues and a.on]
        while not self.stop.is_set():
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
                    if not own and any(matches(pat, ev) for pat in a.on):
                        self.queues[a.name].put(ev)
            self.stop.wait(TICK)

    def start(self) -> None:
        from . import history
        history.note(self.p)
        seq = self.p.events.last_seq()
        for name in self.queues:
            threading.Thread(target=self._work, args=(name,), daemon=True).start()
        threading.Thread(target=self._schedule, daemon=True).start()
        threading.Thread(target=self._follow, args=(seq,), daemon=True).start()
        threading.Thread(target=self._prune, daemon=True).start()
        self.p.events.add("ergostat.started", source=SOURCE, data={"agents": sorted(self.queues), "pid": os.getpid()})

    def close(self) -> None:
        self.stop.set()
        kill_all()
        self.p.events.add("ergostat.stopped", source=SOURCE, data={"pid": os.getpid()})


# ---- in the background

def pid_file(project) -> Path:
    return project.dir / "run.pid"


_LOCK = None     # the open, locked pid file of the runner in this process


def take_lock(project) -> bool:
    """Lock ``run.pid`` for this process's life and write its pid: one runner per repository. A
    pid file whose lock nobody holds is stale (a crash, a reboot), whatever pid it names."""
    import fcntl
    global _LOCK
    f = open(pid_file(project), "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return False
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    _LOCK = f
    return True


def running_pid(project) -> int | None:
    """The runner's pid, when one holds the lock on ``run.pid``."""
    import fcntl
    try:
        with open(pid_file(project)) as f:
            try:
                fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:                     # held: a runner is there
                try:
                    return int(f.read().strip() or 0) or None
                except ValueError:
                    return None
            fcntl.flock(f, fcntl.LOCK_UN)
            return None                                 # nobody holds it: stale
    except FileNotFoundError:
        return None


def web_url(project) -> str | None:
    try:
        return json.loads((project.dir / "web.json").read_text())["url"]
    except (FileNotFoundError, ValueError, KeyError):
        return None


def start_background(project, args: list[str]) -> int:
    log = project.dir / "run.log"
    with open(log, "a") as lf:
        p = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(project.repo), "run", "--foreground", *args],
                             stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    return p.pid
