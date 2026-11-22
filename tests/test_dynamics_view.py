"""The system dynamics view (``ergostat/dynamics.py``): the same model drawn as Sterman, Vensim and
Stella draw it, with no sensor, controller or agent; each goal as a desired level and a gap; every
connector signed where the model knows its sign; every feedback loop's members as drawn."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def factory(tmp_path):
    d = tmp_path / "software-factory"
    shutil.copytree(ROOT / "examples" / "software-factory", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    live = Live(Project(mdl.load(d)))
    return lambda **q: api(live, "graph", {k: [v] for k, v in q.items()})


@pytest.mark.parametrize("example,box,description", [("the-job", "job", "what I am expected to do, and what I am judged on"),
                                                    ("software-factory", "product", "textkit and its customers")])
def test_each_closed_system_box_is_given_the_description_it_prints(tmp_path, example, box, description):
    """A closed system's box in Dynamics prints the description its node carries (dynamics.js sdSystem); with none
    it falls back to 'a module: open it…'. The browser half of this check, that the box shows it and counts no
    loops, is tests/test_diagram_rendering.py::test_each_closed_system_box_says_what_the_system_is."""
    d = tmp_path / example
    shutil.copytree(ROOT / "examples" / example, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    g = api(Live(Project(mdl.load(d))), "graph", {"view": ["dynamics"], "open": ["-"]})
    closed = {n["label"]: n.get("description") for n in g["nodes"] if n["kind"] == "system"}
    assert closed.get(box) == description, closed


def test_no_sensor_controller_or_agent_is_drawn_and_every_connector_says_its_sign(factory):
    g = factory(view="dynamics", open="*")
    assert g["kind"] == "dynamics"
    assert {n["kind"] for n in g["nodes"]} <= {"stock", "auxiliary", "valve", "disturbance", "cloud", "terminal"}   # (shadows)
    assert {e["kind"] for e in g["edges"]} == {"pipe", "connector"}
    assert not any(n.get("agent") for n in g["nodes"])
    conn = {(e["from"], e["target"]): e["polarity"] for e in g["edges"] if e["kind"] == "connector"}
    # driven-by as written: people come when what they ask for works, and leave when it does not
    assert conn[("stock:bugs-live", "flow:signups")] == "-" and conn[("stock:bugs-live", "flow:churn")] == "+"
    # support reads bugs-live, which a goal it serves (no-live-bugs ≤ 0) is about: it files more as bugs-live rises
    assert conn[("stock:bugs-live", "flow:filed-bugs")] == "+"


def test_each_loop_gives_every_link_around_it_a_sign_and_a_plain_name(factory):
    g = factory(view="dynamics", system="product")                  # (R2 runs through delivery, closed here)
    loops = {c["label"]: c for c in g["causalLoops"]}
    r2 = loops["R2"]["around"]
    assert len(r2) == len(set(loops["R2"]["nodes"])) >= 4
    assert all(x["sign"] in ("+", "-") for x in r2), r2
    assert not [x for x in r2 if ":" in x["fromName"] + x["toName"]], r2
    for c in loops.values():                                         # every loop's links signed alike with its polarity
        signs = [x["sign"] for x in c["around"]]
        if c["polarity"] and None not in signs:
            assert (signs.count("-") % 2 == 1) == (c["polarity"] == "B"), (c["label"], c["around"])
    # by definition: an outflow drains its stock, an inflow fills it; a ceiling's excess rises with its stock
    every = {(x["from"], x["to"]): x["sign"] for c in loops.values() for x in c["around"]}
    assert every.get(("flow:deployed", "stock:awaiting-deploy")) == "-" and every.get(("flow:merged", "stock:awaiting-deploy")) == "+"
    assert every.get(("stock:awaiting-deploy", "gap:all-live")) == "+"


def test_a_goal_is_drawn_as_a_desired_level_and_a_gap_feeding_the_flow_that_closes_it(factory):
    g = factory(view="dynamics", open="*")
    ids = {n["id"]: n for n in g["nodes"]}
    # a desired level is a value; the switching condition is the panel's
    assert ids["desired:backlog-clear"]["label"] == "desired backlog" and ids["desired:backlog-clear"]["valueText"] == "0"
    assert ids["desired:backlog-clear"]["switching"] == "on while backlog > 0; off once backlog ≤ 0"
    # a ceiling: the excess (actual − desired) drives the outflow +, as Sterman defines the discrepancy
    assert ids["gap:backlog-clear"]["label"] == "excess backlog" and ids["gap:backlog-clear"]["excess"]
    conn = {(e.get("from", e["source"]), e["target"]): e["polarity"] for e in g["edges"] if e["kind"] == "connector"}
    assert conn[("stock:backlog", "gap:backlog-clear")] == "+"
    assert conn[("desired:backlog-clear", "gap:backlog-clear")] == "-"
    sub = next(e for e in g["edges"] if e.get("from") == "gap:backlog-clear" and e["target"] == "flow:submitted")
    assert sub["polarity"] == "+"                                      # more backlog: more is worked off
    # a goal with no gap drawn here is no structure: it is said on its stock, with what serves it anywhere in the model
    assert "gap:no-live-bugs" not in ids
    assert ids["stock:bugs-live"]["goals"] == [{"name": "no-live-bugs", "setpoint": "≤ 0", "desired": "0",
                                                "by": [{"block": "support", "system": "factory"}], "acted": True}]
    assert ids["stock:users"]["goals"][0]["by"] == [{"block": "product-manager", "system": "factory"}]
    # ≤ and ≥, never <= and >=
    assert not [n for n in g["nodes"] if "<=" in str(n) or ">=" in str(n)]
    # the control view is untouched: the blocks view still reads its controllers from it
    ctl = factory(view="control", open="*")
    assert any(n["kind"] == "controller" for n in ctl["nodes"]) and any(n["kind"] == "sensor" for n in ctl["nodes"])


def test_a_goal_with_no_controller_anywhere_is_the_only_one_said_unacted(tmp_path):
    d = tmp_path / "software-factory"
    shutil.copytree(ROOT / "examples" / "software-factory", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    intake = d / "factory" / "intake.yaml"                   # support reads users instead: nothing reads bugs-live now
    intake.write_text(intake.read_text().replace("in: stock.bugs-live", "in: stock.users"))
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    g = api(Live(Project(mdl.load(d))), "graph", {"view": ["dynamics"], "open": ["*"]})
    ids = {n["id"]: n for n in g["nodes"]}
    assert ids["stock:bugs-live"]["goals"] == [{"name": "no-live-bugs", "setpoint": "≤ 0", "desired": "0", "by": [],
                                                "acted": False}]


def test_every_loop_is_labelled_and_runs_through_parts_drawn_and_lines_it_is_a_link_of(factory):
    g = factory(view="dynamics", open="*")
    ids = {n["id"] for n in g["nodes"]}
    loops = {c["name"]: c for c in g["causalLoops"]}
    assert loops["backlog-clear"]["polarity"] == "B" and loops["backlog-clear"]["label"].startswith("B")
    assert loops["backlog-clear"]["nodes"] == ["stock:backlog", "gap:backlog-clear", "flow:submitted"]
    assert loops["rework"]["label"] == "R1" and loops["rework"]["polarity"] == "R"     # named in the model (loops:)
    # every loop's sign is known here, and no name is numbered or a "+"-joined list
    assert all(c["polarity"] for c in g["causalLoops"])
    assert not [c["name"] for c in g["causalLoops"] if "+" in c["name"] or c["name"][-1].isdigit()]
    assert len({c["label"] for c in g["causalLoops"]}) == len(g["causalLoops"])
    for c in g["causalLoops"]:
        assert set(c["nodes"]) <= ids, c["name"]                         # (a shadow stands in for a part, never in its loop)
        ns = c["nodes"]
        for a, b in zip(ns, ns[1:] + ns[:1], strict=False):             # each link of it is a line drawn here
            assert any(c["name"] in e["causal"] and {e["from"], e["to"]} == {a, b} for e in g["edges"]), (c["name"], a, b)


def test_closed_systems_fold_the_loops_into_their_boxes(factory):
    g = factory(view="dynamics")
    ids = {n["id"] for n in g["nodes"]}
    assert all(i.startswith("system:") for i in ids)
    for c in g["causalLoops"]:
        assert set(c["nodes"]) <= ids
    assert all(not n["measures"] and n["status"] is None for n in g["nodes"])
    alone = factory(view="dynamics", system="delivery")
    assert any(n["kind"] == "terminal" for n in alone["nodes"])
    assert not any(n["kind"] in ("sensor", "controller") for n in alone["nodes"])


def test_a_line_between_parts_drawn_in_two_open_systems_is_drawn_as_itself(factory):
    g = factory(view="dynamics", open="*")
    ids = {n["id"]: n for n in g["nodes"]}
    assert not [n["id"] for n in g["nodes"] if n["kind"] in ("terminal",) or n.get("beyond")]   # no shadow, stub or named cloud
    conn = {(e["source"], e["target"]) for e in g["edges"] if e["kind"] == "connector"}
    # deployed (delivery) drives fixes, regressions and shipped (product): real connectors across the two open systems
    assert {("flow:deployed", "flow:fixes"), ("flow:deployed", "flow:regressions"), ("flow:deployed", "flow:shipped")} <= conn
    assert ids["flow:deployed"]["systems"][0] != ids["flow:fixes"]["systems"][0]
    assert ("gap:backlog-clear", "flow:submitted") in conn                # intake's excess drives delivery's flow
    pipes = {(e["source"], e["target"]) for e in g["edges"] if e["kind"] == "pipe"}
    assert ("stock:backlog", "flow:submitted") in pipes                   # and the pipe between them is a pipe


def test_a_closed_module_s_inside_is_still_a_shadow_in_the_open_system(factory):
    g = factory(view="dynamics", open="product")
    assert any(n.get("role") == "shadow" and n["label"] == "deployed" and n["in"] == "factory" for n in g["nodes"])


def test_a_shadow_is_an_input_only_pipes_out_end_in_clouds_and_connectors_out_in_stubs(factory):
    g = factory(view="dynamics", system="delivery")
    ids = {n["id"]: n for n in g["nodes"]}
    for e in g["edges"]:
        t = ids[e["target"]]
        assert not (t["kind"] == "terminal" and t.get("role") != "stub"), e["id"]        # nothing points into a shadow
        if e["kind"] == "pipe":
            assert "terminal" not in (ids[e["source"]]["kind"], t["kind"]), e["id"]   # a pipe leaves by a cloud
    clouds = {n["beyond"] for n in g["nodes"] if n["kind"] == "cloud" and n.get("beyond")}
    assert clouds == {"backlog"}
    assert sum(1 for e in g["edges"] if e["kind"] == "pipe" and ids[e["source"]].get("beyond") or
               e["kind"] == "pipe" and ids[e["target"]].get("beyond")) == 2      # submitted from it, rejected into it: a cloud each
    stubs = {n["label"] for n in g["nodes"] if n.get("role") == "stub"}
    assert stubs == {"fixes", "regressions", "shipped"}


def test_lines_out_of_and_into_a_closed_module_end_in_a_shadow_and_a_stub_inside_the_open_system(factory):
    g = factory(view="dynamics", open="product")
    ids = {n["id"]: n for n in g["nodes"]}
    for e in g["edges"]:
        if e["kind"] != "connector":
            continue
        s, t = ids[e["source"]], ids[e["target"]]
        assert not (s["kind"] == "system" and t["kind"] != "system"), e["id"]     # module → part: from a shadow
        assert not (t["kind"] == "system" and s["kind"] != "system"), e["id"]     # part → module: to a stub
    assert ids["shadow:product:flow:deployed"]["in"] == "factory"
    assert any(n.get("role") == "stub" and n["in"] == "factory" for n in g["nodes"])
    used = {e.get(k) for e in g["edges"] for k in ("sourcePort", "targetPort")}
    ports = {p["id"] for n in g["nodes"] if n["kind"] == "system" for p in n["ports"]}
    assert ports <= used                                                    # a port nothing crosses is not drawn


def test_the_attention_cards_speak_system_dynamics():
    from ergostat.dynamics import attention
    snap = {"loops": {"backlog-clear": {"status": "off", "stock": "backlog", "value": 4.0, "setpoint": "<= 0", "error": -4.0}}}
    att = [{"level": "bad", "what": "loop backlog-clear", "says": "backlog is 4, setpoint <= 0 (off by 4)"},
           {"level": "hint", "what": "controller backlog-clear", "says": "loop backlog-clear was off 60% of the time; why (a valve "
            "too small, or acting too seldom) is said after 10m of record"},
           {"level": "hint", "what": "controller x", "says": "dev (ai) decided \"go\" 9 of 10 times: a rule could fill controller x"},
           {"level": "hint", "what": "controller a", "says": "loop a keeps feeding x: Hold a back (its controller can read x)"}]
    out = attention(att, snap)
    assert out[0]["says"] == "backlog is 4, desired backlog = 0: excess 4"
    import re
    for a in out:
        text = a["what"] + " " + a["says"]
        assert not re.search(r"controller|setpoint|\brule|\bgoal|valve|<=|>=", text), text


def test_each_valve_says_its_equation_or_what_is_not_known_yet(factory):
    """A valve's panel says what its rate is as far as the model says: its equation where it writes
    one, a decision that sets it, or declared causes with a sign and no size yet, and which act at once."""
    g = factory(view="dynamics", open="*")
    ids = {n["id"]: n for n in g["nodes"]}
    assert ids["flow:regressions"]["equation"] == "auxiliary.ops-broken-per-ticket * flow.deployed (per hour, written)"
    assert ids["flow:submitted"]["equation"].startswith("set by the decision ")
    assert "not known yet: a declared cause with a sign, its size not estimated" in ids["flow:asks"]["equation"]
    from ergostat.dynamics import equation
    from ergostat.spec.ir import Flow, Spec
    s = Spec("t", ROOT, [])
    s.flows["leak"] = Flow("leak", rate=2.0)
    s.flows["rain"] = Flow("rain")
    assert equation(s, "leak") == "2 per hour, declared: a constant"
    assert equation(s, "rain") == "not known: nothing in the model drives it, and it is not measured"


def test_a_connector_declared_with_driven_by_says_so_and_no_other_does(factory):
    """The page draws a driven-by link dashed (dynamics.js) from this flag; every connector carries it."""
    g = factory(view="dynamics", open="*")
    conn = {(e.get("from", e["source"]), e["target"]): e for e in g["edges"] if e["kind"] == "connector"}
    assert all(isinstance(e["drivenBy"], bool) for e in conn.values())
    # signups: driven-by: [-stock.bugs-live, -stock.missing-ops] (product.yaml)
    assert conn[("stock:bugs-live", "flow:signups")]["drivenBy"] is True
    # a goal's gap feeding the flow that closes it is no driven-by: drawn solid
    assert conn[("gap:backlog-clear", "flow:submitted")]["drivenBy"] is False
