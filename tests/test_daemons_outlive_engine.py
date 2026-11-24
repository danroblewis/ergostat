"""A daemon kept by a keeper goes on through an engine restart and picks its messages back up (SPEC §9.7, *A daemon
that outlives its engine*): the engine SIGKILLed with the daemon mid-item, the item's result is recorded by the next
engine; a message not answered is sent again with its id, none lost; a daemon that died while no engine was up is
restarted by the next; one declared to stop with the engine does."""

import json
import os
import shlex
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.compute.worker import keeper
from ergostat.daemons import kept
from ergostat.leases import ENDED
from ergostat.spec import adopt, read
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = shlex.quote(sys.executable)

# Every line it is sent noted in GOT ({op, run, pid}); an item's run already seen is dropped (a repeat, by its id).
# Each item: a first line, then, once GO exists, the item moved on and done; once DIE exists, it exits 3 instead.
DAEMON = """
import json, os, sys, threading, time
got, go = sys.argv[1], sys.argv[2]
lock, seen = threading.Lock(), set()
def say(o):
    with lock:
        sys.stdout.write(json.dumps(o) + "\\n")
        sys.stdout.flush()
def work(run):
    say({"event": "ticket.noted", "data": {"n": 1}, "run": run})
    while not os.path.exists(go):
        if os.path.exists(go + ".die"):
            os._exit(3)
        time.sleep(0.05)
    say({"event": "ticket.done", "run": run})
    say({"done": 0, "run": run})
for raw in sys.stdin:
    m = json.loads(raw)
    with open(got, "a") as f:
        f.write(json.dumps({"op": m.get("op"), "run": m.get("run"), "pid": os.getpid()}) + "\\n")
    if m.get("op") == "stop":
        break
    if m.get("op") == "item" and m["run"] not in seen:
        seen.add(m["run"])
        threading.Thread(target=work, args=(m["run"],)).start()
while True:
    time.sleep(1)
"""

MODEL = """
name: a
items:
  ticket:
    id: ticket/*
    states: [ready, done]
    on: {ticket.done: done}
blocks:
  worker:
    type: program
    takes: {kind: ticket, at: ready}
    daemon: {run: RUN, outlive-engine: true}
"""


@pytest.fixture(autouse=True)
def _stopping_cleared():
    yield
    runner.STOPPING.clear()


def wait_for(cond, seconds=30.0):
    end = time.time() + seconds
    while time.time() < end:
        if got := cond():
            return got
        time.sleep(0.05)
    return cond()


def project(tmp_path, model: str = MODEL) -> Project:
    (tmp_path / "daemon.py").write_text(textwrap.dedent(DAEMON))
    run = f"{PY} daemon.py {shlex.quote(str(tmp_path / 'got'))} {shlex.quote(str(tmp_path / 'go'))}"
    (tmp_path / "ergostat.yaml").write_text(model.replace("RUN", json.dumps(run)))
    p = Project(mdl.load(tmp_path))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    return p


@pytest.fixture
def daemons():
    """Every kept daemon a test left, stopped and let go at its end: nothing outlives the test."""
    made: list = []
    yield made.append
    for p in made:
        for base in (p.dir.resolve() / "daemons").glob("*"):
            keeper.stop_all(str(base), 0)
            for d in (base / "runs").glob("*"):
                wait_for(lambda d=d: keeper.ended(str(d)) is not None, 10)
                keeper.put(str(d / "done"), "")


def state(p) -> dict:
    return kept.read_state(kept.folder(p.dir, "block.worker"), "block.worker")


def got(tmp_path) -> list[dict]:
    f = tmp_path / "got"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


def engine(tmp_path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "run", "--foreground", "--no-web"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def killed_mid_item(p, tmp_path) -> str:
    """An engine hands ticket/1 to the daemon, which says its first line; the engine's whole group is SIGKILLed. The
    run's id, once the daemon is seen still going."""
    proc = engine(tmp_path)
    try:
        assert wait_for(lambda: p.events.query(n=1, type="ticket.noted"), 60), "the item never reached the daemon"
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    run = p.events.query(n=1, type="ticket.noted")[0]["causedby"]
    st = state(p)
    assert st and run in st["held"], "the run it holds is in its state before it was handed over"
    assert adopt.alive({"pid": st["pid"], "start": st["start"]}) is not False, "the daemon died with its engine"
    return run


def ends(p) -> list[dict]:
    return p.events.query(n=None, type="agent.ran,agent.failed", item="worker")


def ended_once(p, run: str, noted: int = 1) -> None:
    """One end, the item moved on, its lease acked; ``noted``: its first line's events, one per process that ran it
    (a line read again adds none)."""
    got_ = ends(p)
    assert len(got_) == 1 and got_[0]["type"] == "agent.ran" and got_[0]["causedby"] == run, [x["data"] for x in got_]
    assert got_[0]["data"]["exit"] == 0 and got_[0]["data"]["taken_up"] is True
    assert len(p.events.query(n=None, type="ticket.noted")) == noted, "a line read again added an event"
    assert wait_for(lambda: p.events.query(n=None, type=ENDED, item="ticket/1"), 10), "its lease never ended"
    it = its.one(p.events, p.model.spec, "ticket/1")
    assert it.state == "done" and it.fields["lease"]["holder"] is None
    assert [x["data"]["how"] for x in p.events.query(n=None, type=ENDED, item="ticket/1")] == ["ack"]
    assert wait_for(lambda: run not in (state(p) or {"held": {}})["held"], 5), "its end recorded, still held"


def taken_up(p) -> Engine:
    e = Engine(p, say=lambda s: None)
    e.daemons.sync(e.spec)
    return e


@pytest.mark.slow
def test_a_daemon_finishes_its_item_through_an_engine_kill_and_its_result_is_recorded_after(tmp_path, daemons):
    """Done 1: the engine SIGKILLed mid-item; the daemon finishes it with no engine up (its journal has the end), and
    the next engine records it: one agent.ran, the item moved on, its lease acked."""
    p = project(tmp_path)
    daemons(p)
    run = killed_mid_item(p, tmp_path)
    (tmp_path / "go").write_text("")
    out = kept.files(kept.folder(p.dir, "block.worker"), state(p)["proc"])["out"]
    assert wait_for(lambda: f'"done": 0, "run": "{run}"' in out.read_text()), "it never finished while no engine was up"
    assert not ends(p), "an end recorded with no engine up"
    e = taken_up(p)
    try:
        assert wait_for(lambda: ends(p)), "its result was never recorded after the restart"
        ended_once(p, run)
        assert [x["run"] for x in got(tmp_path) if x["op"] == "item"] == [run], "answered, yet sent again"
    finally:
        e.daemons.close()


@pytest.mark.slow
def test_a_message_not_answered_is_sent_again_with_its_id_and_none_is_lost(tmp_path, daemons):
    """Done 2: the item it held unanswered at the kill is sent again by the next engine, with the same run id, to the
    same process (which drops the repeat); its answer after that is recorded once."""
    p = project(tmp_path)
    daemons(p)
    run = killed_mid_item(p, tmp_path)
    pid = state(p)["pid"]
    e = taken_up(p)
    try:
        items = lambda: [x for x in got(tmp_path) if x["op"] == "item"]   # noqa: E731
        assert wait_for(lambda: len(items()) == 2), f"not sent again: {items()}"
        assert {x["run"] for x in items()} == {run}, "sent again under another id"
        assert len({x["pid"] for x in items()}) == 1 and state(p)["pid"] == pid, "not the same daemon taken up"
        (tmp_path / "go").write_text("")
        assert wait_for(lambda: ends(p)), "its answer after the restart was never recorded"
        ended_once(p, run)
    finally:
        e.daemons.close()


@pytest.mark.slow
def test_a_daemon_that_died_while_no_engine_was_up_is_restarted_and_given_what_it_held(tmp_path, daemons):
    """Done 3: it exits while no engine is up; the next engine restarts it (``ergostat.daemon.restarted``) and hands
    the new process the run it had not answered, whose end is then recorded once."""
    p = project(tmp_path)
    daemons(p)
    run = killed_mid_item(p, tmp_path)
    old = state(p)
    (tmp_path / "go.die").write_text("")
    assert wait_for(lambda: keeper.ended(str(kept.files(kept.folder(p.dir, "block.worker"), old["proc"])["keeper"]))
                    is not None), "it never died"
    (tmp_path / "go.die").unlink()
    e = taken_up(p)
    try:
        again = p.events.query(n=None, type="ergostat.daemon.restarted", item="block.worker")
        assert len(again) == 1 and "ended while no engine was up" in again[0]["data"]["why"], again
        assert state(p)["proc"] != old["proc"] and state(p)["pid"] != old["pid"]
        items = lambda: [x for x in got(tmp_path) if x["op"] == "item"]   # noqa: E731
        assert wait_for(lambda: len(items()) == 2) and items()[1]["run"] == run and items()[1]["pid"] != items()[0]["pid"]
        (tmp_path / "go").write_text("")
        assert wait_for(lambda: ends(p)), "the run it held was never ended by the restarted daemon"
        ended_once(p, run, noted=2)                  # (the new process did the item again: at least once)
        assert not (kept.folder(p.dir, "block.worker") / f"{old['proc']}.out").exists(), "the dead one's files stay"
    finally:
        e.daemons.close()


@pytest.mark.slow
def test_a_clean_stop_leaves_a_kept_daemon_going_with_its_run_and_lease(tmp_path, daemons):
    """``ergostat run`` stopped with SIGTERM: a kept daemon is not sent ``stop`` nor killed; its run's end is not that
    engine's and its lease stays held for the next, which records it."""
    p = project(tmp_path)
    daemons(p)
    proc = engine(tmp_path)
    try:
        assert wait_for(lambda: p.events.query(n=1, type="ticket.noted"), 60), "the item never reached the daemon"
        run = p.events.query(n=1, type="ticket.noted")[0]["causedby"]
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(30) is not None
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    assert p.events.query(n=1, type="ergostat.stopped"), "the engine did not stop cleanly"
    st = state(p)
    assert adopt.alive({"pid": st["pid"], "start": st["start"]}) is not False, "stopped with the engine"
    assert "stop" not in [x["op"] for x in got(tmp_path)], "sent stop"
    assert not ends(p) and its.one(p.events, p.model.spec, "ticket/1").fields["lease"]["holder"] == run
    (tmp_path / "go").write_text("")
    e = taken_up(p)
    try:
        assert wait_for(lambda: ends(p))
        ended_once(p, run)
    finally:
        e.daemons.close()


def test_a_daemon_declared_to_stop_with_the_engine_keeps_that(tmp_path):
    """``runs: outlive_engine`` makes a daemon kept unless it says ``outlive-engine: false``; a warm one never is
    (and saying it is, is an error); none of it, as before: stopped with the engine."""
    base = MODEL.replace("    daemon: {run: RUN, outlive-engine: true}\n", "    daemon: DAEMON\n")
    for runs, daemon, want in (("", "{run: x}", False), ("runs: {outlive_engine: true}\n", "{run: x}", True),
                               ("runs: {outlive_engine: true}\n", "{run: x, outlive-engine: false}", False),
                               ("runs: {outlive_engine: true}\n", "{run: x, warm: true}", False),
                               ("", "{run: x, outlive-engine: true}", True)):
        (tmp_path / "ergostat.yaml").write_text(runs + base.replace("DAEMON", daemon))
        spec, problems = read(tmp_path / "ergostat.yaml")
        assert not [x for x in problems if x.level == "error"], problems
        assert spec.daemons["block.worker"].outlive is want, (runs, daemon)
    for daemon in ("{run: x, warm: true, outlive-engine: true}", "{run: x, outlive-engine: 1}"):
        (tmp_path / "ergostat.yaml").write_text(base.replace("DAEMON", daemon))
        _, problems = read(tmp_path / "ergostat.yaml")
        assert any("outlive-engine: true or false" in x.message for x in problems if x.level == "error"), daemon


def test_a_daemon_stopped_with_the_engine_is_stopped(tmp_path):
    """Done 4's side: one not kept is sent ``stop`` and ended as the engine closes, as before."""
    p = project(tmp_path, MODEL.replace(", outlive-engine: true", ""))
    e = Engine(p, say=lambda s: None)
    e.daemons.sync(e.spec)
    pid = wait_for(lambda: e.daemons.status().get("block.worker", {}).get("pid"))
    e.daemons.close()
    assert wait_for(lambda: adopt.alive({"pid": pid}, start=False) is False, 10), "a daemon not kept outlived its engine"
    assert not (p.dir.resolve() / "daemons").exists()
