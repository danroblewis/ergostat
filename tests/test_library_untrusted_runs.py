"""Untrusted libraries at run time (SPEC §2a, *Untrusted libraries*): the runs at once of every untrusted block together
are counted and added under the engine's one lock, in ``start`` and in a lease's ``take`` (reserved before the lease is
written), counting a run still draining and a block the model no longer has; the clock never paces one faster than the
floor, whatever the spec says after it was compiled."""

import copy
import dataclasses
import json
import textwrap
import threading
import time
import types

import pytest

from ergostat import model as mdl
from ergostat.leases import TAKEN
from ergostat.library import bounds, trust
from ergostat.library.bounds import UNTRUSTED_EVERY, UNTRUSTED_RUNS
from ergostat.spec import engine as engine_module
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.spec.load import Where
from ergostat.store import Project

BOT = """
template: bot
params:
  kind: {type: name, default: "${name}"}
  work: {type: map, default: {type: program, run: "true", every: 5m}}
items:
  ${kind}:
    id: ${kind}/*
    states: [ready, done]
stocks:
  waiting:
    unit: items
    sensor: {run: "echo 1", every: 5m}
blocks:
  work: ${work}
"""
JUDGED = "template: judged\nblocks:\n  judge: {type: judge}\n"
TAKES = {"type": "program", "run": "true", "takes": {"kind": "t", "at": "ready"}}
MAIN = {"a": {"use": "bot"}, "b": {"use": "bot"}, "t": {"use": "bot", "with": {"work": TAKES}},
        "j": {"use": "judged"}}                                   # 1 + 1 + 1 + 1: the cap
OWN = "stocks:\n  mine: {unit: x, sensor: {run: 'echo 1'}}\nblocks:\n  go: {type: program, run: 'true', every: 1s}\n"
GONE = [f"gone-{i} item/{i}" for i in range(UNTRUSTED_RUNS)]     # runs of blocks the model no longer has: untrusted


def project(tmp_path) -> Project:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "bot.yaml").write_text(textwrap.dedent(BOT))
    (tmp_path / "lib" / "judged.yaml").write_text(JUDGED)
    (tmp_path / "ergostat.yaml").write_text("name: t\nlibrary:\n  - {folder: lib, untrusted: true}\n" + OWN
                                            + "uses: " + json.dumps(MAIN) + "\n")
    return Project(mdl.load(tmp_path))


MADE: list[Engine] = []


@pytest.fixture(autouse=True)
def second_line(monkeypatch):
    """The allowlist (library/trust.py) refuses these untrusted blocks before compile; the run-time gates are a second
    line behind it (and behind the compile check), so they are shown here with the first line taken away."""
    monkeypatch.setattr(trust, "refused", lambda *a: None)


@pytest.fixture(autouse=True)
def closed():
    """Every engine a test made is closed when it ends (none left to this worker's later tests), after the stand-in
    entries it put in ``running`` (no run of theirs exists) are taken out, so close does not wait on them."""
    yield
    while MADE:
        e = MADE.pop()
        with e.lock:
            e.running.difference_update(GONE)
            if "_run" in vars(e):                                 # its runs stood in for: none was ever done
                e.running.clear()
        e.stop.set()
        e.close()


def engine(tmp_path) -> tuple[Engine, Project]:
    p = project(tmp_path)
    e = Engine(p, say=lambda s: None)
    MADE.append(e)
    return e, p


def untrusted_running(e) -> int:
    return sum(1 for k in e.running if bounds.untrusted_block(e.spec, k.split(" ", 1)[0], k in e.untrusted_runs))


def test_start_refused_at_ceiling(tmp_path):
    e, p = engine(tmp_path)
    e._run = lambda *a, **k: None                                 # (a run that is never done: it stays in running)
    blocks = e.spec.blocks
    assert blocks["a-work"].untrusted and blocks["b-work"].untrusted and not blocks["go"].untrusted
    e.running |= set(GONE)
    assert e.start(blocks["a-work"], "t") is False, "four runs of blocks the model no longer has: at the cap"
    assert e.start(blocks["go"], "t") is True, "the owner's own block is not counted against it"
    e.running.discard(GONE[0])
    assert e.start(blocks["a-work"], "t") is True and "a-work" in e.running
    assert e.start(blocks["b-work"], "t") is False and untrusted_running(e) == UNTRUSTED_RUNS


def opened(p, n: int):
    for i in range(n):
        p.events.add("t.opened", item=f"t/{i}", source="t", data={})


def test_take_reserves_before_lease(tmp_path):
    e, p = engine(tmp_path)
    opened(p, 1)
    b = e.spec.blocks["t-work"]
    it = its.one(p.events, e.spec, "t/0")
    assert it is not None and it.state == "ready"
    e.running |= set(GONE)
    try:
        assert e.dispatch.take(b, it, inline=True) is None
        assert not p.events.query(n=None, type=TAKEN), "no lease is written for a run that cannot start"
        assert f"t-work {it.id}" not in e.running
        e.running.discard(GONE[0])
        assert e.dispatch.take(b, it, inline=True) is not None, "with room, it takes"
        assert p.events.query(n=None, type=TAKEN) and f"t-work {it.id}" in e.running
    finally:
        e.running.clear()


def test_start_race_holds_cap(tmp_path, monkeypatch):
    """At the cap less one, a start and a take both pass the count only if they count outside the lock that adds: the
    first to count waits on a barrier for the other, which can reach it only if the lock is not held across both."""
    e, p = engine(tmp_path)
    opened(p, 1)
    e._run = lambda *a, **k: None
    e.running |= set(GONE[1:])
    barrier = threading.Barrier(2, timeout=2.0)
    real = bounds.room

    def waits(engine_, b):                                        # counted, then held between the count and the add
        got = real(engine_, b)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:                      # (the other could not come: it waits on the lock)
            pass
        return got
    monkeypatch.setattr(bounds, "room", waits)
    got = {}
    it = its.one(p.events, e.spec, "t/0")
    runs = [threading.Thread(target=lambda: got.__setitem__("start", e.start(e.spec.blocks["a-work"], "t"))),
            threading.Thread(target=lambda: got.__setitem__("take", e.dispatch.take(e.spec.blocks["t-work"], it,
                                                                                       inline=True)))]
    try:
        for t in runs:
            t.start()
        for t in runs:
            t.join(10)
        assert (got["start"] is True) + (got["take"] is not None) == 1, got
        assert untrusted_running(e) == UNTRUSTED_RUNS
    finally:
        e.running.clear()


def blocked(e):
    entered, go, done = threading.Event(), threading.Event(), threading.Event()

    def run_block(b, *a, **k):
        entered.set()
        go.wait(10)                                               # a run cancelled, its process still exiting
        return []
    e.run_block = run_block
    e.poke = lambda *a, **k: done.set()                           # (after its entry has left running)
    return entered, go, done


def test_draining_run_still_counts(tmp_path):
    e, p = engine(tmp_path)
    entered, go, done = blocked(e)
    e.running |= set(GONE[1:])
    blocks = e.spec.blocks
    try:
        assert e.start(blocks["a-work"], "t") and entered.wait(5)
        assert e.start(blocks["b-work"], "t") is False, "a run still draining counts"
        go.set()
        assert done.wait(5) and "a-work" not in e.running
        assert e.start(blocks["b-work"], "t") is True, "once it has returned, the next starts"
    finally:
        go.set()


def test_reload_making_it_trusted_still_counts_its_draining_run(tmp_path):
    """A reload that keeps the block's name and makes it trusted (its folder's trust flipped, or the owner's own block
    reusing the name): its run that began untrusted still counts until it returns."""
    e, p = engine(tmp_path)
    entered, go, done = blocked(e)
    e.running |= set(GONE[1:])
    try:
        assert e.start(e.spec.blocks["a-work"], "t") and entered.wait(5)
        new = copy.copy(e.spec)
        new.blocks = {**e.spec.blocks, "a-work": dataclasses.replace(e.spec.blocks["a-work"], untrusted=False,
                                                                   where=Where(tmp_path / "ergostat.yaml", 3))}
        with e.lock:
            e.spec = new
        assert not bounds.untrusted_block(e.spec, "a-work"), "the model says it is trusted now"
        assert e.start(e.spec.blocks["b-work"], "t") is False, "its run began untrusted: it still counts"
    finally:
        go.set()


def clocked(e, monkeypatch, rounds: list[float]) -> dict:
    """The scheduler's loop run once a time in ``rounds`` (its clock patched), recording what it reads and starts."""
    clock, got = [rounds[0]], {"reads": [], "starts": [], "judged": []}
    e.read_soon = lambda x: got["reads"].append((clock[0], x.series))
    e.start = lambda x, *a, **k: got["starts"].append((clock[0], x.name))
    e._readings = lambda tick: False
    e._sweep = lambda: None

    def judged(b):
        got["judged"].append((clock[0], b.name))
        with e.lock:
            e.running.discard(b.name)
    e.judge = judged

    def wait(_t=None):                                            # one round of the loop done: the clock moves on
        assert wait_for(lambda: not any(n.endswith("-judge") for n in e.running)), "a judge's pass started this round ends"
        rounds.pop(0)
        if rounds:
            clock[0] = rounds[0]
        else:
            e.stop.set()
        return False
    monkeypatch.setattr(e.wake, "wait", wait)
    # The engine module's clock only: patching time.monotonic itself would move every other thread of this worker
    # (a wait worked out as a real deadline less this clock could last hours).
    fake = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith("_")})
    fake.monotonic = lambda: clock[0]
    monkeypatch.setattr(engine_module, "time", fake)
    e._schedule(e.loop_gen)
    return got


def wait_for(cond, seconds=5.0):
    """Until ``cond`` holds (looked at again each 20 ms, an event's wait: time.monotonic may be patched)."""
    tick = threading.Event()
    for _ in range(int(seconds / 0.02)):
        if cond():
            return True
        tick.wait(0.02)
    return cond()


def test_a_block_run_by_its_readings_is_paced_too(tmp_path):
    """A block changed after it was compiled to run on its inputs' readings (no every:, cron: or takes:): due no
    faster than the floor since its last run began."""
    from ergostat.spec.ir import Ref
    e, p = engine(tmp_path)
    b = e.spec.blocks["a-work"]
    b.every, b.inputs = None, {"x": Ref("stock", "a-waiting")}
    e.last_reading = time.time()
    e.began["a-work"] = time.time() - (UNTRUSTED_EVERY - 10)
    assert e.due(b) is False, "a new reading, but its last run began under the floor ago"
    e.began["a-work"] = time.time() - (UNTRUSTED_EVERY + 10)
    assert e.due(b) is True
    own = e.spec.blocks["go"]
    own.every, own.inputs = None, {"x": Ref("stock", "mine")}
    e.began["go"] = time.time() - 1
    assert e.due(own) is True, "the owner's own block runs on its readings, unpaced"


def test_judge_pass_counted_at_ceiling(tmp_path, monkeypatch):
    e, p = engine(tmp_path)
    e.running |= set(GONE)
    got = clocked(e, monkeypatch, [1000.0])
    assert not got["judged"] and "j-judge" not in e.running, "at the cap, an untrusted judge's pass waits"
    e.running.clear()
    e.stop.clear()
    got = clocked(e, monkeypatch, [2000.0])
    assert [n for _, n in got["judged"]] == ["j-judge"]


def test_engine_paces_untrusted_at_floor(tmp_path, monkeypatch):
    e, p = engine(tmp_path)
    s, b, j = e.spec.stocks["a-waiting"].sensors["main"], e.spec.blocks["a-work"], e.spec.blocks["j-judge"]
    s.every = b.every = j.every = 1                               # changed after it was compiled
    t0, t1 = 1000.0, 1000.0 + UNTRUSTED_EVERY
    got = clocked(e, monkeypatch, [t0, t1 - 1, t1])
    reads, starts = got["reads"], got["starts"]
    assert [t for t, k in reads if k == s.series] == [t0, t1], reads
    assert [t for t, n in starts if n == "a-work"] == [t0, t1], starts
    assert [t for t, _ in got["judged"]] == [t0, t1], got["judged"]
    mine = [t for t, k in reads if k == e.spec.stocks["mine"].sensors["main"].series]
    assert mine == [t0, t0 + UNTRUSTED_EVERY - 1], "the owner's own sensor keeps its own period (60s)"
