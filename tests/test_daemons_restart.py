"""Daemons across ergostat's own restarts (SPEC §9.7, *ergostat restarting itself*): before the engine starts its
process again in place (``cli.running._restart``, and ``_restart_hard``, the watchdog's last resort), every daemon's
process group is ended, with no supervisor's lock taken: TERM, one shared deadline of at most 3 s, then KILL.

Each test names the break that makes it fail. "Dead" is ESRCH or a zombie (state Z): a daemon this process spawned
stays unreaped a moment after its KILL, and its orphaned child is reaped by whoever adopts it."""

import os
import signal
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from ergostat import runner
from ergostat.cli import running
from ergostat.daemons import proc, supervise
from ergostat.daemons.proc import Process

from .test_daemons import block
from .test_leases import project, start, wait_for

DEAF = r'''
import os, signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)     # (inherited by its child: neither ends on TERM)
name = sys.argv[1]
kid = subprocess.Popen(["sleep", "600"])          # in its group, as a daemon's helper is
for f, v in ((name + ".kid", kid.pid), (name + ".pid", os.getpid())):
    open(f + ".tmp", "w").write(str(v)); os.replace(f + ".tmp", f)
for _ in sys.stdin:                               # nor on the end of its input
    pass
while True:
    time.sleep(1)
'''


class Exec(Exception):
    """The sentinel the patched ``os.execv`` raises: ergostat would have started again here."""


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    """``proc.CLOSING`` and ``proc.GROUPS`` are process-wide: left as they were found. Anything a test started is
    killed, so a failing test leaves no deaf process behind."""
    before = set(proc.GROUPS)
    monkeypatch.setattr(runner, "keep_lock_across_exec", lambda: {})
    started: list[int] = []
    yield started
    with proc.GROUPS_LOCK:
        proc.CLOSING = False
        proc.GROUPS.intersection_update(before)
    runner.STOPPING.clear()                           # (kill_all sets it)
    for pgid in started:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass


def dead(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] == "Z"
    except OSError:                                   # (no /proc: macOS)
        st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        return not st or st.startswith("Z")


def pids(tmp_path, name: str) -> tuple[int, int]:
    """The deaf daemon's pid and its child's, once it has written both."""
    assert wait_for(lambda: (tmp_path / f"{name}.pid").exists(), 10), f"deaf {name} never started"
    return int((tmp_path / f"{name}.pid").read_text()), int((tmp_path / f"{name}.kid").read_text())


def deaf(tmp_path, name: str, started: list[int]) -> Process:
    """A deaf daemon's process, started directly: in no supervisor's slot."""
    (tmp_path / "deaf.py").write_text(DEAF)
    d = SimpleNamespace(name=name, run=f"python3 deaf.py {name}", warm=False)
    p = Process(d, tmp_path, dict(os.environ), open(tmp_path / f"{name}.log", "a"), lambda s, v: False)
    started.append(p.pid)
    return p


def patched_exec(monkeypatch, watch: list[int]) -> dict:
    """``os.execv`` recorded: called, and whether every pid watched was dead by then (a KILL just sent lands within
    a moment: polled for at most 1 s, where a daemon not sent it lives forever)."""
    seen: dict = {}

    def execv(path, argv):
        seen["called"] = True
        seen["dead"] = {pid: bool(wait_for(lambda pid=pid: dead(pid), 1.0)) for pid in watch}
        raise Exec()
    monkeypatch.setattr(running.os, "execv", execv)
    return seen


ARGS = SimpleNamespace(no_web=True, port=None)


def test_hard_restart_ends_a_deaf_daemon_and_its_child_before_the_exec(tmp_path, monkeypatch, fresh):
    """Fails if _restart does not call end_all (both live: they ignore EOF and TERM), if end_all takes the
    supervisor's lock (it hangs past 6 s), or if only the pid is killed and not the group (the child lives)."""
    (tmp_path / "deaf.py").write_text(DEAF)
    p = project(tmp_path, block("{run: python3 deaf.py a}"))
    e = start(p)
    try:
        pid, kid = pids(tmp_path, "a")
        fresh.append(pid)
        seen = patched_exec(monkeypatch, [pid, kid])
        held, release = threading.Event(), threading.Event()

        def wedge():                                  # the supervisor's lock held throughout, as by what is wedged
            with e.daemons.lock:
                held.set()
                release.wait(30)
        threading.Thread(target=wedge, daemon=True).start()
        assert held.wait(5)
        got: dict = {}

        def hard():
            try:
                running._restart_hard(SimpleNamespace(repo=tmp_path), ARGS, "test")
            except Exec:
                got["exec"] = True
        t0 = time.monotonic()
        t = threading.Thread(target=hard, daemon=True)
        t.start()
        t.join(6)
        took = time.monotonic() - t0
        release.set()
        assert not t.is_alive(), "the hard restart hung: something it called waited on the supervisor's lock"
        assert got.get("exec") and seen.get("called"), "it never reached the exec"
        assert took < 6
        assert seen["dead"] == {pid: True, kid: True}, f"alive at the exec: {seen['dead']}"
    finally:
        e.close()


def test_soft_restart_also_ends_groups_close_left_behind(tmp_path, monkeypatch, fresh):
    """A group no slot holds (a warm process dying, a group whose _kill thread the exec would end), so
    Supervisor.close() never saw it. Fails if end_all reads the supervisor's lists instead of GROUPS."""
    deaf(tmp_path, "b", fresh)
    pid, kid = pids(tmp_path, "b")
    seen = patched_exec(monkeypatch, [pid, kid])
    with pytest.raises(Exec):
        running._restart(SimpleNamespace(repo=tmp_path), ARGS)
    assert seen["dead"] == {pid: True, kid: True}, f"alive at the exec: {seen['dead']}"


def test_a_daemon_spawned_while_the_restart_collects_groups_kills_itself(tmp_path, monkeypatch, fresh):
    """A daemon spawned right after end_all's snapshot (the supervisor's tick, start_all under the start-up
    watchdog). Fails if registration does not check CLOSING under GROUPS_LOCK (lesson-1): the new group escapes."""
    (tmp_path / "deaf.py").write_text(DEAF)
    collect, late = supervise.collect, []

    def then_spawn():
        got = collect()
        late.append(deaf(tmp_path, "late", fresh))
        return got
    monkeypatch.setattr(supervise, "collect", then_spawn)
    supervise.end_all(0.2)
    assert late, "the spawn in the gap never ran"
    pgid = late[0].pid
    assert wait_for(lambda: dead(pgid), 2), "spawned after the snapshot, it escaped the restart"
    assert pgid not in proc.GROUPS


@pytest.mark.serial
def test_end_all_waits_once_for_all_groups_not_once_each(tmp_path, fresh):
    """Fails with a wait per group (three deaf groups at 1 s each: 3 s or more), or without the clamp (an hour)."""
    for n in ("c1", "c2", "c3"):
        deaf(tmp_path, n, fresh)
    watch = [x for n in ("c1", "c2", "c3") for x in pids(tmp_path, n)]
    t0 = time.monotonic()
    supervise.end_all(1.0)
    assert time.monotonic() - t0 < 2.5, "a wait per group, not one shared deadline"
    assert wait_for(lambda: all(dead(x) for x in watch), 2), "a group or a child outlived end_all"

    with proc.GROUPS_LOCK:
        proc.CLOSING = False                          # (else the next spawn kills itself)
    deaf(tmp_path, "c4", fresh)
    pid, kid = pids(tmp_path, "c4")
    t0 = time.monotonic()
    supervise.end_all(3600)
    assert time.monotonic() - t0 < 5, "the wait was not clamped to 3 s"
    assert wait_for(lambda: dead(pid) and dead(kid), 2)


def test_groups_are_forgotten_once_they_end(tmp_path):
    """A daemon crashes, is restarted, and the engine closes: once its _kill threads finish, none of its groups is
    left in GROUPS. Fails if killpg does not remove a group gone (lesson-5: a pgid the OS could reuse)."""
    from .test_daemons import events, setup, starts
    p = setup(tmp_path, block("{run: python3 d.py kids-crash, restart: {max: 50, backoff: [0.2s, 0.2s]}}"))
    e = start(p)
    try:
        assert wait_for(lambda: len(starts(tmp_path)) >= 2 and events(p, "ergostat.daemon.restarted"), 10)
    finally:
        e.close()
    mine = set(starts(tmp_path))
    assert mine
    assert wait_for(lambda: not (mine & proc.GROUPS), 5), f"still kept: {mine & proc.GROUPS}"


def test_a_group_that_cannot_be_signalled_is_dropped_not_retried(monkeypatch):
    """Fails if EPERM is retried until the deadline (2 s here, where it must take well under 1 s) or forever, or is
    left in GROUPS (lesson-3: only "none left" or EPERM drops a group)."""
    real, pgid = os.killpg, 2 ** 22 + 12345            # (above any pid a test spawns here; never really signalled)

    def killpg(g, sig):
        if g == pgid:
            raise PermissionError(1, "Operation not permitted")
        return real(g, sig)
    monkeypatch.setattr(supervise.os, "killpg", killpg)
    with proc.GROUPS_LOCK:
        proc.GROUPS.add(pgid)
    t0 = time.monotonic()
    sent = supervise.end_all(2.0)
    assert time.monotonic() - t0 < 1.0, "a group that cannot be signalled was waited for"
    assert pgid not in sent and pgid not in proc.GROUPS
