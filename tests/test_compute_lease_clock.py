"""The engine's lease renewals as its keeper's deadline, on the worker's own clock (SPEC §12s.5, ``leaseclock.py``):
``sent + base + left``, ``base`` the least ``heard - sent`` of the last ten minutes, so the deadline is never later than
the engine's expiry plus the fastest transit seen; the time of day is never read; a slow renewal never extends; an
older fence is ignored; with the session cut, the keeper still kills by the last deadline plus K. At most 4 processes
a test, each group killed at the end."""

from __future__ import annotations

import json
import os
import random
import signal
import sys
import time
import uuid

import pytest

from tests.compute_pipe import WORKER, Node
from tests.compute_pipe import until as _until

DEAF = "trap '' TERM; exec sleep 30"


@pytest.fixture
def bare(monkeypatch):
    """The worker's modules as its process loads them: by bare name, its folder first on the path."""
    monkeypatch.syspath_prepend(str(WORKER))
    import deadline as d
    import leaseclock as lc
    yield lc, d
    for name in ("leaseclock", "keeper", "deadline"):
        sys.modules.pop(name, None)


class Said:
    def __init__(self):
        self.frames: list[dict] = []

    def send(self, type, **fields):
        self.frames.append({"type": type, **fields})


def _run(tmp_path, d, lease: float | None = 100.0) -> tuple[str, str]:
    run = uuid.uuid4().hex
    (tmp_path / "runs" / run).mkdir(parents=True)
    path = str(tmp_path / "runs" / run / "deadline")
    d.write(path, d.now() + 1000, lease, 0.25 if lease is not None else 2.0)
    return run, path


def _lease(path: str) -> float:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["lease"]


def test_with_random_delays_the_deadline_is_never_later_than_the_expiry_plus_the_least_delay(tmp_path, bare):
    lc, d = bare
    t = [0.0]
    clock = lc.Clock(str(tmp_path), now=lambda: t[0])
    run, path = _run(tmp_path, d)
    rng, off = random.Random(7), 81234.5                 # (the engine's clock: the worker's plus off)
    msgs, expiry = [], 40.0
    for i in range(400):                                 # sent every 0.5 s (200 s, inside the window), each delayed
        at = i * 0.5
        expiry = max(expiry, at + 1) + rng.choice([0, 0, 3, -2])
        delay = 0.003 + rng.expovariate(1 / 0.2) + (rng.random() < 0.05) * 4
        kind = "renew" if i % 3 == 0 else "ping"
        msgs.append((at + delay, delay, kind, at + off, expiry + off - (at + off)))
    least, checked = float("inf"), 0
    for heard, delay, kind, sent, left in sorted(msgs):  # (heard in the order they arrive, often not the order sent)
        t[0], least = heard, min(least, delay)
        if kind == "ping":
            clock.handlers({"start": None, "ping": lambda r, w: None})["ping"]({"id": 1, "sent": sent}, Said())
            continue
        w = Said()
        clock.renew({"id": 1, "run": run, "fence": 1, "left": left, "sent": sent}, w)
        expires_here = sent + left - off                 # the engine's expiry on the worker's clock
        got = _lease(path)
        assert w.frames == [] and expires_here - 1e-9 <= got <= expires_here + least + 1e-9, (got, expires_here, least)
        checked += 1
    assert checked > 100


def test_a_time_of_day_an_hour_off_changes_nothing(tmp_path, monkeypatch, bare):
    lc, d = bare
    clock = lc.Clock(str(tmp_path))
    run, path = _run(tmp_path, d)
    real_time, real_ns, real_get = time.time, time.time_ns, time.clock_gettime
    for jump in (0, 3600, -3600):
        monkeypatch.setattr(time, "time", lambda j=jump: real_time() + j)
        monkeypatch.setattr(time, "time_ns", lambda j=jump: real_ns() + int(j * 1e9))
        monkeypatch.setattr(time, "clock_gettime",
                            lambda c, j=jump: real_get(c) + (j if c == time.CLOCK_REALTIME else 0))
        clock.renew({"id": 1, "run": run, "fence": 1, "left": 30, "sent": time.monotonic()}, Said())
        assert abs(_lease(path) - (d.now() + 30)) < 0.2, jump
    assert d.CLOCK != time.CLOCK_REALTIME


def test_a_delayed_renewal_does_not_extend(tmp_path, bare):
    lc, d = bare
    t = [100.0]
    clock = lc.Clock(str(tmp_path), now=lambda: t[0])
    run, path = _run(tmp_path, d)
    off = -50.0                                          # (engine = worker + off; transit 0.01 s, then one of 5 s)

    def renew(sent_at: float, transit: float, expiry: float) -> float:
        t[0] = sent_at + transit
        clock.renew({"id": 1, "run": run, "fence": 2, "left": expiry - sent_at, "sent": sent_at + off}, Said())
        return _lease(path)

    first = renew(100.0, 0.01, 120.0)
    assert first == pytest.approx(120.01)
    assert renew(101.0, 5.0, 120.0) == pytest.approx(first)      # the same expiry, heard 5 s late: no later
    assert renew(107.0, 0.01, 112.0) == pytest.approx(112.01)    # the same fence may move it earlier...
    assert renew(108.0, 0.01, 130.0) == pytest.approx(130.01)    # ...or later


def test_an_older_fence_is_ignored(tmp_path, bare):
    lc, d = bare
    clock = lc.Clock(str(tmp_path))
    run, path = _run(tmp_path, d)
    started = []
    h = clock.handlers({"start": lambda r, w: started.append(r["run"]), "ping": None})
    h["start"]({"id": 1, "run": run, "lease": {"fence": 3, "ttl": 10, "left": 100, "sent": time.monotonic()}}, Said())
    assert started == [run]
    before = open(path).read()

    def renew(fence: int, left: float, r: str = run) -> list:
        w = Said()
        h["renew"]({"id": 2, "run": r, "fence": fence, "left": left, "sent": time.monotonic()}, w)
        return w.frames

    assert renew(2, 5) == [] and open(path).read() == before     # below start's fence: nothing written
    assert renew(4, 50) == [] and json.loads(open(path).read())["fence"] == 4
    held = open(path).read()
    assert renew(3, 5) == [] and open(path).read() == held       # below the fence written: ignored
    assert renew(4, 5) == [] and _lease(path) < d.now() + 6      # the same fence moves it earlier
    bare_run, _ = _run(tmp_path, d, lease=None)
    assert renew(9, 5, bare_run)[0]["why"] == "no lease"         # never a lease on a run started without one
    assert renew(9, 5, uuid.uuid4().hex)[0]["why"] == "no such run"
    with pytest.raises(ValueError):
        renew(True, 5)


@pytest.fixture
def node(tmp_path):
    n = Node(tmp_path)
    yield n
    n.end()


def test_after_a_cut_session_the_keeper_kills_by_the_last_deadline_plus_k(node):
    run, got = node.start(DEAF, limits={"wall": 30},
                          lease={"left": 30, "ttl": 10, "fence": 1, "sent": time.monotonic()})
    assert got["type"] == "started"
    assert node.ask("ping", sent=time.monotonic())["type"] == "pong"
    t0 = time.monotonic()
    node.tell("renew", run=run, fence=1, left=1.0, sent=t0)
    assert node.ask("ping", sent=time.monotonic())["type"] == "pong"     # (the renewal taken: answered in order)
    held = json.loads((node.dir(run) / "deadline").read_text())
    assert held["fence"] == 1 and held["kill"] == 0.25
    assert node.w.close() == 0                          # the worker ended, its session hung up as a cut one's is
    for sig in (signal.SIGHUP, signal.SIGKILL):
        try:
            os.killpg(node.w.p.pid, sig)
        except ProcessLookupError:
            pass
    assert _until((node.dir(run) / "exit").exists, 10)
    took = time.monotonic() - t0
    assert node.exit(run) == {"code": -signal.SIGKILL, "how": "lease"}
    assert 1.0 + 0.25 <= took < 1.0 + 0.25 + 1.5, took
