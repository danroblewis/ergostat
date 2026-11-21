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
    import time

    from ergostat.spec import watchdog as wd
    restarted, said = [], []
    wd.startup(tmp_path, said.append, restarted.append, deadline=0.2)
    fine = wd.startup(tmp_path / "x", said.append, restarted.append, deadline=0.2)
    fine.set()
    deadline = time.monotonic() + 5
    while not restarted and time.monotonic() < deadline:
        time.sleep(0.05)
    time.sleep(0.3)
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
    assert not problems and cfg.logs == {"block": MB, "runs": 50, "run": 2 * MB, "threads": 500 * 1024,
                                         "transcripts": 7 * 86400}
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


def test_compact_projects_skips_a_folder_an_engine_runs_in(tmp_path, home, monkeypatch):
    import shutil

    from ergostat import projects
    gone = _repo(tmp_path)
    p = Project(mdl.load(gone))
    shutil.rmtree(gone)
    monkeypatch.setattr("ergostat.runner.running_pid", lambda project, wait=True: 123 if project.dir == p.dir else None)
    assert projects.orphans() == []
