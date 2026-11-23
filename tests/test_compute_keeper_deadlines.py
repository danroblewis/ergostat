"""A node run's wall and lease deadlines, held by its keeper (SPEC §12s.5): ``start`` writes ``runs/RUN/deadline``,
the keeper reads it each quarter second on a clock that counts suspend and ends the run at the earlier deadline
(SIGTERM, SIGKILL after K), its exit's ``how`` saying which. Garbage in the file never extends; a deadline moved
earlier is taken within half a second; the worker gone changes nothing; nor does the time of day. At most 8
processes a test, each group killed at the end."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from ergostat.compute.worker import deadline, keeper
from tests.compute_pipe import WORKER, Node
from tests.compute_pipe import until as _until

DEAF = "trap '' TERM; exec sleep 30"                   # (TERM ignored across the exec: only SIGKILL ends it)


@pytest.fixture
def node(tmp_path):
    n = Node(tmp_path)
    yield n
    n.end()


def _timed(node, run, t0) -> tuple[dict, float]:
    got = node.exit(run, 15)
    return got, time.monotonic() - t0


def test_a_run_past_its_wall_is_killed_how_wall(node):
    t0 = time.monotonic()
    run, got = node.start("exec sleep 30", limits={"wall": 1})
    assert got["type"] == "started"
    held = json.loads((node.dir(run) / "deadline").read_text())
    assert held["lease"] is None and held["kill"] == keeper.WALL_GRACE
    assert 0.5 < held["wall"] - deadline.now() <= 1.0     # (on the keeper's clock: its start plus the wall)
    got, took = _timed(node, run, t0)
    assert got == {"code": -signal.SIGTERM, "how": "wall"} and 1.0 <= took < 3.0, (got, took)
    deaf, _ = node.start(DEAF, limits={"wall": 1})      # TERM ignored: SIGKILL after K, still how wall
    t1 = time.monotonic()
    assert node.exit(deaf, 15) == {"code": -signal.SIGKILL, "how": "wall"}
    assert time.monotonic() - t1 >= 1.0 + keeper.WALL_GRACE - 0.3


def test_a_run_whose_lease_passes_is_killed_how_lease(node):
    t0 = time.monotonic()
    run, got = node.start(DEAF, limits={"wall": 30}, lease={"left": 1, "ttl": 10})
    assert got["type"] == "started"
    held = json.loads((node.dir(run) / "deadline").read_text())
    assert held["kill"] == deadline.kill_after(10) == 0.25 and held["wall"] - held["lease"] == pytest.approx(29, abs=0.01)
    got, took = _timed(node, run, t0)
    assert got == {"code": -signal.SIGKILL, "how": "lease"} and 1.25 <= took < 3.0, (got, took)
    for bad in ({"left": 0, "ttl": 10}, {"left": 1}, {"left": True, "ttl": 10}, {"left": 86401, "ttl": 10}, [1]):
        assert node.start("true", lease=bad)[1]["type"] == "error", bad


def _garbage(at: float) -> list[bytes]:
    later = at + 100
    return [b"", b"nonsense", b"{", b"[]", b"\xff\xfe", b"[" * 100000, b'{"wall": "x", "lease": null, "kill": 1}',
            b'{"wall": NaN, "lease": null, "kill": 1}', b'{"wall": 1e999, "lease": 1e999, "kill": 1}',
            b'{"wall": true, "lease": null, "kill": 1}', b'{"wall": 9' + b"9" * 5000 + b', "kill": 1}',
            json.dumps({"wall": later, "lease": at + 3 * 86400, "kill": 1}).encode(),
            json.dumps({"wall": later, "lease": later, "kill": -1}).encode(),
            json.dumps({"wall": later, "lease": later, "kill": 601}).encode(),
            json.dumps({"wall": later, "lease": later}).encode(),
            json.dumps({"wall": later, "lease": None, "kill": 0.25}).encode()]   # (well-formed: never later all the same)


def test_garbage_in_the_deadline_file_never_extends(node):
    t0 = time.monotonic()
    walled, _ = node.start("exec sleep 30", limits={"wall": 1.5})
    leased, _ = node.start("exec sleep 30", limits={"wall": 30}, lease={"left": 1.5, "ttl": 10})
    assert node.pgid(walled) and node.pgid(leased)      # (both going: a keeper never starts on a garbage file)
    stop = threading.Event()

    def scribble():
        while not stop.is_set():
            bad = _garbage(deadline.now())
            for g in bad:                               # each garbage, then the well-formed later one held longer
                for text, wait in ((g, 0.01), (bad[-1], 0.03)):
                    for run in (walled, leased):
                        try:
                            (node.dir(run) / "deadline").write_bytes(text)     # (in place: half-written reads too)
                        except OSError:
                            pass
                    time.sleep(wait)

    t = threading.Thread(target=scribble, daemon=True)
    t.start()
    try:
        assert _until(lambda: (node.dir(walled) / "exit").exists() and (node.dir(leased) / "exit").exists(), 4)
        took = time.monotonic() - t0
    finally:
        stop.set()
        t.join(5)
    assert node.exit(walled)["how"] == "wall" and node.exit(leased)["how"] == "lease"
    assert 1.5 <= took < 3.0, took
    f = node.dir(walled) / "deadline"
    for g in _garbage(deadline.now())[:-1]:             # a keeper given garbage at its start does not start the run
        f.write_bytes(g)
        with pytest.raises(ValueError):
            deadline.Held(str(f))


def test_a_deadline_moved_earlier_takes_effect_within_half_a_second(node):
    for which in ("lease", "wall"):
        run, _ = node.start("exec sleep 30", limits={"wall": 30}, lease={"left": 30, "ttl": 10})
        f, ended = node.dir(run) / "deadline", node.dir(run) / "exit"
        node.pgid(run)
        time.sleep(0.6)
        held = json.loads(f.read_text())
        held[which] = deadline.now()
        deadline.write(str(f), held["wall"], held["lease"], held["kill"])
        t = time.monotonic()
        assert _until(ended.exists, 2)
        took = time.monotonic() - t
        assert node.exit(run) == {"code": -signal.SIGTERM, "how": which} and took < 0.5, (which, took)


def test_with_the_worker_gone_both_deadlines_still_hold(node):
    t0 = time.monotonic()
    walled, _ = node.start("exec sleep 30", limits={"wall": 1.5})
    leased, _ = node.start("exec sleep 30", limits={"wall": 30}, lease={"left": 1.5, "ttl": 10})
    assert node.w.close() == 0                          # the worker has ended (its stdin closed)...
    for sig in (signal.SIGHUP, signal.SIGKILL):         # ...and its session is hung up, as a cut SSH session's is
        try:
            os.killpg(node.w.p.pid, sig)
        except ProcessLookupError:
            pass
    assert not (node.dir(walled) / "exit").exists() and not (node.dir(leased) / "exit").exists()
    assert node.exit(walled) == {"code": -signal.SIGTERM, "how": "wall"}
    assert node.exit(leased) == {"code": -signal.SIGTERM, "how": "lease"}
    assert 1.5 <= time.monotonic() - t0 < 3.5


@pytest.fixture
def bare(monkeypatch):
    """The keeper's modules as its own process loads them: by bare name, the worker's folder first on the path."""
    monkeypatch.syspath_prepend(str(WORKER))
    import deadline as d
    import keeper as k
    yield k, d
    for name in ("keeper", "deadline"):
        sys.modules.pop(name, None)


@pytest.mark.parametrize("jump", [3600, -3600])
def test_a_jump_in_the_time_of_day_changes_nothing(tmp_path, monkeypatch, jump, bare):
    """The keeper in this process, its run a real child, the time of day an hour off a third of a second in."""
    keeper, deadline = bare
    real_time, real_ns, real_get, t0 = time.time, time.time_ns, time.clock_gettime, time.monotonic()

    def off() -> float:
        return jump if time.monotonic() - t0 > 0.3 else 0

    monkeypatch.setattr(time, "time", lambda: real_time() + off())
    monkeypatch.setattr(time, "time_ns", lambda: real_ns() + int(off() * 1e9))
    monkeypatch.setattr(time, "clock_gettime",
                        lambda c: real_get(c) + (off() if c == time.CLOCK_REALTIME else 0))
    assert deadline.CLOCK != time.CLOCK_REALTIME
    d = tmp_path / "run"
    d.mkdir()
    f = str(d / "deadline")
    deadline.write(f, deadline.now() + 1.0, deadline.now() + 30, 0.25)
    p = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        code, how = keeper.keep(str(d), p.pid, None, deadline.Held(f))
        took = time.monotonic() - t0
    finally:
        keeper.group(p.pid, signal.SIGKILL)
    assert (code, how) == (-signal.SIGTERM, "wall") and 1.0 <= took < 1.8, (code, how, took)
