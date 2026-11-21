"""What upkeep's fault injection found (docs/proposals/upkeep.md §4), each fault caused here first, then shown mended:
a dead engine, the watchdog's cause and back-off, alarms shown, and the caps."""

import json
import re
import textwrap

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.store import Project

MODEL = """
name: rz
items:
  job:
    id: job/*
    states: [new, done]
    on:
      job.end: done
stocks:
  waiting: {unit: jobs, sensor: {items: job, state: new, every: 1s}}
goals:
  few:
    stock: waiting
    hold: "<= 5"
"""


@pytest.fixture(autouse=True)
def _stopping_cleared():
    yield
    from ergostat import runner
    runner.STOPPING.clear()                              # (an engine closed here stops every run: not the next test's)


def _repo(tmp_path, text: str = MODEL):
    d = tmp_path / "rz"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    return d


# ---- (item 1, the CLI's fallback to the last good model, is on branch resilience)

def test_stop_and_uninstall_work_with_the_yaml_broken(tmp_path, capsys):
    d = _repo(tmp_path)
    p = Project(mdl.load(d))
    (d / "ergostat.yaml").write_text("broken: [\n")
    assert main(["-C", str(d), "run", "--stop"]) == 0
    assert "not running" in capsys.readouterr().out and (p.dir / "stopped").exists()


# ---- 2. a dead engine restarted

@pytest.fixture
def at_home(tmp_path, monkeypatch):
    """A temporary HOME, an installed ergostat on PATH, and the service manager's commands recorded, never run: nothing
    is installed here."""

    from ergostat import service
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    bin_ = tmp_path / "tools" / "bin"
    bin_.mkdir(parents=True)
    (bin_ / "python").write_text("")                                     # (the installed one: never run here)
    (bin_ / "ergostat").write_text(f"#!{bin_ / 'python'}\n")
    (bin_ / "ergostat").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{tmp_path / 'nothing'}")
    monkeypatch.setattr("tempfile.gettempdir", lambda: "/no-such-temp")   # (pytest's tmp_path is under the real one)
    ran = []
    monkeypatch.setattr(service, "run", lambda cmds: ran.extend(cmds) or [])
    return ran


def _key(d):
    return Project(mdl.load(d)).dir.name                                  # rz-<hash of the repository>


def test_service_installs_a_launch_agent_in_home_and_uninstalls_it(tmp_path, at_home, capsys):
    import plistlib
    d = _repo(tmp_path)
    assert main(["-C", str(d), "run", "--service", "launchd", "--install", "--no-web"]) == 0
    path = tmp_path / "user" / "Library" / "LaunchAgents" / f"local.ergostat.{_key(d)}.plist"
    plist = plistlib.loads(path.read_bytes())
    py = str(tmp_path / "tools" / "bin" / "python")
    assert plist["ProgramArguments"] == [py, "-m", "ergostat.watcher", "-C", str(d.resolve()), "--no-web"]
    assert plist["KeepAlive"] is True and plist["RunAtLoad"] is True and plist["Label"] == f"local.ergostat.{_key(d)}"
    assert at_home[-1][:2] == ["launchctl", "bootstrap"] and at_home[-1][-1] == str(path)
    assert "installed" in capsys.readouterr().out
    (d / "ergostat.yaml").write_text("broken: [\n")                     # removed with the YAML broken too
    assert main(["-C", str(d), "run", "--service", "launchd", "--uninstall"]) == 0
    assert not path.exists() and at_home[-1][:2] == ["launchctl", "bootout"]


def test_service_prints_by_default_and_installs_a_systemd_user_unit(tmp_path, at_home, capsys):
    d = _repo(tmp_path)
    assert main(["-C", str(d), "run", "--service", "systemd"]) == 0
    unit = tmp_path / "user" / ".config" / "systemd" / "user" / f"ergostat-{_key(d)}.service"
    assert not unit.exists() and not at_home and "Restart=always" in capsys.readouterr().out
    assert main(["-C", str(d), "run", "--service", "systemd", "--install"]) == 0
    text = unit.read_text()
    assert "Restart=always" in text and "ergostat.watcher" in text and "WantedBy=default.target" in text
    assert ["systemctl", "--user", "enable", "--now", unit.name] in at_home


def test_service_refuses_a_worktrees_or_temporary_python(tmp_path, at_home, monkeypatch, capsys):
    venv = tmp_path / "repo" / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text("")
    (venv / "ergostat").write_text(f"#!{venv / 'python'}\n")
    (venv / "ergostat").chmod(0o755)
    monkeypatch.setenv("PATH", str(venv))
    d = _repo(tmp_path)
    assert main(["-C", str(d), "run", "--service", "--install"]) == 2
    assert "no installed ergostat" in capsys.readouterr().err and not at_home


def test_service_skips_a_launcher_for_the_next_installed_ergostat(tmp_path, at_home, monkeypatch, capsys):
    import os
    launcher = tmp_path / "launcher"
    launcher.mkdir()
    (launcher / "ergostat").write_text("#!/usr/bin/env python3\nexec something\n")
    (launcher / "ergostat").chmod(0o755)
    monkeypatch.setenv("PATH", f"{launcher}{os.pathsep}{os.environ['PATH']}")
    from ergostat import service
    assert service.python() == str(tmp_path / "tools" / "bin" / "python")
    d = _repo(tmp_path)
    assert main(["-C", str(d), "run", "--install"]) == 2 and "go with --service" in capsys.readouterr().err


def _watched(tmp_path, monkeypatch, rc: int = 0):
    import subprocess

    from ergostat import watcher
    d = _repo(tmp_path)
    p = Project(mdl.load(d))
    started = []
    monkeypatch.setattr(watcher.subprocess, "run",
                        lambda cmd, **kw: started.append(cmd) or subprocess.CompletedProcess(cmd, rc, b"", b"refused"))
    return watcher, d, p, started


def test_the_watcher_starts_a_dead_engine_and_leaves_one_stopped_on_purpose(tmp_path, monkeypatch, capsys):
    watcher, d, p, started = _watched(tmp_path, monkeypatch)
    main(["-C", str(d), "run", "--stop"])                                 # on purpose
    assert watcher.look(d, p.dir, []) is None and not started
    p.events.add("ergostat.started", source="ergostat")                    # started, then killed: nothing said
    (p.dir / "stopped").unlink()                                           # (as a start removes it)
    did = watcher.look(d, p.dir, ["--no-web"])
    assert did["what"] == "dead" and started[-1][-3:] == [str(d), "run", "--no-web"]
    assert p.events.query(n=1, type="ergostat.engine.restarted")[-1]["data"]["what"] == "dead"
    again = watcher.look(d, p.dir, [])                                     # dead again at once: the restart didn't help
    assert again["waiting"] > 0 and len(started) == 1


def test_the_watcher_starts_the_engine_again_after_a_logout_or_shutdown(tmp_path, monkeypatch):
    watcher, d, p, started = _watched(tmp_path, monkeypatch)
    p.events.add("ergostat.started", source="ergostat")
    p.events.add("ergostat.stopped", source="ergostat")                    # closed by a logout's SIGTERM: not on purpose
    assert watcher.look(d, p.dir, [])["what"] == "dead" and started       # at login: started again


def test_the_watcher_records_no_restart_when_the_start_is_refused(tmp_path, monkeypatch):
    watcher, d, p, started = _watched(tmp_path, monkeypatch, rc=2)
    did = watcher.look(d, p.dir, [])
    assert did["failed"] == "refused" and started and not p.events.query(n=1, type="ergostat.engine.restarted")
    assert watcher.look(d, p.dir, [])["waiting"] > 0                       # and backs off


def test_the_watcher_stops_and_starts_an_engine_whose_heartbeat_is_stale(tmp_path, monkeypatch):
    import subprocess
    import sys
    import time

    from ergostat.runner import running_pid
    watcher, d, p, started = _watched(tmp_path, monkeypatch)
    hold = (f"import fcntl, os, time; f = open({str(p.dir / 'run.pid')!r}, 'a+'); fcntl.flock(f, fcntl.LOCK_EX); "
            "f.write(str(os.getpid())); f.flush(); time.sleep(60)")   # run.pid held, as a live engine holds it
    frozen = subprocess.Popen([sys.executable, "-c", hold])
    try:
        for _ in range(200):
            if running_pid(p) == frozen.pid:
                break
            time.sleep(0.05)
        (p.dir / "heartbeat.json").write_text(json.dumps({"pass": time.time() - 300, "pid": frozen.pid}))
        did = watcher.look(d, p.dir, [])
        assert did["what"] == "stale" and did["seconds"] >= 300 and started
        assert frozen.wait(timeout=5) is not None                         # stopped
    finally:
        frozen.kill()


def test_status_says_engine_not_running_last_seen(tmp_path, capsys):
    import time
    d = _repo(tmp_path)
    p = Project(mdl.load(d))
    p.measurements.add("sensor/waiting.sensor", 2, at=time.time() - 400)
    p.events.add("loop.holding", item="few", source="ergostat", at=time.time() - 400)
    (p.dir / "heartbeat.json").write_text(json.dumps({"pass": time.time() - 300, "written": time.time() - 300}))
    main(["-C", str(d), "status"])
    out = capsys.readouterr().out
    assert "engine not running (last seen 5m ago)" in out and "loops as last seen" in out
    assert re.search(r"^few\s+was \w+", out, re.M)                    # its status as it was, never as now


# ---- 3. the watchdog finds the cause and backs off

def test_a_stall_dump_names_the_thread_holding_the_index_lock_with_its_stack(tmp_path):
    import threading

    from ergostat.spec import watchdog as wd
    from ergostat.spec.itemindex import index_for
    d = _repo(tmp_path)
    p = Project(mdl.load(d))
    p.events.add("job.made", item="job/1")
    ix = index_for(p.events, p.model.spec, False)
    held, go = threading.Event(), threading.Event()

    def hold_it_here():
        with ix.lock:
            held.set()
            go.wait(10)
    t = threading.Thread(target=hold_it_here, name="the-holder")
    t.start()
    try:
        held.wait(5)
        path = wd.dump(p.dir, "pass")
        text = open(path).read()
        assert "its lock held by thread the-holder" in text and "hold_it_here" in text
    finally:
        go.set()
        t.join()


def test_restarts_that_do_not_help_back_off_exponentially_capped(tmp_path):
    from ergostat import restarts
    t = 1_000_000.0
    assert restarts.wait(tmp_path, t) == (0.0, 1)
    assert restarts.note(tmp_path, "pass", "watchdog", t) == 1
    assert restarts.wait(tmp_path, t + 30) == (30.0, 2)                    # did not help: 60 s after it
    gaps = []
    for _ in range(8):
        left, n = restarts.wait(tmp_path, t + 1)
        t += 1 + left
        restarts.note(tmp_path, "pass", "watchdog", t)
        gaps.append(round(left + 1))
    assert gaps == [60, 120, 240, 480, 960, 1800, 1800, 1800]
    assert restarts.wait(tmp_path, t + 4000) == (0.0, 1)                  # it helped: at once again


def test_the_watchdog_backs_off_a_restart_and_does_it_when_its_turn_comes(tmp_path):
    import threading
    import time
    from types import SimpleNamespace

    from ergostat import restarts
    from ergostat.spec import watchdog as wd
    said = []
    e = SimpleNamespace(p=SimpleNamespace(dir=tmp_path, events=SimpleNamespace(add=lambda *a, **k: None)),
                        passed_at=time.monotonic() - 100, pool_lock=threading.Lock(), pool_out={}, pool_done_at=0.0,
                        say=said.append, wedged=None, restart_hard=None)
    restarts.note(tmp_path, "before", "watchdog")                          # a restart just now that did not help
    w = wd.Watchdog(e)
    w.restart("no pass for 100s", "pass")
    assert e.wedged is None and w.held and any("backed off" in s for s in said)
    w.look(w.held[0] + 1)                                                  # its turn
    assert e.wedged == "no pass for 100s"


def test_a_hang_while_starting_is_restarted_after_the_deadline(tmp_path):
    import threading

    from ergostat.spec import watchdog as wd
    before = set(threading.enumerate())
    restarted, said = [], []
    wd.startup(tmp_path, said.append, restarted.append, deadline=0.2)
    fine = wd.startup(tmp_path / "x", said.append, restarted.append, deadline=30)   # finished long before it
    fine.set()
    for t in set(threading.enumerate()) - before:     # each watcher done: the hung one restarted, the fine one not
        if t.name == "ergostat-startup":
            t.join(60)                                # (the dump runs lsof, slow under load)
    assert restarted == ["not started within 0s"] and any("not started" in s for s in said)
    assert list((tmp_path / "stalls").glob("*-start.txt"))


def test_a_late_reading_from_a_replaced_pool_leaves_the_new_one_alone(tmp_path):
    from ergostat.spec.engine import Engine
    text = ALARMED.replace("{unit: jobs, sensor: {items: job, state: new, every: 1s}}",
                           "{unit: jobs, sensor: {run: echo 4, every: 1s}}")
    p = Project(mdl.load(_repo(tmp_path, text)))
    e = Engine(p, say=lambda s: None)
    try:
        s = p.model.spec.sensors()[0]
        e.alarm_pool_out[s.series] = (200.0, 30.0, None)                  # handed again to a fresh pool
        e._read_one(s, "alarm_", 100.0)                                     # the old pool's, late
        assert e.alarm_pool_out[s.series] == (200.0, 30.0, None)
        e._read_one(s, "alarm_", 200.0)
        assert s.series not in e.alarm_pool_out
    finally:
        e.close()


def test_the_alarms_pool_wedged_three_times_restarts_like_the_sensor_pool(tmp_path):
    import threading
    import time
    from types import SimpleNamespace

    from ergostat.spec import watchdog as wd
    now = time.monotonic()
    e = SimpleNamespace(p=SimpleNamespace(dir=tmp_path, events=SimpleNamespace(add=lambda *a, **k: None)),
                        passed_at=now, pool_lock=threading.Lock(), lock=threading.Lock(), reading=set(),
                        pool=None, pool_out={}, pool_done_at=now, alarm_pool=None, alarm_pool_out={},
                        alarm_pool_done_at=0.0, say=lambda s: None, wedged=None, restart_hard=None,
                        wake=threading.Event())
    w = wd.Watchdog(e)
    for i in range(3):                                                    # wedged again each time, 200 s apart
        t = now + 200 * i
        e.passed_at = t
        e.alarm_pool_out["sensor/x"] = (t - 100, 5.0, t - 100)
        w.look(t)
    assert e.wedged and "alarms pool wedged 3 times" in e.wedged


def test_a_queued_reading_with_a_long_timeout_does_not_lengthen_the_wedge_limit():
    import threading
    from types import SimpleNamespace

    from ergostat.spec import watchdog as wd
    now = 1000.0
    out = {f"s{i}": (now - 35, 5.0, now - 35) for i in range(8)}          # eight wedged, each with a 5 s timeout
    out["measure"] = (now - 35, 120.0, None)                                # queued behind them: not begun
    e = SimpleNamespace(pool_lock=threading.Lock(), pool_out=out, pool_done_at=0.0)
    assert wd.Watchdog(e).pool_wedged(now) is not None                     # found at STALL, not at 120 s + GRACE


# ---- 4. alarms show

ALARMED = MODEL + """
flows:
  arriving: {to: waiting}
blocks:
  backlog-alarm:
    type: alarm
    in: stock.waiting
    above: 3
"""


def test_an_active_alarm_is_one_line_in_needs_attention_and_marked_on_its_block(tmp_path):
    from ergostat import state as st
    from ergostat.blockdiagram import diagram
    p = Project(mdl.load(_repo(tmp_path, ALARMED)))
    p.measurements.add("block/backlog-alarm", 1.0)
    snap = st.snapshot(p)
    lines = [a for a in st.attention(snap, True, p.model) if a["what"] == "alarm backlog-alarm"]
    assert len(lines) == 1 and lines[0]["level"] == "bad" and "stock.waiting above 3" in lines[0]["says"]
    nodes = {n["id"]: n for n in diagram(p.model, snap)["nodes"]}
    assert nodes["blk:backlog-alarm"]["alarm"] == "raised"
    p.measurements.add("block/backlog-alarm", 0.0)
    snap = st.snapshot(p)
    assert "alarm backlog-alarm" not in {a["what"] for a in st.attention(snap, True, p.model)}
    assert "alarm" not in {n["id"]: n for n in diagram(p.model, snap)["nodes"]}["blk:backlog-alarm"]


def test_an_alarm_block_that_fails_is_no_longer_said_raised(tmp_path):
    import time

    from ergostat.spec.engine import Engine
    p = Project(mdl.load(_repo(tmp_path, ALARMED)))
    e = Engine(p, say=lambda s: None)
    try:
        e.signals["stock.waiting"] = 9.0
        rows: list = []
        e._builtins(time.time(), None, {}, [], rows)
        assert ("block/backlog-alarm", 1.0) in [(r[0], r[2]) for r in rows]
        e.builtins["backlog-alarm"].step = lambda get, now: 1 / 0         # failing
        rows = []
        e._builtins(time.time(), None, {}, [], rows)
        assert ("block/backlog-alarm", 0.0) in [(r[0], r[2]) for r in rows]
    finally:
        e.close()


def test_an_alarms_sensor_is_read_off_the_sensor_pool(tmp_path):
    from ergostat.spec.engine import Engine
    text = ALARMED.replace("{unit: jobs, sensor: {items: job, state: new, every: 1s}}",
                           "{unit: jobs, sensor: {run: echo 4, every: 1s}}")
    p = Project(mdl.load(_repo(tmp_path, text)))
    e = Engine(p, say=lambda s: None)
    try:
        s = p.model.spec.sensors()[0]
        assert s.series in e._alarmed()
        e._begin([s], False, False, True, set())
        assert s.series not in e.pool_out and e.pool is None and e.alarm_pool is not None
    finally:
        e.close()


# ---- 5. caps

def test_block_logs_threads_and_run_log_are_capped(tmp_path):
    from ergostat.storage import MB, parse, rotate, trim
    problems = []
    cfg = parse({"logs": {"block": "1MB", "run": "2MB", "threads": "500KB", "transcripts": "7d"}}, problems)
    assert not problems and cfg.logs == {"block": MB, "run": 2 * MB, "threads": 500 * 1024, "transcripts": 7 * 86400}
    assert parse({"logs": {"block": "lots"}}, problems) and problems
    log = tmp_path / "b.log"
    log.write_bytes(b"x" * 99 + b"\n" + b"line\n" * 400_000)
    trim(log, MB)
    assert MB // 5 - 10 < log.stat().st_size <= MB // 5 and log.read_bytes().startswith(b"line\n")
    run = tmp_path / "run.log"
    with open(run, "a") as writer:                                         # a writer with it open carries on
        writer.write("y" * (2 * MB + 1))
        writer.flush()
        rotate(run, 2 * MB)
        writer.write("after\n")
    assert run.read_text() == "after\n" and (tmp_path / "run.log.1").stat().st_size == 2 * MB + 1


def test_transcripts_json_forgets_old_transcripts(tmp_path):
    import os
    import time

    from ergostat.transcripts import Ingester
    d = _repo(tmp_path)
    p = Project(mdl.load(d))
    old, new = d / "old.jsonl", d / "new.jsonl"
    for f in (old, new):
        f.write_text('{"type": "user", "message": {"content": "hi"}}\n')
    os.utime(old, (time.time() - 40 * 86400,) * 2)
    ing = Ingester(p, p.model.spec)
    assert ing.read("t/1", "old.jsonl", old) == 1                         # first contact: read, however old
    ing.read("t/2", "new.jsonl", new)
    ing._save()
    assert list(json.loads((p.dir / "transcripts.json").read_text())) == [f"t/2\n{new}"]   # the old one forgotten
    assert Ingester(p, p.model.spec).read("t/1", "old.jsonl", old) == 0   # read before: never read again


def test_compact_projects_lists_and_deletes_only_folders_whose_repo_is_gone(tmp_path, home, capsys):
    import shutil
    kept, gone, unmounted = _repo(tmp_path), tmp_path / "gone", tmp_path / "drive" / "rz"
    shutil.copytree(kept, gone)
    shutil.copytree(kept, unmounted)
    for r in (kept, gone, unmounted):
        Project(mdl.load(r))
    shutil.rmtree(gone)
    shutil.rmtree(tmp_path / "drive")                                      # its parent gone too: a drive not mounted
    (home / "no-note").mkdir()                                            # no repo.json: never touched
    before = {x.name for x in home.iterdir()}
    assert main(["compact", "--projects"]) == 0
    out = capsys.readouterr().out
    assert str(gone) in out and str(kept) not in out and str(unmounted) not in out
    assert {x.name for x in home.iterdir()} == before
    assert main(["compact", "--projects", "--yes"]) == 0
    out = capsys.readouterr().out
    assert str(gone) in out and "1 of 1 deleted" in out                   # listed, then deleted
    left = {x.name for x in home.iterdir()}
    assert len(before - left) == 1 and "no-note" in left and len([n for n in left if n.startswith("rz-")]) == 2


# ---- 6. the engine's own hard restart (cli.running._restart_hard): one run of an item at a time, no attempt spent

TAKES = """
name: rz
items:
  job:
    id: job/*
    states: [new, done]
    on:
      job.end: done
  ticket:
    id: ticket/*
    states: [ready, done]
blocks:
  doer:
    type: program
    takes: {kind: job, at: new}
    pool: 2
    run: 'echo "$ERGOSTAT_ITEM $$" >> runs.log; exec sleep 600'
    lease: {ttl: 1m, attempts: 1}
"""
DEAF_BLOCK = """
  deaf:
    type: program
    takes: {kind: ticket, at: ready}
    pool: 1
    lease: {ttl: 1m}
    daemon: {run: python3 deaf.py a}
"""


class _Exec(Exception):
    """The patched ``os.execv``: ergostat would have started its process again here."""


@pytest.fixture
def hard(monkeypatch):
    """``_restart_hard`` on a real engine, its exec patched to record the runs alive at that moment; whatever the test
    started, and the process-wide flags the restart sets, put back."""
    from types import SimpleNamespace

    from ergostat import runner
    from ergostat.cli import running
    from ergostat.daemons import proc

    from .test_daemons_restart import dead
    from .test_leases import wait_for
    monkeypatch.setattr(runner, "keep_lock_across_exec", lambda: {})
    seen: dict = {"pids": []}

    def runs(d):
        f = d / "runs.log"
        return [(x.split()[0], int(x.split()[1])) for x in f.read_text().splitlines()] if f.exists() else []

    def execv(path, argv):                        # (a KILL just sent lands within a moment: polled for at most 1 s)
        seen["alive"] = [(i, pid) for i, pid in runs(seen["d"]) if not wait_for(lambda pid=pid: dead(pid), 1.0)]
        raise _Exec()
    monkeypatch.setattr(running.os, "execv", execv)

    def restart(p, e):
        seen["d"] = p.repo
        with pytest.raises(_Exec):
            running._restart_hard(p, SimpleNamespace(no_web=True, port=None), "test", e)
        return seen
    yield SimpleNamespace(restart=restart, runs=runs, seen=seen)
    import os
    import signal
    for _, pid in runs(seen["d"]) if "d" in seen else []:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    with proc.GROUPS_LOCK:
        proc.CLOSING = False


def test_a_hard_restart_never_leaves_two_runs_of_one_item(tmp_path, hard, monkeypatch):
    """A job made while the restart waits on a daemon deaf to SIGTERM (end_all's whole 3 s): fails when the hard path
    leaves dispatch open (a run of it is alive at the exec, outliving the process; the next engine, finding its lease
    expired, would start a second); the run going before the restart must be dead at the exec too."""
    import time

    from ergostat.daemons import supervise
    from ergostat.leases import TAKEN

    from .test_daemons_restart import DEAF, dead, pids
    from .test_leases import item, start, wait_for
    d = _repo(tmp_path, TAKES + DEAF_BLOCK)
    (d / "deaf.py").write_text(DEAF)
    p = Project(mdl.load(d))
    e = start(p)
    try:
        deaf = pids(d, "a")                                                # (its group: ended by end_all, KILL at 3 s)
        p.events.add("job.made", item="job/1", source="t")
        assert wait_for(lambda: hard.runs(d), 10), "the run before the restart never started"
        end_all, window = supervise.end_all, {}

        def made_in_the_window(wait):
            p.events.add("job.made", item="job/2", source="t")
            t0 = time.monotonic()
            got = end_all(wait)
            window["seconds"] = time.monotonic() - t0
            return got
        monkeypatch.setattr(supervise, "end_all", made_in_the_window)
        seen = hard.restart(p, e)
        assert window["seconds"] > 2, "the deaf daemon did not hold end_all open: no window was tested"
        assert seen["alive"] == [], f"runs alive at the exec (they outlive it): {seen['alive']}"
        assert not p.events.query(n=None, type=TAKEN, item="job/2"), "a lease was taken once stopping had begun"
        assert item(p, "job/2").state == "new"
        assert all(wait_for(lambda x=x: dead(x), 2) for x in deaf), "the deaf daemon outlived the restart"
    finally:
        e.close()


def test_a_hard_restart_spends_no_attempt(tmp_path, hard):
    """A job held by a run when the engine restarts hard (wedged: its run's end never recorded), with one attempt
    allowed: the next engine expires the lease uncounted and it waits to be taken again. Fails, a dead letter, when
    an expiry of a previous engine's run is counted; the next engine's own run's expiry still counts."""
    from ergostat.leases import EXPIRED
    from ergostat.leases.terms import grace
    from ergostat.spec.engine import Engine

    from .test_leases import item, start, wait_for
    d = _repo(tmp_path, TAKES)
    p = Project(mdl.load(d))
    e = start(p)
    try:
        p.events.add("job.made", item="job/1", source="t")
        assert wait_for(lambda: hard.runs(d) and item(p, "job/1").state == "leased", 10)
        e.dispatch.finish = lambda *a, **k: None                           # wedged: nothing it does is recorded
        e.dispatch.give_back = lambda *a, **k: None
        assert hard.restart(p, e)["alive"] == []
    finally:
        e.close()
    lease = item(p, "job/1").fields["lease"]
    assert lease["holder"] and lease["max"] == 1, "the lease is left held, as by an engine that was exec'd"
    after = Engine(Project(mdl.load(d)), say=lambda s: None)                 # the next process's engine
    try:
        late = float(lease["expires"]) + float(lease["ttl"]) + 10          # (no fixed sleep: two looks, a grace apart)
        after.dispatch.watch(now=late, mono=100.0)
        after.dispatch.watch(now=late, mono=101.0 + grace(float(lease["ttl"])))
        it = item(p, "job/1")
        (ev,) = p.events.query(n=None, type=EXPIRED, item="job/1")
        assert it.state == "new", f"an attempt spent by the restart: {it.state}"
        assert it.fields["lease"]["attempts"] == 0 and it.fields["lease"]["history"][-1]["counted"] is False
        assert ev["data"].get("count") is False and ev["data"]["state"] == "new"
        assert [i.id for i in after.dispatch.ready(after.spec.blocks["doer"], [it], late)] == ["job/1"], "taken again"
        # its own run's lease, silent past its TTL: counted (a dead letter, with one attempt)
        after.dispatch.ours.add("mine")
        p.events.add("ergostat.lease.taken", item="job/1", source="ergostat",
                     data={"run": "mine", "block": "doer", "fence": lease["fence"] + 1, "ttl": 1.0, "max": 1, "back": "new"})
        late = float(item(p, "job/1").fields["lease"]["expires"]) + 10
        after.dispatch.watch(now=late, mono=200.0)
        after.dispatch.watch(now=late, mono=202.0)
        assert item(p, "job/1").state == "dead"
    finally:
        after.close()


def test_compact_projects_skips_a_folder_an_engine_runs_in(tmp_path, home, monkeypatch):
    import shutil

    from ergostat import projects
    gone = _repo(tmp_path)
    p = Project(mdl.load(gone))
    shutil.rmtree(gone)
    monkeypatch.setattr("ergostat.runner.running_pid", lambda project, wait=True: 123 if project.dir == p.dir else None)
    assert projects.orphans() == []


def test_a_lease_kill_reaches_a_detached_child(tmp_path):
    """A run starts a child in a session of its own through a parent that then exits (the child's parent is pid 1, or
    a subreaper, by the time the lease expires): the run's ``Watch`` saw it, so the kill stops it too."""
    from ergostat.leases.kill import KILLED

    from .test_lease_kill import alive, one, pid_in
    from .test_leases import start, wait_for
    kid = ("sh -c 'python3 -c \"import os, time; os.setsid(); open(\\\"kid.pid\\\", \\\"w\\\").write(str(os.getpid())); "
           "time.sleep(60)\" & until [ -s kid.pid ]; do sleep 0.1; done; sleep 1; touch gone'; sleep 60")
    p = one(tmp_path, kid, lease="{ttl: 5s, attempts: 3}")
    e = start(p)
    other = None
    try:
        other = pid_in(tmp_path / "kid.pid")
        assert wait_for(lambda: (tmp_path / "gone").exists(), 5)
        assert not p.events.query(n=None, type=KILLED), "its parent gone before the kill: the window the test is for"
        got = wait_for(lambda: p.events.query(n=None, type=KILLED), 15)
        assert got, "killed once its lease expired"
        assert wait_for(lambda: not alive(other), 5), "the detached child too, though no longer under the run"
        assert other in got[0]["data"]["pids"]
    finally:
        e.close()
        if other and alive(other):
            import os
            import signal
            os.kill(other, signal.SIGKILL)


def test_a_lease_kill_leaves_a_reused_pid_alone(tmp_path, monkeypatch):
    """A pid the run's ``Watch`` saw, now another process's (its start time not the one seen), is never signalled;
    one still the process seen is (lesson-5)."""
    import subprocess
    import threading
    import types

    from ergostat.leases import kill
    from ergostat.library import reap

    from .test_lease_kill import alive
    monkeypatch.setattr(kill, "GRACE", 1.0)
    procs = [subprocess.Popen(["sleep", "30"], start_new_session=True) for _ in range(3)]
    run, seen_child, reused = procs
    said = []
    eng = types.SimpleNamespace(lock=threading.Lock(), live={"r1": run}, say=lambda *a: None,
                                p=types.SimpleNamespace(events=types.SimpleNamespace(add=lambda *a, **k: said.append(k))))
    try:
        run.watch = reap.Watch(run.pid)
        run.watch.look()
        now: dict[int, str] = {}
        reap.tree(now)
        run.watch.started[seen_child.pid] = now[seen_child.pid]           # seen under the run, detached since
        run.watch.started[reused.pid] = "Thu Jan  1 00:00:00 1970"         # seen once; the pid is another's now
        kill._stop(eng, run, "r1", "its lease expired", "ticket/1", 1, "worker")
        run.wait(5)
        seen_child.wait(5)
        assert alive(reused.pid) and reused.poll() is None, "a pid used again is left alone"
        pids = said[0]["data"]["pids"]
        assert run.pid in pids and seen_child.pid in pids and reused.pid not in pids
    finally:
        run.watch.close()
        for x in procs:
            x.kill()
            x.wait()


def test_a_lease_kill_still_stops_the_run_when_ps_fails(tmp_path, monkeypatch):
    """``ps`` failing (``tree`` empty, so the watch knows of nothing live) does not leave the run going (lesson-3): its
    own pid, an unwaited child of this engine and so never another's, is signalled, and its group with it."""
    import os
    import signal
    import subprocess
    import threading
    import types

    from ergostat.leases import kill
    from ergostat.library import reap

    from .test_lease_kill import alive, pid_in
    from .test_leases import wait_for
    monkeypatch.setattr(kill, "GRACE", 1.0)
    run = subprocess.Popen(["sh", "-c", "sleep 30 & echo $! > kid.pid; wait"], cwd=tmp_path, start_new_session=True)
    kid = pid_in(tmp_path / "kid.pid")
    said = []
    eng = types.SimpleNamespace(lock=threading.Lock(), live={"r1": run}, say=lambda *a: None,
                                p=types.SimpleNamespace(events=types.SimpleNamespace(add=lambda *a, **k: said.append(k))))
    monkeypatch.setattr(reap, "tree", lambda started=None: {})
    try:
        run.watch = reap.Watch(run.pid)
        kill._stop(eng, run, "r1", "its lease expired", "ticket/1", 1, "worker")
        assert run.wait(5) is not None, "the run is stopped, though ps saw nothing"
        gone = lambda: not alive(kid) or subprocess.run(["ps", "-o", "stat=", "-p", str(kid)], capture_output=True,  # noqa: E731
                                                        text=True).stdout.strip().startswith("Z")    # (reaped, or a zombie)
        assert wait_for(gone, 5), "and its group with it"
        assert run.pid in said[0]["data"]["pids"]
    finally:
        run.watch.close(look=False)
        if run.poll() is None:
            run.kill()
            run.wait()
        if alive(kid):
            os.kill(kid, signal.SIGKILL)


# ---- 6. a run no longer depends on the engine that started it (docs/roadmap/overnight/rs-detach.md)

def _blocked(tmp_path, run: str, extra: str = ""):
    return Project(mdl.load(_repo(tmp_path, MODEL + textwrap.dedent(f"""
        blocks:
          worker:
            type: program
            run: {json.dumps(run)}
            every: 1h
        """) + extra)))


def _until(cond, seconds: float = 15.0):
    import time
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.02)
    return cond()


def test_a_run_keeps_going_when_its_engine_is_killed(tmp_path):
    import os
    import signal
    import subprocess
    import sys

    from ergostat.spec import runrecord
    marker = tmp_path / "finished"
    p = _blocked(tmp_path, f"echo begun; sleep 1; echo still here; echo done > {marker}")
    engine = subprocess.Popen([sys.executable, "-c", textwrap.dedent("""
        import sys
        from pathlib import Path
        from ergostat import model as mdl
        from ergostat.spec.engine import Engine
        from ergostat.store import Project
        p = Project(mdl.load(Path(sys.argv[1])))
        Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["worker"], "schedule")
        """), str(tmp_path / "rz")])
    rec, pid = None, None
    try:
        found = _until(lambda: [f for f in (p.dir / "runs").glob("*.json")] if (p.dir / "runs").is_dir() else [])
        assert found, "no run record written"
        rec = json.loads(found[0].read_text())
        pid = rec["pid"]
        assert rec["block"] == "worker" and rec["run"] == found[0].stem and rec["lease"] is None and rec["start"]
        assert runrecord.alive(rec) and os.getsid(pid) == pid                    # its own session
        assert _until(lambda: b"begun" in found[0].with_suffix(".out").read_bytes())
        engine.send_signal(signal.SIGKILL)                                      # the engine dies mid-run
        engine.wait(10)
        assert _until(marker.exists), "the run died with its engine"
        assert _until(lambda: found[0].with_suffix(".exit").exists())
        assert found[0].with_suffix(".exit").read_text() == "0\n"               # its exit, written by no engine
        assert found[0].with_suffix(".out").read_text() == "begun\nstill here\n"
        assert _until(lambda: not runrecord.alive(rec))
    finally:
        engine.kill()
        engine.wait()
        if pid and rec and runrecord.alive(rec):
            os.killpg(pid, signal.SIGKILL)


def test_a_detached_runs_output_and_exit_are_recorded_once(tmp_path, monkeypatch):
    from ergostat import runner as old
    from ergostat.spec import runrecord
    from ergostat.spec.engine import Engine
    run = ("printf 'half'; sleep 0.3; echo ' whole'; i=0; while [ $i -lt 1200 ]; do i=$((i+1)); echo line $i; done; "
           "printf 'no newline at the end'; exit 3")
    p = _blocked(tmp_path, run)
    exits = []
    real = runrecord.remove
    monkeypatch.setattr(runrecord, "remove",
                        lambda f: exits.append(f["exit"].read_text() if f["exit"].exists() else None) or real(f))
    e = Engine(p, say=lambda s: None)
    try:
        e.run_block(p.model.spec.blocks["worker"], "schedule")
    finally:
        e.close()
    logged = old.log_path(p, "worker").read_text().splitlines()
    assert logged.count("half whole") == 1                                     # a partial line waits for its rest
    assert [x for x in logged if x.startswith("line ")] == [f"line {i}" for i in range(1, 1201)]   # each once, in order
    assert logged.count("no newline at the end") == 1
    ended = p.events.query(n=None, type="agent.*", item="worker")
    assert [x["type"] for x in ended] == ["agent.started", "agent.failed"]
    assert ended[-1]["data"]["exit"] == 3 and ended[-1]["data"]["note"] == "exited 3"
    assert exits == ["3\n"]                                                    # the wrapper's own record of its exit
    assert not list((p.dir / "runs").iterdir())                                # nothing left to take again


def test_a_runs_timeout_and_stop_still_end_it(tmp_path):
    import threading
    import time

    from ergostat.spec.engine import STOPPED_BY_OWNER, Engine
    p = _blocked(tmp_path, "echo first; sleep 30; echo never", "    timeout: 1s\n")
    e = Engine(p, say=lambda s: None)
    try:
        t0 = time.monotonic()
        e.run_block(p.model.spec.blocks["worker"], "schedule")
        assert time.monotonic() - t0 < 10
        ended = p.events.query(n=1, type="agent.failed", item="worker")[-1]["data"]
        assert ended["note"] == "stopped after its timeout of 1s"
        e.spec.blocks["worker"].timeout = None
        t = threading.Thread(target=e.run_block, args=(e.spec.blocks["worker"], "schedule"))
        t.start()
        assert _until(lambda: "worker" in e.procs)
        assert e.stop_run("worker")
        t.join(10)
        assert not t.is_alive()
        assert p.events.query(n=1, type="agent.ran", item="worker")[-1]["data"]["note"] == STOPPED_BY_OWNER
    finally:
        e.close()


def test_a_run_record_detects_a_reused_pid(tmp_path):
    import os
    import subprocess

    from ergostat.spec import runrecord
    proc = subprocess.Popen(["sleep", "30"])
    try:
        rec = {"pid": proc.pid, "start": runrecord.start_time(proc.pid)}
        assert rec["start"] and runrecord.alive(rec)
        reused = {"pid": os.getpid(), "start": rec["start"]}                  # its pid now another process's
        assert runrecord.start_time(os.getpid()) and not runrecord.alive(reused)
        assert not runrecord.alive({"pid": proc.pid, "start": None})          # its start unread: not taken as it
    finally:
        proc.kill()
        proc.wait()
    assert not runrecord.alive(rec)                                           # ended


@pytest.mark.parametrize("program, state", [
    ("import os, resource, signal\nresource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n"
     "os.kill(os.getpid(), signal.SIGSEGV)\n", "noted"),                       # as `kill -SEGV $$`, no core left
    ("import sys\nsys.exit(7)\n", "open")])                                   # a plain failing exit: the code's to fix
def test_a_run_killed_by_a_core_dumping_signal_is_triaged_as_a_signal(tmp_path, program, state):
    import sys

    from ergostat.repair import FAILURE
    from ergostat.runner import STOPPING
    from ergostat.spec import items as its
    from ergostat.spec.engine import Engine
    d = tmp_path / "rz"
    d.mkdir()
    (d / "crash.py").write_text(program)
    (d / "ergostat.yaml").write_text(textwrap.dedent(f"""\
        name: crash
        blocks:
          crasher: {{type: program, run: {sys.executable} crash.py, every: 1h}}
        uses:
          repair: {{use: repair, with: {{count-every: 1h, approver: person}}}}
        """))
    m = mdl.load(d)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    p = Project(m)
    STOPPING.clear()
    e = Engine(p, say=lambda s: None)
    try:
        e.run_block(p.model.spec.blocks["crasher"], "test")
    finally:
        e.close()
        STOPPING.clear()
    got = its.project(p.events, p.model.spec, FAILURE)
    assert len(got) == 1 and got[0].fields["program"] == "crash.py", got
    assert got[0].fields["exit"] == (128 + 11 if state == "noted" else 7)     # SEGV: the wrapper's 128+N (SPEC §9.1)
    assert got[0].state == state                                              # a signal is never opened (SPEC §12)


@pytest.mark.parametrize("shell", ["sh", "bash", "dash"])
def test_the_run_wrapper_records_the_exit_under_each_shell(tmp_path, shell):
    import shutil
    import subprocess

    from ergostat.spec import runrecord
    path = shutil.which(shell)
    if path is None:
        pytest.skip(f"no {shell} here")
    f = runrecord.files(tmp_path, "r1")
    got = subprocess.run([path, *runrecord.command("echo said; exit 5", f)[1:]], capture_output=True, text=True)
    assert (got.returncode, got.stdout, f["exit"].read_text()) == (5, "said\n", "5\n")
    got = subprocess.run([path, *runrecord.command("exit 0", f)[1:]])
    assert got.returncode == 0 and f["exit"].read_text() == "0\n"
    got = subprocess.run([path, *runrecord.command("kill -TERM $$", f)[1:]])
    assert got.returncode == -15 and f["exit"].read_text() == "143\n"          # ended by a signal: as without it
    import os
    import signal
    tstp = 128 + signal.SIGTSTP                                                # a stop signal's code: never stops the wrapper
    got = subprocess.run([path, *runrecord.command(f"exit {tstp}", f)[1:]], timeout=10, start_new_session=True)
    assert got.returncode == tstp and f["exit"].read_text() == f"{tstp}\n"
    for code in (128 + signal.SIGABRT, 128 + signal.SIGSEGV):                 # a core-dumping signal's code: no crash
        got = subprocess.run([path, *runrecord.command(f"exit {code}", f)[1:]], timeout=10, start_new_session=True)
        assert got.returncode == code and f["exit"].read_text() == f"{code}\n"
        assert runrecord.by_signal(got.returncode)                             # and still filed as a signal's end
    segv = 128 + signal.SIGSEGV                                                # really killed by one: the same code
    got = subprocess.run([path, *runrecord.command("ulimit -c 0; kill -SEGV $$", f)[1:]], timeout=10,
                         start_new_session=True, cwd=tmp_path)
    assert got.returncode == segv and f["exit"].read_text() == f"{segv}\n" and runrecord.by_signal(segv)
    assert not runrecord.by_signal(5) and not runrecord.by_signal(128 + signal.SIGTSTP) and runrecord.by_signal(-15)
    import sys
    import time
    deaf = f"{sys.executable} -c \"import signal, time; signal.signal(15, signal.SIG_IGN); time.sleep(1); print('late')\""
    with open(f["out"], "wb") as out:
        proc = subprocess.Popen([path, *runrecord.command(deaf, f)[1:]], stdout=out, start_new_session=True)
    time.sleep(0.3)
    os.killpg(proc.pid, signal.SIGTERM)                                       # the group told to stop: as a lease's kill
    proc.wait(10)
    assert f["exit"].exists()                                                  # the wrapper lived to write its exit
    assert _until(lambda: f["out"].read_text() == "late\n", 10)               # and the command carried on
