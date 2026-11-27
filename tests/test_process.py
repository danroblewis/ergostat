"""The Process view (process.py, SPEC §5b): the directly-follows graph of each projection, read from a synthetic
record: its counts, median times, rework loops, start and end; the lines between kinds where an event on one
item caused one on another (a fan-out and a join); the frequency filter and the caps; the items behind a node
or a line, as the Items page lists them; and the API."""

import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import process as pm
from ergostat.spec import item_sets
from ergostat.store import Project

MODEL = """
name: flags
systems:
  delivery: {description: the flags}
  research: {description: what is found out}
projections:
  flag:
    id: flag/*
    system: delivery
    states: [asked, researching, researched, shipped]
    on: {flag.researching: researching, flag.researched: researched, flag.shipped: shipped, flag.reworked: researching}
  facet:
    id: facet/*
    system: research
    states: [open, done]
    on: {facet.done: done}
stocks:
  flags-asked:
    unit: flags
    sensor: {projection: flag, state: asked}
"""

H = 3600.0


@pytest.fixture
def p(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    return Project(mdl.load(tmp_path))


def seed(p: Project, now: float) -> None:
    """Three flags in the last hours. Each is researched by two facets: the flag going to researching starts
    them (through a block's run, an event about no item), and the last facet done makes the flag researched.
    Flag 1 is researched in 1h, flag 2 in 2h, flag 3 in 3h; flag 3 goes back to researching once (rework) and
    is noted twice while researching; flags 1 and 2 ship."""
    t0 = now - 8 * H
    for i in (1, 2, 3):
        f = f"flag/{i}"
        t = t0 + i * 60
        p.events.add("flag.asked", item=f, at=t)
        go = p.events.add("flag.researching", item=f, at=t + 600)
        run = p.events.add("agent.started", item="researcher", source="ergostat", causedby=go["id"], at=t + 601)
        last = None
        for j in (1, 2):
            fid = f"facet/{i}{j}"
            p.events.add("facet.opened", item=fid, causedby=run["id"], at=t + 602 + j)
            last = p.events.add("facet.done", item=fid, at=t + 600 + i * H - (2 - j) * 60)
        p.events.add("flag.researched", item=f, causedby=last["id"], at=t + 600 + i * H + 1)
    p.events.add("flag.noted", item="flag/3", at=t0 + 180 + 1200)
    p.events.add("flag.noted", item="flag/3", at=t0 + 180 + 1300)
    p.events.add("flag.reworked", item="flag/3", at=t0 + 180 + 600 + 3 * H + 100)
    p.events.add("flag.researched", item="flag/3", at=t0 + 180 + 600 + 3 * H + 200)
    for i in (1, 2):
        p.events.add("flag.shipped", item=f"flag/{i}", at=t0 + i * 60 + 600 + 4 * H)


def edge(g, kind, a, b, k="follows"):
    pre = "f" if k == "follows" else "c"
    key = f"{pre}:{kind}:{a}>{b}" if k == "follows" else f"c:{a}>{b}"
    return next((e for e in g["edges"] if e["id"] == key), None)


def node(g, kind, a):
    return next((n for n in g["nodes"] if n["id"] == f"p:{kind}:{a}"), None)


def test_states_count_the_moves_with_their_median_times_start_end_and_rework(p):
    now = time.time()
    seed(p, now)
    g = pm.process(p.events, p.model.spec, ["flag", "facet"], now - 24 * H, now, "states")
    assert g["kind"] == "process" and g["by"] == "states"
    assert node(g, "flag", "^")["count"] == 3 and node(g, "flag", "asked")["count"] == 3
    assert node(g, "flag", "researching")["count"] == 4            # three, and flag 3 again
    assert node(g, "flag", "$")["count"] == 2                       # shipped is the last state: flags 1 and 2
    e = edge(g, "flag", "researching", "researched")
    assert e["count"] == 4 and e["items"] == 3
    assert e["median"] == pytest.approx(1.5 * H, abs=5)             # 1h, 2h, 3h, and the rework's 100s
    back = edge(g, "flag", "researched", "researching")
    assert back["count"] == 1 and back["rework"] and not edge(g, "flag", "asked", "researching")["rework"]
    # deliberate (fix-process-rework-flag): rework is a repeated step, so flag 3's second move into researched is a
    # return too, though the line runs forward; the other three passages along it are not
    assert e["rework"] and e["returns"] == 1 and back["returns"] == 1
    assert next(k for k in g["projections"] if k["name"] == "flag")["returns"] == 2
    assert edge(g, "flag", "asked", "researching")["median"] == pytest.approx(600, abs=1)
    assert edge(g, "flag", "^", "asked")["count"] == 3 and edge(g, "flag", "shipped", "$")["count"] == 2
    # the noted events move nothing: states leave them out
    assert not any(n["activity"] == "flag.noted" for n in g["nodes"])


def test_events_draw_each_type_and_a_self_loop(p):
    now = time.time()
    seed(p, now)
    g = pm.process(p.events, p.model.spec, ["flag"], now - 24 * H, now, "events")
    assert node(g, "flag", "flag.noted")["count"] == 2
    loop = edge(g, "flag", "flag.noted", "flag.noted")
    assert loop["count"] == 1 and loop["self"] and loop["rework"] and loop["median"] == pytest.approx(100, abs=1)
    assert edge(g, "flag", "flag.researching", "flag.noted")["count"] == 1
    assert edge(g, "flag", "flag.reworked", "flag.researched")["rework"]          # back to where it usually comes
    assert not edge(g, "flag", "flag.researched", "flag.reworked")["rework"]
    assert edge(g, "flag", "flag.asked", "flag.researching")["count"] == 3
    assert edge(g, "flag", "flag.shipped", "$")["count"] == 2


def test_a_fan_out_and_a_join_across_kinds_through_a_run(p):
    now = time.time()
    seed(p, now)
    g = pm.process(p.events, p.model.spec, ["flag", "facet"], now - 24 * H, now, "states")
    out = edge(g, "flag", "flag:researching", "facet:open", "caused")
    assert out["count"] == 6 and out["items"] == 6 and out["causes"] == 3
    assert out["types"] == [{"cause": "flag.researching", "effect": "facet.opened", "count": 6}]
    join = edge(g, "flag", "facet:done", "flag:researched", "caused")
    assert join["count"] == 3 and join["median"] == pytest.approx(1, abs=0.5)
    ev = pm.process(p.events, p.model.spec, ["flag", "facet"], now - 24 * H, now, "events")
    assert edge(ev, "", "flag:flag.researching", "facet:facet.opened", "caused")["count"] == 6


def test_the_window_bounds_what_is_read(p):
    now = time.time()
    seed(p, now)
    g = pm.process(p.events, p.model.spec, ["flag"], now - 4.5 * H, now, "states")
    assert node(g, "flag", "^") is None and node(g, "flag", "asked") is None     # nothing arrived in the window
    e = edge(g, "flag", "researched", "shipped")                                 # its ends, entered before it: timed
    assert e["count"] == 2 and node(g, "flag", "shipped")["count"] == 2 and e["median"] > 0


def test_the_frequency_filter_hides_rare_paths_and_the_caps_say_so(p, monkeypatch):
    now = time.time()
    seed(p, now)
    g = pm.process(p.events, p.model.spec, ["flag"], now - 24 * H, now, "events", paths=0.5)
    assert edge(g, "flag", "flag.noted", "flag.noted") is None and edge(g, "flag", "flag.asked", "flag.researching")
    assert node(g, "flag", "flag.noted") is None and g["hidden"]["edges"] > 0 and g["hidden"]["nodes"] > 0
    monkeypatch.setattr(pm, "MOST_EDGES", 3)
    g = pm.process(p.events, p.model.spec, ["flag"], now - 24 * H, now, "events")
    assert len(g["edges"]) == 3 and g["capped"]["edges"]


def test_a_leases_hold_is_folded_out_of_the_states(p):
    now = time.time()
    t = now - H
    p.events.add("flag.asked", item="flag/9", at=t)
    p.events.add("ergostat.lease.taken", item="flag/9", at=t + 10, data={"run": "r1", "block": "b", "fence": 1, "ttl": 600})
    p.events.add("flag.researching", item="flag/9", at=t + 100)
    moves = [{"time": 1, "from": None, "to": "asked", "event": "a", "type": "x"},
             {"time": 2, "from": "asked", "to": "leased", "event": "b", "type": "y"},
             {"time": 3, "from": "leased", "to": "asked", "event": "c", "type": "y"},          # handed back: no move
             {"time": 4, "from": "asked", "to": "leased", "event": "d", "type": "y"},
             {"time": 5, "from": "leased", "to": "researching", "event": "e", "type": "z"}]
    assert [(m["from"], m["to"]) for m in pm.unleased(moves)] == [(None, "asked"), ("asked", "researching")]
    g = pm.process(p.events, p.model.spec, ["flag"], now - 2 * H, now, "states")
    assert node(g, "flag", "leased") is None
    e = edge(g, "flag", "asked", "researching")
    assert e["count"] == 1 and e["median"] == pytest.approx(100, abs=1)


def test_the_default_reading_and_the_kinds_of_a_system(p):
    spec = p.model.spec
    assert pm.default_by(spec, ["flag", "facet"]) == "states"
    assert pm.kinds_of(spec, "research") == ["facet"] and pm.kinds_of(spec, None) == ["flag", "facet"]


def test_the_items_behind_a_node_and_a_line(p):
    now = time.time()
    seed(p, now)
    spec = p.model.spec
    got = pm.items_through(p.events, spec, "flag", now - 24 * H, now, "states", followed=("researched", "researching"))
    assert list(got) == ["flag/3"]
    got = pm.items_through(p.events, spec, "flag", now - 24 * H, now, "states", through="$")
    assert sorted(got) == ["flag/1", "flag/2"]
    got = pm.items_through(p.events, spec, "facet", now - 24 * H, now, "states", caused=[("flag", "researching", "open")])
    assert len(got) == 6
    s = item_sets.parse({"projection": ["flag"], "followed": ["researched>researching"], "by": ["states"],
                         "moved_since": [str(now - 24 * H)], "moved_until": [str(now)]})
    sel = item_sets.select(p.events, spec, s, until=now)
    assert [i["id"] for i in sel["items"]] == ["flag/3"] and sel["total"] == 1
    assert s.says() == "flag, researched → researching" and s.params()["followed"] == ["researched>researching"]


def test_the_api_draws_the_process_view_and_wiring_reaches_it(p):
    from ergostat.web.server import Live, api
    now = time.time()
    seed(p, now)
    live = Live(p)
    g = api(live, "graph", {"view": ["process"], "since": ["1d"]})
    assert g["kind"] == "process" and g["by"] == "states" and {k["name"] for k in g["projections"]} == {"flag", "facet"}
    assert any(e["kind"] == "caused" for e in g["edges"]) and "corr" in g
    assert api(live, "graph", {"view": ["wiring"], "since": ["1d"]})["kind"] == "process"
    one = api(live, "graph", {"view": ["process"], "since": ["1d"], "projections": ["flag"], "by": ["events"], "paths": ["50"]})
    assert {n["projection"] for n in one["nodes"]} == {"flag"} and one["by"] == "events" and one["paths"] == 0.5
    sys_ = api(live, "graph", {"view": ["process"], "since": ["1d"], "system": ["research"]})
    assert {k["name"] for k in sys_["projections"]} == {"facet"}
    listed = api(live, "items", {"projection": ["flag"], "followed": ["researched>researching"], "by": ["states"],
                                 "moved_since": [str(now - 24 * H)], "moved_until": [str(now)], "alone": ["1"]})
    assert [i["id"] for i in listed["items"]] == ["flag/3"]


def test_a_scheduled_runs_events_fan_out_from_its_schedule(tmp_path):
    """A sweep on every: opens facets: each run is the cause its events cite (no event of its own needed), and the
    map draws the block's schedule as the source of a fan-out, its items found by the line (caused=)."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL) + textwrap.dedent("""
        blocks:
          sweep:
            type: program
            every: 15m
            run: "true"
    """))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    for r in range(2):                                   # two firings, each opening three facets
        t = now - H + r * 900
        run = p.events.add("agent.started", item="sweep", source="ergostat", at=t, data={"trigger": "schedule"})
        for j in range(3):
            p.events.add("facet.opened", item=f"facet/{r}{j}", causedby=run["id"], at=t + 1 + j)
    other = p.events.add("agent.started", item="sweep", source="ergostat", at=now - 60, data={"trigger": "command"})
    p.events.add("facet.opened", item="facet/x", causedby=other["id"], at=now - 59)
    spec = p.model.spec
    g = pm.process(p.events, spec, ["facet"], now - 2 * H, now, "states")
    src = node(g, pm.SCHEDULE, "sweep")
    assert src["kind"] == "schedule" and src["label"] == "sweep · every 15m" and src["count"] == 2
    out = edge(g, "", f"{pm.SCHEDULE}:sweep", "facet:open", "caused")
    assert out["count"] == 6 and out["causes"] == 2 and out["items"] == 6, "a fan-out: two runs into six facets"
    assert out["types"] == [{"cause": "agent.started", "effect": "facet.opened", "count": 6}]
    assert g["projections"][0] == {"name": pm.SCHEDULE, "schedule": True, "states": [], "drawn": True, "by": "runs", "items": 2}
    assert not any(n["activity"] == "sweep" and n["projection"] == "facet" for n in g["nodes"])
    s = item_sets.parse({"projection": ["facet"], "caused": [f"{pm.SCHEDULE}:sweep>open"], "by": ["states"],
                         "moved_since": [str(now - 2 * H)], "moved_until": [str(now)]})
    sel = item_sets.select(p.events, spec, s, until=now)
    assert sel["total"] == 6 and "facet/x" not in {i["id"] for i in sel["items"]}


def test_a_real_scheduled_runs_events_cite_it(tmp_path):
    """Run by the engine on every:, the run's own agent.started is the cause its printed events cite; the map draws it."""
    from ergostat.spec.engine import Engine
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: t
        projections:
          x:
            id: x/*
            states: [o, c]
        blocks:
          sweep:
            type: program
            every: 1h
            run: python3 say.py
            out: flow.f
        stocks:
          s:
            sensor: {projection: x, state: o, every: 1m}
        flows:
          f:
            to: s
            sensor: {projection: x, entering: o, over: 1h}
    """))
    (tmp_path / "say.py").write_text('import json\nprint(json.dumps({"event": "x.opened", "item": "x/1"}), flush=True)\n')
    p = Project(mdl.load(tmp_path))
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        end = time.time() + 10
        while time.time() < end and not p.events.query(n=None, item="x/1"):
            time.sleep(0.05)
        run = p.events.query(n=1, item="sweep", type="agent.started")[-1]
        assert run["data"]["trigger"] == "schedule" and run["causedby"] is None
        assert p.events.query(n=None, item="x/1")[0]["causedby"] == run["id"]
        g = pm.process(p.events, p.model.spec, ["x"], time.time() - 60, time.time() + 1, "states")
        assert any(x["id"] == f"c:{pm.SCHEDULE}:sweep>x:o" for x in g["edges"])
    finally:
        e.close()


def test_relations_between_the_items_drawn_are_lines_between_their_activities(tmp_path):
    """Each link between two items drawn is a line from the activity the naming item was last at to the one the
    named item was last at, aggregated, named by its relation; a link to an item not drawn is no line."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace(
        "    on: {facet.done: done}", "    on: {facet.done: done}\n    relations: {parent: flag}"))
    p = Project(mdl.load(tmp_path))
    now = time.time()
    seed(p, now)
    for i in (1, 2, 3):
        for j in (1, 2):
            p.events.add("facet.linked", item=f"facet/{i}{j}", data={"parent": f"flag/{i}"}, at=now - 60)
    p.events.add("facet.linked", item="facet/11", data={"parent": "flag/99"}, at=now - 30)      # never recorded
    g = pm.process(p.events, p.model.spec, ["flag", "facet"], now - 24 * H, now, "states")
    rel = [e for e in g["edges"] if e["kind"] == "related"]
    shipped = next(e for e in rel if e["to"] == "shipped")
    researched = next(e for e in rel if e["to"] == "researched")
    assert shipped["source"] == "p:facet:done" and shipped["target"] == "p:flag:shipped" and shipped["relation"] == "parent"
    assert (shipped["count"], shipped["items"], shipped["targets"]) == (4, 4, 2)             # flags 1 and 2 shipped
    assert (researched["count"], researched["targets"]) == (2, 1) and len(rel) == 2


# ---- rework is a repeated step on one item (fix-process-rework-flag)

JOBS = """
name: jobs
systems:
  work: {description: the jobs}
projections:
  job:
    id: job/*
    system: work
    states: [new, a, b, c, d]
    on: {job.a: a, job.b: b, job.c: c, job.d: d}
"""


def jobs_project(where) -> Project:
    where.mkdir(exist_ok=True)
    (where / "ergostat.yaml").write_text(textwrap.dedent(JOBS))
    return Project(mdl.load(where))


def run(p: Project, item: str, steps: list[str], t: float, gap: float = 60.0) -> None:
    for i, s in enumerate(steps):
        p.events.add(f"job.{s}", item=item, at=t + i * gap)


def returns(g) -> dict[str, int]:
    """Each line with a return: how many (and they add up to the kind's total)."""
    got = {e["id"]: e["returns"] for e in g["edges"] if e["kind"] == "follows" and e["rework"]}
    assert all(n > 0 for n in got.values())
    assert not any(e["rework"] for e in g["edges"] if e["kind"] != "follows")
    assert sum(got.values()) == next(k for k in g["projections"] if k["name"] == "job")["returns"]
    return got


@pytest.mark.parametrize("by", ["states", "events"])
def test_two_items_in_opposite_orders_show_no_rework(tmp_path, by):
    """Done 1: one item doing a, b and another b, a repeat nothing: no line is rework."""
    p, now = jobs_project(tmp_path), time.time()
    run(p, "job/1", ["a", "b"], now - 3 * H)
    run(p, "job/2", ["b", "a"], now - 3 * H + 10)
    g = pm.process(p.events, p.model.spec, ["job"], now - 24 * H, now, by)
    x = "job." if by == "events" else ""
    assert edge(g, "job", f"{x}a", f"{x}b")["count"] == 1 and edge(g, "job", f"{x}b", f"{x}a")["count"] == 1
    assert returns(g) == {}


@pytest.mark.parametrize("by", ["states", "events"])
def test_one_item_coming_back_to_a_step_is_one_return(tmp_path, by):
    """Done 2: one item doing a, b, a: the line b → a is rework, with one return; a → b is not."""
    p, now = jobs_project(tmp_path), time.time()
    run(p, "job/1", ["a", "b", "a"], now - 3 * H)
    g = pm.process(p.events, p.model.spec, ["job"], now - 24 * H, now, by)
    x = "job." if by == "events" else ""
    assert returns(g) == {f"f:job:{x}b>{x}a": 1}


def test_a_state_entered_before_the_window_counts_as_done(tmp_path):
    """By States, the item's moves before the window count: a, b before it, then a in it, is a return."""
    p, now = jobs_project(tmp_path), time.time()
    run(p, "job/1", ["a", "b"], now - 30 * H)
    run(p, "job/1", ["a"], now - H)
    g = pm.process(p.events, p.model.spec, ["job"], now - 24 * H, now, "states")
    assert returns(g) == {"f:job:b>a": 1}


def concurrent_log(p: Project, now: float, items: int, redo: dict[int, int]) -> dict[str, int]:
    """``items`` jobs, each taking the four steps once in an order of its own, all interleaved in the same hours
    (concurrency); job i in ``redo`` then goes back to the step at that index of its order. The returns this
    plants, by line."""
    import random
    rnd = random.Random(7)
    want: dict[str, int] = {}
    for i in range(items):
        order = rnd.sample(["a", "b", "c", "d"], 4)
        start, gap = now - 6 * H + rnd.uniform(0, 600), rnd.uniform(30, 900)
        if i in redo:
            again = order[redo[i]]
            want[f"{order[-1]}>{again}"] = want.get(f"{order[-1]}>{again}", 0) + 1
            order.append(again)
        run(p, f"job/{i}", order, start, gap=gap)
    return want


@pytest.mark.parametrize("by", ["states", "events"])
def test_a_concurrent_log_with_no_repeated_step_shows_no_rework_and_its_planted_returns_exactly(tmp_path, by):
    """Done 3: many items, each in its own order and all at once, repeat nothing: zero rework, though lines
    between two steps are taken both ways; the same log with some items sent back shows exactly those returns."""
    now = time.time()
    x = "job." if by == "events" else ""
    p = jobs_project(tmp_path / "once")
    assert concurrent_log(p, now, 120, {}) == {}
    g = pm.process(p.events, p.model.spec, ["job"], now - 24 * H, now, by)
    assert edge(g, "job", f"{x}d", f"{x}a")["count"] > 0 and edge(g, "job", f"{x}a", f"{x}d")["count"] > 0
    assert returns(g) == {}
    p2 = jobs_project(tmp_path / "again")
    want = concurrent_log(p2, now, 120, {i: i % 3 for i in range(0, 120, 7)})
    assert sum(want.values()) == 18
    g2 = pm.process(p2.events, p2.model.spec, ["job"], now - 24 * H, now, by)
    assert returns(g2) == {f"f:job:{x}{k.replace('>', '>' + x)}": n for k, n in want.items()}
