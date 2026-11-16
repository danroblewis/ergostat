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


def test_no_sensor_controller_or_agent_is_drawn_and_every_connector_says_its_sign(factory):
    g = factory(view="dynamics", open="*")
    assert g["kind"] == "dynamics"
    assert {n["kind"] for n in g["nodes"]} <= {"stock", "auxiliary", "valve", "disturbance", "cloud"}
    assert {e["kind"] for e in g["edges"]} == {"pipe", "connector"}
    assert not any(n.get("agent") for n in g["nodes"])
    conn = {(e["source"], e["target"]): e["polarity"] for e in g["edges"] if e["kind"] == "connector"}
    # driven-by as written: people come when what they ask for works, and leave when it does not
    assert conn[("stock:bugs-live", "flow:signups")] == "-" and conn[("stock:bugs-live", "flow:churn")] == "+"
    # a support block reads the stock: what it does with it is its own, so the sign is not known
    assert conn[("stock:bugs-live", "flow:filed-bugs")] is None


def test_a_goal_is_drawn_as_a_desired_level_and_a_gap_feeding_the_flow_that_closes_it(factory):
    g = factory(view="dynamics", open="*")
    ids = {n["id"]: n for n in g["nodes"]}
    assert ids["desired:backlog-clear"]["label"] == "desired backlog" and ids["desired:backlog-clear"]["valueText"] == "≤ 0"
    assert ids["gap:backlog-clear"]["label"] == "backlog gap"
    conn = {(e["source"], e["target"]): e["polarity"] for e in g["edges"] if e["kind"] == "connector"}
    assert conn[("stock:backlog", "gap:backlog-clear")] == "-"          # gap = desired − actual
    assert conn[("desired:backlog-clear", "gap:backlog-clear")] == "+"
    assert conn[("gap:backlog-clear", "flow:submitted")] == "-"         # a bigger backlog: the gap falls, more is worked off
    # a goal nothing acts on is no structure: it is said on its stock, not drawn
    assert "gap:no-live-bugs" not in ids
    assert ids["stock:bugs-live"]["goals"] == [{"name": "no-live-bugs", "setpoint": "<= 0", "acted": False}]
    # the control view is untouched: the blocks view still reads its controllers from it
    ctl = factory(view="control", open="*")
    assert any(n["kind"] == "controller" for n in ctl["nodes"]) and any(n["kind"] == "sensor" for n in ctl["nodes"])


def test_every_loop_is_labelled_and_runs_through_parts_drawn_and_lines_it_is_a_link_of(factory):
    g = factory(view="dynamics", open="*")
    ids = {n["id"] for n in g["nodes"]}
    loops = {c["name"]: c for c in g["causalLoops"]}
    assert loops["backlog-clear"]["polarity"] == "B" and loops["backlog-clear"]["label"].startswith("B")
    assert loops["backlog-clear"]["nodes"] == ["stock:backlog", "gap:backlog-clear", "flow:submitted"]
    assert loops["backlog-clear+reviews-done"]["label"] == "R1"
    assert len({c["label"] for c in g["causalLoops"]}) == len(g["causalLoops"])
    for c in g["causalLoops"]:
        assert set(c["nodes"]) <= ids, c["name"]
        ns = c["nodes"]
        for a, b in zip(ns, ns[1:] + ns[:1], strict=False):             # each link of it is a line drawn here
            assert any(c["name"] in e["causal"] and {e["source"], e["target"]} == {a, b} for e in g["edges"]), (c["name"], a, b)


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
