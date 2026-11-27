"""A daemon kept by a keeper goes on through an engine restart and picks its messages back up (SPEC §9.7, *A daemon
that outlives its engine*): the engine SIGKILLed with the daemon mid-item, the item's result is recorded by the next
engine; a message not answered is sent again with its id, none lost; a daemon that died while no engine was up is
restarted by the next; one declared to stop with the engine does."""

import contextlib
import json
import os
import shlex
import signal
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.compute.worker import keeper
from ergostat.daemons import kept
from ergostat.leases import ENDED, EXPIRED, RENEWED
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
projections:
  ticket:
    match:
      key: ticket/*
    states: [ready, done]
    events:
      ticket.done:
        state: set('done')
    otherwise: rest
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready}
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
                with contextlib.suppress(FileNotFoundError):      # (let go already: its folder gone)
                    keeper.put(str(d / "done"), "")


def state(p) -> dict | None:
    """The newest process's state the daemon's folder holds."""
    return next(iter(kept.states(kept.folder(p.dir, "block.worker"), "block.worker")), None)


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
    st = state(p)                                    # (as if killed between a line's events and its offset saved:
    f = kept.files(kept.folder(p.dir, "block.worker"), st["proc"])["state"]     # read again, adding none)
    f.write_text(json.dumps({**st, "offset": 0}))
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
        lease = its.one(p.events, p.model.spec, "ticket/1").fields["lease"]
        assert lease["holder"] == run and p.events.query(n=1, type=RENEWED)[-1]["data"]["seen"] == "taken up"
        e.dispatch.watch(now=lease["expires"] + 3600)    # (past its expiry: its daemon still holds it)
        assert not p.events.query(n=None, type=EXPIRED), "the watchdog expired a lease its daemon holds"
        assert p.events.query(n=1, type=RENEWED)[-1]["data"]["seen"] == "keeper"
        (tmp_path / "go").write_text("")
        assert wait_for(lambda: ends(p)), "its answer after the restart was never recorded"
        ended_once(p, run)
    finally:
        e.daemons.close()


def answered_in_the_window(p, tmp_path, monkeypatch, window) -> None:
    """The second engine takes the run up and sends it again; the daemon answers; ``window(run)`` (patched in) puts that
    engine's end between reading the answer (its offset saved past it) and recording the run's end. A third engine
    must record it once, from the journal, without sending it a third time (the daemon drops a repeat)."""
    run = killed_mid_item(p, tmp_path)
    items = lambda: [x for x in got(tmp_path) if x["op"] == "item"]   # noqa: E731
    seen = window(run)
    e = taken_up(p)
    try:
        assert wait_for(lambda: len(items()) == 2), f"not sent again: {items()}"
        (tmp_path / "go").write_text("")
        assert seen.wait(30), "its answer never read"
        out = kept.files(kept.folder(p.dir, "block.worker"), state(p)["proc"])["out"]
        assert wait_for(lambda: state(p)["offset"] == out.stat().st_size), "its offset never saved past the answer"
    finally:
        e.daemons.close()
    assert not ends(p) and run in state(p)["held"], "the window not opened: its end recorded, or it not held"
    monkeypatch.undo()
    e = taken_up(p)
    try:
        assert wait_for(lambda: ends(p)), "its answer, read before the engine ended, is lost"
        ended_once(p, run)
        assert len(items()) == 2, "answered, yet sent again"
    finally:
        e.daemons.close()


@pytest.mark.slow
def test_an_answer_read_by_an_engine_killed_before_it_recorded_the_end_is_recorded_by_the_next(tmp_path, daemons,
                                                                                                 monkeypatch):
    """The engine killed after its journal's offset was saved past a run's ``done`` and before the run's end was
    recorded (``_through`` never gets to it): the next engine reads the journal again from where it was when the run
    was handed over, and records the end."""
    p = project(tmp_path)
    daemons(p)

    def window(run):
        seen = threading.Event()

        def killed_before_the_end(sup, b, begun, h, *a):
            h.done.wait()                            # (the answer read, its offset saved; then nothing: killed)
            seen.set()
        monkeypatch.setattr(kept, "_through", killed_before_the_end)
        return seen
    answered_in_the_window(p, tmp_path, monkeypatch, window)


@pytest.mark.slow
def test_an_answer_read_as_the_engine_stops_is_recorded_by_the_next(tmp_path, daemons, monkeypatch):
    """A clean stop's ``leave`` while the reader is taking the run's ``done``: the line is dropped as of no run held,
    its offset saved past it; the next engine reads it again and records the end."""
    p = project(tmp_path)
    daemons(p)
    chunk = kept.KeptProcess.chunk

    def window(run):
        seen = threading.Event()

        def stopping_meanwhile(self, data, eof=False):
            if f'"done": 0, "run": "{run}"'.encode() in data and not seen.is_set():
                self.leave()
                seen.set()
            return chunk(self, data, eof)
        monkeypatch.setattr(kept.KeptProcess, "chunk", stopping_meanwhile)
        return seen
    answered_in_the_window(p, tmp_path, monkeypatch, window)


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


@pytest.mark.slow
def test_a_daemon_whose_command_changed_while_no_engine_was_up_is_drained_and_a_new_one_started(tmp_path, daemons):
    """The model changed during the outage: the old process is taken up only to finish what it holds (sent ``stop``),
    and the new command takes the new work; the old one's run is still recorded once."""
    p = project(tmp_path)
    daemons(p)
    run = killed_mid_item(p, tmp_path)
    old = state(p)
    text = (tmp_path / "ergostat.yaml").read_text()
    (tmp_path / "ergostat.yaml").write_text(text.replace("daemon.py", "./daemon.py"))
    p = Project(mdl.load(tmp_path))
    first = got(tmp_path)[0]["pid"]                  # (the daemon's own: its relay's is old["pid"])
    e = taken_up(p)
    try:
        assert wait_for(lambda: "stop" in [x["op"] for x in got(tmp_path) if x["pid"] == first]), "not drained"
        assert state(p)["proc"] != old["proc"] and "./daemon.py" in state(p)["run"], "no new process of the new command"
        (tmp_path / "go").write_text("")
        assert wait_for(lambda: ends(p)), "the old process's run was never recorded"
        ended_once(p, run)
        assert wait_for(lambda: adopt.alive({"pid": old["pid"]}, start=False) is False, 15), "the old one goes on"
    finally:
        e.daemons.close()


@pytest.mark.slow
def test_stop_runs_stops_a_daemon_left_going(tmp_path, daemons):
    """``ergostat run --stop --runs`` with no engine up: a kept daemon's keeper stops its whole group."""
    p = project(tmp_path)
    daemons(p)
    killed_mid_item(p, tmp_path)
    st = state(p)
    out = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "run", "--stop", "--runs"],
                         capture_output=True, text=True, timeout=60)
    assert "stopped 1 of 1 runs left going" in out.stdout, out
    assert wait_for(lambda: adopt.alive({"pid": st["pid"]}, start=False) is False, 10), "the daemon goes on"


@pytest.mark.slow
def test_a_daemon_no_longer_kept_is_taken_up_drained_and_its_run_recorded(tmp_path, daemons):
    """``outlive-engine: false`` written while no engine was up: no kept slot claims its process, yet the next engine
    takes up its run (its lease kept, never leased again meanwhile), drains it once it is done, and records the run
    once; the daemon of the model, not kept now, is started beside it."""
    p = project(tmp_path)
    daemons(p)
    run = killed_mid_item(p, tmp_path)
    old = state(p)
    first = got(tmp_path)[0]["pid"]
    text = (tmp_path / "ergostat.yaml").read_text()
    (tmp_path / "ergostat.yaml").write_text(text.replace("outlive-engine: true", "outlive-engine: false"))
    p = Project(mdl.load(tmp_path))
    e = taken_up(p)
    try:
        assert wait_for(lambda: "stop" in [x["op"] for x in got(tmp_path) if x["pid"] == first]), "not drained"
        lease = its.one(p.events, p.model.spec, "ticket/1").fields["lease"]
        assert lease["holder"] == run, "its run not taken up: its item leased again while it still works on it"
        assert e.daemons.status()["block.worker"]["pid"] not in (None, old["pid"]), "the model's daemon not started"
        (tmp_path / "go").write_text("")
        assert wait_for(lambda: ends(p)), "the run of the process no longer kept was never recorded"
        ended_once(p, run)
        assert wait_for(lambda: adopt.alive({"pid": old["pid"]}, start=False) is False, 15), "the old one goes on"
        assert wait_for(lambda: not list(kept.folder(p.dir, "block.worker").glob("*.json")), 10), "its state stays"
    finally:
        e.daemons.close()


@pytest.mark.slow
def test_a_daemon_removed_from_the_model_is_stopped(tmp_path, daemons, monkeypatch):
    """The daemon gone from the model (its block renamed) while no engine was up: its process, of no daemon now and
    holding nothing taken up, is stopped by the next engine, its files removed."""
    from ergostat.leases import kill
    monkeypatch.setattr(kill, "GRACE", 1.0)
    p = project(tmp_path)
    daemons(p)
    killed_mid_item(p, tmp_path)
    old = state(p)
    text = (tmp_path / "ergostat.yaml").read_text()
    (tmp_path / "ergostat.yaml").write_text(text.replace("  worker:", "  doer:").replace(", outlive-engine: true", ""))
    p = Project(mdl.load(tmp_path))
    e = taken_up(p)
    try:
        assert wait_for(lambda: adopt.alive({"pid": old["pid"]}, start=False) is False, 20), "the orphan goes on"
        base = kept.folder(p.dir, "block.worker")
        assert wait_for(lambda: not any(base.glob("*.*")), 10), "its files stay"
    finally:
        e.daemons.close()


@pytest.mark.slow
def test_a_run_whose_daemon_cannot_be_started_again_is_given_back(tmp_path, daemons, monkeypatch):
    """The process found ended, and its new one fails to launch: the run it held is not left held by none (leased
    for the engine's life, then lost): it is ended as failed and its item given back, uncounted."""
    p = project(tmp_path)
    daemons(p)
    run = killed_mid_item(p, tmp_path)
    old = state(p)
    (tmp_path / "go.die").write_text("")
    assert wait_for(lambda: keeper.ended(str(kept.files(kept.folder(p.dir, "block.worker"), old["proc"])["keeper"]))
                    is not None), "it never died"
    (tmp_path / "go.die").unlink()

    def refused(*a, **k):
        raise OSError("no keeper here")
    monkeypatch.setattr(keeper, "launch", refused)
    e = taken_up(p)
    try:
        assert wait_for(lambda: ends(p), 15), "the run its daemon held is held by none and never ended"
        end = ends(p)
        assert len(end) == 1 and end[0]["type"] == "agent.failed" and end[0]["causedby"] == run, end
        assert "could not be started again" in end[0]["data"]["note"]
        back = wait_for(lambda: p.events.query(n=None, type=ENDED, item="ticket/1"), 10)
        assert [x["data"]["how"] for x in back] == ["nack"] and back[0]["data"].get("count") is False, back
        assert state(p) is None, "a state of the dead one stays"
    finally:
        e.daemons.close()


@pytest.mark.slow
def test_a_daemon_taken_up_but_no_longer_wanted_finishes_what_it_holds(tmp_path, daemons, monkeypatch):
    """Its slot drained while it was being taken up (``_spawn``'s stale path): the process is drained, not killed with
    the run it took up in it, and that run's end is recorded once."""
    p = project(tmp_path)
    daemons(p)
    run = killed_mid_item(p, tmp_path)
    first = got(tmp_path)[0]["pid"]
    spawn = kept.spawn

    def drained_meanwhile(sup, slot, *a):
        got_ = spawn(sup, slot, *a)
        slot.state = "stopped"
        return got_
    monkeypatch.setattr(kept, "spawn", drained_meanwhile)
    e = taken_up(p)
    try:
        assert wait_for(lambda: "stop" in [x["op"] for x in got(tmp_path) if x["pid"] == first]), "not drained"
        (tmp_path / "go").write_text("")
        assert wait_for(lambda: ends(p)), "the run it took up was never recorded"
        ended_once(p, run)
    finally:
        e.daemons.close()


def test_a_run_taken_up_that_no_process_holds_is_ended(tmp_path):
    """``unheld``: its holder without it at two looks in a row ends it, given back; held, or moved to another holder
    between the looks, it is not."""
    from types import SimpleNamespace

    from ergostat.daemons.proc import Handle
    a = SimpleNamespace(lock=threading.Lock(), runs={}, d=SimpleNamespace(name="x"))
    b = SimpleNamespace(lock=threading.Lock(), runs={}, d=SimpleNamespace(name="x"))
    h = Handle()
    h.kept = a
    a.runs["r"] = h
    assert kept.unheld(h, "r", None) is None
    del a.runs["r"]
    missed = kept.unheld(h, "r", None)
    assert missed is a and not h.done.is_set(), "ended at the first look (a done ends it just after)"
    h.kept, b.runs["r"] = b, h                       # (moved meanwhile: held)
    assert kept.unheld(h, "r", missed) is None and not h.done.is_set()
    del b.runs["r"]
    assert kept.unheld(h, "r", kept.unheld(h, "r", None)) is b and h.done.is_set()
    assert h.requeue and "no longer holds it" in h.note


def test_a_run_is_in_its_daemon_s_state_before_its_line_is_sent(tmp_path):
    """An engine killed just after it sent a run's line leaves the run in the state the next engine reads: written
    before the line, never after (else a run the daemon holds is one no engine knows of)."""
    from ergostat.daemons.proc import Handle
    from ergostat.spec.ir import Daemon
    base = tmp_path / "d"
    with open(tmp_path / "log", "a") as log:
        p = kept.KeptProcess(Daemon("x", "cat > /dev/null", outlive=True), base, tmp_path, dict(os.environ), log,
                             lambda *a: False, lambda *a: False)
        try:
            seen, send = [], p.send
            p.send = lambda obj: (seen.append(obj["run"] in kept.read_state(p.f["state"], "x")["held"]), send(obj))[1]
            assert p.hold("r1", Handle(), {"op": "item", "run": "r1"})
            assert seen == [True], "its line sent before the run was in its state"
            assert p.acked("r1") and kept.read_state(p.f["state"], "x")["held"] == {}, "its end recorded, still held"
        finally:
            keeper.stop_all(str(base), 0)
            wait_for(lambda: p.proc.poll() is not None, 10)
            p.finish()
    assert wait_for(lambda: not any(base.glob("*.*")) and not any((base / "runs").glob("*")), 10), "its files stay"


def test_a_journal_read_again_gives_only_a_held_run_its_lines_again(tmp_path):
    """Taken up from where its earliest held run was handed over: below the saved offset, only a run still held is
    given its lines again (a push, an observation or another run's line was taken by the engine before); past it,
    every line is; the offset saved is never below the one read before."""
    from types import SimpleNamespace
    out = tmp_path / "a.out"
    before = [{"sensor": "s", "reading": 1}, {"event": "e", "run": "gone"}, {"event": "e", "run": "r"},
              {"done": 0, "run": "r"}]
    text = "".join(json.dumps(x) + "\n" for x in before)
    out.write_text(text + json.dumps({"sensor": "s", "reading": 2}) + "\n")
    given, saved = [], []
    x = SimpleNamespace(f={"out": out}, offset=len(text), replay=len(text), skipping=False, lock=threading.Lock(),
                        runs={"r": object()}, lines={"r": {}}, at={"r": 0}, procid="p",
                        chunk=lambda raw: given.append(json.loads(raw)), _save=lambda: saved.append(x.offset))
    x.held_line = lambda raw: kept.KeptProcess.held_line(x, raw)
    kept.KeptProcess.take_from_held(x)
    assert x.offset == 0
    assert kept.KeptProcess.take(x)
    assert given == [before[2], before[3], {"sensor": "s", "reading": 2}], given
    assert saved == [out.stat().st_size]


def test_an_inbox_its_relay_has_not_delivered_counts_as_input_not_read(tmp_path):
    """What the supervisor holds against ``stdin-timeout``: since when its relay is behind its inbox; caught up, none."""
    from types import SimpleNamespace
    x = SimpleNamespace(f={"in": tmp_path / "a.in", "pos": tmp_path / "a.pos"}, writing_since=None)
    x.f["in"].write_text('{"op": "item"}\n')
    kept.KeptProcess.behind(x)
    first = x.writing_since
    assert first is not None, "an undelivered line not seen"
    kept.KeptProcess.behind(x)
    assert x.writing_since == first, "since when, kept while it stays behind"
    x.f["pos"].write_text(str(x.f["in"].stat().st_size))
    kept.KeptProcess.behind(x)
    assert x.writing_since is None


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
