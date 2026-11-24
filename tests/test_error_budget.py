"""An error budget sets how much checking a change gets (SPEC §9.2, the built-in block ``budget``): the level moves with
the budget both ways, each move recorded with its reason; with no retroactive way to find and revert regressions
declared it never drops; the budget and the level are series a dashboard charts. The factory is its first user
(dev/model/landing.yaml)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import series as sr
from ergostat.numbers import measures
from ergostat.spec import read
from ergostat.spec.engine import Engine, every_pass
from ergostat.store import Project

DAY = 86400.0
T0 = 1_800_000_000.0

MODEL = """\
name: eb
auxiliaries:
  escapes:
    unit: regressions
    sensor: {manual: true}
  retro:
    unit: switch
    sensor: {manual: true}
  level:
    unit: level
    sensor: {builtin: ergostat.errors.level@eb, every: 1m}
  left:
    unit: regressions
    sensor: {builtin: ergostat.errors.left@eb, every: 1m}
blocks:
  eb:
    type: budget
    in: {spent: auxiliary.escapes%s}
    budget: 4
    levels: [light, standard, full]
    healthy: 0.5
    hold: 1d
dashboards:
  checks:
    panels:
      - {panel: chart, refs: [auxiliary.left, auxiliary.level]}
"""


def project(tmp_path: Path, retroactive: bool = True) -> Project:
    (tmp_path / "ergostat.yaml").write_text(MODEL % (", retroactive: auxiliary.retro" if retroactive else ""))
    return Project(mdl.load(tmp_path))


def stepper(p: Project):
    """The engine's own built-in pass, on the readings given: (level, its events, its rows) a step."""
    e = Engine(p, say=lambda s: None)

    def step(at: float, escapes, retro=1.0):
        e.signals["auxiliary.escapes"], e.signals["auxiliary.retro"] = escapes, retro
        events, rows = [], []
        e._builtins(at, None, {}, events, rows)
        p.measurements.add_many(rows)
        return e.signals.get("block.eb"), [x for x in events if x["type"] == "controller.decided"], rows
    return step


def test_the_level_moves_with_the_budget_both_ways_with_a_recorded_reason(tmp_path):
    step = stepper(project(tmp_path))
    level, said, rows = step(T0, 0.0)
    assert level == 2                                     # it starts at the strictest
    assert said[0]["data"]["decision"] == "check level starts at full (2)" and said[0]["item"] == "eb"
    assert ("block/eb/left", T0, 4.0) in rows             # the budget left, a series of its own
    level, said, _ = step(T0 + DAY / 2, 0.0)              # healthy, but not held a day yet
    assert level == 2 and not said
    level, said, _ = step(T0 + DAY, 0.0)                  # healthy a day: down one step
    assert level == 1
    assert said[0]["data"]["decision"] == "check level drops to standard (1)"
    assert "4 of 4 regressions left (100%; healthy at 50%)" in said[0]["data"]["why"]
    level, _, _ = step(T0 + DAY * 1.5, 0.0)               # one step a day, never two at once
    assert level == 1
    level, said, _ = step(T0 + 2 * DAY, 1.0)              # 3 of 4 left: still healthy, down again
    assert level == 0 and said[0]["data"]["decision"] == "check level drops to light (0)"
    level, said, rows = step(T0 + 2 * DAY + 60, 3.0)      # the budget burns: 1 of 4 left, up at once
    assert level == 1 and said[0]["data"]["decision"] == "check level rises to standard (1)"
    assert "1 of 4 regressions left (25%" in said[0]["data"]["why"] and ("block/eb/left", T0 + 2 * DAY + 60, 1.0) in rows
    level, said, _ = step(T0 + 2 * DAY + 120, 4.0)        # none left: the strictest at once
    assert level == 2 and said[0]["data"]["decision"] == "check level rises to full (2)"
    level, said, _ = step(T0 + 3 * DAY + 120, 1.0)        # healthy again, and held a day: it drops again
    assert level == 1 and said[0]["data"]["decision"] == "check level drops to standard (1)"


@pytest.mark.parametrize("retro", [0.0, None, float("nan"), -1.0])
def test_with_the_retroactive_way_off_or_unread_the_level_is_the_strictest(tmp_path, retro):
    step = stepper(project(tmp_path))
    step(T0, 0.0)
    assert step(T0 + DAY, 0.0)[0] == 1                    # on: it dropped
    level, said, _ = step(T0 + DAY + 60, 0.0, retro)      # off (or unread): back to the strictest at once
    assert level == 2 and said[0]["data"]["decision"] == "check level rises to full (2)"
    assert "off or unread" in said[0]["data"]["why"]
    assert step(T0 + 10 * DAY, 0.0, retro)[0] == 2        # and it stays there, however healthy the budget


@pytest.mark.parametrize("spent", [None, float("nan"), float("inf"), -1.0])
def test_regressions_that_cannot_be_read_count_as_the_budget_spent(tmp_path, spent):
    step = stepper(project(tmp_path))
    step(T0, 0.0)
    assert step(T0 + DAY, 0.0)[0] == 1
    level, said, _ = step(T0 + DAY + 60, spent)
    assert level == 2 and "cannot be read" in said[0]["data"]["why"]


def test_with_no_retroactive_mechanism_declared_the_level_never_drops(tmp_path):
    step = stepper(project(tmp_path, retroactive=False))
    level, first, _ = step(T0, 0.0)
    assert level == 2
    for d in range(1, 31):                                # a month of a whole budget left, even a reading of 1
        level, said, _ = step(T0 + d * DAY, 0.0, 1.0)
        assert (level, said) == (2, []), d
    assert "never drops" in first[0]["data"]["why"]


def test_the_budget_and_the_level_are_dashboard_series(tmp_path):
    p = project(tmp_path)
    _, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], problems       # (the chart's refs among them)
    with pytest.raises(measures.MeasureError):                              # before the block's first pass
        measures.measure(p, "ergostat.errors.level@nothing")
    assert measures.measure(p, "ergostat.errors.level@eb") is None
    step = stepper(p)
    spec = p.model.spec
    for at, escapes in [(T0, 0.0), (T0 + DAY, 0.0), (T0 + DAY + 600, 3.0)]:
        step(at, escapes)
        for aux in ("level", "left"):                    # what each sensor reads, as `ergostat measure` gives it
            s = next(iter(spec.auxiliaries[aux].sensors.values()))
            p.measurements.add(s.series, measures.measure(p, s.builtin), at=at + 1)
    snap = {"at": T0 + DAY + 1200, "window": 2 * DAY}
    got = sr.series(p, snap, ["auxiliary.left", "auxiliary.level"], n=4)
    by = {s["ref"]: [v for v in s["values"] if v is not None] for s in got["series"]}
    assert by["auxiliary.level"] == [2.0, 1.0]           # full at the start; standard a day on, held as 1 of 4 is left
    assert by["auxiliary.left"] == [4.0, 1.0]


@pytest.mark.parametrize("bad,code", [
    ("    budget: 0\n", "bad-number"),
    ("    budget: .nan\n", "bad-number"),
    ("    budget: 2000000\n", "bad-number"),
    ("    levels: [full]\n", "bad-levels"),
    ("    levels: [a, a]\n", "bad-levels"),
    ("    levels: [" + ", ".join(f"l{i}" for i in range(11)) + "]\n", "bad-levels"),
    ("    healthy: 1.5\n", "bad-number"),
    ("    healthy: true\n", "bad-number"),
    ("    hold: soon\n", "bad-duration"),
])
def test_a_bad_budget_is_refused(tmp_path, bad, code):
    key = bad.split(":")[0].strip()
    text = MODEL % ""
    text = "\n".join(line for line in text.splitlines() if not line.startswith(f"    {key}:")) + "\n"
    text = text.replace("    in: {spent: auxiliary.escapes}\n", "    in: {spent: auxiliary.escapes}\n" + bad)
    (tmp_path / "ergostat.yaml").write_text(text)
    _, problems = read(tmp_path / "ergostat.yaml")
    assert code in [x.code for x in problems if x.level == "error"], problems


def test_a_budget_reads_spent_and_retroactive_only(tmp_path):
    (tmp_path / "ergostat.yaml").write_text((MODEL % "").replace("in: {spent: auxiliary.escapes}",
                                                                 "in: {escapes: auxiliary.escapes}"))
    _, problems = read(tmp_path / "ergostat.yaml")
    assert "bad-ref" in [x.code for x in problems if x.level == "error"], problems


def test_a_budget_is_stepped_every_pass_so_a_held_level_drops_on_time_alone(tmp_path):
    assert every_pass(project(tmp_path).model.spec.blocks["eb"])


def test_the_factory_declares_its_error_budget_on_the_verification_lane():
    """The first user: dev/model/landing.yaml's error-budget reads the lane's escapes and drops only while the lane
    finds and reverts regressions; its level and budget left are on the merge pipeline's chart."""
    root = Path(__file__).resolve().parent.parent
    _, problems = read(root / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], [x for x in problems if x.level == "error"][:5]
    spec = mdl.load(root).spec
    b = spec.blocks["error-budget"]
    assert b.type == "budget" and str(b.inputs["retroactive"]) == "auxiliary.verify-retroactive"
    assert str(b.inputs["spent"]) == "auxiliary.verify-escapes"
    refs = textwrap.dedent((root / "dev" / "model" / "landing.yaml").read_text())
    assert "auxiliary.error-budget-left, auxiliary.check-level]" in refs
    mine = ("error-budget", "check-level", "verify-retroactive")
    assert [str(x) for x in problems if "landing.yaml" in str(x.where) and any(n in x.message for n in mine)] == []


def test_the_factory_s_retroactive_reading_is_on_only_while_the_lane_finds_and_reverts(tmp_path, monkeypatch):
    from tests.test_factory import BIN, module
    monkeypatch.syspath_prepend(str(BIN))
    v = module("verify")
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setattr(v.fac, "run_dir", lambda cfg: run)
    monkeypatch.setattr(v, "verified", lambda repo: "abc")
    on = {"verify": {"after": True}}
    assert v.retroactive(on, tmp_path) is True
    assert v.retroactive({"verify": {"after": False}}, tmp_path) is False       # the lane off
    assert v.retroactive({}, tmp_path) is False
    (run / "verify.json").write_text('{"held": {"why": "main red"}}')
    assert v.retroactive(on, tmp_path) is False                                 # held: nothing is reverted
    (run / "verify.json").write_text("[1]")
    with pytest.raises(ValueError):                                             # unreadable: no reading at all
        v.retroactive(on, tmp_path)
    (run / "verify.json").unlink()
    monkeypatch.setattr(v, "verified", lambda repo: "")
    assert v.retroactive(on, tmp_path) is False                                 # no verified commit to bisect from
