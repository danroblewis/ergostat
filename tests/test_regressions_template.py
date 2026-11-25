"""``use: regressions`` (dev/records/regression-template.md): the model's tests passing, its blocks' claims kept, its
model changes and its repair fixes holding, each asked for through ``with:`` and each goal served by a person; and the
reader behind the passing counts, ``python -m ergostat.regressions counts``."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import time

import pytest

from ergostat import model as mdl
from ergostat import regressions
from ergostat.cli import main
from ergostat.spec import observer
from ergostat.spec.engine import Engine, read_sensor
from ergostat.store import Project

FAILING = "echo '=== 1 failed, 2 passed in 0.12s ==='; exit 1"
PASSING = "echo '=== 3 passed in 0.12s ==='"
ALL = "{every: 1h, block: dev, changes: true, repair: repair}"


def model(tmp_path, with_: str | None = ALL, tests: str | None = PASSING, repair: bool = True):
    d = tmp_path / "proj"
    d.mkdir(parents=True, exist_ok=True)
    claims = f"claims:\n  tests: {{run: {tests!r}}}\n" if tests is not None else ""
    uses = "  repair: {use: repair}\n" if repair else ""
    w = f"\n    with: {with_}" if with_ is not None else ""
    (d / "ergostat.yaml").write_text(f"name: t\n{claims}uses:\n{uses}  regressions:\n    use: regressions{w}\n"
                                     "blocks:\n  dev: {type: program, run: 'true', every: 1h}\n")
    return mdl.load(d)


PARTS = {"auxiliary": ("tests-failing", "escapes", "regressed-changes"),
         "stock": ("tests-fixes", "escape-corrections", "change-corrections"),
         "flow": ("tests-fixed", "escapes-corrected", "changes-corrected"),
         "goal": ("tests-green", "claims-kept", "changes-hold"),
         "block": ("tests-fixer", "escapes-reviewer", "changes-reviewer", "fixes-reviewer")}


def test_the_template_checks_clean(tmp_path, monkeypatch, capsys):
    """Every part on: no error, no missing feedback anywhere, no finding about a part it makes, each goal's loop
    closed by its person; repair's fixes-hold is read, not made again."""
    m = model(tmp_path)
    spec = m.spec
    assert spec is not None, [str(x) for x in m.problems]
    assert not [str(x) for x in m.problems if x.level == "error"]
    assert not [str(x) for x in m.problems if x.code == "missing-feedback"]
    mine = {f"{k}.{n}" for k, ns in PARTS.items() for n in ns}
    found = [f"{x.code} {x.message}" for x in m.problems if x.about in mine and x.level != "note"]
    assert not found, found
    for goal, person in (("tests-green", "tests-fixer"), ("claims-kept", "escapes-reviewer"),
                         ("changes-hold", "changes-reviewer")):
        lp = spec.loop(goal)
        assert lp.through[0] == f"block.{person}" and lp.through[-1] == str(spec.goals[goal].of), (goal, lp)
        assert spec.blocks[person].type == "person"
        assert spec.goals[goal].on_stale == "off"
        part = spec.auxiliaries[spec.goals[goal].of.name]
        assert list(part.sensors) == ["main"], "one sensor on a clock (a block setting it would never go stale)"
    main(["-C", str(spec.root), "check", "--json"])                          # the command, its coherence too
    got = json.loads(capsys.readouterr().out)
    said = [x for x in got["found"] + got.get("coherence", {}).get("findings", []) if x.get("level") != "note"]
    assert got["ok"] and not [x for x in said if x["id"].startswith("missing-feedback")], said
    assert not [x for x in said if x["id"].split("@")[-1] in mine], said
    assert "fixes-reviewer" in spec.loop("fixes-hold").controllers and "repair-settle" in spec.loop("fixes-hold").controllers
    assert [g for g in spec.goals if "fixes-hold" in g] == ["fixes-hold"]
    assert str(spec.goals["claims-kept"].of) == "auxiliary.escapes"
    assert next(iter(spec.auxiliaries["escapes"].sensors.values())).builtin == "ergostat.trust.contradicted@dev"
    assert next(iter(spec.auxiliaries["regressed-changes"].sensors.values())).builtin == "ergostat.model.regressed"


def test_each_part_is_opt_in(tmp_path):
    """No with: makes no part; each parameter alone makes its own part and no other."""
    for i, (with_, want) in enumerate(((None, set()), ("{every: 1h}", {"tests-green"}), ("{block: dev}", {"claims-kept"}),
                                        ("{changes: true}", {"changes-hold"}), ("{repair: repair}", set()))):
        m = model(tmp_path / str(i), with_=with_)
        assert m.spec is not None and not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
        made = {n for n in m.spec.goals if n in PARTS["goal"]}
        assert made == want, (with_, made)
        parts = {n for k in ("auxiliary", "stock", "flow") for n in PARTS[k] if n in m.spec.measured(k)}
        assert len(parts) == 3 * len(want), (with_, parts)
        assert ("fixes-reviewer" in m.spec.blocks) == ("repair" in (with_ or "")), with_


@pytest.mark.parametrize("text, counts", [
    ("collected 3\n.F.\n=========== 1 failed, 2 passed in 0.52s ===========\n", {"failed": 1, "passed": 2}),
    ("..\n2 passed, 1 skipped, 3 warnings in 1.00s\n", {"passed": 2, "skipped": 1, "warnings": 3}),
    ("E\n==== 1 passed, 2 errors in 0.1s ====", {"passed": 1, "errors": 2}),
    ("==== 1 error in 0.1s ====", {"errors": 1}),
    ("== 5 passed in 2.00s ==\nlater text\n", {"passed": 5}),
    ("===== no tests ran in 0.01s =====", None),
    ("Traceback (most recent call last):\nImportError: no module", None),
    ("", None),
    ("==== 1 passed, 1 interrupted in 0.1s ====", None),
    ("==== 3 deselected, 1 skipped in 0.1s ====", None),
    ("== 1 failed in 0.3s ==\nall done in 4s\n", {"failed": 1}),
])
def test_counts_parser_forms(text, counts):
    """Passed, failed, errors (one or many), none: the last summary's counts, or None when there is no summary, it
    counts nothing, or it says something not a count."""
    assert regressions.parse(text) == counts
    if counts is not None:
        assert regressions.failing(counts) == counts.get("failed", 0) + counts.get("errors", 0)


def green_project(tmp_path, monkeypatch, tests):
    m = model(tmp_path, with_="{every: 1m}", tests=tests, repair=False)
    monkeypatch.chdir(m.spec.root)
    p = Project(m)
    s = next(iter(m.spec.auxiliaries["tests-failing"].sensors.values()))
    return p, s


def test_a_failing_run_sets_tests_green_off(tmp_path, monkeypatch):
    """The reader runs the model's claims: tests command as the sensor does: a failing run reads 1 and turns
    tests-green off; a passing one reads 0 and holds."""
    for name, tests, want, status in (("fail", FAILING, 1.0, "off"), ("pass", PASSING, 0.0, "holding")):
        p, s = green_project(tmp_path / name, monkeypatch, tests)
        got, why = read_sensor(p.model.spec, s)
        assert got == want, why
        e = Engine(p, say=lambda s: None)
        try:
            p.measurements.add(s.series, got)
            e.evaluate()
            assert e.status.get("tests-green") == status, name
            assert e.signals["goal.tests-green.off"] == (status == "off")
            asked = p.events.query(n=None, type="person.asked", item="tests-fixer")
            assert len(asked) == (status == "off"), name
        finally:
            e.close()


def alive(pidfile, wait: float = 5.0) -> bool:
    """Whether the process whose pid the test command wrote is still running (a zombie is not), after ``wait``."""
    for _ in range(int(wait * 20)):
        if pidfile.exists() and pidfile.read_text().strip():
            got = subprocess.run(["ps", "-o", "stat=", "-p", pidfile.read_text().strip()], capture_output=True,
                                 text=True).stdout.strip()
            if not got or got.startswith("Z"):
                return False
        time.sleep(0.05)
    return True


@pytest.mark.parametrize("exec_", ["", "exec "])
def test_the_sensor_timing_out_first_leaves_no_test_run(tmp_path, monkeypatch, exec_):
    """The sensor's own timeout kills only its shell: the reader orphaned under it (a shell that forks), or the
    reader itself (one that execs). The test command, in a session of its own, is killed all the same: by the reader
    seeing its shell gone, or by its guard seeing the reader gone. No run is left to pile up under the next."""
    p, s = green_project(tmp_path, monkeypatch, "echo $$ > pid; sleep 60; echo '== 1 passed in 60s =='")
    s = dataclasses.replace(s, run=exec_ + s.run.replace("--within 600", "--within 300"), timeout=3.0)
    assert "--within 300" in s.run
    t0 = time.monotonic()
    got, why = read_sensor(p.model.spec, s)
    assert got is None and "no answer within 3s" in why and time.monotonic() - t0 < 20, why
    for _ in range(100):
        if (p.model.spec.root / "pid").exists():
            break
        time.sleep(0.05)
    assert (p.model.spec.root / "pid").exists(), "the test command was started within the sensor's time"
    assert not alive(p.model.spec.root / "pid"), "the test run outlived the reader the sensor killed"


def test_the_reader_counts_its_deadline_from_its_own_start(monkeypatch):
    """The run gets what is left of --within after a fixed margin and the reader's own start, not 0.9 of it from
    the moment the run begins."""
    seen = []
    monkeypatch.setattr(regressions, "counts", lambda within: (seen.append(within), (0, ""))[1])
    monkeypatch.setattr(regressions, "BEGAN", time.monotonic() - 3)
    assert regressions.main(["counts", "--within", "10"]) == 0
    assert 4.5 < seen[0] <= 5.0, seen                     # 10 - 2 (margin) - 3 (since the reader began)


def test_an_unreadable_test_command_is_stale_and_off(tmp_path, monkeypatch):
    """A run with no summary, one that exits non-zero counting no failure, one past its time and a model with no
    claims: tests command each give no value; tests-green, never read again, goes stale and off, never holding."""
    for i, tests in enumerate(("echo nothing to see", "echo '== 2 passed in 0.1s =='; exit 3", None)):
        p, s = green_project(tmp_path / str(i), monkeypatch, tests)
        got, why = read_sensor(p.model.spec, s)
        assert got is None and why, (tests, got)
    assert regressions.main(["counts", "--within", "0.5"]) == 1          # (the last: no command declared)
    p, s = green_project(tmp_path / "slow", monkeypatch, "echo $$ > pid; sleep 30; echo '== 1 passed in 30s =='")
    t0 = time.monotonic()
    assert regressions.counts(0.5) == (None, "no answer within 0.5s") and time.monotonic() - t0 < 10
    assert not alive(p.model.spec.root / "pid"), "the run past its time is killed with its group"
    clock = [1_787_904_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    e = Engine(p, say=lambda s: None)
    e.start = lambda b, why: None                                              # (nothing runs)
    fixer = p.model.spec.blocks["tests-fixer"]
    asked = lambda: p.events.query(n=None, type="person.asked", item="tests-fixer")  # noqa: E731
    try:
        p.measurements.add(s.series, 0, clock[0])
        e.evaluate(tick=True)
        assert e.status.get("tests-green") == "holding" and not e.stale and not asked()
        clock[0] += observer.STALE_AFTER * s.every + 60                         # unread since: each run unreadable
        e.evaluate(tick=True)
        assert "tests-green" in e.stale and e.signals["goal.tests-green.off"] == 1
        went = p.events.query(n=None, type="ergostat.goal.stale", item="tests-green")
        assert len(went) == 1 and went[0]["data"]["on_stale"] == "off"
        assert e.context(fixer, "test")["goals"]["tests-green"]["status"] == "off"   # what its person is told
        assert len(asked()) == 1, "the person is asked: stale is off, never holding"
    finally:
        e.close()
