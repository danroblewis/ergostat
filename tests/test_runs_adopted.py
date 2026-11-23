"""A starting engine takes up the runs an engine before it left going (SPEC §9.1, *Runs taken up again*): each journal
line is in the record once, however the engines before stopped (a clean stop, a SIGKILL, a crash part way through
taking a run up), the run's lease is kept with its fence while it lives, and a run that ended while no engine was up
is ended from its journal and its keeper's exit, at the time it really ended."""

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
from ergostat.costs import record as costs_record
from ergostat.leases import ENDED, EXPIRED, RENEWED, TAKEN
from ergostat.leases import dispatch as dispatch_mod
from ergostat.spec import adopt, runrecord
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = shlex.quote(sys.executable)

MODEL = """
name: a
runs:
  outlive_engine: true
items:
  ticket:
    id: ticket/*
    states: [ready, done]
    on: {ticket.done: done}
stocks:
  handled:
    unit: tickets
flows:
  did:
    to: handled
blocks:
  worker:
    type: program
    run: RUN
    takes: {kind: ticket, at: ready}
    out: flow.did
"""

# Three lines, each after its go file (``go1``, ``go2``), the last moving the item on; a line that is not JSON too.
WORK = """
import json, os, sys, time
sys.stdin.read()
def say(x):
    sys.stdout.write(json.dumps(x) + "\\n")
    sys.stdout.flush()
def until(name):
    end = time.time() + 90
    while not os.path.exists(name) and time.time() < end:
        time.sleep(0.05)
say({"event": "ticket.noted", "data": {"n": 1}})
until(sys.argv[1] + "1")
say({"event": "ticket.noted", "data": {"n": 2}})
print("plain words", flush=True)
say({"out": "flow.did", "moved": 1})
say({"event": "Not A Type", "item": "elsewhere"})
until(sys.argv[1] + "2")
say({"event": "ticket.noted", "data": {"n": 3}})
say({"event": "ticket.done"})
"""


@pytest.fixture(autouse=True)
def _stopping_cleared():
    yield
    runner.STOPPING.clear()


def wait_for(cond, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


def project(tmp_path) -> Project:
    (tmp_path / "work.py").write_text(textwrap.dedent(WORK))
    run = json.dumps(f"{PY} work.py {shlex.quote(str(tmp_path / 'go'))}")
    (tmp_path / "ergostat.yaml").write_text(MODEL.replace("RUN", run))
    p = Project(mdl.load(tmp_path))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    return p


def go(tmp_path, *which) -> None:
    for n in which:
        (tmp_path / f"go{n}").write_text("")


def runs_dir(p):
    return p.dir.resolve() / "runs"


def names(p) -> list[str]:
    d = runs_dir(p)
    return sorted(n for n in os.listdir(d) if keeper.RUN.fullmatch(n)) if d.is_dir() else []


@pytest.fixture
def keepers():
    """Every keeper a test left, stopped and let go at its end: no run or keeper outlives the test."""
    made: list = []
    yield made.append
    for p in made:
        keeper.stop_all(str(p.dir.resolve()), 0)
        for n in names(p):
            x = str(runs_dir(p) / n)
            wait_for(lambda x=x: keeper.ended(x) is not None, 10)
            keeper.put(os.path.join(x, "done"), "")
        wait_for(lambda p=p: not names(p), 10)


def noted(p) -> list[int]:
    return sorted(e["data"]["n"] for e in p.events.query(n=None, type="ticket.noted"))


def ends(p) -> list[dict]:
    return p.events.query(n=None, type="agent.ran,agent.failed", item="worker")


def item(p):
    return its.one(p.events, p.model.spec, "ticket/1")


def lease_ends(p) -> list[dict]:
    return p.events.query(n=None, type=ENDED, item="ticket/1")


def engine(tmp_path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "run", "--foreground", "--no-web"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def killed(proc) -> None:
    os.killpg(proc.pid, signal.SIGKILL)                  # (its own session: the whole group is the engine's)
    proc.wait()


def left_by_a_stop(p, tmp_path) -> tuple[Engine, str]:
    """An engine in this process takes the ticket and starts its run, records its first line, and stops (a clean
    stop): the run goes on, its lease held."""
    e = Engine(p, say=lambda s: None)
    t = threading.Thread(target=e.run_block, args=(e.spec.blocks["worker"], "test"), daemon=True)
    t.start()
    assert wait_for(lambda: noted(p) == [1]), "the run's first line never reached the record"
    run = p.events.query(n=1, type="ticket.noted")[0]["causedby"]
    e.close()
    t.join(20)
    runner.STOPPING.clear()
    assert not t.is_alive() and not ends(p), "the run's end is not that engine's"
    assert item(p).fields["lease"]["holder"] == run, "its lease is not given back as the engine stops"
    return e, run


def take_up(p) -> tuple[Engine, list]:
    e = Engine(p, say=lambda s: None)
    return e, adopt.scan(e)


def joined(threads, seconds=30.0) -> None:
    for t in threads:
        t.join(seconds)
        assert not t.is_alive(), "the run taken up was never ended"


def ended_once(p, run: str) -> dict:
    """Each line once, one end, the item moved on and its lease acked with no attempt counted, its files gone."""
    assert noted(p) == [1, 2, 3], "every line in the record exactly once"
    assert len(p.events.query(n=None, type="ticket.done")) == 1
    assert len(p.events.query(n=None, type="valve.opened")) == 1, "its valve opening once"
    assert len(p.events.query(n=None, type="agent.refused")) == 1, "its refused line once"
    got = ends(p)
    assert len(got) == 1 and got[0]["type"] == "agent.ran" and got[0]["causedby"] == run, got
    assert got[0]["data"]["exit"] == 0 and "note" not in got[0]["data"] and got[0]["data"]["events"] == 4
    assert got[0]["data"]["moved"] == {"did": 1} and got[0]["data"]["openings"] == 1 and got[0]["data"]["refused"] == 1
    it = item(p)
    assert it.state == "done" and it.fields["lease"]["holder"] is None and it.fields["lease"]["attempts"] == 0
    assert [x["data"]["how"] for x in lease_ends(p)] == ["ack"], "its lease ended once, an ack"
    assert wait_for(lambda: not any(runs_dir(p).glob(f"{run}.*")), 5), "its files stay after its end"
    assert wait_for(lambda: not names(p), 5), "its keeper was never let go"
    return got[0]


@pytest.mark.slow
def test_a_killed_engine_s_run_is_taken_up_and_ends_normally_each_line_once(tmp_path, keepers):
    """Done 1: the engine SIGKILLed mid-run; the next takes the run up from its saved offset, keeps its lease (renewed
    as it is taken up, and by the watchdog while its keeper says it lives), and ends it normally."""
    p = project(tmp_path)
    keepers(p)
    proc = engine(tmp_path)
    try:
        assert wait_for(lambda: noted(p) == [1], 60), "the run's first line never reached the record"
    finally:
        killed(proc)
    run = p.events.query(n=1, type="ticket.noted")[0]["causedby"]
    t0 = time.time()
    e, threads = take_up(p)
    assert len(threads) == 1 and isinstance(e.live.get(run), adopt.Adopted), "taken up, and stoppable from here"
    lease = item(p).fields["lease"]
    assert lease["holder"] == run and lease["renewed"] >= t0, "kept, the time no engine was up not held against it"
    e.dispatch.watch(now=lease["expires"] + 3600)        # (past its expiry: its keeper says it lives)
    assert not p.events.query(n=None, type=EXPIRED), "the watchdog expired a lease its keeper says is alive"
    assert p.events.query(n=1, type=RENEWED)[-1]["data"]["seen"] == "keeper"
    go(tmp_path, 1, 2)
    joined(threads)
    ended_once(p, run)


@pytest.mark.slow
def test_a_run_that_ended_while_no_engine_was_up_is_ended_at_the_time_it_ended(tmp_path, keepers):
    """Done 2: it finishes during the outage; the next start ends it, at its keeper's time, its costs at that time."""
    p = project(tmp_path)
    keepers(p)
    proc = engine(tmp_path)
    try:
        assert wait_for(lambda: noted(p) == [1], 60)
    finally:
        killed(proc)
    run = p.events.query(n=1, type="ticket.noted")[0]["causedby"]
    go(tmp_path, 1, 2)
    d = str(runs_dir(p) / run)
    assert wait_for(lambda: keeper.ended(d) is not None), "the run never ended"
    at = os.stat(os.path.join(d, "exit")).st_mtime
    time.sleep(1.5)                                      # (the outage goes on after it ended)
    t0 = time.time()
    e, threads = take_up(p)
    assert run not in e.live, "an ended run is not stoppable from here"
    joined(threads)
    end = ended_once(p, run)
    assert end["time"] == at < t0 - 1, "its end is when it ended, not when it was found"
    begun = p.events.get(run)
    assert end["data"]["taken_up"] is True and end["data"]["seconds"] == round(at - begun["time"], 3)
    got = p.measurements.range("run/worker/seconds", at - 0.001, at + 0.001)
    assert len(got) == 1 and got[0][0] == at, "its metrics at the time it ended, once"


STEPS = {"save": (adopt, "save"), "costs": (costs_record, "write_series"),
         "lease": (dispatch_mod.Dispatcher, "finish"), "files": (adopt, "let_go")}


@pytest.mark.parametrize("step", sorted(STEPS))
def test_an_engine_killed_while_taking_a_run_up_leaves_each_line_once(tmp_path, keepers, monkeypatch, step):
    """Done 3: the engine taking a run up dies at each step (a crash: its thread raises there, and nothing after it
    runs): after its lines' events and before their offset; after the run's end and before its costs; before its
    lease's end; before its files go. The next engine takes it up again: each line, the end, its costs and its
    lease's end are each recorded once."""
    p = project(tmp_path)
    keepers(p)
    _, run = left_by_a_stop(p, tmp_path)
    go(tmp_path, 1, 2)
    assert wait_for(lambda: keeper.ended(str(runs_dir(p) / run)) is not None)
    owner, name = STEPS[step]
    real = getattr(owner, name)

    def crash(*a, **k):
        raise RuntimeError(f"killed at {step}")
    monkeypatch.setattr(owner, name, crash)
    e, threads = take_up(p)
    joined(threads)
    monkeypatch.setattr(owner, name, real)
    assert any(runs_dir(p).glob(f"{run}.jsonl")), "its journal went with the crash"
    e, threads = take_up(p)
    assert len(threads) == 1
    joined(threads)
    end = ended_once(p, run)
    assert len(p.measurements.range("run/worker/seconds", end["time"] - 0.001, end["time"] + 0.001)) == 1


def test_a_pid_reused_by_another_process_is_not_taken_for_the_run(tmp_path, keepers):
    """Done 4: the run and its keeper killed while no engine was up (no exit written), and its pid now another
    process's: that process is neither waited on, nor stoppable through the run, nor signalled; the run ends killed."""
    p = project(tmp_path)
    keepers(p)
    e1 = Engine(p, say=lambda s: None)
    t = threading.Thread(target=e1.run_block, args=(e1.spec.blocks["worker"], "test"), daemon=True)
    t.start()
    assert wait_for(lambda: noted(p) == [1])
    run = p.events.query(n=1, type="ticket.noted")[0]["causedby"]
    kept = e1.live[run]
    e1.close()
    t.join(20)
    runner.STOPPING.clear()
    os.kill(kept.keeper.pid, signal.SIGKILL)
    os.killpg(kept.pid, signal.SIGKILL)
    kept.keeper.wait()
    assert wait_for(lambda: runrecord.start_time(kept.pid) is None, 10)
    other = subprocess.Popen(["sleep", "60"])
    try:
        rec = runs_dir(p) / f"{run}.json"
        was = json.loads(rec.read_text())
        assert runrecord.start_time(other.pid) != was["start"]
        rec.write_text(json.dumps({**was, "pid": other.pid}))        # (its pid, as if the system gave it again)
        assert adopt.alive({**was, "pid": other.pid}) is False
        assert adopt.alive({**was, "pid": other.pid, "start": runrecord.start_time(other.pid)}) is True
        e, threads = take_up(p)
        assert run not in e.live and "worker" not in e.procs, "another process taken for the run"
        joined(threads)
        assert other.poll() is None, "another process was signalled as the run"
    finally:
        other.kill()
        other.wait()
    got = ends(p)
    assert len(got) == 1 and got[0]["type"] == "agent.failed" and got[0]["data"]["exit"] == -9, got
    assert noted(p) == [1] and [x["data"]["how"] for x in lease_ends(p)] == ["nack"]


def test_a_run_whose_lease_was_taken_over_cannot_move_the_item(tmp_path, keepers):
    """Done 5: while no engine was up its lease ended and the item was leased again (a newer fence): taken up, the
    run's lines about it are refused (fencing), its lease is not renewed nor ended by it, and the item stays."""
    p = project(tmp_path)
    keepers(p)
    _, run = left_by_a_stop(p, tmp_path)
    p.events.add(EXPIRED, item="ticket/1", source="ergostat", data={"run": run, "fence": 1, "count": False})
    p.events.add(TAKEN, item="ticket/1", source="ergostat",
                 data={"item": "ticket/1", "run": "other", "block": "worker", "fence": 2, "ttl": 3600, "max": 3,
                       "back": "ready"})
    e, threads = take_up(p)
    go(tmp_path, 1, 2)
    joined(threads)
    it = item(p)
    assert it.state == "leased" and it.fields["lease"]["holder"] == "other" and it.fields["lease"]["fence"] == 2
    refused = p.events.query(n=None, type="agent.refused", item="worker")
    assert len(refused) == 4 and sum("fencing" in x["data"]["why"] for x in refused) == 3, refused
    assert not [x for x in p.events.query(n=None, type=RENEWED) if x["data"]["run"] == run]
    assert not lease_ends(p) and len(ends(p)) == 1


def test_a_run_taken_up_is_stopped_by_its_block_s_stop(tmp_path, keepers):
    """``ergostat block NAME --stop`` reaches a run taken up (it is the engine's own now): its whole group stopped,
    recorded as the owner's stop, its lease given back uncounted."""
    p = project(tmp_path)
    keepers(p)
    _, run = left_by_a_stop(p, tmp_path)
    e, threads = take_up(p)
    pid = e.live[run].pid
    assert e.stop_run("worker")
    joined(threads)
    assert wait_for(lambda: runrecord.start_time(pid) is None, 5), "the run outlived its stop"
    got = ends(p)
    assert len(got) == 1 and got[0]["type"] == "agent.ran" and got[0]["data"]["note"] == "stopped as the owner asked"
    assert [(x["data"]["how"], x["data"].get("count")) for x in lease_ends(p)] == [("nack", False)]


def test_a_run_with_no_record_is_not_taken_for_gone(tmp_path, keepers):
    """Its record never written (the engine died between its keeper's start and it): known by its keeper's group id
    alone, with no start time to tell it from another process, it is waited for, never signalled, and ends as it did."""
    p = project(tmp_path)
    keepers(p)
    _, run = left_by_a_stop(p, tmp_path)
    (runs_dir(p) / f"{run}.json").unlink()
    e, threads = take_up(p)
    assert run not in e.live
    time.sleep(adopt.WAIT + 0.5)
    assert threads[0].is_alive() and not ends(p), "a run still going read as gone"
    e.dispatch.watch(now=item(p).fields["lease"]["expires"] + 3600)
    assert not p.events.query(n=None, type=EXPIRED), "its lease expired while it went on"
    go(tmp_path, 1, 2)
    joined(threads)
    ended_once(p, run)


def test_a_lease_its_keeper_holds_is_never_given_back_as_the_engine_stops(tmp_path, monkeypatch):
    """However late the run's own thread is to say it was left going, ``give_back`` passes a run its keeper holds."""
    p = project(tmp_path)
    e = Engine(p, say=lambda s: None)
    b, given = e.spec.blocks["worker"], []
    monkeypatch.setattr(e.dispatch, "finish", lambda *a, **k: given.append(a[3]))
    e.dispatch.mine.update({"kept": (b, "ticket/1", 1), "plain": (b, "ticket/2", 1)})
    e.dispatch.keeping.add("kept")
    e.dispatch.give_back()
    assert given == ["plain"]


@pytest.mark.parametrize("backend", ["sqlite", "segments"])
def test_a_journal_line_s_events_are_kept_once_in_either_record(tmp_path, backend):
    """The ids a line's events are given (``store.line_id``): the same for the same line read again, so either kind
    of record keeps one; outside a line, a fresh id each time."""
    from ergostat import segments, store
    ev = store.Events(tmp_path) if backend == "sqlite" else segments.Segments(tmp_path)
    for _ in range(2):
        token = store.LINE.set(["run:120", 0])
        try:
            ev.add("thing.said", source="w")
            ev.add("thing.also", source="w")
        finally:
            store.LINE.reset(token)
    ev.add("thing.said", source="w")
    assert sorted(e["type"] for e in ev.query(n=None)) == ["thing.also", "thing.said", "thing.said"]


@pytest.mark.slow
def test_two_restarts_during_one_run_lose_nothing(tmp_path, keepers):
    """Done 6: SIGKILLed, a second engine takes the run up and takes a line, SIGKILLed too; a third ends it."""
    p = project(tmp_path)
    keepers(p)
    proc = engine(tmp_path)
    try:
        assert wait_for(lambda: noted(p) == [1], 60)
    finally:
        killed(proc)
    run = p.events.query(n=1, type="ticket.noted")[0]["causedby"]
    proc = engine(tmp_path)
    try:
        assert wait_for(lambda: [x for x in p.events.query(n=None, type=RENEWED) if x["data"].get("seen") == "taken up"],
                        60), "the second engine never took the run up"
        go(tmp_path, 1)
        assert wait_for(lambda: noted(p) == [1, 2], 30), "the second engine never took its next line"
    finally:
        killed(proc)
    go(tmp_path, 2)
    e, threads = take_up(p)
    joined(threads)
    ended_once(p, run)
