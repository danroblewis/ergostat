"""A model change reaches running work only at run boundaries (SPEC §9.1): the model is swapped in place, a run under
way finishes under the model it started with and its output is taken, new runs start under the new model, goals
switch at once, and only a stop (``ergostat run --stop``) kills what is running."""

import os
import subprocess
import sys
import textwrap
import time

import pytest

from ergostat import history, runner
from ergostat import model as mdl
from ergostat.spec.engine import Engine
from ergostat.store import Project

BASE = """
name: r
stocks:
  done:
    unit: things
    sensor:
      run: echo 10
      every: 0.3s
flows:
  made:
    to: done
goals:
  enough:
    stock: done
    hold: "<= 20"
blocks:
  maker:
    type: program
    run: {run}
    every: {every}
    out: flow.made
"""


@pytest.fixture(autouse=True)
def _stopping_cleared():
    """An engine's close sets the process-wide STOPPING: the tests after these must not see it."""
    yield
    runner.STOPPING.clear()


def write(path, text: str) -> None:
    f = path / "ergostat.yaml"
    before = f.stat().st_mtime_ns if f.exists() else 0
    f.write_text(textwrap.dedent(text))
    if f.stat().st_mtime_ns == before:                   # a clock too coarse to see the edit: move it on
        os.utime(f, ns=(before + 1_000_000, before + 1_000_000))


def until(cond, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


def engine(tmp_path, text: str) -> tuple[Project, Engine]:
    write(tmp_path, text)
    p = Project(mdl.load(tmp_path))
    e = Engine(p, say=lambda s: None)
    e.start_all()
    return p, e


def swap(e: Engine, tmp_path, text: str) -> dict:
    write(tmp_path, text)
    return e.swap(mdl.load(tmp_path))


def test_a_run_under_way_carries_on_and_records_its_version(tmp_path):
    p, e = engine(tmp_path, BASE.format(run="sleep 1.5; echo 5", every="60s"))
    try:
        assert until(lambda: p.events.query(type="agent.started", item="maker"))
        v0 = e.version
        got = swap(e, tmp_path, BASE.format(run="sleep 1.5; echo 5", every="60s").replace('"<= 20"', '"<= 30"'))
        assert got["carried"] == 1 and got["runs"] == ["maker"] and got["version"] != v0
        assert until(lambda: p.events.query(type="agent.ran,agent.failed", item="maker"))
    finally:
        e.close()
    ran = p.events.query(type="agent.ran,agent.failed", item="maker")[0]
    assert ran["type"] == "agent.ran" and ran["data"]["exit"] == 0, ran
    assert ran["data"]["model"] == v0 and ran["data"]["model_now"] == e.version   # it ran across the change
    assert p.events.query(type="agent.started", item="maker")[0]["data"]["model"] == v0
    assert [x["data"]["amount"] for x in p.events.query(type="valve.opened", item="maker")] == [5.0]
    changed = p.events.query(type="model.changed")[-1]["data"]
    assert changed["carried"] == 1 and changed["runs"] == ["maker"] and changed["version"] == e.version
    assert changed["version_before"] == v0 and "goal.enough" not in changed.get("finishing", {}).get("changed", [])


def test_a_page_noticing_the_change_first_leaves_it_to_the_runner(tmp_path):
    import fcntl

    from ergostat.web.server import Live
    p, e = engine(tmp_path, BASE.format(run="sleep 3; echo 5", every="60s"))
    live = Live(Project(p.model, p.dir))                  # the page's own Project, on the same event log
    live.watch.settle = 0
    held = open(runner.pid_file(p), "a+")                # a runner holds run.pid (as `ergostat run` does)
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.write(str(os.getpid()))
        held.flush()
        assert until(lambda: p.events.query(type="agent.started", item="maker"))
        v0 = history.version(p.model)
        edited = BASE.format(run="sleep 3; echo 5", every="60s").replace('"<= 20"', '"<= 30"')
        write(tmp_path, edited)
        assert until(lambda: history.version(live.get().model) != v0)   # the page takes the edit first
        assert len(p.events.query(n=None, type="model.changed")) == 1     # the startup record only: left to the runner
        e.swap(mdl.load(tmp_path))
    finally:
        e.close()
        held.close()
    changes = p.events.query(n=None, type="model.changed")
    assert len(changes) == 2 and changes[-1]["data"]["carried"] == 1 and changes[-1]["data"]["runs"] == ["maker"]
    write(tmp_path, BASE.format(run="sleep 3; echo 5", every="60s"))   # no runner now: the page records it
    assert until(lambda: history.version(live.get().model) == v0)
    assert len(p.events.query(n=None, type="model.changed")) == 3


def test_a_removed_block_finishes_its_run_and_starts_no_more(tmp_path):
    p, e = engine(tmp_path, BASE.format(run="sleep 1.5; echo 5", every="0.3s"))
    try:
        assert until(lambda: p.events.query(type="agent.started", item="maker"))
        gone = BASE.split("blocks:")[0]
        got = swap(e, tmp_path, gone)
        assert got["finishing"] == {"removed": ["maker"]}
        assert until(lambda: p.events.query(type="agent.ran,agent.failed", item="maker"))
        time.sleep(1.5)                                  # its every has come round several times
    finally:
        e.close()
    assert len(p.events.query(type="agent.started", item="maker")) == 1
    ran = p.events.query(type="agent.ran,agent.failed", item="maker")[0]
    assert ran["type"] == "agent.ran" and ran["data"]["exit"] == 0
    assert p.events.query(type="valve.opened", item="maker"), "its flow is still there: what it moved is taken"


def test_the_owner_may_stop_a_run_left_to_finish(tmp_path):
    from ergostat.cli import main
    p, e = engine(tmp_path, BASE.format(run="sleep 30; echo 5", every="60s"))
    try:
        assert until(lambda: p.events.query(type="agent.started", item="maker"))
        swap(e, tmp_path, BASE.split("blocks:")[0])
        assert main(["-C", str(tmp_path), "block", "maker", "--stop"]) == 0      # removed, but its run is still going
        assert until(lambda: p.events.query(type="agent.ran,agent.failed", item="maker"), 5)
    finally:
        e.close()
    ran = p.events.query(type="agent.ran,agent.failed", item="maker")[0]
    assert ran["type"] == "agent.ran" and ran["data"]["note"] == "stopped as the owner asked"
    assert main(["-C", str(tmp_path), "block", "maker", "--stop"]) == 2           # nothing under way now


def test_a_removed_blocks_run_still_takes_messages_while_it_goes(tmp_path):
    from ergostat.messages import route
    p, e = engine(tmp_path, BASE.format(run="sleep 30; echo 5", every="60s"))
    try:
        assert until(lambda: p.events.query(type="agent.started", item="maker"))
        swap(e, tmp_path, BASE.split("blocks:")[0])
        assert [r["block"] for r in route.running(p, e.spec)] == ["maker"]      # live delivery still finds it
    finally:
        e.close()
    assert route.running(p, e.spec) == []


def test_an_output_whose_target_left_the_model_is_recorded_and_refused(tmp_path):
    p, e = engine(tmp_path, BASE.format(run="sleep 1.5; echo 5", every="60s"))
    try:
        assert until(lambda: p.events.query(type="agent.started", item="maker"))
        swap(e, tmp_path, BASE.split("flows:")[0] + "goals:" + BASE.split("goals:")[1].split("blocks:")[0])
        assert until(lambda: p.events.query(type="agent.ran,agent.failed", item="maker"))
    finally:
        e.close()
    ran = p.events.query(type="agent.ran,agent.failed", item="maker")[0]
    assert ran["type"] == "agent.ran" and ran["data"]["refused"] == 1
    why = p.events.query(type="agent.refused", item="maker")[0]["data"]["why"]
    assert "flow.made is no longer in the model" in why
    assert not p.events.query(type="valve.opened")


def test_a_changed_command_starts_under_the_new_definition(tmp_path):
    p, e = engine(tmp_path, BASE.format(run="sleep 1; echo 1", every="0.2s"))
    try:
        assert until(lambda: p.events.query(type="agent.started", item="maker"))
        v0 = e.version
        swap(e, tmp_path, BASE.format(run="echo 2", every="0.2s"))
        assert until(lambda: len(p.events.query(type="valve.opened", item="maker")) >= 2)
    finally:
        e.close()
    amounts = [x["data"]["amount"] for x in p.events.query(type="valve.opened", item="maker")]
    assert amounts[0] == 1.0 and set(amounts[1:]) == {2.0}       # the old run's output, then only the new command's
    runs = p.events.query(type="agent.ran", item="maker")
    assert runs[0]["data"]["model"] == v0 and all(r["data"]["model"] == e.version for r in runs[1:])
    assert p.events.query(type="model.changed")[-1]["data"]["finishing"] == {"changed": ["maker"]}


def test_a_changed_setpoint_applies_at_the_next_tick(tmp_path):
    p, e = engine(tmp_path, BASE.format(run="echo 0", every="60s"))
    try:
        assert until(lambda: p.events.query(type="loop.holding", item="enough"))
        swap(e, tmp_path, BASE.format(run="echo 0", every="60s").replace('"<= 20"', '"<= 5"'))
        assert until(lambda: p.events.query(type="loop.off", item="enough"), 3.0), "the new setpoint holds from the next pass"
        assert e.signals["goal.enough"] == 5
    finally:
        e.close()
    assert len(p.events.query(type="ergostat.started")) == 1                    # no restart


def test_a_kept_builtin_keeps_its_state_and_a_changed_one_takes_it_over(tmp_path):
    text = BASE.format(run="echo 0", every="60s") + textwrap.dedent("""
      count:
        type: counter
        in: goal.enough.off
      late:
        type: timer
        in: goal.enough.off
        after: 100
    """).replace("\n", "\n  ")
    p, e = engine(tmp_path, text)
    try:
        assert until(lambda: "block.count" in e.signals)
        e.builtins["count"].n = 7.0
        e.builtins["late"].since = 123.0
        swap(e, tmp_path, text.replace("after: 100", "after: 200"))
        assert e.builtins["count"].n == 7.0                       # written the same: the same block, kept
        assert e.builtins["late"].p["after"] == 200 and e.builtins["late"].since == 123.0   # bumpless
    finally:
        e.close()


def test_the_legacy_runner_swaps_in_place_too(repo):
    repo.write("clean.py", "import time\ntime.sleep(1.5)\nprint(5)\n")
    p = Project(mdl.load(repo.path))
    r = runner.Runner(p, say=lambda s: None)
    r.start()
    try:
        assert until(lambda: p.events.query(type="agent.started", item="cleaner"))
        v0 = r.version
        repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace("<= 80", "<= 70"))
        got = r.swap(mdl.load(repo.path))
        assert got["carried"] == 1 and got["version"] != v0
        assert until(lambda: p.events.query(type="agent.ran,agent.failed", item="cleaner"))
    finally:
        r.close()
    ran = p.events.query(type="agent.ran,agent.failed", item="cleaner")[0]
    assert ran["type"] == "agent.ran" and ran["data"]["model"] == v0 and "note" not in ran["data"]
    assert history.version(p.model) == r.version


# ---- through ergostat run itself


def ergostat(repo, *args, **kw):
    return subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(repo), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, **kw)


def test_ergostat_run_takes_an_edit_in_place_and_stop_still_kills(tmp_path):
    long = BASE.format(run="sleep 15; echo 5", every="60s")  # the edit, taken once it settles (1.5s), lands inside the run, under load too
    write(tmp_path, long)
    p = Project(mdl.load(tmp_path))
    proc = ergostat(tmp_path, "run", "--foreground", "--no-web")
    try:
        assert until(lambda: p.events.query(type="agent.started", item="maker"), 60)
        write(tmp_path, long.replace('"<= 20"', '"<= 30"'))
        def reloads():
            return [x for x in p.events.query(n=None, type="model.changed") if x["data"].get("reload")]
        assert until(reloads, 60), "the edit was taken in place"
        assert until(lambda: p.events.query(type="agent.ran,agent.failed", item="maker"), 60)
        order = [x["type"] for x in p.events.query(n=None, type="model.changed,agent.ran,agent.failed")
                 if x["type"] != "model.changed" or x["data"].get("reload")]
        assert order == ["model.changed", "agent.ran"], order       # the swap came while the run was under way
        ran = p.events.query(type="agent.ran,agent.failed", item="maker")[0]
        assert ran["type"] == "agent.ran" and ran["data"]["exit"] == 0, ran
        assert [x["data"]["amount"] for x in p.events.query(type="valve.opened", item="maker")] == [5.0]
        changed = reloads()[0]["data"]
        assert changed["carried"] == 1 and changed["runs"] == ["maker"]
        assert len(p.events.query(type="ergostat.started")) == 1 and proc.poll() is None   # the same runner, no restart

        write(tmp_path, BASE.format(run="sleep 30; echo 9", every="0.5s"))   # a long run, then a stop
        assert until(lambda: len(p.events.query(type="agent.started", item="maker")) == 2, 60)
        began = time.monotonic()
        stop = ergostat(tmp_path, "run", "--stop")
        assert stop.wait(60) == 0
        assert until(lambda: len(p.events.query(type="agent.ran,agent.failed", item="maker")) == 2, 20)
        assert time.monotonic() - began < 25, "killed, not waited for (its run sleeps 30s)"
        last = p.events.query(type="agent.ran,agent.failed", item="maker")[-1]
        assert last["data"]["note"] == "stopped with ergostat" and last["type"] == "agent.ran"
        assert proc.wait(30) is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
