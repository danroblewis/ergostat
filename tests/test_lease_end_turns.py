"""A run's lease end waits its turn and is retried, never left to expire (dev/records/a-lease-end-is-never-dropped.md,
SPEC §9.5): two ends at once both end; a slow end blocks no take or look; an end that cannot complete before its TTL
is given up and said (the heartbeat's dispatch error, the pipeline's situation); and a run whose end was tried is
never renewed: the watchdog ends its lease, else expires it, on its first look."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat import runner as old
from ergostat.leases import ENDED, EXPIRED, RENEWED, TAKEN
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

BIN = str(Path(__file__).resolve().parent.parent / "dev" / "bin")

MODEL = """
name: t
items:
  ticket:
    id: ticket/*
    states: [ready, doing, done]
    on: {ticket.started: doing, ticket.done: done}
  note:
    id: note/*
    states: [new, read]
    on: {note.read: read}
blocks:
  worker:
    type: program
    takes: {kind: ticket, at: ready}
    pool: 4
    run: "true"
    lease: {lease}
  other:
    type: program
    takes: {kind: note, at: new}
    pool: 1
    run: "true"
    lease: {ttl: 1m}
"""


def engine(tmp_path, n: int, lease: str = "{ttl: 1m}") -> tuple[Project, Engine]:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("{lease}", lease)))
    p = Project(mdl.load(tmp_path))
    for i in range(n):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t")
    e = Engine(p, say=lambda s: None)
    e.lock_wait = 0.3
    return p, e


def taken(e: Engine, i: int) -> tuple:
    """Ticket ``i`` leased to a run of the worker, as a look takes it, not run: (block, fence, run)."""
    b = e.spec.blocks["worker"]
    got = e.dispatch.take(b, its.one(e.p.events, e.spec, f"ticket/{i}"), inline=True)
    assert got is not None
    return b, got[2]["fence"], got[3]


def lease(p, i: int) -> dict:
    return its.one(p.events, p.model.spec, f"ticket/{i}").fields["lease"]


def ending(e, b, i, fence, run, errors: list, **k) -> threading.Thread:
    def go():
        try:
            e.dispatch.finish(b, f"ticket/{i}", fence, run, {"exit": 0}, **k)
        except Exception as x:
            errors.append(x)
    t = threading.Thread(target=go, name=f"end-{i}", daemon=True)
    t.start()
    return t


def closed(e: Engine) -> None:
    try:
        e.close()
    finally:
        old.STOPPING.clear()


def test_two_runs_ending_at_once_the_first_s_fold_slowed_past_lock_wait_both_end(tmp_path, monkeypatch):
    """The first end's read of the item takes longer than ``lock_wait`` (the factory's record under load): the second
    end, arriving meanwhile, is not held behind it (it ends first); neither raises."""
    p, e = engine(tmp_path, 2)
    (b, f0, r0), (_, f1, r1) = taken(e, 0), taken(e, 1)
    real_one, reading = its.one, threading.Event()

    def one(events, spec, id, *a, **k):
        if id == "ticket/0" and threading.current_thread().name == "end-0" and not reading.is_set():
            reading.set()                             # the second end arrives now
            time.sleep(1.0)
        return real_one(events, spec, id, *a, **k)
    monkeypatch.setattr(its, "one", one)
    errors: list = []
    try:
        first = ending(e, b, 0, f0, r0, errors)
        assert reading.wait(10)
        second = ending(e, b, 1, f1, r1, errors)
        first.join(10)
        second.join(10)
        assert not errors, errors
        for i in (0, 1):
            got = lease(p, i)
            assert got["holder"] is None and got["history"][-1]["how"] == "nack", got
        assert [x["item"] for x in p.events.query(n=None, type=ENDED)] == ["ticket/1", "ticket/0"], "not behind the read"
        assert not e.dispatch.dropped and e.dispatch.failing is None
    finally:
        closed(e)


def test_a_slow_end_does_not_block_a_take_or_a_look_on_another_block(tmp_path):
    """An end waiting its turn (another end holds the lock) holds no dispatcher lock: the other block's look takes its
    item, the watchdog's pass runs, and the end completes once its turn comes."""
    p, e = engine(tmp_path, 1)
    b, f0, r0 = taken(e, 0)
    errors: list = []
    e.dispatch.ends.acquire()                          # another end under way, slow
    try:
        waiting = ending(e, b, 0, f0, r0, errors)
        free = []
        for _ in range(40):                            # (2 s: past several lock_waits and pauses, it is retrying)
            free.append(e.dispatch.lock.acquire(blocking=False))
            if free[-1]:
                e.dispatch.lock.release()
            time.sleep(0.05)
        assert all(free), "the dispatcher's lock is free all the while the end waits"
        assert waiting.is_alive() and not errors
        p.events.add("note.made", item="note/1", source="t")
        t0 = time.monotonic()
        e.dispatch.tick()
        e.dispatch.watch()
        assert time.monotonic() - t0 < 2.0
        assert [x["item"] for x in p.events.query(n=None, type=TAKEN)] == ["ticket/0", "note/1"]
    finally:
        e.dispatch.ends.release()
    try:
        waiting.join(10)
        assert not errors and lease(p, 0)["holder"] is None, errors
    finally:
        closed(e)


def test_an_end_that_cannot_complete_before_the_ttl_raises_a_situation(tmp_path):
    """Another end holds the lock for good: the end retries until a lock_wait before its lease expires, then gives up,
    naming the item and the run; the dispatcher's standing error (the heartbeat's ``dispatch_error``) says so from
    when the end was first tried, which the pipeline watch raises as a situation past two minutes. On the watchdog's
    first look past the expiry, the run (seen active elsewhere) is not renewed: its end tried again, still blocked,
    it expires."""
    from ergostat.spec.watchdog import heartbeat
    p, e = engine(tmp_path, 1, "{ttl: 2s}")
    b, f0, r0 = taken(e, 0)
    expires = float(lease(p, 0)["expires"])
    errors: list = []
    e.dispatch.ends.acquire()                          # wedged for good
    try:
        t0 = time.time()
        ending(e, b, 0, f0, r0, errors).join(10)
        assert len(errors) == 1 and isinstance(errors[0], TimeoutError), errors
        assert r0 in str(errors[0]) and "ticket/0" in str(errors[0])
        assert time.time() < expires, "given up before the TTL ran out"
        why, since = e.dispatch.failing
        assert r0 in why and "ticket/0" in why and t0 - 1 <= since <= t0 + 1
        e.dispatch.note(None)                          # (a clean look does not clear it)
        assert e.dispatch.failing == (why, since)
        t1 = time.time()
        e.dispatch.note("other: KeyError: 'y'")        # a look's own error is not hidden behind it: said first, its since
        got, at = e.dispatch.failing
        assert got == "other: KeyError: 'y'" and t1 <= at <= time.time()
        e.dispatch.note(None)
        assert e.dispatch.failing == (why, since)
        heartbeat(tmp_path, time.time(), 0, failing=e.dispatch.failing)
        beat = json.loads((tmp_path / "heartbeat.json").read_text())
        assert beat["dispatch_error"]["why"] == why
        code = f"import json, sys\nsys.path[:0] = [{BIN!r}]\nimport live\nprint(json.dumps(live.dispatch_failing({beat!r}, {since + 121})))"
        r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=60)
        got = json.loads(r.stdout.strip().splitlines()[-1])   # (what the pipeline watch raises as `dispatch`)
        assert got and r0 in got and "ticket/0" in got, r.stderr
        p.events.add("x.seen", item="note/9", source="t", causedby=r0)     # (the run active elsewhere: no renewal)
        e.dispatch.watch(now=expires + 1)
    finally:
        e.dispatch.ends.release()
    try:
        assert not p.events.query(n=None, type=RENEWED)
        assert [x["data"]["run"] for x in p.events.query(n=None, type=EXPIRED)] == [r0], "expired on its first look"
        assert lease(p, 0)["holder"] is None
        assert e.dispatch.failing == (why, since), "still said until a pass finds the lease let go"
        e.dispatch.watch()                             # (the next pass: no lease held by the run)
        assert e.dispatch.failing == (why, since) and e.dispatch.dropped[r0][2] is not None
    finally:
        closed(e)


def test_a_given_up_end_is_said_only_while_its_lease_is_held_and_one_watch_pass_after(tmp_path, monkeypatch):
    """Once the watchdog has ended the lease of a run whose end was given up, the situation stands for ``HOLD`` (one
    pipeline-watch pass, so it is seen once), then is gone: the record of it too."""
    from ergostat.leases import dispatch as dp
    p, e = engine(tmp_path, 1, "{ttl: 2s}")
    b, f0, r0 = taken(e, 0)
    expires = float(lease(p, 0)["expires"])
    errors: list = []
    e.dispatch.ends.acquire()
    try:
        ending(e, b, 0, f0, r0, errors).join(10)
    finally:
        e.dispatch.ends.release()
    try:
        assert len(errors) == 1 and e.dispatch.dropped[r0][2] is None
        later = time.time() + 10 * dp.HOLD             # (held, the end stands however long ago it was given up)
        monkeypatch.setattr(dp, "time", type("T", (), {"time": staticmethod(lambda: later), "sleep": time.sleep,
                                                       "monotonic": time.monotonic}))
        assert r0 in e.dispatch.failing[0]
        monkeypatch.setattr(dp, "time", time)
        e.dispatch.watch(now=expires + 1)              # its end tried again, done: the lease let go
        assert lease(p, 0)["holder"] is None and r0 in e.dispatch.failing[0]
        gone = e.dispatch.dropped[r0][2]
        assert gone is not None
        monkeypatch.setattr(dp, "time", type("T", (), {"time": staticmethod(lambda: gone + dp.HOLD + 1),
                                                       "sleep": time.sleep, "monotonic": time.monotonic}))
        assert e.dispatch.failing is None and not e.dispatch.dropped
    finally:
        monkeypatch.setattr(dp, "time", time)
        closed(e)


def test_a_run_whose_end_failed_does_not_hold_the_lease_past_one_watchdog_pass(tmp_path):
    """The run ended (its end given up), and something it caused still turns up: the watchdog's first look past the
    expiry never renews it; it ends the lease as the run would have."""
    p, e = engine(tmp_path, 1, "{ttl: 2s}")
    b, f0, r0 = taken(e, 0)
    expires = float(lease(p, 0)["expires"])
    errors: list = []
    e.dispatch.ends.acquire()
    try:
        ending(e, b, 0, f0, r0, errors).join(10)
    finally:
        e.dispatch.ends.release()
    try:
        assert len(errors) == 1 and lease(p, 0)["holder"] == r0
        p.events.add("x.seen", item="note/9", source="t", causedby=r0)
        e.dispatch.watch(now=expires + 1)
        assert not p.events.query(n=None, type=RENEWED) and not p.events.query(n=None, type=EXPIRED)
        (end,) = p.events.query(n=None, type=ENDED)
        assert end["data"]["run"] == r0 and lease(p, 0)["holder"] is None and r0 not in e.dispatch.ending
    finally:
        closed(e)
