"""Candidates to aggregate, from loop dominance over the window (SPEC §12c): a chain of stocks in one system that
no feedback loop beyond each stock's own drove, named as a candidate to aggregate into one delay; anything the
dominance does not know disqualifies."""

from __future__ import annotations

import copy
import itertools
import math
import os
import time

from ergostat import model as mdl
from ergostat.numbers import aggregation as ag
from ergostat.numbers import dominance as dm
from ergostat.numbers import observe as ob
from ergostat.store import Project

from .test_numbers import write

CHAIN = """\
name: p
parameters:
  tau: 0.25
  g: 1
systems:
  plant:
    description: the plant
  other:
    description: another one
stocks:
  a:
    unit: x
    system: plant
    sensor:
      manual: true
  b:
    unit: x
    system: plant
    sensor:
      manual: true
  c:
    unit: x
    system: plant
    sensor:
      manual: true
flows:
  in:
    to: a
    unit: x
    system: plant
    sensor:
      manual: true
  ab:
    from: a
    to: b
    system: plant
    driven-by: +stock.a
    equation: stock.a / tau
  bc:
    from: b
    to: c
    system: plant
    driven-by: +stock.b
    equation: stock.b / tau
  out:
    from: c
    system: plant
    driven-by: +stock.c
    equation: stock.c / tau
"""
SYSTEMS = "systems:\n  plant:\n    description: the plant\n  other:\n    description: another one\n"
ABC = ["stock.a", "stock.b", "stock.c"]
MADE = itertools.count()


def chain(tmp_path, text: str = CHAIN, moving: bool = True, minutes: int = 60, extra=()):
    """The model, its record over the last ``minutes`` (a fed from outside; each stock read once a minute), and
    its dominance on a grid of 20 buckets over that window. Each call is a project of its own (a record of its own)."""
    tmp_path = tmp_path / f"m{next(MADE)}"
    tmp_path.mkdir(parents=True)
    write(tmp_path, text)
    p = Project(mdl.load(tmp_path))
    now = time.time()
    since = now - minutes * 60
    for i in range(minutes + 1):
        t = since + i * 60
        p.measurements.add("sensor/in.main", (10 + 8 * math.sin(i / 5)) if moving else 0.0, at=t)
        for s in ("a", "b", "c", *extra):
            p.measurements.add(f"sensor/{s}.main", 2.0 if moving else 0.0, at=t)
    data = ob.measured(p, ob.Grid(since, now, 20))
    return p, data, dm.dominance(p.model.spec, data)


def groups(p, dom, system="plant"):
    return [g["stocks"] for g in (ag.candidates(p.model.spec, dom) or {}).get(system, [])]


def test_a_chain_of_first_order_stages_is_a_candidate_to_aggregate(tmp_path):
    p, data, dom = chain(tmp_path)
    got = ag.candidates(p.model.spec, dom)
    assert [g["stocks"] for g in got["plant"]] == [ABC] and got["other"] == []
    since, until = (time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) for t in (data.grid.since, data.grid.until))
    assert got["plant"][0]["said"] == (f"over the window ({since} to {until}) no feedback loop beyond each stock's own "
                                       f"drove stock.a, stock.b, stock.c: a candidate to aggregate into one delay")


BACK = """\
  back:
    to: a
    system: plant
    driven-by: +stock.c
    equation: g * stock.c
"""


def drove(dom, loop):
    return [s for s, x in dom["stocks"].items() if loop in x["dominant"]]


def test_a_dominant_loop_through_two_stocks_disqualifies_them(tmp_path):
    p, _, dom = chain(tmp_path, CHAIN.replace("g: 1", "g: 3.9") + BACK)
    assert dom["polarity"]["a via bc"] == "R" and "stock.a" in drove(dom, "a via bc")     # it dominated a in the window
    assert groups(p, dom) == []                       # it runs through a, b and c: none of them is a candidate
    p, _, dom = chain(tmp_path, CHAIN.replace("g: 1", "g: 0.01") + BACK)           # the same loop, too weak to dominate
    assert "a via bc" in dom["polarity"] and drove(dom, "a via bc") == []
    assert groups(p, dom) == [ABC]


DECIDE = """\
  feed:
    to: a
    system: plant
blocks:
  decide:
    type: program
    run: "true"
    in: [INPUTS]
    out: flow.feed
"""


def test_unknown_dominance_is_never_a_candidate(tmp_path):
    p, _, dom = chain(tmp_path)
    assert groups(p, dom) == [ABC]                                    # the unchanged chain is one
    # a loop through b (and a and c) through a decision with 2 inputs: not scored; with 1 input it is, and qualifies
    p, _, dom = chain(tmp_path, CHAIN + DECIDE.replace("INPUTS", "+stock.c, +flow.in"))
    assert dom["not_scored"] and not dom["stocks"]["stock.b"]["named"]
    assert groups(p, dom) == []
    p, _, dom = chain(tmp_path, CHAIN + DECIDE.replace("INPUTS", "+stock.c"))
    assert not dom["not_scored"] and len(dom["polarity"]) == 4 and dom["stocks"]["stock.b"]["named"]
    assert groups(p, dom) == [ABC]
    # a window in which nothing moves
    p, _, dom = chain(tmp_path, moving=False)
    assert dom["stocks"]["stock.b"]["steps"] == 0
    assert groups(p, dom) == []
    # the dominance missing, or worked out for another version of the model (other loops)
    p, _, dom = chain(tmp_path)
    assert groups(p, None) == [] and groups(p, {}) == []
    _, _, other = chain(tmp_path / "x", CHAIN.replace("g: 1", "g: 0.01") + BACK)
    assert groups(p, other) == []


def test_each_thing_the_dominance_does_not_know_disqualifies_on_its_own(tmp_path):
    """Each rule alone, on the dominance worked out and then changed in one field (the same dominance unchanged
    qualifies), so that each check, removed, fails here."""
    p, _, dom = chain(tmp_path, CHAIN.replace("g: 1", "g: 0.01") + BACK)
    assert groups(p, dom) == [ABC]

    def changed(edit):
        d = copy.deepcopy(dom)
        edit(d["stocks"]["stock.a"], d)
        return groups(p, d)

    assert changed(lambda x, d: x.update(named=False)) == [ABC[1:]]                 # not named
    assert changed(lambda x, d: x.update(steps=0)) == [ABC[1:]]                     # never moved
    assert changed(lambda x, d: x["tied"].__setitem__(3, True)) == [ABC[1:]]        # tied, with a loop through c too
    assert changed(lambda x, d: d["not_scored"].update({"a via bc": "why"})) == []  # a loop through all three not scored
    assert changed(lambda x, d: x["scored"].remove("a")) == [ABC[1:]]               # its own loop not scored
    assert changed(lambda x, d: d["stocks"].pop("stock.a")) == [ABC[1:]]            # not in the dominance at all
    # a tie at a stock whose only loop is its own does not disqualify it (no other loop is in the tie)
    q, _, plain = chain(tmp_path / "plain")
    plain["stocks"]["stock.a"]["tied"][3] = True
    assert groups(q, plain) == [ABC]


ACCUMULATOR = """\
  d:
    unit: x
    system: plant
    sensor:
      manual: true
"""


def test_a_stock_with_no_drain_of_its_own_is_not_a_stage_of_a_delay(tmp_path):
    """A pure accumulator (no loop runs through it) is not a first-order stage: it is in no group, moving or not, with
    the dominance or without it; with its drain it is."""
    text = CHAIN.replace("flows:\n", ACCUMULATOR + "flows:\n").replace("  out:\n    from: c\n", "  out:\n    from: c\n    to: d\n")
    p, _, dom = chain(tmp_path, text, extra=("d",))
    assert "stock.d" not in dom["stocks"] and groups(p, dom) == [ABC]
    p, _, dom = chain(tmp_path, text, moving=False, extra=("d",))
    assert groups(p, dom) == [] and groups(p, None) == []
    drained = text + "  drain:\n    from: d\n    system: plant\n    driven-by: +stock.d\n    equation: stock.d / tau\n"
    p, _, dom = chain(tmp_path, drained, extra=("d",))
    assert groups(p, dom) == [[*ABC, "stock.d"]]
    grows = text + "  grow:\n    to: d\n    system: plant\n    driven-by: +stock.d\n    equation: 0.01 * stock.d\n"
    p, _, dom = chain(tmp_path, grows, extra=("d",))                 # its own loop reinforcing: not a drain
    assert dom["stocks"]["stock.d"]["named"] and dom["stocks"]["stock.d"]["steps"] and groups(p, dom) == [ABC]


TWO = """\
name: p
parameters:
  tau: 0.25
systems:
  plant:
    description: the plant
  other:
    description: another one
stocks:
  a:
    unit: x
    system: plant
    sensor:
      manual: true
  b:
    unit: x
    system: SYSTEM_B
    sensor:
      manual: true
flows:
  in:
    to: a
    system: plant
    sensor:
      manual: true
  inb:
    to: b
    system: plant
    driven-by: +flow.in
    equation: flow.in
  outa:
    from: a
    TO_B
    system: plant
    driven-by: +stock.a
    equation: stock.a / tau
  outb:
    from: b
    system: plant
    driven-by: +stock.b
    equation: stock.b / tau
"""


def test_stocks_without_a_flow_between_them_are_not_a_group(tmp_path):
    def run(sub, system_b, to_b):
        text = TWO.replace("SYSTEM_B", system_b).replace("    TO_B\n", "    to: b\n" if to_b else "")
        p, _, dom = chain(tmp_path / sub, text)
        return p, dom, ag.qualifying(p.model.spec, dom)
    p, dom, ok = run("apart", "plant", False)                         # both qualify, no flow between them
    assert ok == {"stock.a", "stock.b"} and groups(p, dom) == []
    p, dom, ok = run("joined", "plant", True)                         # the counterpart: a flow from a to b
    assert groups(p, dom) == [["stock.a", "stock.b"]]
    p, dom, ok = run("two-systems", "other", True)                    # joined, but one in each system
    assert ok == {"stock.a", "stock.b"} and groups(p, dom) == [] and groups(p, dom, "other") == []


def test_the_dominance_api_returns_aggregate_and_drops_it_when_the_model_changes(tmp_path):
    from ergostat.web.server import Live, api
    p, _, _ = chain(tmp_path)
    live = Live(p)
    q = {"since": ["1h"]}
    got = api(live, "dominance", q)
    assert [(g["system"], g["stocks"]) for g in got["aggregate"]] == [("plant", ABC)]
    assert "a candidate to aggregate into one delay" in got["aggregate"][0]["said"]
    f, was = p.model.path, live.mtime
    before = f.stat().st_mtime_ns
    f.write_text(CHAIN.replace("g: 1", "g: 3.9") + BACK)             # the same model with the dominating loop
    os.utime(f, ns=(before + 2_000_000_000, before + 2_000_000_000))  # its time moved on, whatever the clock's grain
    p.model = mdl.load(p.model.path.parent)
    live.reloaded()
    assert live.mtime != was
    got = api(live, "dominance", q)
    assert "a via bc" in got["polarity"] and got["aggregate"] == []


BRANCH = """\
  ac:
    from: a
    to: c
    system: plant
    driven-by: +stock.a
    equation: stock.a / tau
"""


def test_a_branch_is_not_a_chain(tmp_path):
    """Groups are linear chains only: a → b and a → c (each qualifying) give no group, since no one order is material."""
    text = CHAIN.replace("  bc:\n    from: b\n    to: c\n", "  bc:\n    from: b\n").replace("  out:\n", BRANCH + "  out:\n")
    p, _, dom = chain(tmp_path, text)
    assert ag.qualifying(p.model.spec, dom) == set(ABC) and groups(p, dom) == []


def test_a_model_with_no_systems_has_no_answer(tmp_path):
    text = CHAIN.replace(SYSTEMS, "").replace("    system: plant\n", "")
    assert text != CHAIN and "system:" not in text
    p, _, dom = chain(tmp_path, text)
    assert ag.candidates(p.model.spec, dom) is None
