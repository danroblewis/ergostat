"""The sampler's ramp and floor (``costs/sampler.py``): a new process sampled about ``floor`` after it is tracked, then
at doubling gaps up to its interval; never two samples within ``floor``, however many processes start."""

import subprocess
import time

import pytest

from ergostat.costs import sampler as cs
from ergostat.costs.sampler import Sampler
from ergostat.daemons import supervise


@pytest.fixture
def sleepers():
    procs = []

    def make():
        procs.append(subprocess.Popen(["sleep", "30"]))
        return procs[-1]
    yield make
    for p in procs:
        p.kill()
        p.wait()


def test_a_ramped_sampler_samples_early_then_at_its_interval(sleepers):
    s = Sampler(interval=0.8, floor=0.2, thread=False)
    assert s.wait(0.0) is None, "nothing tracked: nothing to wait for but a wake"
    s.track(sleepers(), now=0.0)
    now, waits = 0.0, []
    for _ in range(4):
        waits.append(s.wait(now))
        now += waits[-1]
        s.sample(now)
    assert waits == pytest.approx([0.2, 0.4, 0.8, 0.8], abs=1e-9)
    assert s.thread is None, "thread=False: never started"


def test_the_sampler_never_samples_sooner_than_its_floor(sleepers):
    s = Sampler(30.0, floor=1.0, thread=False)
    s.sample(10.0)
    t = s.track(sleepers(), now=10.1)
    t.gap, t.due = 0.1, 10.2
    assert s.wait(10.1) == pytest.approx(0.9, abs=1e-9), "due at 10.2, but not within 1 s of the last sample"
    assert s.wait(11.5) == 0.0

    real, at = Sampler(30.0, "test-sampler", floor=1.0), []
    sample = real.sample

    def timed(now=None):
        at.append(time.monotonic())
        sample(now)
    real.sample = timed
    tracked = []
    try:
        for _ in range(20):                          # (each track wakes its thread)
            tracked.append(real.track(sleepers()))
            time.sleep(0.05)
        end = time.monotonic() + 3.0
        while time.monotonic() < end and len(at) < 2:
            time.sleep(0.05)
    finally:
        for t in tracked:
            real.finish(t)
    assert at, "a sample within 3 s"
    gaps = [b - a for a, b in zip(at, at[1:], strict=False)]
    assert all(g >= 0.95 for g in gaps), gaps


def test_the_samplers_keep_their_intervals_and_floor(sleepers):
    assert (cs.SAMPLER.interval, cs.SAMPLER.floor) == (1.0, 1.0)
    assert (supervise.SAMPLER.interval, supervise.SAMPLER.floor) == (30.0, 1.0)
    s = Sampler(thread=False)
    t = s.track(sleepers(), now=0.0)
    for now in (1.0, 2.0, 3.0):
        s.sample(now)
    assert t.gap == 1.0 and s.wait(3.0) == pytest.approx(1.0)
