"""The soak: a running ``ergostat run`` whose model an agent edits 200 times in two minutes, with half-written files,
invalid YAML, missing references, renames, includes added and removed and a sensor deleted and put back, is healthy
after it: the same process, its sensors answering, a pass recent, items folding, the page answering, no stall."""

import json
import os
import random
import socket
import subprocess
import sys
import textwrap
import time
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat.calls.client import call, find
from ergostat.store import Project

EDITS = int(os.environ.get("ERGOSTAT_SOAK_EDITS") or 200)
SPAN = float(os.environ.get("ERGOSTAT_SOAK_SECONDS") or 120)

MAIN = """
name: soak
include:
  - parts/*.yaml
items:
  job:
    id: job/*
    states: [new, doing, done]
    on:
      job.start: doing
      job.end: done
stocks:
  doing:
    unit: jobs
    sensor:
      items: job
      state: doing
      every: 0.5s
goals:
  few-doing:
    stock: doing
    hold: "<= 50"
  enough:
    stock: level
    hold: "<= 20"
blocks:
  ticker:
    type: program
    run: echo 1
    every: 2s
    out: flow.made
"""

PART = """
stocks:
  level:
    unit: things
    sensor:
      run: echo 10
      every: 0.3s
flows:
  made:
    to: level
"""

EXTRA = """
stocks:
  spare:
    unit: things
    sensor:
      run: echo 3
      every: 1s
"""


def _get(url: str, timeout: float = 10.0) -> tuple[int, float, bytes]:
    t = time.monotonic()
    with urllib.request.urlopen(url, timeout=timeout) as r:      # noqa: S310
        return r.status, time.monotonic() - t, r.read()


def _threads(pid: int) -> int:
    if sys.platform == "darwin":
        out = subprocess.run(["ps", "-M", "-p", str(pid)], capture_output=True, text=True).stdout
        return max(0, len(out.splitlines()) - 1)
    try:
        return len(os.listdir(f"/proc/{pid}/task"))
    except OSError:
        return 0


def _write(path, text: str) -> None:
    path.write_text(textwrap.dedent(text))


def _pieces(path, text: str) -> None:
    """As an editor that truncates, then writes: read in between, it is empty, then half written."""
    text = textwrap.dedent(text)
    with open(path, "w") as f:
        f.flush()
        time.sleep(0.05)
        f.write(text[: len(text) // 2])
        f.flush()
        time.sleep(0.1)
        f.write(text[len(text) // 2:])


def _ergostat(repo, *args, **kw):
    return subprocess.run([sys.executable, "-m", "ergostat", "-C", str(repo), *args], capture_output=True, text=True,
                          timeout=60, **kw)


def test_two_hundred_edits_in_two_minutes_leave_the_engine_healthy(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_RELOAD_SETTLE", "0.5")
    repo = tmp_path / "soak"
    (repo / "parts").mkdir(parents=True)
    main, part, extra = repo / "ergostat.yaml", repo / "parts" / "level.yaml", repo / "parts" / "spare.yaml"
    _write(main, MAIN)
    _write(part, PART)
    p = Project(mdl.load(repo))
    p.events.add_many([{"type": "job.made", "item": f"job/{i}"} for i in range(20)], new=True)
    log = open(tmp_path / "run.log", "w")                       # noqa: SIM115
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(repo), "run", "--foreground", "--port", str(port)],
                            stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 60
        while not (p.dir / "web.json").exists() or p.measurements.latest("sensor/level.main") is None:
            assert time.monotonic() < deadline, (tmp_path / "run.log").read_text()
            assert proc.poll() is None, (tmp_path / "run.log").read_text()
            time.sleep(0.2)
        url = json.loads((p.dir / "web.json").read_text())["url"]

        rnd = random.Random(7)
        good_main = textwrap.dedent(MAIN)
        ops = [
            lambda: _write(main, MAIN + f"\n# edit {time.time()}\n"),                       # a plain change
            lambda: _pieces(main, MAIN + f"\n# in pieces {time.time()}\n"),                 # written in pieces
            lambda: main.write_text(good_main[: rnd.randrange(1, len(good_main))]),         # truncated mid-write
            lambda: main.write_text(""),                                                    # truncated, not written yet
            lambda: _write(main, MAIN + "\n  : bad: [yaml\n"),                              # invalid YAML
            lambda: _write(main, MAIN.replace("stock: level", "stock: missing")),           # a missing reference
            lambda: _write(part, PART.replace("level:", "level-renamed:", 1)),              # a part renamed that is used
            lambda: _write(main, MAIN.replace('"<= 20"', f'"<= {rnd.randrange(10, 40)}"')),  # a setpoint moved
            lambda: _write(extra, EXTRA),                                                   # an include added
            lambda: extra.unlink(missing_ok=True),                                          # and removed
            lambda: _write(part, PART.replace("      run: echo 10\n      every: 0.3s\n", "      manual: true\n")),
            lambda: _write(part, PART),                                                     # the sensor back
            lambda: _write(main, MAIN.replace("ticker:", "ticking:")),                      # a block renamed
            lambda: (_write(main, MAIN), _write(part, PART)),                               # all good again
        ]
        began = time.monotonic()
        shown = False
        for i in range(EDITS):
            rnd.choice(ops)()
            if i == EDITS // 2:                              # held broken long enough to be seen
                _write(part, PART)
                _write(main, MAIN.replace("stock: level", "stock: missing"))
                assert _until_true(lambda: (p.dir / "reload.json").exists(), 10), (tmp_path / "run.log").read_text()
                st = _ergostat(repo, "status")
                assert "the edited model has errors (ergostat.yaml:" in st.stdout, st.stdout + st.stderr
                assert "still running the last good version" in st.stdout
                assert "goal enough.stock: 'missing' is not a stock" in st.stdout
                code, _, body = _get(f"{url}/api/status")
                assert code == 200 and "still running the last good version" in json.loads(body)["edited"]["banner"]
                shown = True
            time.sleep(max(0.0, began + SPAN * (i + 1) / EDITS - time.monotonic()))
        assert shown
        _write(main, MAIN)
        _write(part, PART)
        extra.unlink(missing_ok=True)
        ended = time.time()

        assert proc.poll() is None, (tmp_path / "run.log").read_text()
        assert len(p.events.query(n=None, type="ergostat.started")) == 1, "the same runner throughout: no restart"
        assert _until_true(lambda: not (p.dir / "reload.json").exists(), 15), "the fixed model is taken"
        assert _until_true(lambda: (p.measurements.latest("sensor/level.main") or (0,))[0] > ended, 15), "sensors answer"
        ping = call("ping", path=find(repo))
        assert ping["passed"] < 5, ping                      # a pass completed recently
        assert ping["stalls"] == 0
        assert not p.events.query(n=None, type="ergostat.engine.stalled")
        for i in range(3):                                   # items fold, and are counted
            r = _ergostat(repo, "event", "--add", "job.start", "--item", f"job/{i}")
            assert r.returncode == 0, r.stderr
        got = json.loads(_ergostat(repo, "item", "job/2", "--json").stdout)
        assert got["state"] == "doing", got
        assert _until_true(lambda: (p.measurements.latest("stock/doing") or p.measurements.latest("sensor/doing.main")
                                    or (0, 0))[1] >= 3, 15)
        for path in ("status", "items", "graph", "loops"):  # the page answers, promptly
            code, took, _ = _get(f"{url}/api/{path}")
            assert code == 200 and took < 10, (path, took)
        assert _threads(proc.pid) < 300, _threads(proc.pid)
        changes = [e for e in p.events.query(n=None, type="model.changed") if not e["data"].get("first")]
        assert changes, "edits were taken in place"
        text = (tmp_path / "run.log").read_text()
        assert "restarting" not in text, text[-3000:]
    finally:
        _ergostat(repo, "run", "--stop")
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log.close()


def _until_true(cond, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture(autouse=True)
def _cleared():
    yield
    from ergostat import runner
    runner.STOPPING.clear()
