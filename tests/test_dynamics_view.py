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
    # support reads bugs-live, which a goal it serves (no-live-bugs ≤ 0) is about: it files more as bugs-live rises,
    # drawn through the goal's excess (Sterman §5.2: the decision acts on the discrepancy)
    assert ("stock:bugs-live", "flow:filed-bugs") not in conn
    assert conn[("stock:bugs-live", "gap:no-live-bugs")] == "+" and conn[("gap:no-live-bugs", "flow:filed-bugs")] == "+"


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
    # every goal is drawn, and said on its stock too, with what serves it anywhere in the model
    assert "gap:no-live-bugs" in ids and not ids["gap:no-live-bugs"].get("noFeedback")
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
    # an open loop: drawn all the same, its desired level and its gap, the gap marked 'no feedback', and no link out
    assert ids["gap:no-live-bugs"]["noFeedback"] and "desired:no-live-bugs" in ids
    assert not [e for e in g["edges"] if e.get("from", e["source"]) == "gap:no-live-bugs"]
    assert [i for i, n in ids.items() if n.get("noFeedback")] == ["gap:no-live-bugs"]


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


def test_every_product_goal_is_a_desired_level_and_a_gap_driving_the_flow_its_actor_moves(factory):
    """software-factory's product goals are served by intake's blocks reading their stocks: each is drawn in product,
    its gap between the stock and the flow the block moves, and no loop is added or lost by the routing."""
    g = factory(view="dynamics", open="*")
    ids = {n["id"]: n for n in g["nodes"]}
    gaps = sorted(i for i in ids if i.startswith("gap:"))
    mine = {f"gap:{k}" for k in ["backlog-clear", "reviews-done", "all-live", *PRODUCT_GOALS]}   # (and the upkeep's two)
    assert set(gaps) - mine == {"gap:model-fits", "gap:requests-handled"}, gaps
    assert sorted(i for i in ids if i.startswith("desired:")) == [i.replace("gap:", "desired:") for i in gaps]
    conn = {(e["from"], e["to"]): e["polarity"] for e in g["edges"] if e["kind"] == "connector"}
    for goal, (stock, flow, into) in PRODUCT_GOALS.items():
        assert ids[f"gap:{goal}"]["systems"] == ["product"] and ids[f"desired:{goal}"]["systems"] == ["product"]
        assert (f"stock:{stock}", f"flow:{flow}") not in conn
        assert [b for a, b in conn if a == f"gap:{goal}"] == [f"flow:{flow}"]
        assert conn[(f"gap:{goal}", f"flow:{flow}")] == "+" and conn[(f"stock:{stock}", f"gap:{goal}")] == into
    assert not [x for n in g["nodes"] for x in n.get("goals") or [] if not x["acted"]]
    assert len(g["causalLoops"]) == len(factory(view="control", open="*")["causalLoops"])     # (the loops are the model's)
    read = ("stock.users", "block.product-manager")              # the loops through that read run through the gap
    users = [c for c in g["causalLoops"] if read in zip(c["parts"][-1:] + c["parts"], c["parts"], strict=False)]
    assert users and all("gap:users-growing" in c["nodes"] for c in users)


def test_a_goal_whose_actor_is_in_a_closed_system_links_through_its_port(factory):
    """product open, factory closed: each gap's link ends at the stub naming the flow inside factory; all closed, it
    leaves product's box at the gap's port and enters factory's at the flow's."""
    g = factory(view="dynamics", open="product")
    ids = {n["id"]: n for n in g["nodes"]}
    for goal, (_, flow, _) in PRODUCT_GOALS.items():
        assert f"desired:{goal}" in ids
        (e,) = [e for e in g["edges"] if e["source"] == f"gap:{goal}"]
        stub = ids[e["target"]]
        assert (stub["role"], stub["label"], stub["in"]) == ("stub", flow, "factory"), stub
    closed = factory(view="dynamics", open="-")
    ports = {(e.get("sourcePort"), e.get("targetPort")) for e in closed["edges"] if e["kind"] == "connector"}
    for goal, (_, flow, _) in PRODUCT_GOALS.items():
        assert (f"system:product:out:gap:{goal}", f"system:factory:in:flow:{flow}") in ports, ports


def test_a_block_that_only_reads_a_goals_stock_is_not_drawn_through_its_gap(tmp_path):
    """remote-pair/support: 'customers' reads stock.incidents-open (a cause, not a controller of incidents-calm, which
    is acted on in the other ergostat). It is drawn reading the stock, the gap closes nothing here ('no feedback'),
    and the stock's panel names no block serving the goal."""
    d = tmp_path / "support"
    shutil.copytree(ROOT / "examples" / "remote-pair" / "support", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    g = api(Live(Project(mdl.load(d))), "graph", {"view": ["dynamics"], "open": ["*"]})
    ids = {n["id"]: n for n in g["nodes"]}
    conn = {(e["source"], e["target"]) for e in g["edges"] if e["kind"] == "connector"}
    assert ids["gap:incidents-calm"].get("noFeedback") and not [b for a, b in conn if a == "gap:incidents-calm"]
    assert not ids["gap:tickets-short"].get("noFeedback")
    (calm,) = [x for n in g["nodes"] for x in n.get("goals") or [] if x["name"] == "incidents-calm"]
    assert calm["by"] == [] and not calm["acted"]


def test_a_block_naming_another_goal_still_serves_a_goal_whose_loop_it_closes(tmp_path):
    """alert-triage: 'investigation' names facets-investigated and also works off alerts-investigating, closing
    investigations-joined's loop (join-keeps-up): that goal's gap drives what it moves, with no 'no feedback' mark."""
    d = tmp_path / "alert-triage"
    shutil.copytree(ROOT / "examples" / "alert-triage", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    os.environ["ERGOSTAT_HOME"] = tempfile.mkdtemp()
    from ergostat.web.server import Live, api
    g = api(Live(Project(mdl.load(d))), "graph", {"view": ["dynamics"], "open": ["*"]})
    gap = next(n for n in g["nodes"] if n["id"] == "gap:investigations-joined")
    assert not gap.get("noFeedback")
    assert [e for e in g["edges"] if e["kind"] == "connector" and e["source"] == gap["id"]]
    assert ("stock:alerts-investigating", gap["id"]) in {(e["source"], e["target"]) for e in g["edges"]}


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


PRODUCT_LOOPS = {"bug-fixing": "no-live-bugs", "features-shipped": "few-missing", "users-won": "users-growing",
                 "regressions": None, "long-tail": None}


def test_the_named_loops_and_one_per_goal_are_drawn_and_every_other_loop_is_minor(factory):
    """SPEC §12a: a `loops:` entry names one loop; each goal's goal-seeking loop is the shortest balancing loop
    through its gap (a named one first); those are drawn, the rest are minor. software-factory's product names its
    main loops, and each product goal's loop is the named one, so no marker carries a goal's name there."""
    g = factory(view="dynamics", open="*")
    spec = mdl.load(ROOT / "examples" / "software-factory").spec
    loops = {c["name"]: c for c in g["causalLoops"]}
    assert set(spec.named_loops) == {"rework", *PRODUCT_LOOPS}
    assert {n for n, c in loops.items() if c["named"]} == set(spec.named_loops)      # each entry names exactly one loop
    for name, goal in PRODUCT_LOOPS.items():
        assert loops[name]["goal"] == goal and loops[name]["shown"] == name, loops[name]
        assert "product" in loops[name]["systems"]
    seekers = {c["goal"]: c for c in loops.values() if c["goal"]}
    assert len(seekers) == sum(1 for c in loops.values() if c["goal"]) <= len(spec.goals)   # one loop per goal at most
    for goal, c in seekers.items():                                       # balancing, through its gap, the shortest
        assert c["polarity"] == "B" and f"gap:{goal}" in c["nodes"], c
        rivals = [x for x in loops.values() if x["polarity"] == "B" and f"gap:{goal}" in x["nodes"]]
        assert len(c["parts"]) == min(len(x["parts"]) for x in rivals), (goal, c["name"])
        assert c["shown"] == (c["name"] if c["named"] else goal)
    major = [c for c in loops.values() if not c["minor"]]
    assert {c["name"] for c in major} == set(spec.named_loops) | {c["name"] for c in seekers.values()}
    assert len(major) <= len(spec.named_loops) + len(spec.goals) < len(loops), (len(major), len(loops))
    assert not [c["shown"] for c in major if " via " in c["shown"]]
    for pol in "RB":                                                       # the drawn take the first numbers: B1, B2 …
        ns = sorted(int(c["label"][1:]) for c in major if c["polarity"] == pol)
        assert ns == list(range(1, len(ns) + 1)), (pol, ns)
    assert all(not c["named"] and not c["goal"] for c in loops.values() if c["minor"])
    # the routed read: users-won runs through the stock → block read its goal's gap is drawn on
    assert ("stock.users", "block.product-manager") in zip(loops["users-won"]["parts"], loops["users-won"]["parts"][1:], strict=False)


def test_a_system_s_box_and_the_list_drawing_it_alone_count_its_loops_alike(factory):
    """Q22: a system's loop count is the loops with a part in it, named and minor: on its box (closed) and in the side
    list of the view drawing it alone, the same two numbers."""
    top = factory(view="dynamics", open="-")
    box = next(n for n in top["nodes"] if n["kind"] == "system" and n["label"] == "product")["loopCount"]
    alone = factory(view="dynamics", system="product")
    assert alone["loopCount"] == box and box["named"] and box["minor"], (alone["loopCount"], box)
    mine = [c for c in alone["causalLoops"] if "product" in c["systems"]]
    assert box == {"named": sum(not c["minor"] for c in mine), "minor": sum(c["minor"] for c in mine)}
    assert top["loopCount"]["named"] + top["loopCount"]["minor"] == len(top["causalLoops"])     # everything: every loop


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
    snap = {"loops": {"backlog-clear": {"status": "off", "stock": "backlog", "value": 4.0, "setpoint": "<= 0", "error": -4.0,
                                       "off_by_words": "off by 4"}}}
    att = [{"level": "bad", "what": "loop backlog-clear", "says": "backlog is 4, setpoint <= 0 (off by 4)"},
           {"level": "hint", "what": "loop backlog-clear", "says": "was off 60% of the time: saturated, moving its most "
            "each run. Its valve moved 2/h out while 3/h came in"},
           {"level": "hint", "what": "controller x", "says": "dev (ai) decided \"go\" 9 of 10 times: a rule could fill it"},
           {"level": "hint", "what": "loop a", "says": "keeps feeding x: Hold it back (its controller can read x)"}]
    out = attention(att, snap)
    assert out[0]["says"] == "backlog is 4, desired backlog = 0: off by 4"
    # a controlled goal is called a goal ('loop' is for R and B loops): never 'loop backlog-clear'
    assert [a["what"] for a in out] == ["goal backlog-clear", "goal backlog-clear", "goal x", "goal a"]
    assert out[1]["says"].startswith("was off 60% of the time: saturated, moving its most each run. Its flow moved")
    assert "(what serves it can read x)" in out[3]["says"], out[3]["says"]
    import re
    for a in out:
        text = re.sub(r"\bgoal (backlog-clear|x|a)\b", "", a["what"] + " " + a["says"])
        assert not re.search(r"controller|setpoint|\brule|\bgoal|\bloop |valve|<=|>=", text), text


def test_a_goal_s_suggestion_says_what_serves_it():
    from ergostat.dynamics import attention
    att = [{"level": "hint", "what": "controller fixes", "says": "loop fixes was off 70% of the time though its valve keeps "
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
