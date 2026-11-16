"""Variables: what is measured or set but does not accumulate. A goal holds a measured variable; a
block turns a knob (a variable it sets); the loop closes through what the knob drives; the engine
records what the block set as the knob's reading; the diagram draws both as variables."""

import os
import tempfile
import textwrap
import time

from ergostat import model as mdl
from ergostat.spec import read
from ergostat.spec.engine import Engine
from ergostat.spec.explain import explain
from ergostat.store import Project

MODEL = """
variables:
  quality:
    unit: ssim
    sensor:
      manual: true
    driven-by: variable.setting
  setting:
    unit: q
goals:
  quality-held:
    variable: quality
    hold: "== 0.9"
    tolerance: 0.02
blocks:
  tuner:
    type: program
    run: echo 75
    in: goal.quality-held.error
    out: variable.setting
"""


def load(tmp_path, text=MODEL):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return read(tmp_path / "ergostat.yaml")


def test_a_goal_on_a_variable_closes_through_the_knob_that_drives_it(tmp_path):
    spec, problems = load(tmp_path)
    assert not [x for x in problems if x.level == "error"], problems
    assert "missing-feedback" not in {x.code for x in problems}
    lp = spec.loop("quality-held")
    assert lp.closes and lp.through == ["block.tuner", "variable.setting", "variable.quality"]
    assert spec.setter_of("setting").name == "tuner" and "set" in spec.variables["setting"].sensors
    text = explain(spec, "setting")
    assert "Set by block tuner" in text and "manipulated variable" in text
    assert "Closes through what it sets" in explain(spec, "quality-held")


def test_the_compiler_refuses_two_setters_and_unknown_variables(tmp_path):
    bad = MODEL + "  other:\n    type: program\n    run: echo 1\n    out: variable.setting\n" \
                  "  reader:\n    type: program\n    run: echo 1\n    in: variable.qualty\n"
    _, problems = load(tmp_path, bad)
    codes = {x.code for x in problems if x.level == "error"}
    assert "two-actuators" in codes and "unknown-ref" in codes
    assert any("did you mean quality" in x.message for x in problems)


def test_the_engine_records_what_a_block_sets_and_judges_the_goal(tmp_path):
    load(tmp_path)
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    p = Project(mdl.load(tmp_path))
    p.measurements.add("sensor/quality.main", 0.7)
    e = Engine(p, say=lambda s: None)
    e.evaluate()
    assert e.status["quality-held"] == "off"
    e.run_block(p.model.spec.blocks["tuner"], "test")
    assert p.measurements.latest("sensor/setting.set")[1] == 75
    assert p.events.query(n=1, type="variable.set", item="setting")
    e.evaluate()
    assert e.signals["variable.setting"] == 75


def test_the_diagram_draws_variables_and_the_knob_it_turns(tmp_path):
    load(tmp_path)
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    p = Project(mdl.load(tmp_path))
    p.measurements.add("sensor/quality.main", 0.91, time.time())
    from ergostat.web.server import Live, api
    g = api(Live(p), "graph", {})
    kinds = {n["id"]: n["kind"] for n in g["nodes"]}
    assert kinds["stock:quality"] == "variable" and kinds["stock:setting"] == "variable"
    assert not any(n["id"] == "sensor:setting.set" for n in g["nodes"])          # what it was set to is not an instrument
    edges = {(e["source"], e["target"], e["kind"]) for e in g["edges"]}
    assert ("controller:quality-held", "stock:setting", "action") in edges
    assert ("stock:setting", "stock:quality", "influence") in edges
    setting = next(n for n in g["nodes"] if n["id"] == "stock:setting")
    assert setting["agent"]["name"] == "tuner"
    assert g["loops"]["quality-held"]["closes"]
