"""One bad link never stops dispatch (dev/records/one-bad-link-never-stops-dispatch.md): a child depending on its own
split parent is a loop through a group relation; the graph marks it a cycle and nothing in it is taken."""

from __future__ import annotations

import textwrap
import time

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.spec import items as its
from ergostat.store import Project

MODEL = """
projections:
  gap:
    match:
      key: gap/*
    states: [open, building, merged]
    events:
      gap.opened:
        state: set('open')
      gap.started:
        state: set('building')
      gap.merged:
        state: set('merged')
    otherwise: rest
    relations:
      depends_on: gap
      parent: gap
messages:
  done: {gap: [merged]}
"""


def project(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def test_a_child_depending_on_its_split_parent_does_not_raise_and_is_not_taken(tmp_path):
    p = project(tmp_path)
    ev, t = p.events, time.time() - 100
    ev.add("gap.opened", item="gap/p", at=t)
    ev.add("gap.opened", item="gap/c", data={"parent": "gap/p", "depends_on": ["gap/p"]}, at=t + 1)
    ev.add("gap.opened", item="gap/sib", data={"parent": "gap/p"}, at=t + 2)
    ev.add("gap.opened", item="gap/free", at=t + 3)
    spec = p.model.spec
    g = pr.build(ev, spec, ["gap"], time.time(), t)
    by = {x["id"]: x for x in g["items"]}
    assert ["gap/c", "gap/p"] in g["cycles"]
    assert by["gap/c"]["cycle"] and by["gap/p"]["cycle"] and "es" not in by["gap/c"]
    assert by["gap/c"]["waiting"] == ["gap/p"] and by["gap/c"]["status"] == "blocked"     # it names what it waits on
    assert not by["gap/free"]["cycle"] and "es" in by["gap/free"]
    todo = [i for i in its.project(ev, spec, "gap") if i.state == "open"]
    got = [i.id for i in pr.order_ready(ev, spec, "gap", todo, time.time())]
    assert "gap/c" not in got and "gap/p" not in got and "gap/free" in got


def test_a_parent_depending_on_its_child_and_a_grandchild_on_its_grandparent_are_cycles_not_taken(tmp_path):
    p = project(tmp_path)
    ev, t = p.events, time.time() - 100
    # a parent on its own child: the parent's start comes before the child, the child before the parent
    ev.add("gap.opened", item="gap/p", data={"depends_on": ["gap/c"]}, at=t)
    ev.add("gap.opened", item="gap/c", data={"parent": "gap/p"}, at=t + 1)
    # a grandchild on its grandparent, and a grandparent on its grandchild
    ev.add("gap.opened", item="gap/g", at=t + 2)
    ev.add("gap.opened", item="gap/m", data={"parent": "gap/g"}, at=t + 3)
    ev.add("gap.opened", item="gap/k", data={"parent": "gap/m", "depends_on": ["gap/g"]}, at=t + 4)
    ev.add("gap.opened", item="gap/G", data={"depends_on": ["gap/K"]}, at=t + 5)
    ev.add("gap.opened", item="gap/M", data={"parent": "gap/G"}, at=t + 6)
    ev.add("gap.opened", item="gap/K", data={"parent": "gap/M"}, at=t + 7)
    ev.add("gap.opened", item="gap/free", at=t + 8)
    spec = p.model.spec
    g = pr.build(ev, spec, ["gap"], time.time(), t)
    by = {x["id"]: x for x in g["items"]}
    for a in ("gap/p", "gap/c", "gap/g", "gap/k", "gap/G", "gap/K"):
        assert by[a]["cycle"] and "es" not in by[a], a
    assert ["gap/c", "gap/p"] in g["cycles"]
    assert by["gap/p"]["waiting"] == ["gap/c"] and by["gap/G"]["waiting"] == ["gap/K"]   # each names what it waits on
    assert not by["gap/free"]["cycle"] and "es" in by["gap/free"]
    todo = [i for i in its.project(ev, spec, "gap") if i.state == "open"]
    got = [i.id for i in pr.order_ready(ev, spec, "gap", todo, time.time())]
    assert got == ["gap/free"]


TWO = """
name: t
projections:
  ticket:
    match:
      key: ticket/*
    states: [ready, doing, done]
    events:
      ticket.started:
        state: set('doing')
      ticket.done:
        state: set('done')
    otherwise: rest
  part:
    match:
      key: part/*
    states: [ready, made]
    events:
      part.made:
        state: set('made')
    otherwise: rest
blocks:
  first:
    type: program
    takes: {projection: ticket, at: ready}
    run: "sleep 30"
  second:
    type: program
    takes: {projection: part, at: ready}
    run: "sleep 30"
"""


def test_a_block_whose_look_raises_does_not_stop_the_next_block_s_dispatch(tmp_path):
    from ergostat.leases import TAKEN
    from ergostat.spec.engine import Engine
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(TWO))
    p = Project(mdl.load(tmp_path))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    p.events.add("part.opened", item="part/1", source="t")
    said: list[str] = []
    e = Engine(p, say=said.append)
    d = e.dispatch
    real = d.ready

    def ready(b, *a, **k):                          # the first block's look meets the incident's error
        if b.name == "first":
            raise KeyError("gap/ai-calls-ask-the-budget")
        return real(b, *a, **k)
    d.ready = ready
    d._work = lambda *a, **k: []                     # (no run: only the take is looked at)
    try:
        assert [b.name for b in d.blocks] == ["first", "second"]
        err = d.tick()
        assert [x["item"] for x in p.events.query(n=None, type=TAKEN)] == ["part/1"]     # the next block still took
        assert err == "first: KeyError: 'gap/ai-calls-ask-the-budget'"
        assert any("leases: first: KeyError" in s for s in said)
    finally:
        e.running.clear()
        e.close()


def test_a_repeated_dispatcher_error_raises_a_situation(tmp_path, monkeypatch):
    """Every look meeting an error, whatever each says, is one standing error from when they began; a clean look ends
    it. The heartbeat carries it, health fails on it, and past two minutes the pipeline watch raises a broken
    situation naming it at once (not after broken_minutes)."""
    import json

    from ergostat.leases.dispatch import Dispatcher
    from ergostat.spec.watchdog import heartbeat
    from tests.test_factory_manager import Pipe
    d = Dispatcher.__new__(Dispatcher)
    d.failing = None
    monkeypatch.setattr(time, "time", lambda: 1000.0)
    d.note("a: KeyError: 'x'")
    monkeypatch.setattr(time, "time", lambda: 1100.0)
    d.note("b: KeyError: 'y'")
    assert d.failing == ("b: KeyError: 'y'", 1000.0)                    # the latest error, since the first
    d.note(None)
    assert d.failing is None
    monkeypatch.undo()
    heartbeat(tmp_path, time.time(), 0, failing=("first: KeyError: 'gap/x'", time.time() - 200))
    beat = json.loads((tmp_path / "heartbeat.json").read_text())
    assert beat["dispatch_error"]["why"] == "first: KeyError: 'gap/x'"
    f = Pipe(tmp_path / "pipe")
    stale = {**beat, "written": beat["written"] - 600}                  # an engine that died while failing
    code = ("import time, watch\nwatch.load.reading = lambda w: 0\n"
            f"watch.live.heartbeat = lambda cfg: {stale!r}\n"
            "dead = watch.conditions(watch.fac.config(), {}, [], time.time())\n"
            "assert 'dispatch' not in dead, dead\n"
            f"watch.live.heartbeat = lambda cfg: {{**{beat!r}, 'written': time.time()}}\n"    # (fresh when read)
            "print(json.dumps({'fresh': watch.live.dispatch_failing({'dispatch_error': {'why': 'w', 'since': time.time()}},"
            " time.time()), 'nan': watch.live.dispatch_failing({'dispatch_error': {'why': 'w', 'since': 'nan'}}, 0),"
            " 'sit': watch.raise_one(watch.fac.config())}))")
    got = f.py(code)
    assert got["fresh"] is None and got["nan"]                           # under two minutes: not yet; NaN: never fresh
    assert got["sit"]["reason"] == "broken" and "KeyError: 'gap/x'" in got["sit"]["broken"]["dispatch"]["why"]
