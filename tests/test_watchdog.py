"""The engine's watchdog (spec/watchdog.py): a wedged sensor pool, a wedged loop, and a pass that never finishes are
found, said (a stack dump in the state folder, ``ergostat.engine.stalled`` in the record) and recovered."""

import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.spec import watchdog as wd
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """
name: wd
stocks:
  done:
    unit: things
    sensor:
      run: echo 10
      every: 0.2s
      timeout: 1s
goals:
  enough:
    stock: done
    hold: "<= 20"
"""


pytestmark = pytest.mark.serial            # its stall is 1 s: a pass slowed past it by the machine's load is a stall

@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(wd, "STALL", 1.0)
    monkeypatch.setattr(wd, "GRACE", 0.5)
    monkeypatch.setattr(wd, "EVERY", 0.1)
    monkeypatch.setattr(wd, "HARD", 0.5)
    yield
    runner.STOPPING.clear()


def until(cond, seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


def started(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(tmp_path))
    e = Engine(p, say=lambda s: None)
    return p, e


def stalled(p, what):
    return [x for x in p.events.query(n=None, type="ergostat.engine.stalled") if x["data"]["what"] == what]


def newest(p):
    got = p.measurements.latest("sensor/done.main")
    return got[0] if got else 0.0


def test_a_wedged_sensor_pool_is_replaced_and_its_readings_asked_again(tmp_path):
    p, e = started(tmp_path)
    gate, calls = threading.Event(), []
    real = e._read_one

    def wedged(s, *a):
        calls.append(s.series)
        if len(calls) == 1:
            gate.wait(60)                                 # held by something other than its command: never back
        real(s, *a)
    e._read_one = wedged
    try:
        e.start_all()
        assert until(lambda: calls)
        held_at = time.time()
        assert until(lambda: stalled(p, "pool"))
        got = stalled(p, "pool")[0]["data"]
        assert "new sensor pool" in got["recovery"] and got["stacks"]
        dump = open(got["stacks"]).read()
        assert "ergostat engine stalled (pool)" in dump and "wedged" in dump   # the stuck thread's stack is in it
        assert until(lambda: newest(p) > held_at)        # read again, by the new pool
        assert e.passed_at > time.monotonic() - 2
    finally:
        gate.set()
        e.close()


def test_a_wedged_loop_is_started_again(tmp_path):
    p, e = started(tmp_path)
    gate, calls = threading.Event(), []
    real = e._readings

    def wedged(tick):
        calls.append(1)
        if len(calls) == 3:
            gate.wait(60)                                 # the loop held inside a round
        return real(tick)
    e._readings = wedged
    try:
        e.start_all()
        assert until(lambda: stalled(p, "pass"))
        assert stalled(p, "pass")[0]["data"]["recovery"] == "the loop started again"
        held_at = time.time()
        assert until(lambda: newest(p) > held_at)
        assert e.loop_gen == 1 and e.wedged is None
        assert until(lambda: time.monotonic() - e.passed_at < 0.5)
    finally:
        gate.set()
        e.close()


def test_a_pass_that_never_finishes_restarts_the_process(tmp_path):
    p, e = started(tmp_path)
    asked = []
    e.restart_hard = asked.append
    try:
        e.start_all()
        assert until(lambda: e.passed_at > 0 and len(p.events.query(n=None, type="loop.*")) >= 0)
        e.passing.acquire()                               # every pass waits for this, for good
        assert until(lambda: stalled(p, "pass"), 10)
        assert until(lambda: e.wedged is not None, 10)    # the loop started again did not help: the run loop restarts it
        assert "no pass for" in e.wedged
        assert until(lambda: asked, 10)                   # and when it has not, the watchdog does
    finally:
        e.passing.release()
        e.close()
