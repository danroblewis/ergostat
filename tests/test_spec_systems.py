"""Systems as parts: they nest (within:), each has an interface worked out from what crosses its
boundary, a system given a setpoint whose measurement goes back out is an inner loop (a cascade),
and the control diagram folds each system into a box with those ports, opens it, or draws it
alone with what it reaches outside as terminals."""

import os
import tempfile
import textwrap

from ergostat import model as mdl
from ergostat.fold import default_open, fold
from ergostat.spec import read
from ergostat.spec.explain import explain
from ergostat.store import Project

MODEL = """
systems:
  plant:
    description: the whole thing
  room:
    within: plant
  heater:
    within: plant
stocks:
  temperature:
    system: room
    unit: degrees
    sensor:
      manual: true
  fuel:
    system: heater
    unit: litres
    sensor:
      manual: true
flows:
  heat-in:
    system: room
    to: temperature
    driven-by: flow.burn
  heat-out:
    system: room
    from: temperature
  burn:
    system: heater
    from: fuel
goals:
  warm:
    system: room
    stock: temperature
    hold: ">= 20"
  burner-rate:
    system: heater
    flow: burn
    hold: "== 2"
blocks:
  thermostat:
    system: room
    type: proportional
    goal: warm
    gain: 0.5
    out: goal.burner-rate
  burner:
    system: heater
    type: program
    run: echo 1
    in: goal.burner-rate
    out: flow.burn
  watcher:
    system: heater
    type: program
    run: echo 1
    in: flow.burn
    out: block.burner
"""


def spec_of(tmp_path, text=MODEL):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    spec, problems = read(tmp_path / "ergostat.yaml")
    return spec, problems


def test_systems_nest_and_a_cycle_or_an_unknown_parent_is_refused(tmp_path):
    spec, problems = spec_of(tmp_path)
    assert not [x for x in problems if x.level == "error"], problems
    assert spec.chain("room") == ["room", "plant"] and spec.subsystems("plant") == ["heater", "room"]
    assert spec.subsystems(None) == ["plant"]
    bad = MODEL.replace("  plant:\n    description: the whole thing", "  plant:\n    within: room")
    _, problems = spec_of(tmp_path, bad)
    assert "system-cycle" in {x.code for x in problems}
    _, problems = spec_of(tmp_path, MODEL.replace("    within: plant\n  heater:", "    within: plnt\n  heater:"))
    assert any(x.code == "unknown-ref" and "did you mean plant" in x.message for x in problems)


def test_the_interface_is_what_crosses_the_boundary_and_a_cascade_is_named(tmp_path):
    spec, _ = spec_of(tmp_path)
    heater = {(p["dir"], p["kind"], p["part"]) for p in spec.interface("heater")}
    assert ("in", "setpoint", "goal.burner-rate") in heater          # the room's thermostat sets it
    assert ("out", "influence", "flow.burn") in heater                # the burn drives heat into the room
    room = {(p["dir"], p["kind"], p["part"]) for p in spec.interface("room")}
    assert ("out", "setpoint", "block.thermostat") in room and ("in", "influence", "flow.heat-in") in room
    assert spec.interface("plant") == []                              # nothing outside the whole thing
    assert spec.inner_loops("heater") == []                           # its burn rate is not read back out
    looped = MODEL + "  logger:\n    system: room\n    type: program\n    run: echo 0\n    in: flow.burn\n"
    spec, _ = spec_of(tmp_path, looped)
    assert spec.inner_loops("heater") == ["burner-rate"]
    text = explain(spec, "system.heater")
    assert "inner loop" in text and "goal.burner-rate" in text and "Within plant" in text


def test_the_diagram_folds_systems_into_boxes_opens_them_and_draws_one_alone(tmp_path):
    spec_of(tmp_path)
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    p = Project(mdl.load(tmp_path))
    from ergostat.web.server import Live, api
    live = Live(p)
    m = p.model
    assert default_open(m.spec, None) == {"plant"}                    # alone at its level: opened
    g = api(live, "graph", {})
    kinds = {n["id"]: n["kind"] for n in g["nodes"]}
    assert kinds == {"system:room": "system", "system:heater": "system"}
    heater = next(n for n in g["nodes"] if n["id"] == "system:heater")
    # the control view draws the room's goal acting on the burn (it draws no goal on a flow, no built-in block)
    assert {(x["side"], x["label"]) for x in heater["ports"]} == {("in", "burn"), ("out", "burn")}
    assert heater["systems"] == ["plant"]                             # drawn inside the plant's outline
    assert all(e["source"] != e["target"] for e in g["edges"])
    assert any(e.get("sourcePort", "").startswith("system:heater:out:") and e["target"] == "system:room" for e in g["edges"])
    opened = api(live, "graph", {"open": ["plant,heater"]})
    ids = {n["id"] for n in opened["nodes"]}
    assert "stock:fuel" in ids and "system:room" in ids and "system:heater" not in ids
    alone = api(live, "graph", {"system": ["heater"]})
    terms = [n for n in alone["nodes"] if n["kind"] == "terminal"]
    assert terms and all(t["in"] == "room" for t in terms)
    assert not any(n["id"].startswith("system:") for n in alone["nodes"])
    flat = api(live, "graph", {"open": ["*"]})
    assert not any(n["kind"] in ("system", "terminal") for n in flat["nodes"])


def test_a_model_without_systems_is_drawn_as_it_was(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("stocks:\n  a:\n    sensor:\n      manual: true\n")
    m = mdl.load(tmp_path)
    g = {"kind": "control", "nodes": [{"id": "stock:a", "kind": "stock", "label": "a"}], "edges": [], "loops": {}}
    assert fold(g, m, None) is g
