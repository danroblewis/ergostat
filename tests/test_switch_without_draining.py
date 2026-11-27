"""switch-without-draining (dev/records/switch-without-draining.md): a version switch (`dev/bin/live.py switch`), and
a reverted one, leave the runs under way alone. Two versions of a small model, each run by the real engine (`runs:
outlive_engine: true`), three runs under way at the switch: none is stopped or given back, none loses an attempt, the
engine the switch starts takes them up from their journals, and each finishes and is recorded once."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.leases import ENDED
from ergostat.spec import items as its
from ergostat.store import Project
from tests.test_factory import BIN, ROOT, Factory

PY = shlex.quote(sys.executable)
TICKETS = ("ticket/1", "ticket/2", "ticket/3")

MODEL = """
name: sw
runs:
  outlive_engine: true
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [ready, done]
    events:
      ticket-done:
        when: type == 'ticket.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
  gap:
    query: key.startswith('gap/')
    fields:
      state:
        type: one of [open]
  upgrade:
    query: key.startswith('upgrade/')
    fields:
      state:
        type: one of [switched, healthy, reverted, failed]
    events:
      upgrade-switched:
        when: type == 'upgrade.switched'
        '...': data
        state: set('switched')
      upgrade-kept:
        when: type == 'upgrade.kept'
        '...': data
        state: set('healthy')
      upgrade-reverted:
        when: type == 'upgrade.reverted'
        '...': data
        state: set('reverted')
      upgrade-failed:
        when: type == 'upgrade.failed'
        '...': data
        state: set('failed')
      other:
        when: true
        '...': data
SENSED
stocks:
  handled:
    unit: tickets
flows:
  did:
    to: handled
blocks:
  merge-queue:
    type: program
    run: RUN
    takes: {projection: ticket, at: ready}
    pool: 3
    lease: {ttl: 2m}
    out: flow.did
"""
SENSED = """auxiliaries:
  suites-running:
    unit: suites
    sensor: {run: echo 0, every: 1s}"""

# A run: its first line, then (once the go file is there) a second, naming the version whose code it runs, and done.
WORK = """
import json, os, sys, time
sys.stdin.read()
VERSION = {version!r}
def say(x):
    sys.stdout.write(json.dumps(x) + "\\n")
    sys.stdout.flush()
say({{"event": "ticket.noted", "data": {{"n": 1, "v": VERSION}}}})
end = time.time() + 120
while not os.path.exists(sys.argv[1]) and time.time() < end:
    time.sleep(0.05)
say({{"event": "ticket.noted", "data": {{"n": 2, "v": VERSION}}}})
say({{"out": "flow.did", "moved": 1}})
say({{"event": "ticket.done"}})
"""


def wait_for(cond, seconds=60.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.1)
    return cond()


def version(live: Path, sha: str, go: Path, healthy: bool = True) -> None:
    """A version in its own folder, as live.py install makes one: its `ergostat` (this checkout's, on this Python),
    its model and dev/ (the run's program, naming the version). Not healthy: no sensor for live.py health to read."""
    d = live / sha
    (d / ".venv" / "bin").mkdir(parents=True)
    (d / "dev").mkdir()
    exe = d / ".venv" / "bin" / "ergostat"
    exe.write_text(f"#!/bin/sh\nexec {PY} -m ergostat \"$@\"\n")
    exe.chmod(0o755)
    run = json.dumps(f"{PY} dev/work.py {shlex.quote(str(go))}")
    (d / "ergostat.yaml").write_text(MODEL.replace("RUN", run).replace("SENSED", SENSED if healthy else ""))
    (d / "dev" / "work.py").write_text(WORK.format(version=sha[:1]))


class Instance:
    """The instance (live/instance) on version a, its engine started, three tickets' runs under way."""

    def __init__(self, tmp: Path, b_healthy: bool, wait: int):
        self.f = Factory(tmp)
        self.f.config.write_text(self.f.config.read_text().replace("[instance]\nport = 0\n",
                                                                   f"[instance]\nport = 0\nhealth_wait = {wait}\n"))
        self.live, self.go = tmp / "live", tmp / "go"
        self.a, self.b = "a" * 40, "b" * 40
        version(self.live, self.a, self.go)
        version(self.live, self.b, self.go, healthy=b_healthy)
        self.inst = self.live / "instance"
        self.inst.mkdir()
        (self.live / "current").symlink_to(self.a)
        self.env = {**self.f.env, "ERGOSTAT_HOME": str(tmp / "home"), "FACTORY_CONFIG": str(self.f.config)}
        self.live_py("init")
        for t in TICKETS:
            self.ergostat("event", "--add", "ticket.opened", "--item", t, "--as", "t")
        self.live_py("start")

    def live_py(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(BIN / "live.py"), *args], cwd=self.inst, env=self.env,
                              capture_output=True, text=True, check=check, timeout=300)

    def ergostat(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "ergostat", "-C", str(self.inst), *args], env=self.env,
                              capture_output=True, text=True, timeout=120)

    def project(self) -> Project:
        os.environ["ERGOSTAT_HOME"] = self.env["ERGOSTAT_HOME"]
        return Project(mdl.load(self.inst))

    def close(self) -> None:
        self.go.touch()
        self.ergostat("run", "--stop", "--runs")


@pytest.fixture
def instance(tmp_path, monkeypatch):
    made: list[Instance] = []
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))

    def make(b_healthy: bool = True, wait: int = 60) -> Instance:
        made.append(Instance(tmp_path, b_healthy, wait))
        return made[-1]
    yield make
    for i in made:
        i.close()


def noted(p: Project, n: int) -> list[dict]:
    return [e for e in p.events.query(n=None, type="ticket.noted") if e["data"]["n"] == n]


def under_way(p: Project) -> dict[str, str]:
    """Each ticket's run, once all three have printed their first line: {ticket: run}."""
    first = noted(p, 1)
    return {e["item"]: e["causedby"] for e in first} if len(first) == 3 else {}


def pids(i: Instance, runs) -> dict[str, int]:
    state = i.project().dir.resolve() / "runs"
    return {r: json.loads((state / f"{r}.json").read_text())["pid"] for r in runs}


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def finished_once(i: Instance, runs: dict[str, str]) -> None:
    """Done 1 and 2's end: each run finished under the version it started with and was recorded once (one start, one
    end, taken up); each ticket done, its lease acked once, no attempt counted; nothing stopped or refused."""
    p = i.project()
    assert wait_for(lambda: all(its.one(p.events, p.model.spec, t).state == "done" for t in TICKETS), 90), \
        "a run never finished"
    assert wait_for(lambda: len(p.events.query(n=None, type="agent.ran,agent.failed", item="merge-queue")) == 3, 30)
    ends = p.events.query(n=None, type="agent.ran,agent.failed", item="merge-queue")
    assert sorted(e["causedby"] for e in ends) == sorted(runs.values()), "a run recorded twice, or another run"
    assert all(e["type"] == "agent.ran" and e["data"]["exit"] == 0 and "note" not in e["data"] for e in ends), ends
    assert all(e["data"].get("taken_up") is True for e in ends), "ended by an engine that did not take it up"
    assert len(p.events.query(n=None, type="agent.started", item="merge-queue")) == 3, "a run started again"
    assert {e["causedby"]: e["data"]["v"] for e in noted(p, 2)} == {r: "a" for r in runs.values()}, \
        "a run's line after the switch not from the version it started with"
    for t in TICKETS:
        it = its.one(p.events, p.model.spec, t)
        assert it.fields["lease"]["attempts"] == 0, f"{t} lost an attempt"
        assert [x["data"]["how"] for x in p.events.query(n=None, type=ENDED, item=t)] == ["ack"], t
    assert not p.events.query(n=None, type="run.refused")


def test_the_factory_keeps_its_runs_going_past_its_engine():
    """The factory's model has `runs: outlive_engine` on, so a switch's stop leaves its runs under way going."""
    from ergostat.spec import read
    spec, _ = read(ROOT / "ergostat.yaml")
    assert spec.outlive_engine is True


@pytest.mark.slow
def test_a_switch_with_runs_under_way_stops_none_and_each_finishes_and_is_recorded(instance):
    """Done 1: three runs under way at `live.py switch`: the engine is stopped and the new version's started, the runs
    go on all through it (their processes, their leases: none ended, given back or expired), and the new engine
    takes them up; then each finishes and is recorded once, with no attempt lost."""
    i = instance()
    p = i.project()
    runs = wait_for(lambda: under_way(p), 90)
    assert runs, "the three runs never started"
    before, t0 = pids(i, runs.values()), time.time()
    os.utime(i.live / i.a, (0, 0))
    r = i.live_py("switch", i.b, check=False)
    assert r.returncode == 0 and json.loads(r.stdout.splitlines()[-1])["healthy"], (r.stdout, r.stderr)
    assert os.readlink(i.live / "current") == i.b and os.readlink(i.live / "previous") == i.a
    assert (i.live / i.a).stat().st_mtime >= t0 - 1, "the runs' version not kept fresh for cleanup.py"
    assert all(alive(x) for x in before.values()), "a run under way was stopped by the switch"
    p = i.project()
    assert not p.events.query(n=None, type=ENDED), "a lease ended at the switch"
    assert not p.events.query(n=None, type="agent.ran,agent.failed", item="merge-queue")
    assert its.one(p.events, p.model.spec, f"upgrade/{i.b[:12]}").state == "healthy"
    assert (i.inst / "dev" / "work.py").read_text().count("VERSION = 'b'") == 1      # the instance on b's code now
    i.go.touch()
    finished_once(i, runs)


@pytest.mark.slow
def test_a_reverted_switch_with_runs_under_way_stops_none_and_each_finishes_and_is_recorded(instance):
    """Done 2: the switch to a version that starts but is not healthy is reverted: its engine took the runs up and is
    stopped, the version before is started again and takes them up in turn; none is stopped or given back, and each
    finishes and is recorded once, with no attempt lost."""
    i = instance(b_healthy=False, wait=8)
    p = i.project()
    runs = wait_for(lambda: under_way(p), 90)
    assert runs, "the three runs never started"
    before, t0 = pids(i, runs.values()), time.time()
    os.utime(i.live / i.b, (0, 0))
    r = i.live_py("switch", i.b, check=False)
    assert r.returncode == 1 and not json.loads(r.stdout.splitlines()[-1])["healthy"], (r.stdout, r.stderr)
    assert os.readlink(i.live / "current") == i.a, "not reverted"
    assert (i.live / i.b).stat().st_mtime >= t0 - 1, "the reverted version not kept fresh for cleanup.py"
    assert all(alive(x) for x in before.values()), "a run under way was stopped by the switch or its revert"
    p = i.project()
    assert its.one(p.events, p.model.spec, f"upgrade/{i.b[:12]}").state == "reverted"
    assert not p.events.query(n=None, type=ENDED), "a lease ended at the switch or its revert"
    i.go.touch()
    finished_once(i, runs)
