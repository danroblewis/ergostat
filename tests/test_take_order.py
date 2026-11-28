"""A block's take order (SPEC §9.5, `takes: {order: ...}`), for any projection: the dispatcher's order, and the
completion estimates' queue (SPEC §5a), by one comparator, so the Timeline shows the order the block will take items
in; and a block switched off now is projected not to take anything."""

from __future__ import annotations

import textwrap
import time
from types import SimpleNamespace

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.leases.ready import order_key, ordered, unblocked
from ergostat.numbers import eta, etamodel
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.store import Project

MODEL = """
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        values: [todo, fix, doing, done]
    events:
      ticket-opened:
        when: type == 'ticket.opened'
        '...': data
        state: set('todo')
      ticket-failed:
        when: type == 'ticket.failed'
        '...': data
        state: set('fix')
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
    relations: {blocked_by: ticket}
messages:
  done: {ticket: [done]}
blocks:
  dev:
    type: program
    run: "true"
    takes: {projection: ticket, at: [fix, todo], to: [done], unblocked: true, order: [-priority]}
"""


def project(tmp_path, text: str = MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def dispatched(p) -> list[str]:
    """What the dispatcher takes, in order: its ready list (the states of at, oldest first), then the hooks."""
    spec, b = p.model.spec, p.model.spec.blocks["dev"]
    got = sorted((i for i in its.project(p.events, spec, "ticket") if i.state in b.takes.at),
                 key=lambda i: (b.takes.at.index(i.state), i.entered, i.first))
    return [i.id for i in ordered(b, unblocked(SimpleNamespace(p=p, spec=spec), b, got))]


def projected(p) -> list[str]:
    inp = etamodel.read(p, p.model.spec, ["ticket"], time.time())
    pos = {i: r["position"] for i, r in eta.reasons(inp).items() if r.get("waits_in") == "dev" and r["position"]}
    return sorted(pos, key=pos.get)


def test_the_estimates_queue_in_the_dispatchers_order(tmp_path):
    p = project(tmp_path)
    ev, t = p.events, time.time() - 1000
    for n, (i, data) in enumerate([("low", {"priority": 1}), ("high", {"priority": 3}), ("none", {}),
                                   ("urgent", {"priority": 5}), ("blocker", {}), ("old-fix", {}),
                                   ("fix-2", {"priority": 2})]):
        ev.add("ticket.opened", item=f"ticket/{i}", data=data, at=t + n)
    ev.add("ticket.started", item="ticket/blocker", at=t + 10)                          # unfinished: holds urgent
    ev.add("ticket.opened", item="ticket/urgent", data={"blocked_by": "ticket/blocker"}, at=t + 11)
    ev.add("ticket.failed", item="ticket/old-fix", at=t + 12)
    ev.add("ticket.failed", item="ticket/fix-2", at=t + 13)
    want = ["ticket/high", "ticket/fix-2", "ticket/low", "ticket/old-fix", "ticket/none"]
    assert dispatched(p) == want            # priority, highest first; then fix before todo; urgent waits on blocker
    assert projected(p) == want             # the Timeline's queue: the same
    ev.add("ticket.done", item="ticket/blocker", at=t + 20)
    assert dispatched(p)[0] == projected(p)[0] == "ticket/urgent"


def test_order_fields_ascending_descending_and_missing_last(tmp_path):
    assert sorted([None, 3, "b", 1, "a"], key=order_key) == [1, 3, "a", "b", None]
    assert sorted([None, 3, "ab", 1, "abc"], key=lambda v: order_key(v, True)) == [3, 1, "abc", "ab", None]
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("order: [-priority]", "order: rank"))
    spec, _ = read(tmp_path / "ergostat.yaml")
    assert spec.blocks["dev"].takes.order == ["rank"]
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("order: [-priority]", "order: [3]"))
    _, problems = read(tmp_path / "ergostat.yaml")
    assert any("takes.order: a field's name" in x.message for x in problems if x.level == "error")
    for bad in ('["pri ority"]', "[.nan]", '["-"]'):
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("order: [-priority]", f"order: {bad}"))
        _, problems = read(tmp_path / "ergostat.yaml")
        assert any("takes.order: a field's name" in x.message for x in problems if x.level == "error"), bad


GATED = MODEL.replace("blocks:\n", """auxiliaries:
  dev-open:
    unit: switch
    exogenous: true
    sensor: {manual: true}
blocks:
  dev-when:
    type: expr
    in: {open: auxiliary.dev-open}
    expr: min(open, 1)
    out: block.dev
""")


def test_a_block_switched_off_is_projected_not_to_take(tmp_path):
    p = project(tmp_path, GATED)
    p.events.add("ticket.opened", item="ticket/a", at=time.time() - 60)
    spec = p.model.spec
    assert etamodel.gated_off(p, spec, time.time()) == {"dev": "dev-when, dev-open at 0"}   # never read: off
    inp = etamodel.read(p, spec, ["ticket"], time.time())
    why = eta.reasons(inp)["ticket/a"]
    assert why["off"] and "switched off now (by dev-when, dev-open at 0)" in why["why"]
    got = eta.simulate(inp, runs=5, budget=2.0)
    assert got["items"]["ticket/a"]["p50"] is None                               # projected not to move
    series = next(iter(spec.auxiliaries["dev-open"].sensors.values())).series
    p.measurements.add(series, 1.0, time.time() - 1)
    assert etamodel.gated_off(p, spec, time.time()) == {}
    assert not eta.reasons(etamodel.read(p, spec, ["ticket"], time.time()))["ticket/a"].get("off")


PAUSED = MODEL.replace("messages:\n  done: {ticket: [done]}", """messages:
  done: {ticket: [done]}
  paused: {ticket: [held]}""").replace("values: [todo, fix, doing, done]", "values: [todo, fix, doing, held, done]").replace(
    "        state: set('done')\n", "        state: set('done')\n      ticket-held:\n        when: type == 'ticket.held'\n"
    "        state: set('held')\n")


