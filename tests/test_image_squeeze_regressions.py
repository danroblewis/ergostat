"""examples/image-squeeze uses ``use: regressions`` (dev/records/regression-template-docs-demo.md): its claims: tests
command's failing count held at 0 (tests-green) and its regressed model changes at 0 (changes-hold), each served by a
person; and in the healthy demo (squeeze as it was handed over, nothing written to the model yet) both hold."""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

from ergostat import model as mdl
from ergostat import regressions
from ergostat.cli import main
from ergostat.spec.engine import Engine, read_sensor
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "image-squeeze"
GOALS = {"tests-green": ("tests-failing", "tests-fixer"), "changes-hold": ("regressed-changes", "changes-reviewer")}


def copy(tmp_path) -> Path:
    d = tmp_path / "image-squeeze"
    shutil.copytree(DEMO, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    return d


def test_image_squeeze_uses_the_template_and_checks_clean(tmp_path, capsys):
    """The two parts it asks for are made, and no other (its developer's escapes are developer-honest already); each
    goal's loop is closed by its person, off while stale; ergostat check finds no error and no missing feedback."""
    m = mdl.load(copy(tmp_path))
    spec = m.spec
    assert spec is not None and not [str(x) for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    mine = {f"goal.{g}" for g in GOALS}                     # (developer-honest and two others are open on purpose)
    assert not [str(x) for x in m.problems if x.code == "missing-feedback" and x.about in mine]
    assert {"tests-green", "changes-hold"} <= set(spec.goals) and "claims-kept" not in spec.goals
    for goal, (part, person) in GOALS.items():
        g = spec.goals[goal]
        assert str(g.of) == f"auxiliary.{part}" and g.on_stale == "off", goal
        assert spec.blocks[person].type == "person" and spec.loop(goal).through[0] == f"block.{person}", goal
    assert "--within 180" in next(iter(spec.auxiliaries["tests-failing"].sensors.values())).run
    main(["-C", str(spec.root), "check", "--json"])
    got = json.loads(capsys.readouterr().out)
    assert got["ok"], got
    assert not [x for x in got["found"] if x["id"].startswith("missing-feedback") and x["id"].split("@")[-1] in mine]
    assert not [x for x in got["found"] if x.get("level") == "error"], got["found"]


def test_its_goals_hold_in_the_healthy_demo(tmp_path, monkeypatch):
    """squeeze as handed over (the seed, where lab.py init puts it): the sensor runs its tests and reads 0 failing,
    the record has no regressed change, and both goals hold."""
    d = copy(tmp_path)
    (d / "run" / "product").mkdir(parents=True)
    for f in (d / "seed").glob("*.py"):
        shutil.copy2(f, d / "run" / "product" / f.name)
    monkeypatch.chdir(d)
    p = Project(mdl.load(d))
    spec = p.model.spec
    e = Engine(p, say=lambda s: None)
    try:
        for goal, (part, _) in GOALS.items():
            s = next(iter(spec.auxiliaries[part].sensors.values()))
            got, why = read_sensor(spec, s, p.events, measurements=p.measurements)
            assert got == 0.0, (goal, why)
            p.measurements.add(s.series, got)
        e.evaluate()
        assert {g: e.status.get(g) for g in GOALS} == {g: "holding" for g in GOALS}
    finally:
        e.close()


def small(tmp_path) -> Path:
    d = tmp_path / "proj"
    d.mkdir()
    (d / "ergostat.yaml").write_text("name: t\nclaims:\n  tests: {run: \"echo '== 2 passed in 0.1s =='\", in: product}\n"
                                     "uses:\n  regressions: {use: regressions, with: {every: 1h}}\n")
    return d


def test_the_reader_waits_for_its_test_folder(tmp_path, monkeypatch):
    """A test folder the model's own first run makes (image-squeeze's run/product, made by its customers' first run)
    is waited for within the reader's time; one never made gives no value, never 0."""
    d = small(tmp_path)
    monkeypatch.chdir(d)
    t0 = time.monotonic()
    assert regressions.counts(1.0) == (None, "no folder product to run the tests in")
    assert time.monotonic() - t0 < 5
    later = threading.Timer(1.0, lambda: (d / "product").mkdir())
    later.start()
    try:
        assert regressions.counts(20.0) == (0, "")
    finally:
        later.join()
