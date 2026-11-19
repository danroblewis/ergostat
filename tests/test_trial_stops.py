"""A try_use trial stops everything it started (author.trial, library/reap.py): a block's run still going when the
trial ends, and what that run started in a session of its own (as a Claude session may be), are gone once the trial
returns; a trial that overruns is stopped with everything under it."""

import os
import sys
import textwrap
import time

from ergostat.library import author

SPAWN = """
import os, subprocess, sys, time
kid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], start_new_session=True)
with open({pids!r}, "a") as f:
    f.write(f"{{os.getpid()}} {{kid.pid}}\\n")
time.sleep(600)
"""


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:                                                  # a zombie (not yet reaped by its parent) is gone
        import subprocess
        st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        return bool(st) and not st.startswith("Z")
    except OSError:
        return True


def gone(pids, within=10.0) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        if not any(alive(p) for p in pids):
            return True
        time.sleep(0.1)
    return False


def test_a_trial_leaves_no_run_and_nothing_a_run_started(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    pids = tmp_path / "pids"
    root = tmp_path / "p"
    root.mkdir()
    (root / "spawn.py").write_text(SPAWN.format(pids=str(pids)))
    (root / "ergostat.yaml").write_text(textwrap.dedent(f"""\
        name: p
        systems:
          s: {{}}
        stocks:
          q: {{unit: x, system: s, sensor: {{run: echo 1, every: 1s}}}}
        flows:
          out: {{from: q, system: s}}
        blocks:
          worker: {{type: program, system: s, every: 1s, timeout: 10m, run: "{sys.executable} spawn.py", out: flow.out}}
        """))
    try:
        got = author.trial(root, "s", 4, blocks=False)
        assert got["check"]["ok"], got
        started = [int(x) for line in pids.read_text().splitlines() for x in line.split()]
        assert started, got
        assert gone(started), [p for p in started if alive(p)]
    finally:
        for line in (pids.read_text().splitlines() if pids.exists() else []):
            for x in line.split():
                try:
                    os.kill(int(x), 9)
                except OSError:
                    pass


def test_a_trial_that_overruns_is_stopped_with_everything_under_it(tmp_path):
    pids = tmp_path / "pids"
    script = tmp_path / "spawn.py"
    script.write_text(SPAWN.format(pids=str(pids)))
    began = time.monotonic()
    p = author.run_trial([sys.executable, str(script)], dict(os.environ), tmp_path, 2)
    assert time.monotonic() - began < 30
    assert "overran" in p.stderr
    started = [int(x) for x in pids.read_text().split()]
    try:
        assert gone(started), [x for x in started if alive(x)]
    finally:
        for x in started:
            try:
                os.kill(x, 9)
            except OSError:
                pass
