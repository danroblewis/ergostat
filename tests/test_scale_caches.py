"""The caches and indexes that let ergostat run larger models (docs/proposals/scale.md, #2 #3 #5 #6 #11) give the
answers the scans they replace gave, on every example and on a generated scale model, and do not go stale: a part
added or removed, a model edited and loaded again, a model swapped while the engine runs, item events folded."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ergostat.spec import load
from ergostat.spec.ir import Block, Flow, Goal, Loop, Ref, Setpoint, Spec

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted(p.name for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists())


@pytest.fixture(scope="module")
def scale_model(tmp_path_factory) -> Path:
    """scripts/scale_model.py's model of 10 workflows: hand-offs, shared pools, loops across systems."""
    d = tmp_path_factory.mktemp("scale") / "n10"
    subprocess.run([sys.executable, str(ROOT / "scripts/scale_model.py"), "10", str(d)], check=True, capture_output=True)
    return d


# ---- the scans the lookups replace, as they were written (spec/ir.py before scale.md #6)


def scan_flows_of(spec: Spec, stock):
    return [f for f in spec.flows.values() if stock in (f.source, f.target)]


def scan_actuator_of(spec: Spec, flow):
    return next((b for b in spec.blocks.values() if Ref("flow", flow) in b.targets()), None)


def scan_setter_of(spec: Spec, aux):
    return next((b for b in spec.blocks.values() if Ref("auxiliary", aux) in b.targets()), None)


def scan_commanders_of(spec: Spec, block):
    reads = {r.name for r in spec.blocks[block].inputs.values() if r.kind == "block"}
    return [b for b in spec.blocks.values() if b.name != block and
            (b.name in reads or any(t.kind == "block" and t.name == block for t in b.targets()))]


def scan_downstream(spec: Spec, block):
    out = {t.name for t in spec.blocks[block].targets() if t.kind == "block"}
    out |= {b.name for b in spec.blocks.values() if any(r.kind == "block" and r.name == block for r in b.inputs.values())}
    return [spec.blocks[n] for n in sorted(out) if n in spec.blocks]


def scan_readers(spec: Spec, kind, name):
    goals = {g for g, x in spec.goals.items() if x.of == Ref(kind, name)} if kind in ("stock", "flow", "auxiliary") else set()
    return [b for b in spec.blocks.values() if any((r.kind == kind and r.name == name) or
                                                     (r.kind == "goal" and (r.name in goals or (kind == "goal" and r.name == name)))
                                                     for r in b.reads())]


def scan_loop(spec: Spec, goal: str) -> Loop:
    """Spec.loop as written before, every question a scan."""
    g = spec.goals[goal]
    what = g.of
    t = spec.measured(what.kind).get(what.name)
    sensors = [str(s.ref) for s in (t.sensors.values() if t else [])]
    stock_flows = [f.name for f in scan_flows_of(spec, what.name)] if what.kind == "stock" else [what.name]
    hit = lambda r: (r.kind == "flow" and what.kind != "auxiliary" and r.name in stock_flows) or \
        (r.kind == "auxiliary" and what.kind == "auxiliary" and r.name == what.name)        # noqa: E731
    ctl = [b for b in spec.blocks.values()
           if any((r.kind == "goal" and r.name == goal) or (r.kind == what.kind and r.name == what.name) for r in b.reads())]
    reach, seen, todo = [], set(), list(ctl)
    while todo:
        b = todo.pop(0)
        if b.name in seen:
            continue
        seen.add(b.name)
        reach.append(b)
        todo += scan_downstream(spec, b.name)
    actuators = [b.name for b in reach if any(hit(t) for t in b.targets())]
    valves = sorted({t.name for b in reach for t in b.targets() if hit(t)})
    controllers = [b.name for b in ctl if b.name not in actuators or any(t.kind == "block" for t in b.targets())]
    if not controllers and actuators:
        controllers = [a for a in actuators if a in {b.name for b in ctl}]
    dist = [f for f in stock_flows if f not in valves] if what.kind != "auxiliary" else []
    toward = set()
    if what.kind == "stock":
        down = g.hold.op in ("<=", "<")
        either = g.hold.op == "=="
        toward = {f"flow.{f.name}" for f in scan_flows_of(spec, what.name) if (f.source == what.name) == down or f.two_way or either}
    targets = {f"auxiliary.{what.name}"} if what.kind == "auxiliary" else {f"flow.{f}" for f in stock_flows}
    through = [] if actuators else scan_long_way(spec, ctl, targets, what, toward)
    if through:
        dist = [f for f in dist if f"flow.{f}" != through[-1]]
    return Loop(goal, sensors, controllers, actuators, valves, dist, through)


def scan_long_way(spec: Spec, ctl, targets, what, toward):
    drives: dict[str, list[str]] = {}
    for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for f in table.values():
            for r in f.driven_by:
                drives.setdefault(f"{r.kind}.{r.name}", []).append(f"{kind}.{f.name}")
    start = [f"block.{b.name}" for b in ctl]
    prev = {s: None for s in start}
    todo, fallback = list(start), []
    while todo:
        n = todo.pop(0)
        kind, name = n.split(".", 1)
        nxt: list[str] = []
        if n in targets:
            path, at = [], n
            while at is not None:
                path.append(at)
                at = prev[at]
            if not toward or n in toward:
                return path[::-1]
            fallback = fallback or path[::-1]
            continue
        if kind == "block":
            b = spec.blocks[name]
            nxt += [f"block.{d.name}" for d in scan_downstream(spec, name)]
            nxt += [str(Ref(t.kind, t.name)) for t in b.targets() if t.kind in ("flow", "goal", "auxiliary")]
        elif kind == "goal":
            nxt += [f"block.{b.name}" for b in scan_readers(spec, "goal", name)]
        elif kind == "flow":
            f = spec.flows[name]
            nxt += [f"stock.{s}" for s in (f.target, f.source) if s and s != what.name]
            nxt += drives.get(n, [])
        elif kind in ("stock", "auxiliary"):
            nxt += [f"block.{b.name}" for b in scan_readers(spec, kind, name)]
            nxt += drives.get(n, [])
        for x in nxt:
            if x not in prev:
                prev[x] = n
                todo.append(x)
    return fallback


def same(a, b) -> bool:
    return [id(x) for x in a] == [id(x) for x in b]


def check_lookups(spec: Spec) -> None:
    for s in [*spec.stocks, None, "nothing-here"]:
        assert same(spec.flows_of(s), scan_flows_of(spec, s)), s
    for f in [*spec.flows, "nothing-here"]:
        assert spec.actuator_of(f) is scan_actuator_of(spec, f), f
    for a in [*spec.auxiliaries, "nothing-here"]:
        assert spec.setter_of(a) is scan_setter_of(spec, a), a
    for b in spec.blocks:
        assert same(spec.commanders_of(b), scan_commanders_of(spec, b)), b
        assert same(spec.downstream(b), scan_downstream(spec, b)), b
    for kind, table in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries), ("goal", spec.goals),
                        ("block", spec.blocks)):
        for n in [*table, "nothing-here"]:
            assert same(spec.readers(kind, n), scan_readers(spec, kind, n)), (kind, n)
    for a in {b.agent for b in spec.blocks.values()} | {"nobody"}:
        assert same(spec.agent_blocks(a), [b for b in spec.blocks.values() if b.agent == a]), a
    got = {g: spec.loop(g) for g in spec.goals}
    for g, lp in got.items():
        assert lp == scan_loop(spec, g), g


@pytest.mark.parametrize("example", EXAMPLES)
def test_the_lookups_answer_as_the_scans_did_on_every_example(example):
    check_lookups(load(ROOT / "examples" / example / "ergostat.yaml"))


def test_the_lookups_answer_as_the_scans_did_on_a_scale_model(scale_model):
    check_lookups(load(scale_model / "ergostat.yaml"))


def test_a_loop_asked_for_is_the_callers_own_to_change():
    spec = load(ROOT / "examples" / "the-job" / "ergostat.yaml")
    g = next(iter(spec.goals))
    first = spec.loop(g)
    first.controllers.append("scribbled")
    first.disturbances.clear()
    assert spec.loop(g) == scan_loop(spec, g)
    assert spec.flows_of(spec.goals[g].of.name) is not spec.flows_of(spec.goals[g].of.name)


def tiny() -> Spec:
    s = Spec("t", ROOT, [])
    s.stocks["q"] = __import__("ergostat.spec.ir", fromlist=["Stock"]).Stock("q")
    s.flows["in"] = Flow("in", target="q")
    s.flows["out"] = Flow("out", source="q")
    s.goals["short"] = Goal("short", Ref("stock", "q"), Setpoint.parse("<= 5"))
    s.blocks["ctl"] = Block("ctl", "onoff", {"in": Ref("goal", "short")}, {"out": [Ref("block", "work")]})
    s.blocks["work"] = Block("work", "program", {}, {"out": [Ref("flow", "out")]})
    return s


def test_a_part_added_or_removed_is_seen_without_being_told():
    s = tiny()
    assert [b.name for b in s.commanders_of("work")] == ["ctl"] and s.loop("short").actuators == ["work"]
    s.blocks["also"] = Block("also", "onoff", {"in": Ref("stock", "q")}, {"out": [Ref("block", "work")]})
    assert [b.name for b in s.commanders_of("work")] == ["ctl", "also"]
    assert s.loop("short").controllers == ["ctl", "also"]
    del s.blocks["ctl"]
    assert [b.name for b in s.commanders_of("work")] == ["also"]
    s.flows["leak"] = Flow("leak", source="q")
    assert [f.name for f in s.flows_of("q")] == ["in", "out", "leak"]
    check_lookups(s)


def test_a_wire_changed_in_place_is_seen_once_the_model_is_reindexed():
    s = tiny()
    assert s.actuator_of("out").name == "work"
    s.blocks["work"].outputs["out"] = [Ref("flow", "in")]
    s.reindex()
    assert s.actuator_of("out") is None and s.actuator_of("in").name == "work"
    check_lookups(s)


# ---- #3: every series' newest reading, kept in memory


def all_latest(m) -> dict:
    with m._c() as c:
        names = [r[0] for r in c.execute("select distinct series from samples")]
        names += [r[0] for r in c.execute("select distinct series from tiers")]
    return {n: m.latest(n) for n in dict.fromkeys(names) if m.latest(n) is not None}


def test_the_newest_readings_are_the_latest_through_writes_ties_deletes_and_another_process(tmp_path):
    from ergostat.store import Measurements
    m = Measurements(tmp_path, raw=120.0, tiers=[(60.0, 86400.0)])
    other = Measurements(tmp_path, raw=120.0, tiers=[(60.0, 86400.0)])      # another process on the same record
    t0 = 1_000_000.0
    assert m.newest() == {} == all_latest(m)
    for i in range(20):
        m.add("a", i, t0 + 10 * i)
        m.add("b", -i, t0 + 10 * i)
    assert m.newest() == all_latest(m)
    m.add("a", 99.0, t0 + 50)                                                # back-dated: not the newest
    m.add("b", 7.0, t0 + 190)                                                # a tie with b's newest: the later row
    other.add("c", 3.0, t0 + 5)
    other.add_many([("a", t0 + 400, 1.5), ("d", t0 + 1, 2.0)])
    assert m.newest() == all_latest(m)
    assert m.newest()["b"] == (t0 + 190, 7.0) and m.newest()["a"] == (t0 + 400, 1.5)
    other.forget("a", above=1.0)                                             # set aside elsewhere: read afresh
    assert m.newest() == all_latest(m) and m.newest()["a"][1] <= 1.0
    m.roll(now=t0 + 10_000)                                                  # raw rows go, the newest among them
    assert m.newest() == all_latest(m)
    m.add("e", 1.0, t0 + 20_000)                                             # (a row number given again)
    other.add("a", 5.0, t0 + 20_001)
    assert m.newest() == all_latest(m)
    other.prune(t0 + 20_001)
    assert m.newest() == all_latest(m)


def test_the_engine_measures_the_same_with_the_newest_kept_or_read_one_by_one(tmp_path, scale_model):
    import shutil

    from ergostat import model as mdl
    from ergostat.spec.engine import Engine
    from ergostat.store import Project
    d = tmp_path / "m"
    shutil.copytree(scale_model, d)
    p = Project(mdl.load(d))
    sensors = p.model.spec.sensors()
    for i, s in enumerate(sensors):
        if i % 3:
            p.measurements.add(s.series, float(i), 1_000_000.0 + i)
    kept = Engine(p, say=lambda s: None)
    kept.measure()

    class OneByOne:
        def __init__(self, m):
            self.latest = m.latest
    plain = Engine(p, say=lambda s: None)
    plain.p = type("P", (), {"measurements": OneByOne(p.measurements), "events": p.events})()
    plain.measure()
    assert kept.signals == plain.signals and kept.seen == plain.seen and kept.last_reading == plain.last_reading


# ---- #5: the items the dispatcher looks at, followed as events fold

DISPATCHED = """
name: t
items:
  ticket:
    id: ticket/*
    states: [ready, doing, review, done]
    on: {ticket.started: doing, ticket.reviewing: review, ticket.done: done}
  note:
    id: note/*
    states: [new, read]
    on: {note.read: read}
blocks:
  worker:
    type: program
    takes: {kind: ticket, at: AT}
    pool: 2
    run: "true"
  checker:
    type: program
    takes: {kind: ticket, at: review}
    run: "true"
"""


def looked_at(e, kind) -> list:
    every, _ = e.dispatch.items_of(kind)
    return [(i.id, i.state, i.fields, i.entered, i.first, i.last) for i in every]


def scanned(e, kind) -> list:
    from ergostat.leases.fold import held
    from ergostat.spec import items as its
    want = {s for b in e.dispatch.blocks if b.takes.kind == kind for s in b.takes.at}
    return [(i.id, i.state, i.fields, i.entered, i.first, i.last)
            for i in its.project(e.p.events, e.spec, kind, transcript=False) if i.state in want or held(i.fields)]


def test_the_dispatcher_looks_at_the_items_a_full_read_would_give_through_events_and_a_model_swap(tmp_path):
    from ergostat import model as mdl
    from ergostat.leases import ENDED, TAKEN
    from ergostat.spec.engine import Engine
    from ergostat.store import Project
    (tmp_path / "ergostat.yaml").write_text(DISPATCHED.replace("AT", "ready"))
    p = Project(mdl.load(tmp_path))
    e = Engine(p, say=lambda s: None)

    def same():
        for k in ("ticket", "note"):
            assert looked_at(e, k) == scanned(e, k), k
    same()
    for i in range(6):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", data={"n": i})
        p.events.add("note.opened", item=f"note/{i}", source="t")
    same()
    for i in (0, 1):
        p.events.add(TAKEN, item=f"ticket/{i}", source="ergostat",
                     data={"run": f"r{i}", "block": "worker", "fence": 1, "ttl": 60, "max": 3, "back": "ready"})
    p.events.add(TAKEN, item="ticket/1", source="ergostat",              # refused by the fold: already held
                 data={"run": "x", "block": "worker", "fence": 1, "ttl": 60, "max": 3, "back": "ready"})
    same()
    p.events.add("ticket.reviewing", item="ticket/0", source="t", causedby="r0")   # moved on while still held
    p.events.add("ticket.done", item="ticket/2", source="t")
    p.events.add("note.read", item="note/3", source="t")
    p.events.add("ticket.changed", item="ticket/4", source="t", data={"n": 40})
    same()
    p.events.add(ENDED, item="ticket/0", source="ergostat", data={"run": "r0", "fence": 1, "how": "ack"})
    p.events.add(ENDED, item="ticket/1", source="ergostat", data={"run": "r1", "fence": 1, "how": "nack", "after": 30})
    same()
    (tmp_path / "ergostat.yaml").write_text(DISPATCHED.replace("AT", "[ready, doing]"))
    e.swap(mdl.load(tmp_path))                                          # another set of states taken: read whole again
    same()
    p.events.add("ticket.started", item="ticket/5", source="t")
    same()
    took = []
    e.dispatch.take = lambda b, it, inline=False: took.append((b.name, it.id, [m["event"] for m in it.moves]))
    e.dispatch.tick()
    from ergostat.spec import items as its
    whole = {i.id: [m["event"] for m in i.moves] for i in its.project(p.events, e.spec, "ticket", transcript=False)}
    assert took and all(moves == whole[i] for _, i, moves in took), "an item taken is given whole, its moves with it"
