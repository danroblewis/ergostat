"""The control view as a block diagram (ergostat/blockdiagram.py): every controller, actuator, process
and sensor once, a function in every block, signs at every summing junction, no placeholder, cascades
nested, MIMO where outputs share their inputs, and systems as subsystem blocks Q(s)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ergostat import blockdiagram as bd
from ergostat.spec import load
from tests.test_spec_systems import MODEL as CASCADE

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted(p.name for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists())


class _M:
    def __init__(self, spec):
        self.spec = spec


def drawn(spec, open_=None, focus=None) -> dict:
    return bd.diagram(_M(spec), {}, open_, focus)


def views(spec):
    yield None, None
    yield {"*"}, None
    for s in spec.systems:
        yield {s}, None
        yield None, s


def function_of(n: dict) -> str:
    fn = n.get("fn") or {}
    return fn.get("name") or (fn.get("sym") or "")


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_view_has_a_function_in_every_block_signs_at_every_junction_and_no_placeholder(example):
    spec = load(ROOT / "examples" / example / "ergostat.yaml")
    for open_, focus in views(spec):
        g = drawn(spec, open_, focus)
        where = f"{example} open={open_} system={focus}"
        ids = [n["id"] for n in g["nodes"]]
        assert len(ids) == len(set(ids)), where
        for n in g["nodes"]:
            assert "valve" not in n.get("label", "") and "no sensor" not in n.get("label", ""), (where, n["id"])
            if n["kind"] == "block":
                assert function_of(n), (where, n["id"], "a block with no function in it")
                assert n.get("math"), (where, n["id"], "a block with no definition")
            if n["kind"] == "sum":
                assert n["ins"] and all(p.get("sign") in ("+", "−") for p in n["ins"]), (where, n["id"])
        ports = {p["id"] for n in g["nodes"] for p in [*n["ins"], *n["outs"]]}
        for e in g["edges"]:
            assert e["sourcePort"] in ports and e["targetPort"] in ports, (where, e["id"])
            assert e["signal"].get("sym") is not None, (where, e["id"])
        # each block of the model drawn once, when everything is open
        if open_ == {"*"} or not spec.systems:
            blocks = [n["id"] for n in g["nodes"] if n["id"].startswith("blk:")]
            assert len(blocks) == len(set(blocks))


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_loop_that_acts_has_its_real_actuator_wired_into_the_world(example):
    spec = load(ROOT / "examples" / example / "ergostat.yaml")
    g = drawn(spec, {"*"})
    nodes = {n["id"]: n for n in g["nodes"]}
    for goal in spec.goals:
        lp = spec.loop(goal)
        for a in lp.actuators:
            out = [e for e in g["edges"] if e["source"] == f"blk:{a}"]
            assert out, f"{example}: {a}, the actuator of {goal}, drives nothing"
            assert any(nodes[e["target"]]["role"] in ("process", "process-sum", None) or nodes[e["target"]]["kind"] in ("mux", "sum")
                       for e in out), (example, a, [e["target"] for e in out])


def test_image_squeeze_the_service_is_one_mimo_process_and_the_tuner_integrates():
    spec = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    g = drawn(spec, {"*"})
    n = {x["id"]: x for x in g["nodes"]}
    svc = n["proc:service"]
    assert svc["mimo"] == [4, 4] and "mux:service" in n and "demux:service" in n
    into = {e["key"] for e in g["edges"] if e["target"] == "mux:service"}
    assert {"stock.quality-setting", "stock.rollout-share", "auxiliary.flat-share"} <= into
    vec = next(e for e in g["edges"] if e["source"] == "mux:service")
    assert vec["signal"]["n"] == 4
    tuner = n["blk:tuner"]["fn"]
    assert (tuner["sym"], tuner["sub"], tuner["arg"]) == ("C", "tuner", "z") and "z − 1" in tuner["expr"]
    # stocks moved only by blocks are integrators, each flow with its sign
    assert n["proc:stock.ideas"]["fn"]["expr"] == "1/s"
    signs = {e["key"]: e["sign"] for e in g["edges"] if e["target"] == "psum:stock.ideas"}
    assert signs == {"flow.proposed": "+", "flow.started": "−"}
    # an AI agent is not a transfer function
    assert n["blk:researcher"]["fn"]["linear"] is False and n["blk:researcher"]["fn"]["name"] == "researcher"
    # the error of the quality loop: e = r − y_m, its measurement through the sensor beneath
    ins = {e["source"]: e["sign"] for e in g["edges"] if e["target"] == "sum:quality-held"}
    assert ins == {"ref:quality-held": "+", "sen:stock.quality": "−"}


def test_closed_systems_are_subsystem_blocks_and_vectors_join_them():
    spec = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    g = drawn(spec)
    assert {n["id"] for n in g["nodes"]} == {"sys:service", "sys:rollout", "sys:lab", "sys:benchmark"}
    for n in g["nodes"]:
        assert n["fn"]["sym"] == "Q" and n["fn"]["arg"] == "s"
    assert any(e["signal"].get("n", 1) > 1 for e in g["edges"])
    one = drawn(spec, {"service"})
    ids = {n["id"] for n in one["nodes"]}
    assert "blk:tuner" in ids and "sys:rollout" in ids and "sys:service" not in ids
    assert any(f["id"] == "frame:service" for f in one["frames"])
    alone = drawn(spec, None, "service")
    assert all(not n["id"].startswith("sys:") for n in alone["nodes"])
    ports = [n for n in alone["nodes"] if n["kind"] == "port"]
    assert ports and {p["port_of"] for p in ports} == {"in", "out"}


def test_a_cascade_draws_its_inner_loop_nested(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(CASCADE))
    spec = load(tmp_path / "ergostat.yaml")
    g = drawn(spec, {"*"})
    n = {x["id"]: x for x in g["nodes"]}
    frame = next(f for f in g["frames"] if f["frame"] == "cascade")
    assert frame["goal"] == "burner-rate" and frame["parent"] == "frame:heater"
    assert n["sum:burner-rate"]["parent"] == frame["id"] and n["blk:burner"]["parent"] == frame["id"]
    assert n["blk:thermostat"]["parent"] == "frame:room"            # the outer controller outside it
    # the outer controller's output is the inner loop's setpoint
    assert any(e["source"] == "blk:thermostat" and e["target"] == "sum:burner-rate" and e["sign"] == "+" for e in g["edges"])
    assert n["blk:thermostat"]["fn"]["expr"] == "K_p = 0.5"
    # a disturbance enters at its own summing junction, in front of the stock's integrator
    assert any(e["source"] == "dist:flow.heat-out" and e["target"] == "psum:stock.temperature" and e["sign"] == "−"
               for e in g["edges"])
    assert n["proc:stock.temperature"]["fn"]["expr"] == "1/s"


def test_feedforward_a_controller_reading_a_disturbance_takes_it_off():
    spec = load(ROOT / "examples" / "docs-fresh" / "ergostat.yaml")
    g = drawn(spec, {"*"})
    d = {e["target"] for e in g["edges"] if e["source"] == "dist:flow.code-changes"}
    assert d == {"psum:stock.stale-pages", "sen:flow.code-changes"}       # into the process, and measured
    assert any(e["source"] == "sen:flow.code-changes" and e["target"] == "blk:page-picker" for e in g["edges"])


def test_an_older_model_is_converted_and_drawn(repo):
    from ergostat import model as mdl
    m = mdl.load(repo.path)
    g = bd.diagram(m, {})
    assert any(n["kind"] == "sum" for n in g["nodes"]) and any(n["kind"] == "block" for n in g["nodes"])
