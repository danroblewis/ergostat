"""Woken by the write (docs/proposals/latency.md): a record's board wakes its waiters when this process writes and,
through the kernel's file notifications, when another process does; the dispatcher takes an item as soon as it is
written, not at its next look; a goal on a queue sees its first item at once; and a run costs one thread."""

import select
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat.leases import TAKEN
from ergostat.leases import dispatch as dp
from ergostat.notify import of
from ergostat.spec.engine import Engine
from ergostat.store import Project

KIND = """
name: n
storage: {{events: {backend}}}
items:
  job:
    id: job/*
    states: [ready, done]
    on: {{job.arrived: ready, job.done: done}}
"""

TAKES = KIND + """
stocks:
  ready:
    sensor: {{items: job, state: ready, every: 1h}}
goals:
  nothing-waits:
    stock: ready
    hold: "<= 0"
blocks:
  worker:
    type: program
    goal: nothing-waits
    run: "echo '{{\\"event\\": \\"job.done\\"}}'"
    takes: {{kind: job, at: ready, to: [done]}}
    pool: 40
"""


def project(tmp_path, text: str, backend: str = "segments") -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text.format(backend=backend)))
    return Project(mdl.load(tmp_path))


@pytest.mark.parametrize("backend", ["segments", "sqlite"])
def test_a_write_in_this_process_wakes_its_waiters_at_once(tmp_path, backend):
    p = project(tmp_path, KIND, backend)
    b = of(p.events)
    mark, got = b.n, {}

    def waiter():
        t = time.monotonic()
        got["n"] = b.wait(mark, 5.0)
        got["s"] = time.monotonic() - t
    w = threading.Thread(target=waiter)
    w.start()
    time.sleep(0.1)
    p.events.add("job.arrived", item="job/1", source="t")
    w.join(5)
    assert got["n"] > mark and got["s"] < 1.0


@pytest.mark.skipif(not hasattr(select, "kqueue"), reason="the kernel's file notifications: kqueue (macOS, the BSDs)")
def test_another_processs_write_wakes_them_too(tmp_path):
    p = project(tmp_path, KIND)
    b = of(p.events)
    time.sleep(0.2)                                           # (its watcher started)
    mark = b.n
    code = (f"from ergostat import model as m; from ergostat.store import Project; "
            f"Project(m.load(__import__('pathlib').Path({str(tmp_path)!r}))).events.add('job.arrived', item='job/2', source='x')")
    t = time.monotonic()
    proc = subprocess.Popen([sys.executable, "-c", code])
    got = b.wait(mark, 10.0)
    proc.wait(30)
    assert got > mark and time.monotonic() - t < 9.0


def test_the_dispatcher_takes_an_item_when_it_is_written_not_at_its_next_look(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "LOOK", 30.0)                     # its old check would come far too late
    monkeypatch.setattr(dp, "EVERY", 30.0)
    p = project(tmp_path, TAKES)
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        time.sleep(1.5)                                       # (its first look, and the queue's first reading, done)
        ev = p.events.add("job.arrived", item="job/1", source="t")
        end = time.time() + 10
        while time.time() < end and not p.events.query(n=1, type=TAKEN):
            time.sleep(0.01)
        taken = p.events.query(n=1, type=TAKEN)
        assert taken and taken[0]["time"] - ev["time"] < 2.0   # the goal saw it at once, the dispatcher took it
    finally:
        e.close()


def test_a_run_costs_one_thread(tmp_path):
    p = project(tmp_path, TAKES.replace("echo '", "sleep 1; echo '"))
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        time.sleep(1.0)
        before = threading.active_count()
        p.events.add_many([{"type": "job.arrived", "item": f"job/{i}", "source": "t"} for i in range(30)])
        end, most = time.time() + 10, 0
        while time.time() < end and len(e.running) < 30:
            time.sleep(0.02)
        time.sleep(0.2)
        most = threading.active_count() - before
        assert len(e.running) == 30
        assert most <= 30 + 4                                  # a thread each, not three (and a few of the engine's)
    finally:
        e.close()
