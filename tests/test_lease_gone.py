"""A lease whose run is gone is released (SPEC §9.5, *A run gone*; dev/records/safe-stalls-heal-themselves.md): a run
left behind by an engine that stopped, its process killed, has its lease given back uncounted within one watchdog
pass, and the queue takes its next item; a live run's lease is never released, a reused pid not taken for it."""

import json
import os
import signal
import subprocess

from ergostat.leases import ENDED, EXPIRED, TAKEN
from ergostat.spec import runrecord
from ergostat.spec.engine import Engine

from .test_leases import item, model, project, wait_for

DONE = 'echo "{\\"event\\": \\"ticket.done\\"}"'


def queue(tmp_path, n: int = 2):
    p = project(tmp_path, model(DONE, "{ttl: 10m, attempts: 1}").replace("pool: 2", "pool: 1"))
    for i in range(1, n + 1):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t")
    return p


def gone_engine() -> dict:
    """An engine that took a lease and is gone: in this process (its pid and start time), closed (no live id)."""
    return {"pid": os.getpid(), "start": runrecord.start_time(os.getpid()), "id": "a-closed-engine"}


def taken(p, it: str, run: str, block: str = "worker", engine: dict | None = None):
    p.events.add(TAKEN, item=it, source="ergostat", data={"run": run, "block": block, "fence": 1, "ttl": 600.0,
                                                         "max": 1, "back": "ready", "engine": engine or gone_engine()})


def left_behind(p, run: str, pid: int, start: str | None = "keep", block: str = "worker", it: str = "ticket/1"):
    """A lease on ``it`` held by ``run``, as an engine that stopped left it: its run record names ``pid``."""
    rec = runrecord.write(runrecord.files(p.dir, run), pid, run, block, it, 1)
    if start != "keep":
        runrecord.files(p.dir, run)["json"].write_text(json.dumps({**rec, "start": start}))
    taken(p, it, run, block)


def ended(p, it: str = "ticket/1") -> list[dict]:
    return p.events.query(n=None, type=ENDED, item=it)


def sleeper():
    return subprocess.Popen(["sleep", "60"], start_new_session=True)


def test_a_killed_runs_lease_is_released_in_one_pass_uncounted_and_the_next_is_taken(tmp_path):
    p = queue(tmp_path)
    proc = sleeper()
    e = Engine(p, say=lambda s: None)
    try:
        left_behind(p, "left", proc.pid)
        e.dispatch.watch()
        assert not ended(p) and item(p, "ticket/1").state == "leased", "alive: held"
        proc.kill()
        proc.wait()
        e.dispatch.watch()                                     # one pass
        (ev,) = ended(p)
        assert ev["data"]["how"] == "nack" and ev["data"]["count"] is False and "process is gone" in ev["data"]["why"]
        it = item(p, "ticket/1")
        assert it.state == "ready", f"a dead letter, one attempt allowed: counted ({it.state})"
        assert it.fields["lease"]["attempts"] == 0
        e.dispatch.tick()                                      # the queue takes its next item at once
        taken = [x for x in p.events.query(n=None, type=TAKEN) if x["data"]["run"] != "left"]
        assert taken, "nothing taken after the release"
        assert wait_for(lambda: item(p, "ticket/1").state == "done" or item(p, "ticket/2").state == "done", 10)
    finally:
        e.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_a_running_engine_releases_it_once_its_process_is_killed(tmp_path):
    p = queue(tmp_path, 1)
    proc = sleeper()
    left_behind(p, "left", proc.pid)
    from .test_leases import start
    e = start(p)
    try:
        assert not wait_for(lambda: ended(p), 2.5), "released while its process lives"
        proc.kill()
        proc.wait()
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 10), "released and taken again"
        hows = lambda: [h.get("how") for h in item(p, "ticket/1").fields["lease"]["history"]]  # noqa: E731
        assert wait_for(lambda: hows() == ["nack", "ack"], 5), hows()
        assert item(p, "ticket/1").fields["lease"]["history"][0]["counted"] is False
    finally:
        e.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_a_live_runs_lease_is_never_released_and_a_reused_pid_is_not_it(tmp_path):
    p = queue(tmp_path, 4)
    proc = sleeper()
    other = sleeper()                                          # the pid is now this process's: another start time
    e = Engine(p, say=lambda s: None)
    try:
        left_behind(p, "live", proc.pid, it="ticket/1")
        left_behind(p, "reused", other.pid, start="1", it="ticket/2")
        left_behind(p, "nostart", proc.pid, start=None, it="ticket/3")      # its start unread: unknown, never gone
        runrecord.files(p.dir, "unreadable")["json"].write_text("{not json")
        taken(p, "ticket/4", "unreadable")
        for _ in range(5):
            e.dispatch.watch()
        assert not ended(p, "ticket/1") and item(p, "ticket/1").state == "leased", "a live run's lease released"
        assert not ended(p, "ticket/3") and not ended(p, "ticket/4"), "unknown taken as gone"
        (ev,) = ended(p, "ticket/2")
        assert ev["data"]["count"] is False, "its pid another process's: the run is gone"
        assert other.poll() is None and proc.poll() is None, "nothing signalled"
    finally:
        e.close()
        for x in (proc, other):
            x.kill()
            x.wait()


def test_an_engines_own_live_run_is_never_released(tmp_path):
    from .test_leases import start
    p = project(tmp_path, model('sleep 3; ' + DONE, "{ttl: 10m, attempts: 1}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 15)
    finally:
        e.close()
    assert [h["how"] for h in item(p, "ticket/1").fields["lease"]["history"]] == ["ack"]


def test_at_start_a_lease_of_a_run_that_no_longer_exists_is_ended(tmp_path):
    """No run record: ended on the engine's first pass; one taken later by a run with no record is left to its TTL
    (another's start, never this engine's); a block this engine does not run (here, none of the model's) is left."""
    p = queue(tmp_path, 4)
    taken(p, "ticket/1", "vanished")
    runrecord.files(p.dir, "starting")["in"].write_text("")       # (begun, its record not written yet: left)
    taken(p, "ticket/4", "starting")
    taken(p, "ticket/3", "elsewhere", block="remote-block")
    other = Engine(p, say=lambda s: None)                          # another engine, live, between its take and RUN.in
    p.events.add("ticket.opened", item="ticket/5", source="t")
    taken(p, "ticket/5", "its-own", engine=other.dispatch.me)
    p.events.add("ticket.opened", item="ticket/6", source="t")
    proc = sleeper()                                               # another process's engine, live
    taken(p, "ticket/6", "theirs", engine={"pid": proc.pid, "start": runrecord.start_time(proc.pid), "id": "x"})
    p.events.add("ticket.opened", item="ticket/7", source="t")
    p.events.add(TAKEN, item="ticket/7", source="ergostat",        # no engine named (taken before owners were): left
                 data={"run": "old", "block": "worker", "fence": 1, "ttl": 600.0, "max": 1, "back": "ready"})
    e = Engine(p, say=lambda s: None)
    try:
        e.dispatch.watch()
        (ev,) = ended(p)
        assert ev["data"]["count"] is False and "no longer exists" in ev["data"]["why"]
        assert not ended(p, "ticket/4"), "a run begun before its record was written taken as gone"
        assert not ended(p, "ticket/5") and not ended(p, "ticket/6"), "a live engine's new run taken as gone"
        assert not ended(p, "ticket/7"), "a lease naming no engine taken as gone"
        taken(p, "ticket/2", "later")
        e.dispatch.watch()
        assert not ended(p, "ticket/2") and not ended(p, "ticket/3")
        assert not p.events.query(n=None, type=EXPIRED)
    finally:
        e.close()
        other.close()
        proc.kill()
        proc.wait()


def test_another_engines_run_ending_is_its_own_counted_end_and_nothing_is_taken_twice(tmp_path, monkeypatch):
    """``ergostat block NAME --now`` (a second engine's ``dispatch.once``) runs an item while the serving engine's
    watchdog loops. Its run's process exits and its owner holds its record (naming that dead pid) for a while before
    its end is written: the window opened here. Fails when the serving engine releases the lease as gone (uncounted,
    the owner's own counted end then dropped)."""
    import threading
    import time

    p = project(tmp_path, model("exit 3", "{ttl: 10m, attempts: 2}").replace("pool: 2", "pool: 1"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    serving, second = Engine(p, say=lambda s: None), Engine(p, say=lambda s: None)
    real, held = runrecord.remove, threading.Event()

    def remove_late(f):                                      # its process gone, its record still naming it
        held.set()
        time.sleep(2.5)
        real(f)
    monkeypatch.setattr(runrecord, "remove", remove_late)
    stop, passes = threading.Event(), []

    def watchdog():
        while not stop.is_set():
            serving.dispatch.watch()
            passes.append(held.is_set())
            time.sleep(0.2)
    t = threading.Thread(target=watchdog, daemon=True)
    t.start()
    try:
        second.dispatch.once(second.spec.blocks["worker"], "by hand")
        assert sum(passes) >= 5, "the window was never watched"
    finally:
        stop.set()
        t.join(5)
        second.close()
        serving.close()
    (ev,) = ended(p)
    assert ev["data"]["how"] == "nack" and ev["data"].get("count") is not False, ev["data"]
    assert "gone" not in ev["data"]["why"]
    lease = item(p, "ticket/1").fields["lease"]
    assert lease["attempts"] == 1 and [h.get("counted") for h in lease["history"]] == [True], lease["history"]
    assert len(p.events.query(n=None, type=TAKEN, item="ticket/1")) == 1, "taken twice"


def test_a_run_record_tells_gone_from_unknown(tmp_path):
    proc = sleeper()
    try:
        rec = {"pid": proc.pid, "start": runrecord.start_time(proc.pid), "run": "r"}
        assert runrecord.state(rec) == "alive"
        assert runrecord.state({**rec, "start": None}) == "unknown"
        assert runrecord.state({**rec, "pid": "12"}) == "unknown"
        assert runrecord.state({**rec, "start": "x"}) == "gone"
        os.kill(proc.pid, signal.SIGKILL)
        assert wait_for(lambda: runrecord.state(rec) == "gone", 5), "a zombie is gone"
    finally:
        proc.kill()
        proc.wait()
    assert runrecord.state(rec) == "gone"
    assert runrecord.look(tmp_path, "r") == "none"
    f = runrecord.files(tmp_path, "r")                         # its input written, its process perhaps started, its
    f["in"].write_text("")                                     # record not yet: unknown, never "no longer exists"
    assert runrecord.look(tmp_path, "r") == "unknown"
    f["in"].unlink()
    f["out"].write_text("")
    assert runrecord.look(tmp_path, "r") == "unknown"
    f["out"].unlink()                                          # a kept run (runs: outlive_engine): its journal is made,
    f["out"].with_suffix(".jsonl").write_text("")              # then its keeper's folder, before its record
    assert runrecord.look(tmp_path, "r") == "unknown"
    f["out"].with_suffix(".jsonl").unlink()
    (tmp_path / "runs" / "r").mkdir()
    assert runrecord.look(tmp_path, "r") == "unknown"
    (tmp_path / "runs" / "r").rmdir()
    assert runrecord.look(tmp_path, "r") == "none"
