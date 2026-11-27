"""Engine shards (SPEC §9.8, ergostat/spec/shards.py): every part in exactly one shard, by top-level system, merged
only by a shared agent, taken kind or daemon, with every in-memory crossing listed as a wire."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ergostat.spec import ir, load
from ergostat.spec.equation import parse as parse_equation
from ergostat.spec.ir import Agent, Auxiliary, Block, Equation, Goal, ItemKind, Join, Ref, Relation, Sensor, Setpoint, Spec, Stock, Takes
from ergostat.spec.shards import MAX_SHARDS, SAFE, plan

ROOT = Path(__file__).resolve().parent.parent


def spec(*systems: str) -> Spec:
    s = Spec("t", Path("."), [])
    for name in systems:
        s.systems[name] = ""
    return s


def stock(s: Spec, name: str, system: str, sensed: bool = True) -> None:
    s.stocks[name] = Stock(name, system=system)
    if sensed:
        s.stocks[name].sensors["n"] = Sensor("n", Ref("stock", name), run="true")


def block(s: Spec, name: str, system: str, **kw) -> Block:
    b = s.blocks[name] = Block(name, "program", system=system, **kw)
    return b


def two(**a) -> Spec:
    """Systems a and b, each a sensed stock and a block; the blocks get ``a`` (their shared keyword arguments)."""
    s = spec("a", "b")
    for x in ("a", "b"):
        stock(s, f"{x}-q", x)
        block(s, f"{x}-work", x, **a)
    return s


def parts_of(s: Spec) -> list[str]:
    """Every part of the spec, listed independently of shards.py."""
    out = [f"{k}.{n}" for k, t in (("stock", s.stocks), ("flow", s.flows), ("auxiliary", s.auxiliaries),
                                   ("goal", s.goals), ("block", s.blocks)) for n in t]
    out += [str(x.ref) for x in s.sensors()]
    out += [f"agent.{n}" for n in s.agents] + [f"projection.{n}" for n in s.items]
    return out


@pytest.fixture(scope="module")
def scale30_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("scale") / "n30"
    subprocess.run([sys.executable, str(ROOT / "scripts/scale_model.py"), "30", str(d)], check=True, capture_output=True)
    return d


@pytest.fixture(scope="module")
def scale30(scale30_dir) -> Spec:
    return load(scale30_dir / "ergostat.yaml")


@pytest.mark.parametrize("which", ["scale", "ticket-factory"])
def test_every_part_in_exactly_one_shard(which, scale30):
    s = scale30 if which == "scale" else load(ROOT / "examples/ticket-factory/ergostat.yaml")
    p = plan(s)
    want = parts_of(s)
    sensors = {str(x.ref) for x in s.sensors()}
    assert len(want) == len(set(want)) and sensors and {"stock", "flow", "auxiliary", "goal", "block", "agent",
                                                        "projection"} <= {w.split(".")[0] for w in want}
    seen = [k for sh in p.shards.values() for k in sh.parts]
    assert sorted(seen) == sorted(want)                   # each in exactly one shard, and nothing else
    for k in want:
        assert k in p.shards[p.of(k)].parts
    assert p.lead in p.shards and any(k.startswith("projection.ergostat.") for k in p.shards[p.lead].parts)


def test_systems_apart_unless_shared():
    p = plan(two())
    assert set(p.shards) == {"lead", "a", "b"} and p.why == {}
    assert p.of("block.a-work") == "a" and p.of("stock.b-q.n") == "b" and p.of(Ref("stock", "b-q", "n")) == "b"
    assert p.of(Ref("block", "a-work", "out")) == "a"     # a block's port is the block
    assert p.shards["lead"].parts == []                   # the lead is there, empty, in a model whose parts all have systems
    assert plan(spec()).shards["lead"].parts == []


def test_shared_agent_merges():
    s = two(agent="pool")
    s.agents["pool"] = Agent("pool", kind="program", at_once=2)
    p = plan(s)
    assert set(p.shards) == {"lead", "a"} and p.of("block.b-work") == "a" and p.of("agent.pool") == "a"
    assert p.why == {"a": [{"joined": "b", "because": "agent", "via": "pool"}]}


def test_shared_taken_kind_merges():
    s = two(takes=Takes("ticket", ["new"]))
    s.items["ticket"] = ItemKind("ticket", "ticket/*", ["new", "done"], system="b")
    p = plan(s)
    assert set(p.shards) == {"lead", "a"} and p.of("projection.ticket") == "a"
    assert p.why == {"a": [{"joined": "b", "because": "projection", "via": "ticket"}]}
    s = two()                                              # through a join: one takes the parent, the other its children
    s.items["epic"] = ItemKind("epic", "epic/*", ["open", "shipped"], join=[Join("parent", ["done"], "shipped")])
    s.items["ticket"] = ItemKind("ticket", "ticket/*", ["new", "done"], relations={"parent": Relation("parent", ["epic"])})
    s.blocks["a-work"].takes, s.blocks["b-work"].takes = Takes("epic", ["open"]), Takes("ticket", ["new"])
    assert plan(s).why == {"a": [{"joined": "b", "because": "projection", "via": "epic"}]}


def test_shared_daemon_merges():
    p = plan(two(params={"daemon": "probes"}))
    assert set(p.shards) == {"lead", "a"}
    assert p.why == {"a": [{"joined": "b", "because": "daemon", "via": "probes"}]}


def test_cross_reads_are_wires_not_merges():
    s = spec("a", "b")
    stock(s, "b-q", "b")                                   # sensed: read from the measurements, never a wire
    stock(s, "b-held", "b", sensed=False)                  # in memory only: a wire
    s.goals["b-level"] = Goal("b-level", Ref("stock", "b-q"), Setpoint("<=", 5), system="b")
    s.goals["a-q-ok"] = Goal("a-q-ok", Ref("stock", "b-q"), Setpoint("<=", 5), system="a")
    s.goals["a-held-ok"] = Goal("a-held-ok", Ref("stock", "b-held"), Setpoint("<=", 5), system="a")
    s.auxiliaries["b-load"] = Auxiliary("b-load", system="b", equation=Equation("stock.b-q * 2", parse_equation(
        "stock.b-q * 2"), ["stock.b-q"]))
    s.auxiliaries["a-load"] = Auxiliary("a-load", system="a", equation=Equation("auxiliary.b-load", parse_equation(
        "auxiliary.b-load"), ["auxiliary.b-load"]))
    block(s, "b-valve", "b")
    block(s, "a-ctl", "a", outputs={"out": [Ref("goal", "b-level"), Ref("block", "b-valve")]})
    p = plan(s)
    assert set(p.shards) == {"lead", "a", "b"} and p.why == {}
    got = {(w.ref, w.source, w.target, w.kind) for w in p.wires}
    assert got == {("goal.b-level", "a", "b", "setpoint"), ("block.b-valve", "a", "b", "command"),
                   ("auxiliary.b-load", "b", "a", "equation"), ("stock.b-held", "b", "a", "memory")}
    assert p.wires == sorted(p.wires)


def test_goal_and_cascade_reads_are_wires():
    s = two()
    s.goals["b-ok"] = Goal("b-ok", Ref("stock", "b-q"), Setpoint("<=", 5), system="b")
    s.blocks["a-work"].inputs = {"e": Ref("goal", "b-ok", "error"), "u": Ref("block", "b-work", "out")}
    got = {(w.ref, w.source, w.target, w.kind) for w in plan(s).wires}
    assert got == {("goal.b-ok.error", "b", "a", "goal"), ("block.b-work.out", "b", "a", "cascade"),
                   ("goal.b-ok", "b", "a", "goal")}         # its hold and status, given with the goal (Engine.context)


def test_estimate_reads_are_wires():
    s = two()
    s.blocks["a-work"].inputs = {"x": Ref("stock", "b-q", "estimate"), "u": Ref("stock", "b-q", "uncertainty"),
                                 "n": Ref("stock", "b-q", "n")}    # its sensor: read from the measurements
    p = plan(s)
    got = {(w.ref, w.source, w.target, w.kind) for w in p.wires}
    assert got == {("stock.b-q.estimate", "b", "a", "estimate"), ("stock.b-q.uncertainty", "b", "a", "estimate")}
    assert p.of(Ref("stock", "b-q", "estimate")) == "b" and p.of("stock.b-q.uncertainty") == "b"
    with pytest.raises(KeyError):
        p.of("stock.nope.estimate")


def test_served_goals_and_observed_flows_are_wires():
    s = two()
    s.flows["a-in"] = ir.Flow("a-in", target="a-q", system="a")
    s.goals["a-ok"] = Goal("a-ok", Ref("stock", "a-q"), Setpoint("<=", 5), system="a")
    s.blocks["a-work"].inputs = {"e": Ref("goal", "a-ok", "error")}
    s.blocks["a-work"].outputs = {"out": [Ref("block", "b-work")]}
    s.blocks["b-work"].outputs = {"out": [Ref("flow", "a-in")]}   # b-work acts in a-ok's loop, reading no goal
    s.flows["b-out"] = ir.Flow("b-out", source="a-q", system="b", equation=Equation("stock.b-q * 0.1", parse_equation(
        "stock.b-q * 0.1"), ["stock.b-q"]))
    got = {(w.ref, w.source, w.target, w.kind) for w in plan(s).wires}
    assert got == {("goal.a-ok", "a", "b", "goal"), ("block.b-work", "a", "b", "command"),
                   ("flow.a-in", "b", "a", "command")}
    s.stocks["a-q"].observe = True                         # now its observer adds up flow.b-out, worked out in b
    s.lookups().kept.pop("observer.opted", None)
    assert ("flow.b-out", "b", "a", "equation") in {(w.ref, w.source, w.target, w.kind) for w in plan(s).wires}


def test_ceiling_merges_smallest():
    s = spec(*(f"s{i:02d}" for i in range(20)))
    for i in range(20):
        for j in range(i % 3 + 1):                         # sizes 1 to 3: the smallest are known
            stock(s, f"s{i:02d}-x{j}", f"s{i:02d}")
    p = plan(s, most=16)
    assert len(p.shards) == 16 and "lead" in p.shards
    assert all(e["because"] == "ceiling" for w in p.why.values() for e in w) and sum(map(len, p.why.values())) == 5
    # 2 parts each (a stock and its sensor) for s00, s03 ... s18; the empty lead takes s00 and s03 (smallest, then by
    # name), s06 + s09 and s12 + s15 pair up, and the lead (4, before s01 by name) takes s18
    assert {n: [e["joined"] for e in w] for n, w in p.why.items()} == {
        "lead": ["s00", "s03", "s18"], "s06": ["s09"], "s12": ["s15"]}
    assert len(plan(s, most=99).shards) == MAX_SHARDS
    one = plan(s, most=0)
    assert list(one.shards) == ["lead"] and len(one.shards["lead"].parts) == len(parts_of(s))


def test_names_safe():
    long = "x" * 80
    s = spec("../x", "A B", long, "lead", "Ok")
    for name in s.systems:
        stock(s, f"p{len(s.stocks)}", name)
    p = plan(s)
    assert all(SAFE.match(n) for n in p.shards) and len(p.shards) == 6
    assert p.of("stock.p3") == "lead-2" and p.of("stock.p4") == "ok" and p.lead == "lead"
    assert p.of("stock.p0").startswith("s-") and p.of("stock.p0") != p.of("stock.p1")


def ring(n: int = 12) -> Spec:
    """n systems, each goal reading the next system's unsensed stock, and two by two sharing an agent: wires and merges
    (the scale model's systems all sit under one top-level system, so it has neither)."""
    s = spec(*(f"r{i:02d}" for i in range(n)))
    for i in range(n):
        x = f"r{i:02d}"
        stock(s, f"{x}-held", x, sensed=False)
        s.goals[f"{x}-ok"] = Goal(f"{x}-ok", Ref("stock", f"r{(i + 1) % n:02d}-held"), Setpoint("<=", 1), system=x)
        block(s, f"{x}-work", x, agent=f"pair-{i // 2}")
    return s


def test_same_plan_any_hash_seed(scale30_dir):
    code = ("import json,sys,pathlib;sys.path.insert(0,sys.argv[2]);from ergostat.spec import load;"
            "from ergostat.spec.shards import plan;from test_shards import ring;"
            "print(json.dumps([plan(load(pathlib.Path(sys.argv[1]))).json(),plan(ring()).json(),"
            "plan(ring(),most=5).json()]))")
    runs = [subprocess.run([sys.executable, "-c", code, str(scale30_dir / "ergostat.yaml"), str(ROOT / "tests")],
                           capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": str(h)})
            for h in (0, 1, 2)]
    assert [r.returncode for r in runs] == [0, 0, 0], runs[0].stderr[-2000:]
    outs = [r.stdout for r in runs]
    assert outs[0] == outs[1] == outs[2]
    got = json.loads(outs[0])
    assert got[0]["shards"] and len(got[1]["wires"]) == 6 and got[1]["why"] and len(got[2]["shards"]) == 5


def test_of_unknown_raises():
    p = plan(two())
    for ref in ("stock.nope", "agent.nope", "projection.nope", Ref("block", "nope"), "stock.a-q.nope"):
        with pytest.raises(KeyError):
            p.of(ref)


def test_daemon_shared_by_sensors_merges():
    """A daemon is one process whoever it serves: sensors in two systems (or a sensor and a block) put them in one shard,
    and the daemon is where they are; one serving nothing is the lead's."""
    s = two()
    s.daemons = {"probe": object(), "spare": object()}
    for x in ("a", "b"):
        s.stocks[f"{x}-q"].sensors["n"].daemon = "probe"
    p = plan(s)
    assert set(p.shards) == {"lead", "a"} and p.of("daemon.probe") == "a" and p.of("daemon.spare") == "lead"
    assert p.why == {"a": [{"joined": "b", "because": "daemon", "via": "probe"}]}
    assert not any(k.startswith("daemon.") for sh in p.shards.values() for k in sh.parts)
    s = two()
    s.daemons = {"probe": object()}
    s.stocks["a-q"].sensors["n"].daemon = "probe"
    s.blocks["b-work"].params["daemon"] = "probe"
    assert plan(s).why == {"a": [{"joined": "b", "because": "daemon", "via": "probe"}]}
