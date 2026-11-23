"""A worker started again lists the runs in its root as running, gone or unknown (SPEC §12s.6): gone only on a
reading made, unknown stopped by name, and a sweep that removes only ended run folders of its own name form. At most
6 processes a test, each group killed at the end."""

from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid

import pytest

from tests.compute_pipe import WORKER, alive, until
from tests.test_compute_keeper import Node


@pytest.fixture
def node(tmp_path):
    n = Node(tmp_path, "--beat", "0.1")
    yield n
    n.end()


@pytest.fixture
def st(monkeypatch):
    """The worker's ``states`` module in this process (its siblings by bare name, as on a node)."""
    for m in ("states", "keeper"):
        sys.modules.pop(m, None)
    monkeypatch.syspath_prepend(str(WORKER))
    yield importlib.import_module("states")
    for m in ("states", "keeper"):
        sys.modules.pop(m, None)


def listed(hello: dict, run: str) -> dict:
    return next(r for r in hello["runs"] if r["run"] == run)


def test_running_after_worker_restart(node):
    run, got = node.start("exec sleep 30")
    assert got["type"] == "started"
    assert until(lambda: (node.dir(run) / "proc").exists())
    assert node.w.close() == 0
    node.connect("--beat", "0.1")                           # the worker started again on the same root
    assert listed(node.hello, run) == {"run": run, "state": "running"}
    beat = node.hear("beat")
    assert beat["runs"][run]["state"] == "running"
    assert alive(node.pgid(run)) and not (node.dir(run) / "stop").exists()     # (never stopped)


def test_gone_on_exit_file(node):
    run, _ = node.start("exit 3")
    assert node.exit(run) == {"code": 3, "how": "exit"}
    node.w.close()
    node.connect("--beat", "0.1")
    assert listed(node.hello, run) == {"run": run, "state": "gone", "code": 3, "how": "exit"}


def test_ps_failure_is_unknown_and_stopped(node, st, monkeypatch):
    run, _ = node.start("exec sleep 30")
    pg = node.pgid(run)
    assert until(lambda: (node.dir(run) / "proc").exists())
    node.w.close()

    def failed(pid):
        raise st.Unread("ps ended 1")
    sent, real = [], os.killpg
    monkeypatch.setattr(st, "start_of", failed)
    monkeypatch.setattr(st, "GRACE", 0.2)
    monkeypatch.setattr(os, "killpg", lambda p, s: sent.append((p, s)) or real(p, s))
    found = st.States(str(node.root))
    assert found.hello() == [{"run": run, "state": "unknown", "why": "ps failed"}]
    assert until(lambda: (pg, signal.SIGTERM) in sent)      # the worker itself signals the recorded group
    assert until(lambda: not alive(pg), 5)
    again = found.look()[run]                                # (gone only once its keeper's exit is there to read)
    assert again == ({"state": "gone", "code": -signal.SIGTERM, "how": "TERM"} if (node.dir(run) / "exit").exists()
                     else {"state": "unknown", "why": "ps failed"})


def _folder(root, proc: dict, pgid: int) -> str:
    run = uuid.uuid4().hex
    d = root / "runs" / run
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"run": run}))
    (d / "proc").write_text(json.dumps(proc))
    (d / "pgid").write_text(f"{pgid}\n")
    return run


def _ended_pid() -> int:
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def test_reused_pid_group_empty_gone(tmp_path, st):
    dead = _ended_pid()
    me = os.getpid()                                         # the run's pid now another's: this process, started otherwise
    run = _folder(tmp_path, {"pid": me, "start": "1", "keeper": dead, "keeper_start": "1"}, dead)
    found = st.States(str(tmp_path))
    assert found.hello() == [{"run": run, "state": "gone", "code": 127, "how": "keeper gone"}]
    assert json.loads((tmp_path / "runs" / run / "exit").read_text()) == {"code": None, "how": "keeper gone"}
    assert not (tmp_path / "runs" / run / "stop").exists()


def test_reused_pid_group_alive_unknown(tmp_path, st, monkeypatch):
    p = subprocess.Popen(["sleep", "30"], start_new_session=True)     # the run's group, still holding a process
    try:
        monkeypatch.setattr(st, "GRACE", 0.2)
        run = _folder(tmp_path, {"pid": os.getpid(), "start": "1", "keeper": _ended_pid(), "keeper_start": "1"}, p.pid)
        found = st.States(str(tmp_path))
        assert found.hello() == [{"run": run, "state": "unknown", "why": "group not empty"}]
        assert p.wait(5) == -signal.SIGTERM                   # its group stopped by name
        assert not (tmp_path / "runs" / run / "exit").exists()
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()


def test_sweep_deletes_only_its_own_names(tmp_path, st):
    root, outside = tmp_path / "r", tmp_path / "outside"
    runs = root / "runs"
    runs.mkdir(parents=True)

    def folder(where, *files, old=False):
        where.mkdir()
        for f in files:
            (where / f).write_text("{}")
        if old:
            t = time.time() - 2 * 86400
            os.utime(where / "exit", (t, t))
        return where
    done = folder(runs / uuid.uuid4().hex, "exit", "done")
    aged = folder(runs / uuid.uuid4().hex, "exit", old=True)
    young = folder(runs / uuid.uuid4().hex, "exit")             # ended under a day ago, not done: kept
    going = folder(runs / uuid.uuid4().hex, "done")             # no exit yet: never removed
    other = folder(runs / "not-a-run", "exit", "done")
    upper = folder(runs / uuid.uuid4().hex.upper(), "exit", "done")
    folder(outside, "exit", "done", old=True)
    link = runs / uuid.uuid4().hex
    link.symlink_to(outside)                                    # a run's name pointing out of the root
    assert sorted(st.sweep(str(root))) == sorted([done.name, aged.name])
    assert not done.exists() and not aged.exists()
    assert young.exists() and going.exists() and other.exists() and upper.exists()
    assert link.is_symlink() and (outside / "exit").exists() and (outside / "done").exists()
