"""A run outlives its engine (SPEC §9.1, ``runs: outlive_engine``): it starts under a detached keeper
(``compute/worker/keeper.py``) in its own session, its standard output appended to its journal (``runs/RUN.jsonl``),
which the engine reads. Killing the engine (SIGKILL) or stopping it (``ergostat run --stop``) leaves the run going to
its end, its journal whole and its exit written by its keeper; an explicit stop, a lease's kill and a timeout still end
its whole process group, and ``run --stop --runs`` stops what was left going. A call that only records, made while no
engine answers, goes to the journal."""

import json
import os
import shlex
import signal
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.compute.worker import keeper
from ergostat.leases import kill as lease_kill
from ergostat.spec import runrecord
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = shlex.quote(sys.executable)

MODEL = """
name: o
runs:
  outlive_engine: {on}
stocks:
  done:
    unit: things
flows:
  did:
    to: done
blocks:
  worker:
    type: program
{extra}    run: {run}
    out: flow.did
"""
EVERY = "    every: 1h\n"                                    # (an engine of its own starts it at once)

# What the run prints, in three writes: before the go file, after it, and a last line with no newline. Bytes that are
# not ASCII, a tab, and a line that is not JSON, so "the same" means byte for byte.
FIRST = b'{"event": "thing.begun"}\n'
REST = b'caf\xc3\xa9\tplain text, for the log\n{"out": "flow.did", "moved": 1}\nlast line, no newline'

WORK = """
import os, sys, time
sys.stdin.read()
out = sys.stdout.buffer
out.write(FIRST)
out.flush()
end = time.time() + 60
while not os.path.exists(sys.argv[1]) and time.time() < end:
    time.sleep(0.05)
out.write(REST)
out.flush()
"""

GROUP = """
import json, os, subprocess, sys, time
sys.stdin.read()
kid = subprocess.Popen(["sleep", "60"])
print(json.dumps({"event": "thing.pids", "data": {"run": os.getpid(), "kid": kid.pid}}), flush=True)
time.sleep(60)
"""


@pytest.fixture(autouse=True)
def _stopping_cleared():
    yield
    runner.STOPPING.clear()


def wait_for(cond, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


def project(tmp_path, script: str, on: str = "true", extra: str = "", args: str = "") -> Project:
    (tmp_path / "work.py").write_text(textwrap.dedent(script).replace("FIRST", repr(FIRST)).replace("REST", repr(REST)))
    run = json.dumps(f"{PY} work.py {args}".strip())
    (tmp_path / "ergostat.yaml").write_text(MODEL.replace("{on}", on).replace("{extra}", extra).replace("{run}", run))
    return Project(mdl.load(tmp_path))


def runs_dir(p) -> str:
    return str(p.dir.resolve() / "runs")


def journals(p) -> list[str]:
    d = runs_dir(p)
    return sorted(os.path.join(d, n) for n in os.listdir(d) if n.endswith(".jsonl")) if os.path.isdir(d) else []


def gone(pid: int) -> bool:
    return runrecord.start_time(pid) is None             # (a zombie no one reaps counts as gone)


@pytest.fixture
def keepers(tmp_path):
    """Every keeper the test left, stopped and let go at its end: no run or keeper outlives the test."""
    made: list = []
    yield made.append
    for p in made:
        d = runs_dir(p)
        keeper.stop_all(str(p.dir.resolve()), 0)
        for n in os.listdir(d) if os.path.isdir(d) else []:
            x = os.path.join(d, n)
            if keeper.RUN.fullmatch(n):
                wait_for(lambda x=x: keeper.ended(x) is not None, 10)
                keeper.put(os.path.join(x, "done"), "")
        wait_for(lambda d=d: not os.path.isdir(d) or not any(keeper.RUN.fullmatch(n) for n in os.listdir(d)), 10)


def engine(tmp_path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "run", "--foreground", "--no-web"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def run_going(tmp_path, keepers) -> tuple[Project, subprocess.Popen, str]:
    """An engine in its own process, and its block's run under way: its first line in the journal, and taken."""
    p = project(tmp_path, WORK, extra=EVERY, args=str(tmp_path / "go"))
    keepers(p)
    proc = engine(tmp_path)
    try:
        path = wait_for(lambda: [j for j in journals(p) if open(j, "rb").read() == FIRST], 60)
        assert path, "the run never started, or its first line never reached its journal"
        assert wait_for(lambda: p.events.query(n=1, type="thing.begun")), "the engine reads the journal as it grows"
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    return p, proc, path[0]


def carries_on(p, path: str, tmp_path) -> None:
    """The engine is gone; the run goes on to its end: its journal whole, its exit written by its keeper."""
    name = os.path.basename(path)[:-len(".jsonl")]
    d = os.path.join(runs_dir(p), name)
    assert keeper.ended(d) is None, "the run ended with its engine"
    (tmp_path / "go").write_text("")
    assert wait_for(lambda: keeper.ended(d) is not None), "the run never ended"
    assert json.loads(open(os.path.join(d, "exit")).read()) == {"code": 0, "how": "exit"}
    assert open(path, "rb").read() == FIRST + REST, "the journal is what it printed, byte for byte, in order"
    assert not p.events.query(n=None, type="agent.ran,agent.failed", item="worker"), "no engine recorded its end"


@pytest.mark.slow
def test_a_run_carries_on_to_its_end_when_its_engine_is_killed(tmp_path, keepers):
    """SIGKILL to the engine's whole process group (as a terminal's or a service manager's kill would reach it)."""
    p, proc, path = run_going(tmp_path, keepers)
    os.killpg(proc.pid, signal.SIGKILL)                  # (its own session: the group is the engine's alone)
    proc.wait()
    carries_on(p, path, tmp_path)


@pytest.mark.slow
def test_a_run_carries_on_to_its_end_when_its_engine_is_stopped(tmp_path, keepers):
    p, proc, path = run_going(tmp_path, keepers)
    try:
        got = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "run", "--stop"],
                             capture_output=True, text=True, timeout=60)
        assert got.returncode == 0 and "stopped" in got.stdout, got
        proc.wait(30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert p.events.query(n=1, type="ergostat.stopped"), "a clean stop"
    carries_on(p, path, tmp_path)


def test_the_journal_is_what_the_run_printed_and_the_engine_takes_it_from_there(tmp_path, keepers, monkeypatch):
    """In one engine, to its end: the journal is the run's output byte for byte (kept here as the engine removes it,
    read to its end), its lines are taken in order, the last with no newline too, and its keeper's folder goes."""
    (tmp_path / "go").write_text("")
    p = project(tmp_path, WORK.replace('out.write(REST)', 'out.write(REST + b\'\\n{"event": "thing.last"}\')'),
                args=str(tmp_path / "go"))
    keepers(p)
    seen, remove = {}, runrecord.remove
    monkeypatch.setattr(runrecord, "remove", lambda f: (seen.update(out=f["out"].read_bytes()) if f["out"].exists()
                                                        else None, remove(f))[1])
    e = Engine(p, say=lambda s: None)
    assert e.run_block(p.model.spec.blocks["worker"], "test") == ["did"]
    assert seen["out"] == FIRST + REST + b'\n{"event": "thing.last"}'
    assert [x["type"] for x in p.events.query(n=None) if x["type"].startswith("thing.")] == ["thing.begun", "thing.last"]
    ran = p.events.query(n=1, type="agent.ran", item="worker")
    assert ran and ran[0]["data"]["exit"] == 0 and "note" not in ran[0]["data"]
    assert not journals(p) and wait_for(lambda: not any(keeper.RUN.fullmatch(n) for n in os.listdir(runs_dir(p))), 5)
    log = (p.dir / ran[0]["data"]["log"]).read_text(errors="replace")
    assert "plain text, for the log" in log


@pytest.mark.parametrize("how", ["stop", "lease", "timeout"])
def test_each_way_of_stopping_a_run_ends_its_whole_process_group(tmp_path, keepers, monkeypatch, how):
    p = project(tmp_path, GROUP, extra="    timeout: 2s\n" if how == "timeout" else "")
    keepers(p)
    monkeypatch.setattr(lease_kill, "GRACE", 0.5)
    e = Engine(p, say=lambda s: None)
    t = threading.Thread(target=e.run_block, args=(e.spec.blocks["worker"], "test"), daemon=True)
    t.start()
    said = wait_for(lambda: p.events.query(n=1, type="thing.pids"))
    assert said, "the run never said its pids"
    pids, run = said[0]["data"], said[0]["causedby"]
    assert isinstance(e.live.get(run), keeper.Kept) and not gone(pids["kid"])
    if how == "stop":
        assert e.stop_run("worker")
    elif how == "lease":
        assert lease_kill.kill(e, run, "its lease expired", block="worker")
    t.join(20)
    assert not t.is_alive()
    # Its end is recorded once its group is empty (or 2 s after its process ended): what a group kill ends is gone by
    # now; 3 s more is slack, not a wait for something else to clear it up.
    assert wait_for(lambda: gone(pids["run"]) and gone(pids["kid"]), 3), "something of its group outlived the stop"
    end = p.events.query(n=1, type="agent.ran,agent.failed", item="worker")[0]
    assert end["data"]["note"] == {"stop": "stopped as the owner asked", "lease": "killed: its lease expired",
                                   "timeout": "stopped after its timeout of 2s"}[how]


@pytest.mark.slow
def test_run_stop_runs_stops_what_was_left_going(tmp_path, keepers):
    """``ergostat run --stop --runs``: the engine stopped, and its run left going is stopped through its keeper, the
    whole group (the run and what it started)."""
    p = project(tmp_path, GROUP, extra=EVERY)
    keepers(p)
    proc = engine(tmp_path)
    try:
        said = wait_for(lambda: p.events.query(n=1, type="thing.pids"), 60)
        assert said, "the run never said its pids"
        got = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "run", "--stop", "--runs"],
                             capture_output=True, text=True, timeout=90, env={**os.environ, "ERGOSTAT_KILL_GRACE": "1"})
        proc.wait(30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert got.returncode == 0 and "stopped 1 of 1 runs left going" in got.stdout, got
    pids = said[0]["data"]
    assert wait_for(lambda: gone(pids["run"]) and gone(pids["kid"]), 10)
    name = os.path.basename(journals(p)[0])[:-len(".jsonl")]
    assert json.loads(open(os.path.join(runs_dir(p), name, "exit")).read())["how"] in ("TERM", "KILL")


def test_a_call_that_only_records_goes_to_the_journal_while_no_engine_answers(tmp_path):
    """``event --add`` and ``lease --nack`` from a kept run, with its engine gone (its socket left, nothing listening):
    each line appended to the journal as the run would print it, at once, and the command succeeds."""
    p = project(tmp_path, "pass")
    path = tmp_path / "j.jsonl"
    path.write_bytes(b"half a line")
    env = {**os.environ, "ERGOSTAT_JOURNAL": str(path), "ERGOSTAT_SOCKET": str(tmp_path / "dead.sock"),
           "ERGOSTAT_STATE_DIR": str(p.dir), "ERGOSTAT_RUN": "r1", "ERGOSTAT_ITEM": "thing/1", "ERGOSTAT_LEASE": "3",
           "ERGOSTAT_CALL_RETRY": "600"}
    (tmp_path / "dead.sock").write_text("")              # (a killed engine's socket file: nothing answers it)
    t0 = time.monotonic()
    a = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "event", "--add", "thing.noted",
                        "--item", "thing/1", "--data", '{"n": 1}'], capture_output=True, text=True, env=env, timeout=60)
    b = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "lease", "--nack", "not now",
                        "--after", "30m"], capture_output=True, text=True, env=env, timeout=60)
    assert a.returncode == 0 and b.returncode == 0, (a, b)
    assert time.monotonic() - t0 < 30, "it waited for an engine instead of writing its line"
    assert path.read_bytes() == b'half a line{"event": "thing.noted", "item": "thing/1", "data": {"n": 1}}\n' \
                                b'{"nack": {"why": "not now", "count": true, "after": "1800s"}}\n'
    assert not p.events.query(n=None, type="thing.noted"), "never written to the record behind the journal's back"


def test_the_setting_is_off_by_default_and_a_boolean(tmp_path):
    p = project(tmp_path, "pass")
    assert p.model.spec.outlive_engine is True
    (tmp_path / "ergostat.yaml").write_text((tmp_path / "ergostat.yaml").read_text().replace("runs:\n  outlive_engine: true\n", ""))
    assert mdl.load(tmp_path).spec.outlive_engine is False
    (tmp_path / "ergostat.local.yaml").write_text("runs:\n  outlive_engine: true\n")
    assert mdl.load(tmp_path).spec.outlive_engine is True, "a per-machine setting"
    (tmp_path / "ergostat.local.yaml").write_text("runs:\n  outlive_engine: 1\n")
    with pytest.raises(mdl.ModelError, match="runs.outlive_engine: true or false"):
        mdl.load(tmp_path)


def test_with_the_setting_off_the_engine_stops_its_runs_as_before(tmp_path):
    p = project(tmp_path, GROUP, on="false")
    e = Engine(p, say=lambda s: None)
    t = threading.Thread(target=e.run_block, args=(e.spec.blocks["worker"], "test"), daemon=True)
    t.start()
    said = wait_for(lambda: p.events.query(n=1, type="thing.pids"))
    assert said and not journals(p) and not isinstance(e.live.get(said[0]["causedby"]), keeper.Kept)
    e.close()
    t.join(20)
    assert wait_for(lambda: gone(said[0]["data"]["run"]) and gone(said[0]["data"]["kid"]), 10)
    assert p.events.query(n=1, type="agent.ran", item="worker")[0]["data"]["note"] == runner.STOPPED_WITH_US
