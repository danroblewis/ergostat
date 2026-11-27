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












def test_an_open_loop_goal_is_drawn_with_the_no_feedback_mark_and_no_link(repo):
    """An open loop (open_loop = true: it acts by the clock, whatever it would measure) closes no feedback: its gap is
    drawn, marked, and drives nothing; the same model closed draws the gap's link to the flow it drives."""
    from ergostat import graph, state
    from ergostat.dynamics import dynamics
    from ergostat.model import load

    def drawn():
        m = load(repo.path)
        g = dynamics(graph.control(m, state.snapshot(Project(m)), graph.select(m)), m)
        return {n["id"]: n for n in g["nodes"]}, [e for e in g["edges"] if e["source"] == "gap:disk-under-80"]
    ids, out = drawn()
    assert "desired:disk-under-80" in ids and not ids["gap:disk-under-80"].get("noFeedback") and out
    text = repo.path.joinpath("ergostat.toml").read_text().replace('reads = ["disk-usage"]\n', 'open_loop = true\n')
    repo.write("ergostat.toml", text)
    ids, out = drawn()
    assert "desired:disk-under-80" in ids and ids["gap:disk-under-80"]["noFeedback"] and not out


PRODUCT_GOALS = {"no-live-bugs": ("bugs-live", "filed-bugs", "+"), "few-missing": ("missing-ops", "filed-features", "+"),
                 "users-growing": ("users", "filed-features", "-")}










EXAMPLES = sorted(str(p.parent.relative_to(ROOT / "examples")) for p in (ROOT / "examples").glob("**/ergostat.yaml")
                  if ".ergostat" not in p.parts and "run" not in p.parts)


@pytest.mark.slow
def test_every_goal_of_every_demo_has_its_gap_drawn(tmp_path):
    """Every goal /api/loops lists has a gap node in Dynamics with every system open, in every example."""
    from ergostat.web.server import Live, api
    missing = {}
    for ex in EXAMPLES:
        d = tmp_path / ex.replace("/", "--") / ex.rsplit("/", 1)[-1]
        shutil.copytree(ROOT / "examples" / ex, d, ignore=shutil.ignore_patterns("run", "__pycache__", ".ergostat"))
        os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
        live = Live(Project(mdl.load(d)))
        ids = {n["id"] for n in api(live, "graph", {"view": ["dynamics"], "open": ["*"]})["nodes"]}
        goals = api(live, "loops", {})
        if lost := sorted(k for k in goals if f"gap:{k}" not in ids):
            missing[ex] = lost
    assert {"remote-pair/incidents", "remote-pair/support"} <= set(EXAMPLES) and len(EXAMPLES) > 10, EXAMPLES
    assert not missing, missing




PRODUCT_LOOPS = {"bug-fixing": "no-live-bugs", "features-shipped": "few-missing", "users-won": "users-growing",
                 "regressions": None, "long-tail": None}






SMALL = """\
name: small
parameters:
  r: 2
  k: 1
stocks:
  people:
    unit: people
    sensor:
      manual: true
flows:
  births:
    to: people
    driven-by: +stock.people
    equation: r * stock.people
  deaths:
    from: people
    driven-by: +stock.people
    equation: k * stock.people
  leaving:
    from: people
goals:
  few:
    stock: people
    hold: "<= 100"
blocks:
  thin:
    type: program
    run: "true"
    in: [goal.few.error]
    out: flow.leaving
"""


def test_each_loop_through_a_gap_names_its_goal_and_the_goal_names_its_loops(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(SMALL)
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    live = Live(Project(mdl.load(tmp_path)))
    g = api(live, "graph", {"view": ["dynamics"], "open": ["*"]})
    loops = {c["name"]: c for c in g["causalLoops"]}
    closing = {n for n, c in loops.items() if c["goal"]}
    # a loop through a gap carries its goal; one through none (births R, deaths B) carries none
    assert closing and all(loops[n]["goal"] == "few" and "goal.few" in loops[n]["parts"] for n in closing)
    assert all(c["goal"] is None and not any(p.startswith("goal.") for p in c["parts"])
               for n, c in loops.items() if n not in closing)
    assert {loops[n]["polarity"] for n in loops if n not in closing} == {"R", "B"}
    assert [loops[n]["polarity"] for n in closing] == ["B"]                # thin drains people when it is over 100
    lp = api(live, "loops/few", {})
    assert [x["name"] for x in lp["feedback_loops"]] == sorted(closing)    # the same loops, from the goal's side
    assert lp["feedback_loops"][0]["label"] == loops[next(iter(closing))]["label"]
    assert lp["control_loop"]["controllers"] == ["thin"] and lp["control_loop"]["name"] == "few"


TWO = """\
name: two
stocks:
  a:
    unit: people
    sensor:
      manual: true
  b:
    unit: people
    sensor:
      manual: true
flows:
  move:
    from: a
    to: b
  back:
    from: b
    to: a
goals:
  calm:
    stock: b
    hold: "<= 50"
  few:
    stock: a
    hold: "<= 100"
blocks:
  thin:
    type: program
    run: "true"
    in: [goal.few.error]
    out: flow.move
  slow:
    type: program
    run: "true"
    in: [goal.calm.error]
    out: flow.back
"""


def test_a_loop_through_two_gaps_closes_both_goals(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(TWO)
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    live = Live(Project(mdl.load(tmp_path)))
    loops = {c["name"]: c for c in api(live, "graph", {"view": ["dynamics"], "open": ["*"]})["causalLoops"]}
    both = [n for n, c in loops.items() if {"goal.few", "goal.calm"} <= set(c["parts"])]
    assert both, loops                                   # a -> few -> thin -> move -> b -> calm -> slow -> back -> a
    assert all(loops[n]["goal"] == "calm" for n in both)  # its one goal, the first by name
    for g in ("few", "calm"):                            # yet it closes each, so each goal's panel lists it
        fl = [x["name"] for x in api(live, f"loops/{g}", {})["feedback_loops"]]
        assert set(both) <= set(fl), (g, fl)
        assert set(fl) == {n for n, c in loops.items() if f"goal.{g}" in c["parts"]}












def test_the_attention_cards_speak_system_dynamics():
    from ergostat.dynamics import attention
    snap = {"loops": {"backlog-clear": {"status": "off", "stock": "backlog", "value": 4.0, "setpoint": "<= 0", "error": -4.0,
                                       "off_by_words": "off by 4"}}}
    g = "backlog-clear"
    att = [{"level": "bad", "what": f"goal {g}", "goal": g, "says": "backlog is 4, setpoint <= 0 (off by 4)"},
           {"level": "hint", "what": f"goal {g}", "goal": g, "says": "was off 60% of the time: saturated, moving its most "
            "each run. Its valve moved 2/h out while 3/h came in"},
           {"level": "hint", "what": "controller x", "controller": "x",
            "says": "dev (ai) decided \"go\" 9 of 10 times: a rule could fill it"},
           {"level": "hint", "what": "goal a", "goal": "a", "says": "keeps feeding x: Hold it back (its controller can read x)"}]
    out = attention(att, snap)
    assert out[0]["says"] == "backlog is 4, desired backlog = 0: off by 4"
    # a controlled goal is called a goal ('loop' is for R and B loops), by its field: never 'loop backlog-clear'
    assert [a["what"] for a in out] == ["goal backlog-clear", "goal backlog-clear", "goal x", "goal a"]
    assert [a["goal"] for a in out] == [g, g, "x", "a"]                         # the field kept, for its Evidence link
    assert out[1]["says"].startswith("was off 60% of the time: saturated, moving its most each run. Its flow moved")
    assert "(what serves it can read x)" in out[3]["says"], out[3]["says"]
    import re
    for a in out:
        text = re.sub(r"\bgoal (backlog-clear|x|a)\b", "", a["what"] + " " + a["says"])
        assert not re.search(r"controller|setpoint|\brule|\bgoal|\bloop |valve|<=|>=", text), text


def test_a_goal_s_suggestion_says_what_serves_it():
    from ergostat.dynamics import attention
    att = [{"level": "hint", "what": "goal fixes", "goal": "fixes", "says": "goal fixes was off 70% of the time though its valve keeps "
            "up on average: it answers too late; its controller (fixer, every 1m) is the slowest stage"}]
    out = attention(att, {"loops": {}})
    assert out[0]["says"] == ("goal fixes was off 70% of the time though its flow keeps up on average: it answers too late; "
                              "what serves it (fixer, every 1m) is the slowest stage"), out[0]["says"]
    assert attention([{"level": "warn", "what": "stock q", "says": "a feedback loop q-x"}], {"loops": {"q": {}}})[0]["says"] \
        == "a feedback loop q-x"                                                # (a name only where it is a goal's, whole)


def test_the_dynamics_wording_keeps_codes_ids_and_tiers_as_they_are():
    from ergostat.dynamics import words
    said = words("modelling holds queue-goal-tolerance on goal.ci-upgrade-planned, waiting 3h (why: a goal's setpoint "
                 "and tolerance are what decides: the owner's to change). ergostat inbox request/80fe1e93e1 --deny")
    assert said == ("modelling holds queue-goal-tolerance on goal.ci-upgrade-planned, waiting 3h (why: a desired level "
                    "and tolerance are what decides: the owner's to change). ergostat inbox request/80fe1e93e1 --deny")
    assert words("the rule tier has no certain change for it: a rule reads goal.x") == \
        "the rule tier has no certain change for it: a fixed decision reads goal.x"




