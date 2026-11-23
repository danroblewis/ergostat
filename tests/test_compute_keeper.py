"""A run on a node under its keeper (SPEC §12s.3): ``start`` makes the run's folder and a detached keeper, which
runs it in its own process group and writes its exit; the run outlives the worker's stdin; on Linux a killed keeper
takes its run with it; ``kill`` is SIGTERM then SIGKILL to the whole group; a refusal makes no folder and no
process. At most 8 processes a test, each group killed at the end."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from tests.compute_pipe import Node
from tests.compute_pipe import alive as _alive
from tests.compute_pipe import until as _until


@pytest.fixture
def node(tmp_path):
    n = Node(tmp_path)
    yield n
    n.end()


def test_a_run_reports_its_exit_code(node):
    run, got = node.start('cat; echo oops >&2; pwd > where; exit 3', input="the input\n", env={"X": "y"})
    assert got == {**got, "type": "started", "run": run} and isinstance(got["keeper"], int)
    d = node.dir(run)
    assert node.exit(run) == {"code": 3, "how": "exit"}
    assert (d / "out").read_text() == "the input\n" and (d / "err").read_text() == "oops\n"
    assert Path((d / "cwd" / "where").read_text().strip()).resolve() == (d / "cwd").resolve()
    spec = json.loads((d / "run.json").read_text())
    assert spec["run"] == run and spec["backend"] == "process" and spec["env"] == {"X": "y"}
    assert int((d / "pgid").read_text()) > 1
    run2, _ = node.start('kill -s USR1 $$')            # a run ended by a signal says which
    assert node.exit(run2) == {"code": -signal.SIGUSR1, "how": "USR1"}
    run3, _ = node.start('yes | head -n1')              # the run's signals are not left ignored (SIGPIPE ends yes)
    assert node.exit(run3) == {"code": 0, "how": "exit"}
    assert (node.dir(run3) / "out").read_text() == "y\n" and (node.dir(run3) / "err").read_text() == ""
    (d / "done").write_text("")                         # done: the keeper removes its folder by name, and ends
    assert _until(lambda: not d.exists()) and _until(lambda: not _alive(node.keepers[0]))
    assert node.dir(run2).exists()


def test_closing_the_workers_stdin_leaves_the_run_going(node, tmp_path):
    gate = tmp_path / "gate"
    run, got = node.start(f'while [ ! -e {gate} ]; do sleep 0.05; done; echo went on; exit 7')
    assert got["type"] == "started"
    pid = node.pgid(run)
    assert node.w.close() == 0                          # the worker has ended...
    for sig in (signal.SIGHUP, signal.SIGKILL):         # ...and its session is hung up, as a cut SSH session's is
        try:
            os.killpg(node.w.p.pid, sig)
        except ProcessLookupError:
            pass
    time.sleep(0.5)
    assert _alive(pid) and _alive(got["keeper"]) and not (node.dir(run) / "exit").exists()     # ...the run has not
    gate.write_text("")
    assert node.exit(run) == {"code": 7, "how": "exit"}
    assert (node.dir(run) / "out").read_text() == "went on\n"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the death signal is Linux's")
def test_a_killed_keeper_takes_its_run_with_it(node):
    run, got = node.start("exec sleep 30")
    pid = node.pgid(run)
    assert _until(lambda: _alive(pid) and "sleep" in Path(f"/proc/{pid}/cmdline").read_text())
    os.kill(got["keeper"], signal.SIGKILL)
    assert _until(lambda: not _alive(pid), 5), "the run outlived its keeper"
    assert not (node.dir(run) / "exit").exists()       # (a killed keeper writes nothing: it holds nothing more)


def test_kill_is_term_then_kill_to_the_whole_group(node):
    script = 'sleep 30 & echo $! > child; wait'
    soft, _ = node.start(script)                        # ends at the TERM, its child with it
    hard, _ = node.start(f"trap '' TERM; {script}")     # TERM ignored by all of the group: KILL past the grace
    kids = {}
    for run in (soft, hard):
        f = node.dir(run) / "cwd" / "child"
        assert _until(lambda f=f: f.exists() and f.read_text().strip())
        kids[run] = int(f.read_text())
    t = time.monotonic()
    got = node.ask("kill", run=soft, grace=20, why="t")
    assert (got["type"], got["run"]) == ("stopping", soft)
    assert node.ask("kill", run=hard, grace=1)["type"] == "stopping"
    assert node.exit(soft) == {"code": -signal.SIGTERM, "how": "TERM"} and time.monotonic() - t < 5
    assert node.exit(hard) == {"code": -signal.SIGKILL, "how": "KILL"} and time.monotonic() - t >= 1
    assert _until(lambda: not _alive(kids[soft]) and not _alive(kids[hard]), 5)
    assert node.ask("kill", run=uuid.uuid4().hex)["why"] == "no such run"
    assert node.ask("kill", run=hard, grace=601)["type"] == "error"


def _ours(root: Path) -> list[str]:
    """The processes whose command line names this root (the worker, keepers)."""
    out = subprocess.run(["ps", "-A", "-ww", "-o", "command="], capture_output=True, text=True, timeout=10).stdout
    return [line for line in out.splitlines() if str(root) in line]


def test_each_refusal_makes_no_folder_and_no_process(node):
    runs = node.root / "runs"
    cpus, memory, slots = node.hello["cpus"], node.hello["memory"], node.hello["slots"]
    before = _ours(node.root)
    for run, limits in (("../x", {}), ("A" * 32, {}), ("a" * 31, {}), ("a" * 32 + "\n", {}), (7, {})):
        assert node.ask("start", run=run, command="true", limits=limits)["why"] == "bad name", run
    for limits in ({"cpus": cpus + 1}, {"memory": (memory or 0) + 1}, {"wall": 86401}, {"pids": 0},
                   {"cpus": True}, {"wall": float("inf")}, {"network": "none"}, [1]):
        got = node.ask("start", run=uuid.uuid4().hex, command="true", limits=limits)
        assert got["type"] == "refused" and got["why"] == "limits over the node", limits
    assert not runs.exists() or not [p for p in runs.iterdir() if p.name != ".lock"]
    held = [uuid.uuid4().hex for _ in range(slots)]     # every slot taken by a run with no exit yet
    for run in held:
        (runs / run).mkdir(parents=True)
    run = uuid.uuid4().hex
    assert node.ask("start", run=run, command="true")["why"] == "full"
    assert node.ask("start", run=held[0], command="true")["why"] == "full"
    assert sorted(p.name for p in runs.iterdir() if p.name != ".lock") == sorted(held)
    (runs / held[0] / "exit").write_text('{"code": 0, "how": "exit"}\n')   # one ended: a slot is free again
    assert node.ask("start", run=held[0], command="true")["why"] == "bad name"   # (never made again over it)
    assert _ours(node.root) == before and len(before) == 1
