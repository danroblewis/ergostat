"""The ticket factory's daemons (examples/ticket-factory, README "Daemons"): the record's measures, the Jira watcher, the
short steps and the teammate are each handed to a long-lived process instead of a process per reading or run. The
model is the same as before (only how parts run changed), each daemon answers lines piped by hand, and under the
engine each fills its sensors or works its tickets, and is restarted and carries on when it is killed."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "ticket-factory"
SHORT = ["pick-up", "locate", "open-pr", "ask-review", "review", "sail", "ci", "merge", "close"]
MEASURES = ["ai-spend", "repings", "cycle-hours"]


@pytest.fixture
def factory(tmp_path, monkeypatch):
    """A fresh copy of the example, offline (against its fakes), its record in a home of its own."""
    d = tmp_path / "tf"
    shutil.copytree(EXAMPLE, d, ignore=shutil.ignore_patterns("run", "reports", "__pycache__", "factory.conf",
                                                              "prometheus.yaml"))
    monkeypatch.setenv("TF_OFFLINE", "1")
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    return d


def test_the_daemons_change_only_how_parts_run(factory):
    spec = mdl.load(factory).spec
    assert set(spec.daemons) == {"steps", "measures", "sensor.arrivals.main", "block.teammate"}
    assert spec.daemons["steps"].concurrency == sum(spec.blocks[b].pool for b in SHORT), \
        "as many tickets at once as when each step was a process"
    for b in SHORT:
        assert spec.blocks[b].params["daemon"] == "steps" and not spec.blocks[b].params.get("run"), b
    for b in ("work", "address", "fix-ci"):                     # the AI steps: a process per run
        assert spec.blocks[b].params["run"] == f"python3 bin/step.py {b}" and not spec.blocks[b].params.get("daemon")
    assert spec.blocks["reporter"].params["run"] == "python3 bin/report.py"
    assert spec.blocks["teammate"].params["daemon"] == "block.teammate"
    sensors = {s.series: s for s in spec.sensors()}
    for m in MEASURES:                                          # the series keep their names, and so their history
        assert sensors[f"sensor/{m}.main"].daemon == "measures"
    assert sensors["sensor/arrivals.main"].daemon == "sensor.arrivals.main"
    own = [s.series for s in spec.sensors() if (s.run or "").startswith("python3 bin/")]
    assert not own, "the factory's own sensors: each read by a daemon now"


def _env(d: Path) -> dict:
    return {**os.environ, "ERGOSTAT_CMD": f"{sys.executable} -m ergostat -C {d}", "ERGOSTAT_NO_SOCKET": "1"}


def _pipe(d: Path, cmd: str, *lines: dict) -> tuple[list[dict], int]:
    r = subprocess.run(["python3", *cmd.split()], cwd=d, env=_env(d), capture_output=True, text=True, timeout=60,
                       input="".join(json.dumps(x) + "\n" for x in lines))
    return [json.loads(x) for x in r.stdout.splitlines()], r.returncode


def test_each_daemon_answers_lines_piped_by_hand(factory):
    got, code = _pipe(factory, "bin/measure.py serve", *[{"op": "read", "sensor": f"{m}.main", "request": m}
                                                         for m in MEASURES], {"op": "stop"})
    assert code == 0 and sorted(x["request"] for x in got) == sorted(MEASURES) and all(x["reading"] == 0 for x in got)

    got, code = _pipe(factory, "bin/watch.py serve", {"op": "read", "sensor": "arrivals.main", "request": "1"},
                      {"op": "stop"})
    assert code == 0 and got == [{"reading": 18.0, "request": "1"}], "three issues waiting at first: 18 an hour"
    found = Project(mdl.load(factory)).events.query(n=None, type="ticket.found")
    assert len(found) == 3 and {e["source"] for e in found} == {"arrivals.main"}, "recorded as the sensor's own"

    got, code = _pipe(factory, "bin/step.py serve",
                      {"op": "item", "run": "r1", "item": "ticket/SCRUM-1", "input": {},
                       "env": {"ERGOSTAT_BLOCK": "sail", "ERGOSTAT_ITEM": "ticket/NONE-1"}},
                      {"op": "cancel", "run": "not-held"}, {"op": "stop"})
    assert code == 0 and {"done": 1, "run": "r1"} in got, "no such ticket: exit 1, as the process would"
    assert all(set(x) in ({"heartbeat"}, {"done", "run"}) for x in got), got
    assert not [x for x in got if x.get("run") == "not-held"], "a cancel for a run it never held is not answered"
    _, code = _pipe(factory, "bin/step.py serve", {"op": "stop"})
    assert code == 0
    r = subprocess.run(["python3", "bin/step.py", "serve"], cwd=factory, env=_env(factory), input="not json\n",
                       capture_output=True, text=True, timeout=30)
    assert r.returncode != 0, "a line it cannot read ends it, for ergostat to restart"


def _readings(p, series: str, since: float) -> bool:
    """A reading of that series since then."""
    got = p.measurements.latest(series)
    return bool(got) and got[0] >= since


def _wait(cond, seconds: float):
    end = time.time() + seconds
    while time.time() < end:
        if got := cond():
            return got
        time.sleep(0.25)
    return cond()


@pytest.mark.slow
def test_the_daemons_start_fill_their_sensors_and_survive_a_kill(factory):
    p = Project(mdl.load(factory))
    e = Engine(p, say=lambda s: None)
    e.start_all()
    sensed = [f"sensor/{m}.main" for m in MEASURES] + ["sensor/arrivals.main"]

    def moved(since: float) -> int:                             # ticket steps done by the steps' daemon since then
        return len([x for x in p.events.query(n=None, type="agent.ran", since=since)
                    if x["data"].get("daemon") == "steps" and x["data"].get("moved")])
    try:
        t0 = time.time()
        assert _wait(lambda: all(_readings(p, s, t0) for s in sensed), 40), "each sensor read by its daemon"
        assert _wait(lambda: p.events.query(n=None, type="auxiliary.set", item="team-reviewing"), 20)
        assert _wait(lambda: moved(t0), 60), "the steps' daemon works tickets"
        status = e.daemons.status()
        assert {n: s["state"] for n, s in status.items()} == dict.fromkeys(status, "running")
        before = {n: s["pid"] for n, s in status.items()}
        for pid in before.values():
            os.kill(pid, signal.SIGKILL)
        killed = time.time()

        def back():
            now = e.daemons.status()
            return all(now[n]["state"] == "running" and now[n]["pid"] not in (None, before[n]) for n in before)
        assert _wait(back, 30), e.daemons.status()
        restarted = {x["item"] for x in p.events.query(n=None, type="ergostat.daemon.restarted", since=killed - 1)}
        assert set(before) <= restarted, restarted
        assert {"steps", "measures", "sensor.arrivals.main", "block.teammate"} <= set(before)
        assert _wait(lambda: all(_readings(p, s, killed + 0.5) for s in sensed), 40), "reading again after the kill"
        assert _wait(lambda: moved(killed + 0.5), 60), "working tickets again after the kill"
    finally:
        e.close()
    assert not [t for t in its.project(p.events, p.model.spec) if t.state == "dead"], "no ticket lost to the kills"


def test_a_sensor_read_by_a_daemon_is_still_the_arrivals_collector(factory):
    """What ergostat makes of a sensor that reads by a program (the Blocks view's collector, the flow measured by the
    items it reported, its stale clock) holds for one read by a daemon as for one read by a command."""
    from ergostat import sensing
    from ergostat.spec import item_sets
    from ergostat.spec.observer import stale_by

    from .test_blockdiagram import drawn
    spec = mdl.load(factory).spec
    watcher = spec.flows["arrivals"].sensors["main"]
    assert any(x is watcher for x in sensing.collectors(spec)["ticket"])
    assert sensing.what(spec, watcher) == "daemon: watch.py serve"
    assert item_sets._events_of(spec, spec.flows["arrivals"], None)["source"] == "arrivals.main"
    assert stale_by(watcher, 100.0) is not None
    col = next(x for x in drawn(spec, {"*"})["nodes"] if x["id"] == "col:arrivals.main")
    assert col["role"] == "collector" and col["label"] == "watch.py serve"
    y = factory / "factory" / "intake.yaml"                   # a push daemon is not asked: no collector, no clock
    y.write_text(y.read_text().replace("      every: 10s\n      averages: 10m\n", "      push: true\n"))
    pushed = mdl.load(factory).spec
    s = pushed.flows["arrivals"].sensors["main"]
    assert s.push and not s.commands and not sensing.collectors(pushed).get("ticket") and stale_by(s, 100.0) is None


@pytest.mark.slow
def test_a_stuck_cancelled_step_ends_its_daemon_and_the_next_ticket_gets_through(factory, monkeypatch):
    """A step hung in a call outside (a git fetch that never answers, under the clone's lock) is cancelled at its
    timeout; still going after the grace, its daemon ends, is started again, and the tickets go on."""
    fake, hang = factory.parent / "fakebin", factory.parent / "hang"
    fake.mkdir()
    (fake / "git").write_text(f'#!/bin/sh\ncase "$*" in *fetch*) [ -e {hang} ] && exec sleep 600 ;; esac\n'
                              f'exec {shutil.which("git")} "$@"\n')
    (fake / "git").chmod(0o755)
    hang.write_text("")
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    monkeypatch.setenv("TF_CANCEL_GRACE", "1s")
    y = factory / "steps" / "02-locate.yaml"
    y.write_text(y.read_text().replace("    pool: 3\n", "    pool: 3\n    timeout: 3s\n"))
    p = Project(mdl.load(factory))
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        def restarted():
            return [x for x in p.events.query(n=None, type="ergostat.daemon.restarted") if x["item"] == "steps"]
        assert _wait(restarted, 60), "the stuck run's daemon ended, and was started again"
        hang.unlink()
        assert _wait(lambda: e.daemons.status()["steps"]["state"] == "running", 20)
        assert _wait(lambda: p.events.query(n=None, type="ticket.locate"), 60), "a ticket located after the restart"
    finally:
        e.close()
    log = (p.dir / "logs" / "daemon-steps.log").read_text()
    assert "still going 1s after its cancel" in log


def test_the_record_is_read_whole_past_a_page(factory):
    """tf.items pages through the socket's listing (500 a page): repings over 600 tickets counts every one."""
    import socket
    import tempfile
    import threading
    tickets = [{"id": f"ticket/T-{n}", "state": "done", "fields": {"repings": 1}} for n in range(600)]
    where = Path(tempfile.mkdtemp(dir="/tmp")) / "s.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(where))
    srv.listen()

    def serve():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            req = json.loads(c.makefile().readline())
            off = int(req.get("offset") or 0)
            c.sendall(json.dumps({"items": tickets[off:off + 500], "total": len(tickets), "offset": off}).encode() + b"\n")
            c.close()
    threading.Thread(target=serve, daemon=True).start()
    try:
        r = subprocess.run(["python3", "bin/measure.py", "repings"], cwd=factory, capture_output=True, text=True,
                           env={**_env(factory), "ERGOSTAT_SOCKET": str(where)}, timeout=30)
    finally:
        srv.close()
    assert r.returncode == 0 and r.stdout.strip() == "600", r.stderr
