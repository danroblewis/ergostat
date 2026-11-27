"""``use: upkeep``'s record loops (SPEC §4b, §2a *Upkeep*): the roll-up and forgetting, and the measurements' retention,
as stocks held by goals and done by ``upkeep rollup`` and ``upkeep retain``, all under one cross-process compaction lock
(``rollup.compaction``) that the engine's pass and ``ergostat compact`` take too."""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat import rollup, runner
from ergostat import upkeep_measures as um
from ergostat.cli import main as cli
from ergostat.library.run import upkeep as uk
from ergostat.numbers import measures as ms
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.spec.findings import find
from ergostat.store import Project

DAY = 86400.0
UPKEEP = "uses:\n  upkeep:\n    use: upkeep\n"
MODEL = """
projections:
  t:
    query: key.startswith('t/')
    fields:
      state:
        type: one of [open, done]
    events:
      t-opened:
        when: type == 't.opened'
        '...': data
        state: set('open')
      t-done:
        when: type == 't.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
stocks:
  open-ts:
    sensor: {projection: t, state: open, every: 1m}
  done-ts: {}
flows:
  finishing:
    from: open-ts
    to: done-ts
    sensor: {projection: t, entering: done, over: 60d}
storage:
  events: {backend}
"""


def _project(root: Path, upkeep: bool = True, backend: str = "sqlite", extra: str = "") -> Project:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ergostat.yaml").write_text(f"name: {root.name}\n" + textwrap.dedent(MODEL).replace("{backend}", backend)
                                        + extra + (UPKEEP if upkeep else ""))
    return Project(mdl.load(root))


def _old(p: Project, now: float) -> None:
    """Five items with events ten days old (past the 7-day roll-up horizon), each touched again now; one item whose
    every event is forty days old (past the 30-day keep)."""
    for i in range(5):
        p.events.add("t.opened", item=f"t/{i}", data={"a": i}, at=now - 10 * DAY)
        p.events.add("t.x", item=f"t/{i}", data={"b": i}, at=now - 10 * DAY + 1)
        if i % 2:
            p.events.add("t.done", item=f"t/{i}", at=now - 10 * DAY + 2)
        p.events.add("t.x", item=f"t/{i}", data={"c": i}, at=now - 60)
    for j in range(3):
        p.events.add("t.x", item="t/ancient", data={"j": j}, at=now - 40 * DAY + j)


def _folds(p: Project) -> dict:
    return {i.id: (i.state, i.fields) for i in its.project(p.events, p.model.spec)}


def _program(p: Project, root: Path, monkeypatch, *argv: str) -> int:
    monkeypatch.chdir(root)
    monkeypatch.setenv("ERGOSTAT_STATE_DIR", str(p.dir))
    return uk.main(list(argv))


def _snapshots(p: Project) -> list[dict]:
    return p.events.query(n=None, type=its.SNAPSHOT)


def test_a_second_compactor_while_one_holds_the_lock_does_nothing(tmp_path, monkeypatch, capsys):
    root = tmp_path / "r"
    p = _project(root)
    _old(p, time.time())
    before, would = p.events.count(), rollup.compact(p, cap=p.model.keep, dry=True)
    assert would["items"] == 6                           # (t/ancient too: rolled up, then forgotten whole)
    inside, release, first = threading.Event(), threading.Event(), []
    real = rollup.compact

    def held(*a, **k):                                  # the first compactor waits inside the lock until told
        if not k.get("dry") and not first:
            first.append(1)
            inside.set()
            assert release.wait(60)
        return real(*a, **k)
    monkeypatch.setattr(rollup, "compact", held)
    got: list[dict] = []
    t = threading.Thread(target=lambda: got.append(rollup.upkeep(p)))
    t.start()
    try:
        assert inside.wait(60), "the first compactor never reached compact"
        assert cli(["-C", str(root), "compact"]) == 0
        said = capsys.readouterr().out
        assert "busy" in said and "rolled up" not in said, said
        assert _program(p, root, monkeypatch, "rollup", "--every", "1h") == 0
        said = capsys.readouterr().out
        assert said.startswith("busy") and "flow.rolled-up" not in said, said
    finally:
        release.set()
        t.join(60)
    assert got and got[0]["rollup"]["items"] == 6 and got[0]["pruned"] == 1
    assert len(first) == 1 and {s["item"] for s in _snapshots(p)} == {f"t/{i}" for i in range(5)}
    assert len(_snapshots(p)) == 5, "one snapshot an item: one roll-up"
    assert p.events.count() == before - would["events"] + would["items"] - got[0]["pruned"]


SLOW = """
import os, sys, time
from ergostat import rollup
def slow(p, now=None):                      # inside the lock: say so, then never finish
    with open(os.environ["UPKEEP_FLAG"], "w") as f:
        f.write(str(os.getpgid(0)))
    while True:
        time.sleep(1)
rollup.record = slow
from ergostat.library.run import upkeep
sys.exit(upkeep.main(sys.argv[1:]))
"""


def _left_in(pgid: int) -> list[str]:
    """The processes of group ``pgid`` still alive (zombies, which hold nothing, left out)."""
    out = subprocess.run(["ps", "-A", "-o", "pgid=,stat=,pid="], capture_output=True, text=True, check=True).stdout
    return [x for x in out.splitlines() if x.split()[0] == str(pgid) and not x.split()[1].startswith("Z")]


@pytest.mark.slow
def test_a_killed_compactor_releases_the_lock(tmp_path, monkeypatch, capsys):
    """The record-compactor run by the engine as the model has it (its command slowed inside the lock), stopped by
    its timeout: nothing of its process group is left, the next ``upkeep rollup`` takes the lock, and the items fold
    as before (lesson-6)."""
    from ergostat.spec import stream
    from ergostat.spec.engine import Engine
    root = tmp_path / "k"
    p = _project(root)
    _old(p, time.time())
    before = _folds(p)
    flag = tmp_path / "flag"
    (tmp_path / "slow.py").write_text(SLOW)
    monkeypatch.setenv("UPKEEP_FLAG", str(flag))
    b = p.model.spec.blocks["record-compactor"]
    slowed = dataclasses.replace(b, timeout=5.0, params={**b.params, "run": b.params["run"].replace(
        "-m ergostat.library.run upkeep", f"{tmp_path / 'slow.py'}")})
    assert "slow.py rollup --every" in slowed.params["run"]
    real, timed = stream.follow, []

    def at_timeout(proc, path, timeout, take):          # its timeout comes once it is inside the lock
        for _ in range(1200):
            if flag.exists() and flag.read_text():
                break
            proc.poll()
            assert proc.returncode is None, "the slowed compactor ended before it took the lock"
            time.sleep(0.05)
        timed.append(timeout)
        return real(proc, path, 1e-6, take)
    monkeypatch.setattr(stream, "follow", at_timeout)
    Engine(p, say=lambda s: None).run_block(slowed, "test")
    assert timed == [5.0]
    ended = p.events.query(n=None, type="agent.failed") + p.events.query(n=None, type="agent.ran")
    assert any("timeout" in str(e["data"].get("note")) for e in ended), ended
    pgid = int(flag.read_text())
    for _ in range(200):                                 # SIGKILL is sent; give the kernel its moment to deliver it
        if not _left_in(pgid):
            break
        time.sleep(0.05)
    try:
        assert not _left_in(pgid), _left_in(pgid)
    except AssertionError:
        import signal
        os.killpg(pgid, signal.SIGKILL)                  # (the test's own group: never left running after a failure)
        raise
    assert _folds(p) == before, "killed before its one write: the record as it was"
    capsys.readouterr()
    assert _program(p, root, monkeypatch, "rollup", "--every", "1h") == 0
    said = capsys.readouterr().out
    assert '"flow.rolled-up"' in said and '"moved": 6' in said and '"pruned": 1' in said, said
    assert _folds(p) == {k: v for k, v in before.items() if k != "t/ancient"}, "rolled up: each item folds as before"


def test_a_store_that_cannot_count_gives_no_reading(tmp_path, capsys):
    p = _project(tmp_path / "v", extra="  measurements: {url: 'http://127.0.0.1:9'}\n")
    assert type(p.measurements).__name__ == "Victoria"
    assert ms.measure(p, "ergostat.upkeep.measurements-due") is None
    assert "keeps its own retention" in capsys.readouterr().err
    stub = SimpleNamespace(events=SimpleNamespace(), model=SimpleNamespace(keep=30 * DAY), measurements=p.measurements)
    assert um.measure(stub, "ergostat.upkeep.events-past-keep") is None
    assert "cannot count" in capsys.readouterr().err
    with pytest.raises(ValueError, match="not one of the record's"):    # (an allowlist: an unknown name falls to nothing)
        um.record(p, "ergostat.upkeep.bogus")


@pytest.mark.parametrize("upkeep", [True, False])
def test_with_upkeep_the_engine_rolls_nothing_up_and_without_it_does(tmp_path, monkeypatch, upkeep):
    p = _project(tmp_path / f"e{int(upkeep)}", upkeep=upkeep)
    calls, said = [], []
    monkeypatch.setattr(rollup, "upkeep", lambda proj, now=None: calls.append(proj) or {
        "rollup": {"items": 0, "events": 0}, "pruned": 0})
    (p.dir / "run.log").write_text("x" * 100)
    runner.prune_once(p, said.append)
    assert calls == ([] if upkeep else [p])
    assert (p.dir / "run.log").exists(), "the logs are still the engine's"
    if not upkeep:                                       # and without the template it takes the lock
        monkeypatch.undo()
        with rollup.compaction(p) as held:
            assert held
            runner.prune_once(p, said.append)
        assert said and "busy" in said[-1], said


def test_events_past_keep_alone_starts_a_pruner_through_its_goal(tmp_path):
    """Nothing to roll up (rollup-due 0), but events past keep that no roll-up would touch: an item-less event and an
    item of no kind. The engine's own pass turns on a block serving record-within-keep (its implied onoff), and that
    block's run forgets them (review round 2: the compactor alone ran only while rollup-due was off)."""
    from ergostat.spec.engine import Engine
    p = _project(tmp_path / "w")
    now = time.time()
    p.events.add("note", data={"n": 1}, at=now - 40 * DAY)
    p.events.add("solo.x", item="solo", at=now - 40 * DAY)
    p.events.add("t.opened", item="t/new", at=now - 60)
    spec = p.model.spec
    e = Engine(p, say=lambda s: None)
    e.machines = []                                      # the pass only: the blocks it turns on are run below
    for stock in ("rollup-due", "events-past-keep", "measurements-due"):
        for s in spec.stocks[stock].sensors.values():
            if (x := ms.measure(p, f"ergostat.upkeep.{stock}")) is not None:    # (measurements-due: none, the server's)
                p.measurements.add(s.series, x, at=now - 1)
    assert e.signals.get("stock.rollup-due") is None
    e.evaluate(full=True)
    assert e.signals["stock.rollup-due"] == 0.0 and e.signals["stock.events-past-keep"] == 2.0, e.signals
    on = [b for b in spec.blocks.values() if b.type == "program" and b.goal and e.command_of(b)[0]]
    assert [b.goal for b in on] == ["record-within-keep"], [b.name for b in on]
    for b in on:
        e.run_block(b, "test")
    assert ms.measure(p, "ergostat.upkeep.events-past-keep") == 0
    assert not p.events.query(n=None, type="note") and not p.events.query(n=None, item="solo")
    assert p.events.query(n=None, item="t/new"), "what is within keep stays"


def test_compaction_stopped_grows_the_record_and_nothing_breaks(tmp_path):
    from ergostat.spec.engine import read_sensor
    p = _project(tmp_path / "s")
    now = time.time()
    _old(p, now)
    rollup.compact(p, now, cap=p.model.keep)             # one roll-up long ago, then the blocks stopped
    spec = p.model.spec
    for rnd in range(3):
        n = p.events.count()
        runner.prune_once(p, lambda s: None)             # the engine's pass: under use: upkeep, nothing rolled
        for i in range(5):
            p.events.add("t.x", item=f"t/{i}", data={"r": rnd}, at=now - 9 * DAY + rnd)   # old, and never rolled up
        assert p.events.count() == n + 5, "the record only grows"
        got = _folds(p)
        assert {k: v[0] for k, v in got.items()} == {"t/0": "open", "t/1": "done", "t/2": "open", "t/3": "done",
                                                    "t/4": "open", "t/ancient": "open"}
        assert all(got[f"t/{i}"][1] == {"a": i, "b": i, "c": i, "r": rnd} for i in range(5)), got
        stock = next(iter(spec.stocks["open-ts"].sensors.values()))
        flow = next(iter(spec.flows["finishing"].sensors.values()))
        assert read_sensor(spec, stock, p.events)[0] == 4.0                # t/0, t/2, t/4 and t/ancient
        assert read_sensor(spec, flow, p.events)[0] == pytest.approx(2 / (60 * 24))   # two entered done in 60d, per hour
        whole = rollup.archived(p, "t/1")
        assert whole["archived"] == 3 and whole["total"] == 3 + 1 + rnd + 1, whole
    assert ms.measure(p, "ergostat.upkeep.rollup-due") == rollup.compact(p, cap=p.model.keep, dry=True)["items"]


@pytest.mark.parametrize("every", ["30s", "2d"])
def test_every_out_of_range_is_refused(tmp_path, monkeypatch, capsys, every):
    for k in ("rollup-every", "retain-every", "rollup-timeout", "due-every"):    # (due-every: a dry roll-up each time)
        root = tmp_path / k
        root.mkdir()
        (root / "ergostat.yaml").write_text("name: x\nuses:\n  upkeep:\n    use: upkeep\n"
                                            f"    with: {{{k}: {every}}}\n")
        errs = [str(x) for x in read(root / "ergostat.yaml")[1] if x.level == "error"]
        assert errs and all(k in e for e in errs), errs
    p = _project(tmp_path / "p")
    assert p.model.spec.blocks["record-compactor"].timeout == 3600.0, "a first roll-up of a backlog gets an hour, not 300s"
    for what in ("rollup", "retain"):
        assert _program(p, tmp_path / "p", monkeypatch, what, "--every", every) == 2
        assert "1m to 1d" in capsys.readouterr().err
        assert _program(p, tmp_path / "p", monkeypatch, what, "--every", "1m") == 0
        assert _program(p, tmp_path / "p", monkeypatch, what, "--every", "1d") == 0


def test_storage_rollup_every_with_upkeep_is_a_finding(tmp_path):
    def codes(name: str, upkeep: bool, every: bool) -> set[str]:
        root = tmp_path / name
        root.mkdir()
        (root / "ergostat.yaml").write_text("name: x\nprojections:\n  t:\n    query: key.startswith('t/')\n"
                                            + ("storage:\n  rollup:\n    every: 2h\n" if every else "")
                                            + (UPKEEP if upkeep else ""))
        spec, ps = read(root / "ergostat.yaml")
        assert not [x for x in ps if x.level == "error"], [str(x) for x in ps]
        return {x.code for x in find(spec, extremes=False)}
    assert "unused-rollup-every" in codes("both", True, True)
    assert "unused-rollup-every" not in codes("upkeep", True, False)
    assert "unused-rollup-every" not in codes("engine", False, True)
    spec, _ = read(tmp_path / "both" / "ergostat.yaml")
    msg = next(x.message for x in find(spec, extremes=False) if x.code == "unused-rollup-every")
    assert "rollup-every" in msg and "storage.rollup.every" in msg


def test_the_lock_is_a_flock_another_process_sees(tmp_path):
    """Held here, ``upkeep`` in another process says busy; the lock file is never a pid file."""
    p = _project(tmp_path / "f")
    code = (f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r}); "
            "from pathlib import Path; from ergostat import model as m, rollup; from ergostat.store import Project; "
            f"p = Project(m.load(Path({str(tmp_path / 'f')!r})), Path({str(p.dir)!r})); "
            "print(rollup.upkeep(p).get('busy'))")
    with rollup.compaction(p) as held:
        assert held
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=os.environ)
        assert out.stdout.strip() == "True", out.stderr
    assert (p.dir / rollup.LOCK).read_text() == ""
