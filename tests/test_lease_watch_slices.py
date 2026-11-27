"""Many overdue leases do not delay a take (event-log-indexes-what-it-is-asked, done item 4): the watchdog reads each
overdue lease's activity in slices of ``SLICE`` seconds, so the dispatcher takes work for another block between them;
and a round cut into slices still looks at every lease, keeping each one's first look."""

import textwrap
import time

from ergostat import model as mdl
from ergostat.leases import TAKEN, dispatch
from ergostat.leases.dispatch import Dispatcher
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """
name: t
projections:
  ticket:
    id: ticket/*
    states: [ready, doing, done]
  job:
    id: job/*
    states: [ready, done]
    on: {job.done: done}
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready}
    pool: 2
    run: "true"
    lease: {ttl: 1m}
  other:
    type: program
    takes: {projection: job, at: ready}
    pool: 2
    run: 'echo "{\\\\"event\\\\": \\\\"job.done\\\\"}"'
    lease: {ttl: 1m}
"""


def held(p, n: int) -> None:
    """``n`` tickets, each held by a lease of another engine's run (one this engine cannot tell is gone), long overdue."""
    at = time.time() - 3600
    for i in range(n):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", at=at)
        p.events.add(TAKEN, item=f"ticket/{i}", source="ergostat", at=at,
                     data={"run": f"r{i}", "block": "elsewhere", "fence": 1, "ttl": 60.0, "max": 3, "back": "ready"})


def test_many_overdue_leases_do_not_delay_a_take(tmp_path, monkeypatch):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(tmp_path))
    held(p, 120)
    looked: list[str] = []

    def slow(self, item, lease):                          # each lease's activity a slow read: 6 s for a whole pass
        looked.append(item)
        time.sleep(0.05)
    monkeypatch.setattr(Dispatcher, "activity", slow)
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        end = time.time() + 10
        while not looked and time.time() < end:
            time.sleep(0.01)
        assert looked, "the watchdog is looking at the overdue leases"
        t0 = time.time()
        p.events.add("job.opened", item="job/1", source="t")
        while not p.events.query(n=1, type=TAKEN, item="job/1") and time.time() < t0 + 10:
            time.sleep(0.02)
        taken = p.events.query(n=1, type=TAKEN, item="job/1")
        assert taken and taken[0]["time"] - t0 < 2.0, "taken between the watchdog's slices, not after its whole pass"
        assert len(set(looked)) < 120, "(the whole pass was not yet read when it was taken)"
        end = time.time() + 20
        while len(set(looked)) < 120 and time.time() < end:
            time.sleep(0.05)
        assert set(looked) == {f"ticket/{i}" for i in range(120)}, "the round goes on, slice by slice, to every lease"
    finally:
        e.close()


def test_a_round_cut_into_slices_keeps_each_first_look(tmp_path, monkeypatch):
    """A lease looked at in one slice keeps its first look while later slices read the others, so its grace runs from
    then: it expires on its second look, not a round later."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(tmp_path))
    held(p, 6)
    monkeypatch.setattr(dispatch, "SLICE", 0.0)            # one lease a pass
    monkeypatch.setattr(Dispatcher, "activity", lambda self, item, lease: None)
    e = Engine(p, say=lambda s: None)
    d = Dispatcher(e)
    now, mono = time.time(), 1000.0
    for i in range(5):                                    # a round: one lease each pass
        d.watch(now, mono)
        assert d.behind and len(d.passed) == i + 1 and not d.watched
    d.watch(now, mono)
    assert not d.behind and d.watched and not d.passed, "the round read whole, in six passes"
    assert len(d.overdue) == 6, "each lease's first look kept across the slices"
    d.watch(now, mono + 100)                              # the second look, past the grace: the first lease expires
    assert len(p.events.query(n=None, type="ergostat.lease.expired")) == 1
