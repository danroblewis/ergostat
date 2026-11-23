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

    calls, real_start = [], st.start_of

    def failed_once(pid):                                    # the look's ps fails; the stop's own reading does not
        calls.append(pid)
        if len(calls) == 1:
            raise st.Unread("ps ended 1")
        return real_start(pid)
    sent, real = [], os.killpg
    monkeypatch.setattr(st, "start_of", failed_once)
    monkeypatch.setattr(st, "GRACE", 0.2)
    monkeypatch.setattr(os, "killpg", lambda p, s: sent.append((p, s)) or real(p, s))
    found = st.States(str(node.root))
    assert found.hello() == [{"run": run, "state": "unknown", "why": "ps failed"}]
    assert until(lambda: (pg, signal.SIGTERM) in sent)      # the worker itself signals the group, its leader read again
    assert {p for p, _ in sent} == {pg}
    assert until(lambda: not alive(pg), 5)
    assert until(lambda: (node.dir(run) / "exit").exists(), 5)
    assert found.look()[run] == {"state": "gone", "code": -signal.SIGTERM, "how": "TERM"}


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


def test_absent_pid_by_group_state(tmp_path, st, monkeypatch):
    """Its pid absent: gone when its group reads empty; a group left holding a process is unknown, and not signalled
    (nothing shows that group is still the run's)."""
    monkeypatch.setattr(st, "GRACE", 0.2)
    sent = []
    monkeypatch.setattr(os, "killpg", lambda p, s: sent.append((p, s)))
    dead, boot = _ended_pid(), st.boot()
    run = _folder(tmp_path, {"pid": dead, "start": "1", "keeper": dead, "keeper_start": "1", "boot": boot}, dead)
    p = subprocess.Popen(["sh", "-c", "sleep 30 >/dev/null 2>&1 & echo $!"], stdout=subprocess.PIPE,
                         start_new_session=True, text=True)
    left = int(p.stdout.readline())                          # its leader ended, one process left in its group
    p.wait()
    try:
        held = _folder(tmp_path, {"pid": p.pid, "start": "1", "keeper": dead, "keeper_start": "1", "boot": boot}, p.pid)
        found = st.States(str(tmp_path))
        assert listed({"runs": found.hello()}, run) == {"run": run, "state": "gone", "code": 127, "how": "keeper gone"}
        assert json.loads((tmp_path / "runs" / run / "exit").read_text()) == {"code": None, "how": "keeper gone"}
        assert not (tmp_path / "runs" / run / "stop").exists()
        assert listed({"runs": found.hello()}, held) == {"run": held, "state": "unknown", "why": "group not empty"}
        assert until(lambda: found.stopping.acquire(blocking=False), 5)      # (the stopping thread has ended)
        assert (tmp_path / "runs" / held / "stop").exists() and sent == [] and alive(left)
    finally:
        os.kill(left, signal.SIGKILL)


def test_reused_pid_stranger_survives(tmp_path, st, monkeypatch):
    """A stranger now leads the run's pid (and so its group): the run's own group is empty, so gone, and the
    stranger is never signalled; nor on its own start time when the record is of another boot."""
    p = subprocess.Popen(["sleep", "30"], start_new_session=True)     # a setsid daemon on the run's old pid
    try:
        sent = []
        monkeypatch.setattr(os, "killpg", lambda g, s: sent.append((g, s)))
        assert until(lambda: st.start_of(p.pid) is not None)
        dead, boot, its = _ended_pid(), st.boot(), st.start_of(p.pid)
        reused = _folder(tmp_path, {"pid": p.pid, "start": "1", "keeper": dead, "keeper_start": "1", "boot": boot},
                         p.pid)
        before = _folder(tmp_path, {"pid": p.pid, "start": its, "keeper": dead, "keeper_start": "1",
                                    "boot": str(uuid.uuid4())}, p.pid)
        found = st.States(str(tmp_path))
        assert listed({"runs": found.hello()}, reused) == {"run": reused, "state": "gone", "code": 127,
                                                           "how": "keeper gone"}
        assert listed({"runs": found.hello()}, before) == {"run": before, "state": "gone", "code": 127,
                                                           "how": "rebooted"}
        assert found.look()[reused]["state"] == "gone" and sent == [] and p.poll() is None
        assert not any((tmp_path / "runs" / r / "stop").exists() for r in (reused, before))

        # Off Linux the boot is kern.bootsessionuuid; a time of day (kern.boottime's form) or a recorded boot that is
        # not a UUID is no boot reading, so never "rebooted".
        odd = _folder(tmp_path, {"pid": p.pid, "start": its, "keeper": dead, "keeper_start": "1", "boot": "old"},
                      p.pid)
        assert st.state(str(tmp_path / "runs" / odd), [None]) == {"state": "unknown", "why": "record unreadable"}
        asked, said = [], [str(uuid.uuid4()).upper()]
        monkeypatch.setattr(st, "LINUX", False)
        monkeypatch.setattr(st.subprocess, "run", lambda argv, **kw: asked.append(argv) or
                            subprocess.CompletedProcess(argv, 0, said[0] + "\n", ""))
        assert st.boot() == said[0] and asked == [["sysctl", "-n", "kern.bootsessionuuid"]]
        said[0] = "{ sec = 1763900000, usec = 0 } Sun Nov 23 10:00:00 2026"
        live = _folder(tmp_path, {"pid": p.pid, "start": its, "keeper": p.pid, "keeper_start": its,
                                  "boot": str(uuid.uuid4())}, p.pid)
        with pytest.raises(st.Unread):
            st.boot()
        assert st.state(str(tmp_path / "runs" / live), [None]) == {"state": "unknown", "why": "ps failed"}
        assert not (tmp_path / "runs" / live / "exit").exists() and sent == []
    finally:
        p.kill()                                             # (os.killpg is the stand-in here)
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
