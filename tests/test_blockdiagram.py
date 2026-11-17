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
            assert any(nodes[e["target"]].get("role") in ("process", "process-sum", None) or nodes[e["target"]]["kind"] in ("mux", "sum")
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
    # the setting the tuner steps reaches the process through its hold and the junction where adopted adds
    assert any(e["source"] == "jsum:tuner" and e["target"] == "mux:service" for e in g["edges"])
    # stocks moved only by blocks are integrators, each flow with its sign
    assert n["proc:stock.ideas"]["fn"]["expr"] == "1/s"
    signs = {e["key"]: e["sign"] for e in g["edges"] if e["target"] == "psum:stock.ideas"}
    assert signs == {"flow.proposed": "+", "flow.started": "−"}
    # an AI agent is not a transfer function
    assert n["blk:researcher"]["fn"]["linear"] is False and n["blk:researcher"]["fn"]["name"] == "researcher"
    # the error of the quality loop: e = r − y_m, its measurement read with unity gain: the wire itself, from the process
    ins = {e["source"]: e["sign"] for e in g["edges"] if e["target"] == "sum:quality-held"}
    assert ins == {"ref:quality-held": "+", "demux:service": "−"}


def test_closed_systems_are_subsystem_blocks_and_vectors_join_them():
    spec = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    g = drawn(spec)
    assert {n["id"] for n in g["nodes"]} == {"sys:service", "sys:rollout", "sys:lab", "sys:benchmark"}
    for n in g["nodes"]:
        assert n["fn"]["sym"] == "Q"
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
    assert d == {"psum:stock.stale-pages", "blk:page-picker"}       # into the process, and read (a unity sensor: the wire)


def test_an_older_model_is_converted_and_drawn(repo):
    from ergostat import model as mdl
    m = mdl.load(repo.path)
    g = bd.diagram(m, {})
    assert any(n["kind"] == "sum" for n in g["nodes"]) and any(n["kind"] == "block" for n in g["nodes"])


# ---- the expert review of the blocks view (REVIEW.md, K1 and K3 to K7, K13)

def _all_views(spec):
    for open_, focus in views(spec):
        yield f"open={open_} system={focus}", drawn(spec, open_, focus)


def _text(x) -> str:
    """Every string in a panel (its sentence, its rows, its MathML), as one text."""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return " ".join(_text(v) for v in x.values())
    if isinstance(x, list | tuple):
        return " ".join(_text(v) for v in x)
    return ""


def test_a_mimo_process_has_a_zero_only_where_no_path_inside_it_leads_from_the_input_to_the_output():
    # deployed reaches users through fixes → bugs-live → signups and through shipped → missing-ops → churn
    spec = load(ROOT / "examples" / "software-factory" / "ergostat.yaml")
    n = {x["id"]: x for x in drawn(spec, {"*"})["nodes"]}
    p = n["proc:product"]
    assert p["pattern"]["stock.users"].get("flow.deployed"), p["pattern"]
    assert all(p["pattern"][o].get("flow.deployed") for o in ("stock.bugs-live", "stock.missing-ops", "stock.users"))
    # two paths of opposite sign: the entry is P, unsigned; never 0
    matrix = next(m for m in p["math"] if "mtable" in str(m))
    assert '["mn", "0"]' not in str(matrix).replace("'", '"')


def test_zero_pattern_follows_paths_through_the_other_outputs_with_their_signs(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        stocks:
          a: {unit: x, sensor: {run: echo 1, every: 1m}}
          b: {unit: x, sensor: {run: echo 1, every: 1m}}
          c: {unit: x, sensor: {run: echo 1, every: 1m}}
        flows:
          push: {to: a}
          into-b: {to: b, driven-by: +stock.a}
          out-of-c: {from: c, driven-by: +stock.b}
          into-c: {to: c, driven-by: +stock.a}
        goals:
          a-low: {stock: a, hold: "<= 5"}
          b-low: {stock: b, hold: "<= 5"}
          c-low: {stock: c, hold: "<= 5"}
        blocks:
          pusher: {type: program, run: echo 1, every: 1m, goal: a-low, out: flow.push}
        """))
    d = bd._Diagram(load(tmp_path / "ergostat.yaml"), {})
    members = ["stock.b", "stock.c"]
    info = {"stock.b": ({"flow.into-b"}, {"stock.a"}, set()),            # (what is inside, inputs, other outputs)
            "stock.c": ({"flow.into-c", "flow.out-of-c"}, {"stock.a"}, {"stock.b"})}
    pat = d.zero_pattern(members, ["stock.a"], info)
    assert pat["stock.b"] == {"stock.a": {1}}
    assert pat["stock.c"]["stock.a"] == {1, -1}        # a → into-c (+), and a → b → out-of-c (−)


def test_a_discrete_controller_meets_the_continuous_process_through_a_sampler_and_a_hold():
    spec = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    for where, g in _all_views(spec):
        n = {x["id"]: x for x in g["nodes"]}
        for b in [x for x in g["nodes"] if (x.get("fn") or {}).get("arg") == "z"]:
            name = b["id"].split(":", 1)[1]
            into = [e for e in g["edges"] if e["target"] == b["id"]]
            if [e["source"] for e in into] == [f"dz:{name}"]:          # its dead band, a nonlinearity between them
                into = [e for e in g["edges"] if e["target"] == f"dz:{name}"]
            assert [e["source"] for e in into] == [f"smp:{name}"], (where, b["id"], into)
            assert n[f"smp:{name}"]["kind"] == "sampler"
            # one hold per output: each output is its own continuous signal, held between samples
            out = [e for e in g["edges"] if e["source"] == b["id"]]
            assert out and all(e["target"] == f"zoh:{name}" or e["target"].startswith(f"zoh:{name}:") for e in out), \
                (where, b["id"], out)
            assert len({e["sourcePort"] for e in out}) == len({e["target"] for e in out})
            for e in out:
                assert n[e["target"]]["role"] == "hold" and "e" in str(n[e["target"]]["math"])
            # what comes after the hold is continuous: nothing from a z block reaches a process unheld
        for e in g["edges"]:
            src = n.get(e["source"]) or {}
            assert (src.get("fn") or {}).get("arg") != "z" or e["target"].startswith("zoh:"), (where, e["id"])


def test_a_subsystem_is_a_transfer_function_only_when_every_part_inside_is_continuous():
    sq = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    n = {x["id"]: x for x in drawn(sq)["nodes"]}
    assert n["sys:service"]["fn"]["arg"] is None and n["sys:rollout"]["fn"]["arg"] is None      # C(z), relays, agents
    assert "operator" in _text(n["sys:rollout"]["math"])
    sf = load(ROOT / "examples" / "software-factory" / "ergostat.yaml")
    g = drawn(sf, {"factory"})
    n = {x["id"]: x for x in g["nodes"]}
    assert n["sys:product"]["fn"]["arg"] == "s"                    # only the world's process inside
    assert next(f for f in g["frames"] if f["id"] == "frame:factory")["fn"]["arg"] is None


def test_a_transfer_function_block_takes_one_input_the_rest_enter_at_a_summing_junction_with_signs():
    for ex in EXAMPLES:
        spec = load(ROOT / "examples" / ex / "ergostat.yaml")
        for where, g in _all_views(spec):
            for b in g["nodes"]:
                fn = b.get("fn") or {}
                if b["kind"] == "block" and fn.get("sym") and not fn.get("name") and b["id"].startswith("blk:"):
                    assert len(b["ins"]) <= 1, (ex, where, b["id"], b["ins"])
    spec = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    g = drawn(spec, {"*"})
    signs = {e["key"]: e["sign"] for e in g["edges"] if e["target"] == "jsum:matcher"}
    assert signs == {"held:matcher": "+", "flow.adopted": "−"}         # it resets its own offset: adopted alone moves it too
    signs = {e["key"]: e["sign"] for e in g["edges"] if e["target"] == "jsum:tuner"}
    assert signs == {"held:tuner": "+", "flow.adopted": "+"}


def test_a_comparator_sits_in_the_frame_of_the_controller_that_reads_its_error():
    spec = load(ROOT / "examples" / "software-factory" / "ergostat.yaml")
    n = {x["id"]: x for x in drawn(spec, {"*"})["nodes"]}
    assert n["sum:backlog-clear"]["parent"] == n["blk:keep-backlog-clear"]["parent"] == "frame:delivery"
    assert n["ref:backlog-clear"]["parent"] == "frame:delivery"


def test_unity_sensors_are_wires_and_a_measured_signal_with_dynamics_is_named_for_its_variable():
    for ex in EXAMPLES:
        spec = load(ROOT / "examples" / ex / "ergostat.yaml")
        d = bd._Diagram(spec, {})
        d.build()
        for nid, n in d.nodes.items():
            if n.get("role") == "sensor":
                assert d.sensor_dynamics(n["part"]), (ex, nid, "a unity sensor drawn as a block")
                assert n["fn"]["expr"] != "1"
        for e in d.wires:
            sg = d.signal(e["key"]) if e["key"] not in d.sig else d.sig[e["key"]]
            if sg.get("what") == "measured":
                assert sg["sub"].startswith("m,") and len(sg["sub"]) > 2, (ex, e["key"], sg)
    # a unity reading says how it is sampled, in the panel of its wire
    spec = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    g = drawn(spec, {"*"})
    fb = next(e for e in g["edges"] if e["target"] == "sum:quality-held" and e["sign"] == "−")
    assert "sampled every" in fb["note"] and "unity" in fb["note"]


def test_a_sensor_with_a_window_is_drawn_as_h_of_s_and_its_signal_is_y_m_of_its_variable(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        stocks:
          queue: {unit: jobs, sensor: {run: echo 3, every: 10s}}
        flows:
          arrivals:
            to: queue
            sensor: {changes: rises, over: 10m, every: 10s}
          served: {from: queue}
        goals:
          calm: {flow: arrivals, hold: "<= 30"}
        blocks:
          gate: {type: program, run: echo 1, every: 1m, goal: calm, out: flow.served}
        """))
    g = drawn(load(tmp_path / "ergostat.yaml"), {"*"})
    n = {x["id"]: x for x in g["nodes"]}
    h = n["sen:flow.arrivals"]
    assert (h["fn"]["sym"], h["fn"]["arg"]) == ("H", "s") and "10m" in _text(h["math"])
    ym = next(e for e in g["edges"] if e["source"] == "sen:flow.arrivals")
    assert (ym["signal"]["sym"], ym["signal"]["sub"]) == ("y", "m,arrivals")


def test_a_reference_is_a_value_and_the_relay_says_its_threshold():
    spec = load(ROOT / "examples" / "software-factory" / "ergostat.yaml")
    g = drawn(spec, {"*"})
    n = {x["id"]: x for x in g["nodes"]}
    r = n["ref:backlog-clear"]
    assert r["fn"]["value"] == "= 0" and "≤" not in r["fn"]["value"]
    relay = n["blk:keep-backlog-clear"]
    rows = dict(relay["rows"])
    assert rows["threshold"] == "backlog ≤ 0: on above it", rows
    assert "y_backlog > 0" in relay["says"]
    sq = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    assert {x["id"]: x for x in drawn(sq, {"*"})["nodes"]}["ref:quality-held"]["fn"]["value"] == "= 0.93"
    for ex in EXAMPLES:                                  # real ≤ ≥ everywhere: no ASCII comparison in a label or a panel
        spec = load(ROOT / "examples" / ex / "ergostat.yaml")
        for where, g in _all_views(spec):
            for x in [*g["nodes"], *g["frames"], *g["loops"].values()]:
                t = _text({k: v for k, v in x.items() if k != "description"} if isinstance(x, dict) else x)
                t = t.replace(_text([r[1] for r in x.get("rows", []) if r[0] == "description"]), "")
                assert not any(op in t for op in ("<=", ">=", "==")), (ex, where, x.get("id"), t[:200])


def test_the_blocks_panels_use_control_words_only():
    banned = ("stock", "flows", "inflow", "outflow", "net flow", "moves ", "a AI", " a run")
    for ex in EXAMPLES:
        spec = load(ROOT / "examples" / ex / "ergostat.yaml")
        descriptions = {d for d in [*(s.description for s in spec.stocks.values()), *(f.description for f in spec.flows.values()),
                                    *(a.description for a in spec.auxiliaries.values()), *(b.description for b in spec.blocks.values()),
                                    *(g.description for g in spec.goals.values()), *spec.systems.values()] if d}
        for where, g in _all_views(spec):
            for n in g["nodes"]:
                said = _text([n.get("says", ""), n.get("math", []), [r for r in n.get("rows", []) if r[0] != "description"]])
                for d in descriptions:
                    said = said.replace(d, "")
                bad = [w for w in banned if w in said]
                assert not bad, (ex, where, n["id"], bad, said[:300])
    # an integrator is said as one
    spec = load(ROOT / "examples" / "software-factory" / "ergostat.yaml")
    n = {x["id"]: x for x in drawn(spec, {"*"})["nodes"]}
    assert n["proc:stock.in-review"]["says"].startswith("integrator: the sum of its inputs over time")


def test_a_block_that_weighs_several_signals_is_not_integral_action():
    spec = load(ROOT / "examples" / "image-squeeze" / "ergostat.yaml")
    n = {x["id"]: x for x in drawn(spec, {"*"})["nodes"]}
    assert n["blk:rollout"]["fn"].get("name") == "rollout" and n["blk:rollout"]["fn"].get("arg") is None
    assert "zoh:rollout" not in n and not any(k.startswith("zoh:rollout:") for k in n)


def test_a_discrete_controller_with_several_outputs_holds_each_one(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        stocks:
          level: {unit: x, sensor: {run: echo 1, every: 1m}}
          knob: {unit: x, sensor: {run: echo 1, every: 1m}}
          other: {unit: x, sensor: {run: echo 1, every: 1m}}
        flows:
          turn: {to: knob, two-way: true}
          fill: {to: level, driven-by: +stock.knob}
          drain: {from: level, driven-by: +stock.other}
          bump: {to: other}
        goals:
          level-held: {stock: level, hold: "== 5"}
        blocks:
          stepper:
            type: program
            run: echo 1
            every: 30s
            in: {err: goal.level-held.error}
            out: {step: flow.turn, also: flow.bump}
        """))
    g = drawn(load(tmp_path / "ergostat.yaml"), {"*"})
    n = {x["id"]: x for x in g["nodes"]}
    assert n["blk:stepper"]["fn"]["arg"] == "z"
    holds = sorted(e["target"] for e in g["edges"] if e["source"] == "blk:stepper")
    assert holds == ["zoh:stepper", "zoh:stepper:flow.bump"], holds
    assert all(n[h]["role"] == "hold" for h in holds)
