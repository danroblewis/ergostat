"""Auxiliaries and stocks, sorted by memory. An auxiliary has none: it is determined at each moment
by others (a goal holds a measured one; a block may state one's whole value each run). A setting a
controller steps keeps its value between steps, so it is a stock, moved by a two-way flow: the
loop closes through it. The old name, variables:, is still read, with a finding."""

import os
import tempfile
import textwrap
import time

from ergostat import model as mdl
from ergostat.spec import read
from ergostat.spec.engine import Engine
from ergostat.spec.explain import explain
from ergostat.store import Project

# an integral controller: the setting is a stock, stepped by the error through a two-way flow
MODEL = """
auxiliaries:
  quality:
    unit: ssim
    sensor:
      manual: true
    driven-by: +stock.setting
stocks:
  setting:
    unit: q
    sensor:
      manual: true
flows:
  steps:
    to: setting
    two-way: true
goals:
  quality-held:
    auxiliary: quality
    hold: "== 0.9"
    tolerance: 0.02
blocks:
  tuner:
    type: program
    run: echo -5
    in: goal.quality-held.error
    out: flow.steps
"""

# a proportional controller states its output whole each run: a memoryless setting, an auxiliary
SET = """
auxiliaries:
  quality:
    unit: ssim
    sensor:
      manual: true
    driven-by: auxiliary.setting
  setting:
    unit: q
goals:
  quality-held:
    auxiliary: quality
    hold: "== 0.9"
blocks:
  tuner:
    type: program
    run: echo 75
    in: goal.quality-held.error
    out: auxiliary.setting
"""


def load(tmp_path, text=MODEL):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return read(tmp_path / "ergostat.yaml")


def project(tmp_path, text=MODEL):
    load(tmp_path, text)
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    return Project(mdl.load(tmp_path))


def test_a_stepped_setting_is_a_stock_and_the_loop_closes_through_it(tmp_path):
    spec, problems = load(tmp_path)
    assert not [x for x in problems if x.level == "error"], problems
    assert "missing-feedback" not in {x.code for x in problems}
    lp = spec.loop("quality-held")
    assert lp.closes and lp.through == ["block.tuner", "flow.steps", "stock.setting", "auxiliary.quality"]
    assert spec.flows["steps"].two_way and spec.auxiliaries["quality"].polarity == {"stock.setting": 1}
    text = explain(spec, "quality-held")
    assert "Closes through a setting it steps" in text and "integral action" in text
    assert "manipulated variable" in text and "process variable" in text
    assert "manipulated variable" in explain(spec, "stock.setting")
    assert "no memory" in explain(spec, "quality")
    assert "either way" in explain(spec, "flow.steps")


def test_a_two_way_flow_moves_back_and_a_one_way_flow_refuses_it(tmp_path):
    p = project(tmp_path)
    e = Engine(p, say=lambda s: None)
    assert e.run_block(p.model.spec.blocks["tuner"], "test") == ["steps"]       # moving back is moving: read again
    opened = p.events.query(n=5, type="valve.opened")
    assert [x["data"]["amount"] for x in opened] == [-5.0]
    assert not p.events.query(n=5, type="agent.refused")
    one_way = MODEL.replace("    two-way: true\n", "")
    p = project(tmp_path, one_way)
    e = Engine(p, say=lambda s: None)
    e.run_block(p.model.spec.blocks["tuner"], "test")
    refused = p.events.query(n=5, type="agent.refused")
    assert refused and "runs one way" in refused[-1]["data"]["why"]


def test_a_memoryless_setting_stays_an_auxiliary_the_block_states_whole(tmp_path):
    spec, problems = load(tmp_path, SET)
    assert not [x for x in problems if x.level == "error"], problems
    lp = spec.loop("quality-held")
    assert lp.closes and lp.through == ["block.tuner", "auxiliary.setting", "auxiliary.quality"]
    assert spec.setter_of("setting").name == "tuner" and "set" in spec.auxiliaries["setting"].sensors
    assert "states its whole value" in explain(spec, "setting")
    assert "Closes through what it sets" in explain(spec, "quality-held")
    p = project(tmp_path, SET)
    p.measurements.add("sensor/quality.main", 0.7)
    e = Engine(p, say=lambda s: None)
    e.evaluate()
    assert e.status["quality-held"] == "off"
    e.run_block(p.model.spec.blocks["tuner"], "test")
    assert p.measurements.latest("sensor/setting.set")[1] == 75
    assert p.events.query(n=1, type="auxiliary.set", item="setting")
    e.evaluate()
    assert e.signals["auxiliary.setting"] == 75


def test_the_old_name_is_read_with_a_finding_that_says_what_to_rename(tmp_path):
    old = SET.replace("auxiliaries:", "variables:").replace("auxiliary.setting", "variable.setting") \
             .replace("auxiliary: quality", "variable: quality")
    spec, problems = load(tmp_path, old)
    assert not [x for x in problems if x.level == "error"], problems
    assert set(spec.auxiliaries) == {"quality", "setting"} and spec.loop("quality-held").closes
    said = [x.message for x in problems if x.code == "deprecated-name"]
    assert any("variables: is now auxiliaries:" in m for m in said)
    assert any("variable.NAME is now auxiliary.NAME" in m and "2 places" in m for m in said)
    assert any("variable: is now auxiliary:" in m for m in said)
    # and an engine still takes a block's old {"out": "variable.setting"}
    (tmp_path / "say.sh").write_text("echo '{\"out\": \"variable.setting\", \"value\": 70}'\n")
    p = project(tmp_path, old.replace("run: echo 75", "run: sh say.sh"))
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["tuner"], "test")
    assert p.measurements.latest("sensor/setting.set")[1] == 70


def test_the_compiler_refuses_two_setters_unknown_auxiliaries_and_a_driven_exogenous_input(tmp_path):
    bad = SET + "  other:\n    type: program\n    run: echo 1\n    out: auxiliary.setting\n" \
                "  reader:\n    type: program\n    run: echo 1\n    in: auxiliary.qualty\n"
    _, problems = load(tmp_path, bad)
    codes = {x.code for x in problems if x.level == "error"}
    assert "two-actuators" in codes and "unknown-ref" in codes
    assert any("did you mean quality" in x.message for x in problems)
    _, problems = load(tmp_path, SET.replace("    driven-by: auxiliary.setting", "    exogenous: true\n    driven-by: auxiliary.setting"))
    assert "exogenous-driven" in {x.code for x in problems}
    _, problems = load(tmp_path, SET.replace("in: goal.quality-held.error", "in: +goal.quality-held.error"))
    assert any("a sign is written on what a block reads of a stock, flow or auxiliary" in x.message for x in problems)


def test_the_diagram_draws_auxiliaries_two_way_flows_and_signed_influences(tmp_path):
    p = project(tmp_path)
    p.measurements.add("sensor/quality.main", 0.91, time.time())
    from ergostat.web.server import Live, api
    g = api(Live(p), "graph", {})
    by = {n["id"]: n for n in g["nodes"]}
    assert by["stock:quality"]["kind"] == "auxiliary" and not by["stock:quality"]["memory"]
    assert by["stock:setting"]["kind"] == "stock" and by["stock:setting"]["memory"]
    assert by["flow:steps"]["twoWay"]
    edges = {(e["source"], e["target"], e["kind"]): e for e in g["edges"]}
    assert edges[("stock:setting", "stock:quality", "influence")]["polarity"] == "+"
    assert edges[("flow:steps", "stock:setting", "pipe")]["polarity"] == "+"
    assert ("controller:quality-held", "flow:steps", "action") in edges
    assert g["loops"]["quality-held"]["closes"]
    held = next(c for c in g["causalLoops"] if c["name"] == "quality-held")
    assert held["polarity"] == "B" and held["nodes"][0] == "stock:quality"
    assert "quality-held" in edges[("flow:steps", "stock:setting", "pipe")]["causal"]
    p = project(tmp_path, SET)
    g = api(Live(p), "graph", {})
    assert not any(n["id"] == "sensor:setting.set" for n in g["nodes"])          # what it was set to is not an instrument
    assert next(n for n in g["nodes"] if n["id"] == "stock:setting")["agent"]["name"] == "tuner"


def test_a_sensor_records_what_it_observed_about_items_and_never_a_command(tmp_path):
    """The benchmark: one command reads the score and reports each case it measured."""
    p = project(tmp_path, """
projections:
  case:
    id: case/*
    states: [unmet, met]
    on:
      case.met: met
auxiliaries:
  score:
    unit: KB/MP
    sensor:
      run: >-
        echo '{"event": "case.met", "item": "case/a", "data": {"kb": 3}}';
        echo '{"event": "auxiliary.set", "item": "case/b"}';
        echo '{"event": "case.met", "item": "nobody"}';
        echo 12.5
""")
    e = Engine(p, say=lambda s: None)
    e._read(p.model.spec.auxiliaries["score"].sensors["main"])
    assert p.measurements.latest("sensor/score.main")[1] == 12.5
    got = p.events.query(n=10, type="case.met")
    assert [(x["item"], x["source"]) for x in got] == [("case/a", "score.main")]
    assert not p.events.query(n=10, type="auxiliary.set")
    assert len(p.events.query(n=10, type="sensor.refused")) == 2
    from ergostat.spec.items import one
    assert one(p.events, p.model.spec, "case/a").state == "met"


def test_a_stock_read_by_a_script_gets_its_flows_from_its_own_rises_and_falls(tmp_path):
    """A benchmark's points: a release that gains 6 is an inflow, a sudden fall of 4 an outflow."""
    text = """
stocks:
  points:
    sensor:
      manual: true
flows:
  gained:
    to: points
    driven-by: +flow.released
    sensor:
      changes: rises
      over: 1h
  lost:
    from: points
    sensor:
      changes: falls
      over: 1h
  drift:
    to: points
    two-way: true
    sensor:
      changes: net
      over: 1h
  released:
    to: points
"""
    p = project(tmp_path, text)
    spec = p.model.spec
    now = time.time()
    for dt, v in ((-7200, 0), (-1800, 10), (-1200, 16), (-600, 12)):
        p.measurements.add("sensor/points.main", v, now + dt)
    from ergostat.spec.engine import changed
    got = {f: changed(spec, spec.flows[f].sensors["main"], p.measurements, now)[0] for f in ("gained", "lost", "drift")}
    assert got == {"gained": 16.0, "lost": 4.0, "drift": 12.0}       # from 0 an hour and more ago: +10, +6, −4
    assert "rose" in explain(spec, "flow.gained")
    _, problems = load(tmp_path, text.replace("      changes: rises", "      changes: falls"))
    assert "bad-changes" in {x.code for x in problems}
    _, problems = load(tmp_path, text.replace("    two-way: true\n", ""))
    assert any("two-way: true" in x.message for x in problems if x.code == "bad-changes")
