"""A frozen window on a block's queue (SPEC §9.5, ``takes: {frozen: {first: N, urgent: FIELD}}``,
dev/records/frozen-window-for-release.md): off unless declared; the first N keep their order against a re-rank or a
later arrival, while a re-rank outside it takes effect; an urgent item goes ahead, recorded with who and why; and the
completion estimates take items in the order the dispatcher does."""

from __future__ import annotations

import random
import textwrap
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat.leases import frozen
from ergostat.numbers import eta, etamodel
from ergostat.spec import read
from ergostat.spec.engine import Engine
from ergostat.store import Project
from ergostat.web.remote_api import answer

PLAIN = """
name: t
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [todo, doing, done]
    events:
      ticket-opened:
        when: type == 'ticket.opened'
        '...': data
        state: set('todo')
      ticket-started:
        when: type == 'ticket.started'
        '...': data
        state: set('doing')
      ticket-done:
        when: type == 'ticket.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
blocks:
  dev:
    type: program
    run: "true"
    takes: {projection: ticket, at: todo, to: [done], order: [-priority]}
"""
FROZEN = PLAIN.replace("order: [-priority]}", "order: [-priority], frozen: {first: 2, urgent: rush}}")
RUSH = {"by": "the owner", "why": "a customer's line is down"}


def project(tmp_path, text: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def dispatcher(p, monkeypatch):
    """The engine's dispatcher, its take recorded (the item moved on, out of the queue) instead of run."""
    said: list[str] = []
    e = Engine(p, say=said.append)
    d, taken = e.dispatch, []

    def take(b, it, **_):
        taken.append(it.id)
        p.events.add("ticket.started", item=it.id)
        return True
    monkeypatch.setattr(d, "take", take)
    return d, taken, said


def look(d, p) -> list[str]:
    """The dispatcher's order now (its ready list, the hooks, the window), as a take would read it."""
    b = p.model.spec.blocks["dev"]
    d.stale = True                                    # (as each look does: the record read again)
    every, _ = d.items_of("ticket")
    got = [i.id for i in d.in_order(b, d.ready(b, every, time.time()))[0]]
    frozen.settle(d, b, [], "test")                   # (a look with room that took nothing: the window written)
    return got


def tick(d, p) -> None:
    d.stale = True                                    # (as Dispatcher.tick sets it before each block's look)
    d.tick_block(p.model.spec.blocks["dev"], time.time())


def opened(p, prio: dict, at: float) -> None:
    for n, (i, v) in enumerate(prio.items()):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"priority": v}, at=at + n)


def lists(p) -> list[list[str]]:
    return [e["data"]["items"] for e in p.events.query(n=None, type=frozen.LIST)]


def test_off_by_default_existing_models_unchanged(tmp_path, monkeypatch):
    """No ``frozen:``: the block's Takes has none, a re-rank reorders the whole queue at once, nothing is written for
    it, and the estimates never take the frozen path."""
    p = project(tmp_path, PLAIN)
    assert p.model.spec.blocks["dev"].takes.frozen is None
    d, taken, _ = dispatcher(p, monkeypatch)
    opened(p, {"a": 4, "b": 3, "c": 2}, time.time() - 100)
    assert look(d, p) == ["ticket/a", "ticket/b", "ticket/c"]
    p.events.add("ticket.ranked", item="ticket/c", data={"priority": 9})
    assert look(d, p) == ["ticket/c", "ticket/a", "ticket/b"]          # the plain order: the re-rank at once
    tick(d, p)
    assert taken == ["ticket/c"]
    assert not p.events.query(n=None, type="block.frozen*")
    inp = etamodel.read(p, p.model.spec, ["ticket"], time.time())
    assert inp.blocks[0].frozen is None and inp.blocks[0].held == []
    monkeypatch.setattr(eta._Run, "pick", lambda self, b: pytest.fail("the frozen path, with no frozen: declared"))
    assert eta.simulate(inp, runs=3, budget=2.0)["items"]["ticket/a"]["p50"] is not None


def test_frozen_checked_with_its_bounds(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(FROZEN))
    spec, _ = read(tmp_path / "ergostat.yaml")
    assert spec.blocks["dev"].takes.frozen == frozen_of(2, "rush")
    for bad in ("{first: 0}", "{first: 201}", "{first: true}", "{first: 2.5}", "3", "{first: 2, urgent: [x]}",
                "{first: 2, later: 1}", "{first: " + "9" * 400 + "}"):
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(PLAIN.replace(
            "order: [-priority]}", f"order: [-priority], frozen: {bad}}}")))
        _, problems = read(tmp_path / "ergostat.yaml")
        assert any("takes.frozen" in x.message for x in problems if x.level == "error"), bad
    assert frozen.arrange(["a", "b"], [], 10_000, set())[1] == ["a", "b"]          # clamped again at run time
    assert frozen.arrange(["a", "b"], [], -3, set())[1] == ["a"]


def frozen_of(n, u):
    from ergostat.spec.ir import Frozen
    return Frozen(n, u)


def test_rerank_inside_the_window_holds_outside_takes_effect(tmp_path, monkeypatch):
    p = project(tmp_path, FROZEN)
    d, taken, _ = dispatcher(p, monkeypatch)
    opened(p, {"a": 4, "b": 3, "c": 2, "d": 1}, time.time() - 100)
    assert look(d, p) == ["ticket/a", "ticket/b", "ticket/c", "ticket/d"]
    assert lists(p) == [["ticket/a", "ticket/b"]]                     # the window, recorded
    p.events.add("ticket.ranked", item="ticket/b", data={"priority": 0})       # inside: it keeps its place
    p.events.add("ticket.ranked", item="ticket/d", data={"priority": 10})      # outside: ahead of c, behind the window
    assert look(d, p) == ["ticket/a", "ticket/b", "ticket/d", "ticket/c"]
    assert lists(p) == [["ticket/a", "ticket/b"]]                     # unchanged: nothing written
    tick(d, p)
    assert taken == ["ticket/a"]
    assert look(d, p) == ["ticket/b", "ticket/d", "ticket/c"]
    assert lists(p)[-1] == ["ticket/b", "ticket/d"]                   # d came in as a left it
    p.events.add("ticket.opened", item="ticket/e", data={"priority": 99})      # a later arrival, ranked highest
    assert look(d, p) == ["ticket/b", "ticket/d", "ticket/e", "ticket/c"]
    assert lists(p)[-1] == ["ticket/b", "ticket/d"]                   # the arrival waits behind the window
    for _ in range(4):
        tick(d, p)
    assert taken == ["ticket/a", "ticket/b", "ticket/d", "ticket/e", "ticket/c"]
    assert not p.events.query(n=None, type=frozen.BROKEN)


def test_a_taken_item_back_before_a_look_waits_behind_the_window(tmp_path, monkeypatch):
    """Pool 1: ``a`` is taken from the window [a, b] and its run fails (back to ``todo``) before any look with room.
    It left the window when taken, so it waits as any other item: behind ``b`` and a later, higher-ranked arrival,
    with no urgent record. The simulation, its run failing the same way, takes in the same order."""
    p = project(tmp_path, FROZEN)
    d, taken, _ = dispatcher(p, monkeypatch)
    opened(p, {"a": 4, "b": 3, "c": 2}, time.time() - 100)
    inp = etamodel.read(p, p.model.spec, ["ticket"], time.time())      # (the simulation's moment: nothing in force)
    tick(d, p)
    assert taken == ["ticket/a"] and lists(p)[-1] == ["ticket/b"]     # taken: it left the window in the record
    p.events.add("ticket.opened", item="ticket/e", data={"priority": 9})
    p.events.add("ticket.opened", item="ticket/a")                   # its run failed: back where it was taken from
    assert look(d, p) == ["ticket/b", "ticket/e", "ticket/a", "ticket/c"]
    for _ in range(4):
        tick(d, p)
    assert taken == ["ticket/a", "ticket/b", "ticket/e", "ticket/a", "ticket/c"]
    assert not p.events.query(n=None, type=frozen.BROKEN)

    run = eta._Run(inp, eta.Flags(arrivals=False), random.Random(1), {}, {}, False)
    started: list[str] = []

    def hold(b, i, t, a):                               # (a start: its end is the test's to say)
        started.append(i)
        run.busy[b] += 1
    monkeypatch.setattr(run, "hold", hold)
    run.go(0.0)
    t = inp.at + 1
    assert started == ["ticket/a"] and run.held[0] == ["ticket/b"]
    run.busy[0] -= 1                                    # its run failed: back in todo, with e arriving as it did
    run.items["ticket/e"] = ["ticket", "todo", t, 0, 0]
    run.inp.items["ticket/e"] = replace(inp.items["ticket/b"], id="ticket/e", fields={"priority": 9})
    run.enter("ticket/e", "todo", t)
    run.enter("ticket/a", "todo", t)
    while len(started) < 5:
        run.busy[0] -= 1
        run.wake(t)
    assert started == taken


def test_urgent_goes_ahead_and_is_recorded_with_who_and_why(tmp_path, monkeypatch):
    p = project(tmp_path, FROZEN)
    d, taken, said = dispatcher(p, monkeypatch)
    opened(p, {"a": 4, "b": 3, "c": 2}, time.time() - 100)
    look(d, p)
    p.events.add("ticket.ranked", item="ticket/c", data={"rush": True})        # no who, no why: no override
    assert look(d, p) == ["ticket/a", "ticket/b", "ticket/c"]
    assert any("ticket/c's rush does not say by: and why:" in s for s in said)
    p.events.add("ticket.ranked", item="ticket/c", data={"rush": {"by": "the owner"}})   # no why: none either
    assert look(d, p)[0] == "ticket/a"
    p.events.add("ticket.ranked", item="ticket/c", data={"rush": RUSH})
    assert look(d, p) == ["ticket/c", "ticket/a", "ticket/b"]
    assert lists(p)[-1] == ["ticket/a", "ticket/b"]                   # the window is kept behind it
    tick(d, p)
    assert taken == ["ticket/c"]
    rec = p.events.query(n=None, type=frozen.BROKEN)
    assert [r["data"] for r in rec] == [{"block": "dev", "urgent": "ticket/c", "by": "the owner",
                                         "why": "a customer's line is down", "ahead": ["ticket/a", "ticket/b"]}]
    assert rec[0]["item"] == "ergostat.frozen/dev"
    tick(d, p)
    assert taken == ["ticket/c", "ticket/a"] and len(p.events.query(n=None, type=frozen.BROKEN)) == 1
    got = answer(SimpleNamespace(get=lambda: p), "/v1/events", {"type": ["block.frozen*"]})   # read as a remote
    assert got[0] == 200 and {e["type"] for e in got[1]["events"]} == {frozen.LIST, frozen.BROKEN}


def test_unreadable_list_takes_the_plain_order_and_says_so(tmp_path, monkeypatch):
    p = project(tmp_path, FROZEN)
    d, taken, said = dispatcher(p, monkeypatch)
    opened(p, {"a": 1, "b": 2}, time.time() - 100)
    p.events.add(frozen.LIST, item=frozen.about("dev"), data={"block": "dev", "items": "ticket/a"})
    assert look(d, p) == ["ticket/b", "ticket/a"]
    assert any("frozen window not read" in s for s in said)
    assert etamodel.read(p, p.model.spec, ["ticket"], time.time()).blocks[0].frozen is None   # the same, projected


def test_newest_list_by_seq(tmp_path):
    p = project(tmp_path, FROZEN)
    t = time.time()
    p.events.add(frozen.LIST, item=frozen.about("dev"), data={"items": ["ticket/x"]}, at=t)
    p.events.add(frozen.LIST, item=frozen.about("dev"), data={"items": ["ticket/y"]}, at=t - 50)   # later, stamped earlier
    assert frozen.in_force(p.events, "dev") == ["ticket/y"]


def test_simulated_order_matches_the_dispatchers(tmp_path, monkeypatch):
    """One fixture: a window recorded, a re-rank inside and outside it, an urgent item, a later arrival. The
    estimates' start order at the block (pool 1, so starts are takes) is the order the dispatcher then takes them in,
    and differs from the plain order the window overrides."""
    p = project(tmp_path, FROZEN)
    d, taken, _ = dispatcher(p, monkeypatch)
    opened(p, {"a": 5, "b": 4, "c": 3, "d": 2, "e": 1}, time.time() - 300)
    look(d, p)                                                         # the window: a, b
    p.events.add("ticket.ranked", item="ticket/b", data={"priority": 0})
    p.events.add("ticket.ranked", item="ticket/e", data={"priority": 9})
    p.events.add("ticket.ranked", item="ticket/d", data={"rush": RUSH})
    p.events.add("ticket.opened", item="ticket/f", data={"priority": 8})
    inp = etamodel.read(p, p.model.spec, ["ticket"], time.time())
    assert inp.blocks[0].frozen == (2, "rush") and inp.blocks[0].held == ["ticket/a", "ticket/b"]
    got = eta.simulate(inp, eta.Flags(arrivals=False), runs=3, budget=5.0)["items"]
    projected = sorted(got, key=lambda i: got[i]["start"])
    pos = {i: r["position"] for i, r in eta.reasons(inp).items()}
    for _ in range(6):
        tick(d, p)
    assert taken == ["ticket/d", "ticket/a", "ticket/b", "ticket/e", "ticket/f", "ticket/c"]
    assert projected == taken                                          # the simulation's order: the dispatcher's
    assert sorted(pos, key=pos.get) == taken                           # and the Items tab's places
    plain = sorted(inp.items, key=lambda i: -(inp.items[i].fields.get("priority") or 0))
    assert plain != taken
    why = eta.reasons(inp)
    assert "held at 2 of its frozen window of 2 in dev" in why["ticket/b"]["why"]
    assert "urgent, ahead of its frozen window in dev (the owner: a customer's line is down)" in why["ticket/d"]["why"]
