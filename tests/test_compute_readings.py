"""A node run's CPU and memory as readings (SPEC §12s.3, *Readings*): a CPU burn's seconds and an allocation's peak are
in its ``ended``, the latest in each ``beat``, with the keys a local run's resources carry; one thread samples every
run. At most 8 processes a test, each group killed at the end."""

from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from ergostat.costs import sampler as local
from tests.compute_pipe import WORKER, Pipe, image_python
from tests.test_compute_keeper import Node, _until

PY = image_python()


class Beating(Node):
    """The keeper tests' node, beating every half second."""

    def __init__(self, tmp: Path):
        self.root, self.keepers, self.n = tmp / "r", [], 0
        self.w = Pipe([PY, "-I", str(WORKER), "--stdio", "--root", str(self.root), "--beat", "0.5"],
                      env={**os.environ, "HOME": str(tmp)})
        self.hello = self.w.read()
        assert self.hello["type"] == "hello", self.w.stderr()

    def start(self, command: str, **fields):
        run, got = super().start(command, **fields)
        assert got["type"] == "started", got
        return run, got


@pytest.fixture
def node(tmp_path):
    n = Beating(tmp_path)
    yield n
    n.end()


def _ended(node, run: str, timeout: float = 30.0) -> tuple[dict, list[dict]]:
    """The run's ``ended``, and every beat on the way."""
    beats, end = [], time.monotonic() + timeout
    while time.monotonic() < end:
        f = node.w.read(end - time.monotonic())
        assert f is not None, node.w.stderr()
        if f["type"] == "beat":
            beats.append(f)
        if f["type"] == "ended" and f["run"] == run:
            return f, beats
    raise AssertionError(f"no ended for {run}")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="what the keeper reaped is read from /proc only; "
                    "elsewhere the sampled sum may miss the last second (SPEC §12s.3)")
def test_a_two_second_cpu_burn_reports_at_least_one_and_a_half(node):
    burn = "import time\nt = time.process_time()\nwhile time.process_time() - t < 2: pass"
    run, _ = node.start(f"{PY} -c '{burn}'")
    ended, beats = _ended(node, run)
    assert ended["code"] == 0 and ended["how"] == "exit"
    assert ended["resources"]["cpu"] >= 1.5, ended
    assert ended["resources"]["method"] == "keeper+sampled", ended     # (exact: what the keeper reaped, not luck)
    assert any(b["runs"].get(run, {}).get("resources", {}).get("samples", 0) >= 1 for b in beats), beats


def test_a_hundred_megabyte_allocation_reports_a_peak_at_least_that(node):
    run, _ = node.start(f"{PY} -c 'import time\nb = bytearray(b\"x\") * (100 << 20)\ntime.sleep(2.5)'")
    ended, _ = _ended(node, run)
    assert ended["code"] == 0 and ended["resources"]["memory_peak"] >= 100 << 20, ended


def test_the_keys_equal_a_local_runs(node):
    run, _ = node.start("sleep 1.5")
    ended, _ = _ended(node, run)
    s = local.Sampler(thread=False)
    p = local.Measured(["sleep", "1.5"], start_new_session=True)
    t = s.track(p)
    time.sleep(0.3)
    s.sample()
    p.wait()
    want = s.finish(t)
    assert set(ended["resources"]) == set(want), (ended["resources"], want)
    assert ended["resources"]["samples"] >= 1 and ended["resources"]["method"] in ("keeper+sampled", "sampled")


class _Writer:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    def send(self, type: str, **fields) -> None:
        self.sent.append((type, fields))


def test_one_thread_samples_four_runs(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("worker_sampler", WORKER / "sampler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    listings = []
    real = mod.listing
    monkeypatch.setattr(mod, "listing", lambda: listings.append(1) or real())
    runs = tmp_path / "runs"
    procs = {}
    for _ in range(4):
        name = uuid.uuid4().hex
        (runs / name).mkdir(parents=True)
        p = subprocess.Popen(["sleep", "30"], start_new_session=True)
        (runs / name / "pgid").write_text(f"{p.pid}\n")
        procs[name] = p
    w, stop = _Writer(), threading.Event()
    r = mod.Readings(str(tmp_path), w)
    before = set(threading.enumerate())
    t = threading.Thread(target=r.loop, args=(stop,), daemon=True)
    t.start()
    try:
        assert _until(lambda: all(v["resources"]["samples"] >= 2 for v in r.latest().values())
                      and len(r.latest()) == 4, 15), r.latest()
        assert set(threading.enumerate()) - before == {t}                    # one thread, not one a run
        assert len(listings) < sum(v["resources"]["samples"] for v in r.latest().values())   # one listing, all four
        for name, p in procs.items():
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            (runs / name / "exit").write_text('{"code": -9, "how": "KILL"}\n')
        assert _until(lambda: len(w.sent) == 4, 10), w.sent
        assert {f["run"] for _, f in w.sent} == set(procs) and {ty for ty, _ in w.sent} == {"ended"}
        assert all(f["resources"]["samples"] >= 2 and f["resources"]["memory_peak"] > 0 for _, f in w.sent)
        assert r.latest() == {}
        time.sleep(2.2)
        assert len(w.sent) == 4                                              # each ended said once
    finally:
        stop.set()
        for p in procs.values():
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
        t.join(5)
