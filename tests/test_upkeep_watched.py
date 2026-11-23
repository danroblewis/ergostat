"""``use: upkeep``'s watched loops (SPEC §2a, *Upkeep*): the engine's watchdog and the outer watcher drawn as external
blocks under the goals ``no-stalls`` and ``heartbeat-fresh``, lease expiry and a workspace pool when asked for, and the
heartbeat goal's limit written into ``heartbeat.json`` for the outer watcher, which reads it bounded."""

from __future__ import annotations

import builtins
import fcntl
import io
import json
import os
import textwrap
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat import runner, watcher
from ergostat import upkeep_measures as um
from ergostat.numbers import measures as ms
from ergostat.spec import read
from ergostat.spec import watchdog as wd
from ergostat.spec.ir import heartbeat_stale, is_measure
from ergostat.store import Project

UPKEEP = "uses:\n  upkeep:\n    use: upkeep\n"


def _model(root: Path, with_: str = "", upkeep: bool = True, extra: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    text = f"name: {root.name}\n" + textwrap.dedent(extra)
    if upkeep:
        text += UPKEEP + (f"    with: {{{with_}}}\n" if with_ else "")
    (root / "ergostat.yaml").write_text(text)
    return root / "ergostat.yaml"


def _errors(ps) -> list[str]:
    return [str(p) for p in ps if p.level == "error"]


# ---- the template's parts

def test_upkeep_draws_the_watchdog_and_watcher_as_external_blocks(tmp_path):
    spec, ps = read(_model(tmp_path / "u"))
    assert not _errors(ps), _errors(ps)
    mine = lambda xs: {n for n, x in xs.items() if x.system == "upkeep"}   # noqa: E731
    assert {"heartbeat-age", "stalls", "restarts"} <= mine(spec.stocks)
    builtin = lambda n: [s.builtin for s in spec.stocks[n].sensors.values()]   # noqa: E731
    assert builtin("heartbeat-age") == ["ergostat.upkeep.heartbeat-age"]
    assert builtin("stalls") == ["ergostat.upkeep.stalls"] and builtin("restarts") == ["ergostat.upkeep.restarts"]
    fresh, calm = spec.goals["heartbeat-fresh"], spec.goals["no-stalls"]
    assert (fresh.of.name, fresh.hold.op, fresh.hold.value) == ("heartbeat-age", "<=", 180)
    assert (calm.of.name, calm.hold.op, calm.hold.value) == ("stalls", "<=", 0)
    for name, goal, code in (("watchdog", "no-stalls", "spec/watchdog.py"),
                             ("outer-watcher", "heartbeat-fresh", "watcher.py")):
        b = spec.blocks[name]
        assert b.type == "external" and b.system == "upkeep" and code in b.description
        assert any(r.kind == "goal" and r.name == goal for r in b.reads())
    none = {"overdue-leases", "expired-leases", "free-workspaces", "quarantined-workspaces", "no-overdue-leases",
            "no-quarantined-workspaces", "lease-expiry", "pool-keeper"}
    assert not none & (set(spec.stocks) | set(spec.goals) | set(spec.blocks))      # nothing not asked for
    assert heartbeat_stale(spec) == 180

    found = [f"{p.code}: {p.message}" for p in ps if p.level == "finding" and p.code != "no-modelling-loop"]
    assert not found, "\n".join(found)                                     # every goal served, every block seen
    for b, f in (("watchdog", "stalls-mended"), ("outer-watcher", "heartbeat-renewed")):
        assert f in {r.name for rs in spec.blocks[b].outputs.values() for r in rs}

    spec, ps = read(_model(tmp_path / "a", "leases: true, pool: p"))
    assert not _errors(ps), _errors(ps)
    found = [f"{p.code}: {p.message}" for p in ps if p.level == "finding" and p.code != "no-modelling-loop"]
    assert not found, "\n".join(found)
    assert none <= set(spec.stocks) | set(spec.goals) | set(spec.blocks)
    assert builtin("overdue-leases") == ["ergostat.leases.overdue"]
    assert builtin("expired-leases") == ["ergostat.leases.expired"]
    assert builtin("free-workspaces") == ["ergostat.workspaces.free@p"]
    assert builtin("quarantined-workspaces") == ["ergostat.workspaces.quarantined@p"]
    for g, s in (("no-overdue-leases", "overdue-leases"), ("no-quarantined-workspaces", "quarantined-workspaces")):
        assert (spec.goals[g].of.name, spec.goals[g].hold.op, spec.goals[g].hold.value) == (s, "<=", 0)
    lease, keeper = spec.blocks["lease-expiry"], spec.blocks["pool-keeper"]
    assert lease.type == "external" and "leases/dispatch.py" in lease.description
    assert keeper.type == "person" and "workspaces p --free" in keeper.params["ask"]

    spec, _ = read(_model(tmp_path / "l", "leases: true"))
    assert "lease-expiry" in spec.blocks and "pool-keeper" not in spec.blocks and "free-workspaces" not in spec.stocks


@pytest.mark.parametrize("bad", [59, 3601, '"x"'])
def test_stale_out_of_range_is_a_load_error(tmp_path, bad):
    _, ps = read(_model(tmp_path / "u", f"stale: {bad}"))
    errs = _errors(ps)
    assert errs and all("stale" in e for e in errs), errs


@pytest.mark.parametrize("ok", [60, 3600])
def test_stale_at_its_bounds_loads(tmp_path, ok):
    spec, ps = read(_model(tmp_path / "u", f"stale: {ok}"))
    assert not _errors(ps), _errors(ps)
    assert spec.goals["heartbeat-fresh"].hold.value == ok and heartbeat_stale(spec) == ok


# ---- the measures

def test_heartbeat_age_reads_none_without_a_heartbeat(tmp_path, capsys):
    assert all(is_measure(f"ergostat.upkeep.{n}") for n in ("heartbeat-age", "stalls", "restarts"))
    p, now = SimpleNamespace(dir=tmp_path), 1_000_000.0
    age = lambda: um.heartbeat_age(p, "ergostat.upkeep.heartbeat-age", now=now)   # noqa: E731
    assert age() is None                                                  # no file: no reading, never 0
    for garbled in ("{not json", "[]", '{"pid": 1}', '{"pass": "x"}', '{"pass": true}', '{"pass": NaN}'):
        (tmp_path / "heartbeat.json").write_text(garbled)
        assert age() is None, garbled
    (tmp_path / "heartbeat.json").write_text(json.dumps({"pass": now + 30}))   # stamped in the future: not "fresh"
    assert age() is None
    (tmp_path / "heartbeat.json").write_text(json.dumps({"pass": now - 42.5, "pid": 1}))
    assert age() == 42.5
    (tmp_path / "heartbeat.json").write_text(json.dumps({"pass": time.time() - 42.5}))
    assert 42 <= ms.measure(p, "ergostat.upkeep.heartbeat-age") < 60       # through the measures' dispatch
    assert "cannot be read" in capsys.readouterr().err


def test_stalls_and_restarts_count_their_windows_and_read_none_without_a_log(tmp_path):
    proj = Project(mdl.load(_model(tmp_path / "u").parent))
    now = time.time()
    for at in (now - 100, now - 3000, now - 4000):
        proj.events.add("ergostat.engine.stalled", source="ergostat", at=at)
    for at in (now - 100, now - 80000, now - 90000):
        proj.events.add("ergostat.engine.restarted", source="ergostat", at=at)
    assert ms.measure(proj, "ergostat.upkeep.stalls") == 2                # the last hour
    assert ms.measure(proj, "ergostat.upkeep.restarts") == 2              # the last day

    def boom(**k):
        raise OSError("the log is gone")
    for broken in (SimpleNamespace(events=SimpleNamespace(query=boom)), SimpleNamespace(events=None)):
        assert um.events(broken, "ergostat.upkeep.stalls") is None        # never 0: 0 reads as no-stalls met
        assert um.events(broken, "ergostat.upkeep.restarts") is None


# ---- the outer watcher reads the goal's limit

NOW = 1_000_000.0


def _frozen(tmp_path, monkeypatch, beat: dict | str, age: float):
    """A state folder whose engine (pid 4242, faked alive until it is sent a signal) last passed ``age`` s ago."""
    d = tmp_path / "state"
    d.mkdir(exist_ok=True)
    alive, started = [True], []
    monkeypatch.setattr(runner, "running_pid", lambda *a, **k: 4242 if alive[0] else None)
    monkeypatch.setattr(watcher.os, "kill", lambda pid, sig: alive.__setitem__(0, False))
    monkeypatch.setattr(watcher.subprocess, "run", lambda cmd, **kw: started.append(cmd)
                        or SimpleNamespace(returncode=0, stdout=b"", stderr=b""))
    monkeypatch.setattr(watcher, "_events", lambda d: SimpleNamespace(add=lambda *a, **k: None))
    monkeypatch.setattr(watcher, "_SAID", set())
    if isinstance(beat, dict):
        beat = json.dumps({"pass": NOW - age, "pid": 4242, **beat})
    (d / "heartbeat.json").write_text(beat)
    return d, started


def test_the_watcher_restarts_at_the_goals_limit(tmp_path, monkeypatch):
    d, started = _frozen(tmp_path, monkeypatch, {"stale": 600}, 300)
    assert watcher.look(tmp_path, d, [], now=NOW) is None and not started     # 300 s: past 180, within 600
    d, started = _frozen(tmp_path, monkeypatch, {"stale": 600}, 700)
    did = watcher.look(tmp_path, d, [], now=NOW)
    assert did["what"] == "stale" and did["seconds"] == 700 and started
    assert not (d / "run.log").exists() or "stale 600" not in (d / "run.log").read_text()


BAD = ["0", "-5", "1e9", '"x"', "true", "NaN", "Infinity", "59", "3601", "null", "[600]", None]


@pytest.mark.parametrize("bad", BAD)
def test_a_bad_stale_falls_back_to_the_default(tmp_path, monkeypatch, bad):
    beat = lambda age: f'{{"pass": {NOW - age}, "pid": 4242' + (f', "stale": {bad}}}' if bad else "}")   # noqa: E731
    d, started = _frozen(tmp_path, monkeypatch, beat(100), 100)
    assert watcher.look(tmp_path, d, [], now=NOW) is None and not started     # 100 s: within 180
    assert watcher.look(tmp_path, d, [], now=NOW) is None
    log = (d / "run.log").read_text() if (d / "run.log").exists() else ""
    if bad is None:
        assert "stale" not in log                                           # a model without the template: no fault
    else:
        assert log.count("heartbeat.json's stale") == 1, log               # said once, not every look
    (d / "heartbeat.json").write_text(beat(200))
    did = watcher.look(tmp_path, d, [], now=NOW)
    assert did and did["what"] == "stale" and started                       # 200 s: past 180


def test_the_watcher_reads_only_its_three_files(tmp_path, monkeypatch):
    d = tmp_path / "state"
    d.mkdir()
    held = open(d / "run.pid", "w")                                         # held, as a live engine holds it
    fcntl.flock(held, fcntl.LOCK_EX)
    held.write("4242")
    held.flush()
    seen: list[str] = []
    real_open, real_io, real_stat = builtins.open, io.open, os.stat

    def spy(real):
        def f(path, *a, **k):
            if isinstance(path, str | os.PathLike):
                seen.append(os.path.basename(os.fspath(path)))
            return real(path, *a, **k)
        return f
    started = []
    monkeypatch.setattr(watcher.subprocess, "run", lambda cmd, **kw: started.append(cmd)
                        or SimpleNamespace(returncode=0, stdout=b"", stderr=b""))
    monkeypatch.setattr(watcher, "_events", lambda d: SimpleNamespace(add=lambda *a, **k: None))
    monkeypatch.setattr(watcher.os, "kill", lambda pid, sig: held.close())  # (stopped: its lock let go)
    try:
        (d / "heartbeat.json").write_text(json.dumps({"pass": NOW - 10, "pid": 4242, "stale": 600}))
        with monkeypatch.context() as m:
            m.setattr(builtins, "open", spy(real_open))
            m.setattr(io, "open", spy(real_io))
            m.setattr(os, "stat", spy(real_stat))
            assert watcher.look(tmp_path, d, [], now=NOW) is None
        assert seen and set(seen) <= {"run.pid", "heartbeat.json", "stopped"}, seen
        seen.clear()
        (d / "heartbeat.json").write_text(json.dumps({"pass": NOW - 700, "pid": 4242, "stale": 600}))
        with monkeypatch.context() as m:
            m.setattr(builtins, "open", spy(real_open))
            m.setattr(io, "open", spy(real_io))
            m.setattr(os, "stat", spy(real_stat))
            did = watcher.look(tmp_path, d, [], now=NOW)
        assert did["what"] == "stale" and started
        # acting, it touches only its own back-off (restarts.json) and its log besides; never the model or the record
        own = {"restarts.json" if n.startswith("restarts.json.") and n.endswith(".tmp") else n for n in seen}
        assert own <= {"run.pid", "heartbeat.json", "stopped", "restarts.json", "run.log"}, seen
        assert {"run.pid", "heartbeat.json"} <= set(seen)
    finally:
        held.close()


# ---- the engine writes it, whole

def test_stale_is_dropped_when_the_template_is(tmp_path):
    with_, _ = read(_model(tmp_path / "w", "stale: 600"))
    without, _ = read(_model(tmp_path / "n", upkeep=False, extra="stocks:\n  x:\n    unit: things\n"))
    assert heartbeat_stale(with_) == 600 and heartbeat_stale(without) is None
    eng = SimpleNamespace(p=SimpleNamespace(dir=tmp_path), passed_at=time.monotonic(), spec=with_)
    dog = wd.Watchdog(eng)
    dog.beat()
    assert json.loads((tmp_path / "heartbeat.json").read_text())["stale"] == 600
    eng.spec, dog.beat_at = without, 0.0                                  # the same state, the template removed
    dog.beat()
    got = json.loads((tmp_path / "heartbeat.json").read_text())
    assert "stale" not in got and got["pid"] == os.getpid()
    wd.heartbeat(tmp_path, time.time(), stale=10**6)                      # out of range: never written
    assert "stale" not in json.loads((tmp_path / "heartbeat.json").read_text())


# ---- the heartbeat the run writes as it starts keeps the last model's limit

class _Started(Exception):
    pass


def _start(tmp_path, monkeypatch, previous: str | None) -> Path:
    """Runs ``ergostat run --foreground``'s real start path up to the start-up watchdog (stopped there), over a state
    folder whose ``heartbeat.json`` is ``previous`` (None: none); gives the state folder."""
    from ergostat.cli import running
    root = _model(tmp_path / "u")
    d = Project(mdl.load(root.parent)).dir
    d.mkdir(parents=True, exist_ok=True)
    (d / "heartbeat.json").unlink(missing_ok=True)
    if previous is not None:
        (d / "heartbeat.json").write_text(previous)
    monkeypatch.setattr(runner, "take_lock", lambda p: True)
    monkeypatch.setattr(runner, "running_pid", lambda *a, **k: None)
    monkeypatch.setattr(running.signal, "signal", lambda *a: None)

    def stop(*a, **k):
        raise _Started
    monkeypatch.setattr(wd, "startup", stop)
    args = SimpleNamespace(C=str(root.parent), foreground=True, stop=False, service=False, install=False,
                           uninstall=False, no_web=True, port=None)
    with pytest.raises(_Started):
        running.cmd_run(args)
    return d


def test_start_heartbeat_keeps_previous_stale(tmp_path, monkeypatch):
    d = _start(tmp_path, monkeypatch, json.dumps({"pass": 1.0, "pid": 1, "stale": 900}))
    got = json.loads((d / "heartbeat.json").read_text())
    assert got["stale"] == 900 and got["pid"] == os.getpid() and got["pass"] > 1.0
    assert watcher.limit(d, watcher.beat(d)) == 900


@pytest.mark.parametrize("previous", [None, "{not json", "[900]", '{"pid": 1}', '{"stale": true}', '{"stale": NaN}',
                                      '{"stale": 30}', '{"stale": 60}', '{"stale": 179.9}', '{"stale": 99999}', '{"stale": "600"}',
                                      '{"stale": 1e999}', "[" * 100_000])
def test_start_heartbeat_drops_bad_stale(tmp_path, monkeypatch, previous):
    d = _start(tmp_path, monkeypatch, previous)
    got = json.loads((d / "heartbeat.json").read_text())
    assert "stale" not in got and got["pid"] == os.getpid()
    monkeypatch.setattr(watcher, "_SAID", set())
    assert watcher.limit(d, watcher.beat(d)) == watcher.STALE == 180


def test_start_heartbeat_never_shortens_the_limit_inside_startup(tmp_path, monkeypatch):
    """A previous ``stale`` of 60 to 179 s would let the watcher stop a start still inside its own ``STARTUP`` (120 s)
    deadline; the start takes the watcher's 180 instead, and 180 itself is carried."""
    assert wd.STARTUP < watcher.STALE
    d = _start(tmp_path, monkeypatch, json.dumps({"pass": 1.0, "pid": 1, "stale": 60}))
    assert "stale" not in json.loads((d / "heartbeat.json").read_text())
    assert watcher.limit(d, watcher.beat(d)) == 180
    d = _start(tmp_path / "b", monkeypatch, json.dumps({"pass": 1.0, "pid": 1, "stale": 180}))
    assert json.loads((d / "heartbeat.json").read_text())["stale"] == 180


def test_shard_start_heartbeat_reads_its_own_file(tmp_path):
    (tmp_path / "heartbeat.json").write_text(json.dumps({"pass": 1.0, "pid": 1, "stale": 900}))
    wd.heartbeat(tmp_path, time.time(), shard="a", start=True)
    assert "stale" not in json.loads((tmp_path / "heartbeat.a.json").read_text())    # never the main file's
    (tmp_path / "heartbeat.a.json").write_text(json.dumps({"pass": 1.0, "pid": 1, "stale": 600}))
    wd.heartbeat(tmp_path, time.time(), shard="a", start=True)
    assert json.loads((tmp_path / "heartbeat.a.json").read_text())["stale"] == 600
    assert json.loads((tmp_path / "heartbeat.json").read_text())["stale"] == 900     # the main file untouched
    (tmp_path / "heartbeat.a.json").write_text('{"stale": true}')
    wd.heartbeat(tmp_path, time.time(), shard="a", start=True)
    assert "stale" not in json.loads((tmp_path / "heartbeat.a.json").read_text())


# ---- restarts have a goal, served by the owner

def test_few_restarts_goal_compiles(tmp_path):
    path = _model(tmp_path / "u")
    spec, ps = read(path)
    assert not _errors(ps), _errors(ps)
    g = spec.goals["few-restarts"]
    assert (g.of.name, g.hold.op, g.hold.value, g.system) == ("restarts", "<=", 3, "upkeep")
    keepers = [b for b in spec.blocks.values() if b.type == "person" and b.goal == "few-restarts"]
    assert [b.name for b in keepers] == ["restarts-keeper"] and keepers[0].system == "upkeep"
    found = [f"{p.code}: {p.message}" for p in ps if p.level == "finding" and p.code != "no-modelling-loop"]
    assert not found, "\n".join(found)
    said = [f"{lv}: {msg}" for lv, msg in mdl.check(mdl.load(path.parent)) if lv != "info"]
    assert not [s for s in said if "restart" in s], said
    spec, ps = read(_model(tmp_path / "s", "restarts-most: 0"))
    assert not _errors(ps) and spec.goals["few-restarts"].hold.value == 0


@pytest.mark.parametrize("bad", [101, -1, '"x"'])
def test_restarts_most_bounded(tmp_path, bad):
    _, ps = read(_model(tmp_path / "u", f"restarts-most: {bad}"))
    errs = _errors(ps)
    assert errs and all("restarts-most" in e for e in errs), errs
    with pytest.raises(mdl.ModelError, match="restarts-most"):           # what ergostat check says, refusing it
        mdl.load(tmp_path / "u")


# ---- the protection stays in the code

WATCHED = """
stocks:
  done:
    unit: things
    sensor:
      run: echo 10
      every: 0.2s
      timeout: 1s
goals:
  enough:
    stock: done
    hold: "<= 20"
"""


def _until(cond, seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.mark.serial                     # its stall is 1 s, as in test_watchdog.py
def test_the_watchdog_runs_whatever_the_goals_say(tmp_path, monkeypatch):
    for k, v in (("STALL", 1.0), ("GRACE", 0.5), ("EVERY", 0.1), ("HARD", 0.5)):
        monkeypatch.setattr(wd, k, v)
    from ergostat.spec.engine import Engine
    root = _model(tmp_path / "u", "stale: 3600, watch-every: 1h, count-every: 1h", extra=WATCHED).parent
    p = Project(mdl.load(root))
    assert heartbeat_stale(p.model.spec) == 3600
    e = Engine(p, say=lambda s: None)
    gate, calls = threading.Event(), []
    real = e._read_one

    def wedged(s, *a):
        if s.series.startswith("sensor/done"):
            calls.append(s.series)
            if len(calls) == 1:
                gate.wait(60)                                 # held by something other than its command
        real(s, *a)
    e._read_one = wedged
    stalled = lambda: [x for x in p.events.query(n=None, type="ergostat.engine.stalled")   # noqa: E731
                       if x["data"]["what"] == "pool"]
    try:
        e.start_all()
        assert _until(lambda: calls)
        held_at = time.time()
        assert _until(stalled), "the watchdog did not replace the wedged pool under use: upkeep"
        assert "new sensor pool" in stalled()[0]["data"]["recovery"]
        got = lambda: (p.measurements.latest("sensor/done.main") or [0.0])[0]   # noqa: E731
        assert _until(lambda: got() > held_at)               # read again, by the new pool
    finally:
        gate.set()
        e.close()
        runner.STOPPING.clear()
