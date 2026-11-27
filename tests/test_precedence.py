"""The Timeline's forward pass levelled by each block's capacity (SPEC §5a, *The critical path*; precedence.level),
the capacity read from one function (numbers/etamodel.capacities), kept with the snapshot. And a precedence
relation's ``starts_at`` (SPEC §5a, *Relations*): a target in a named state does not block, for status and for
``takes: {unblocked: true}``; the critical path stays finish-to-start."""

from __future__ import annotations

import textwrap
import time
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.leases.ready import unblocked
from ergostat.numbers import etamodel
from ergostat.spec import items as its
from ergostat.store import Project

T0 = 1_700_000_000.0
MEDIAN = 1200.0                      # 20 min doing

MODEL = """
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [todo, doing, done]
    events:
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
    relations:
      blocked_by: ticket
messages:
  done: {ticket: [done]}
blocks:
  worker:
    type: program
    run: "true"
    takes: {projection: ticket, at: todo}
    pool: 6
"""

GAPS = """
projections:
  gap:
    query: key.startswith('gap/')
    fields:
      state:
        type: one of [ready, doing, review, fix, approved, merged]
    events:
      gap-opened:
        when: type == 'gap.opened'
        '...': data
        state: set('ready')
      gap-started:
        when: type == 'gap.started'
        '...': data
        state: set('doing')
      gap-reviewed:
        when: type == 'gap.reviewed'
        '...': data
        state: set('review')
      gap-failed:
        when: type == 'gap.failed'
        '...': data
        state: set('fix')
      gap-approved:
        when: type == 'gap.approved'
        '...': data
        state: set('approved')
      gap-merged:
        when: type == 'gap.merged'
        '...': data
        state: set('merged')
      other:
        when: true
        '...': data
    relations:
      depends_on: {projection: gap, starts_at: [approved]}
messages:
  done: {gap: [merged]}
blocks:
  dev:
    type: program
    run: "true"
    takes: {projection: gap, at: [ready], to: [merged], unblocked: true}
  queue:
    type: program
    run: "true"
    takes: {projection: gap, at: [approved], to: [merged]}
"""


def project(tmp_path, text=MODEL) -> Project:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def seeded(tmp_path, n=100, chain=0) -> Project:
    """Five finished tickets (20 min doing each), then ``n`` in todo; the first ``chain`` of them one after another."""
    p = project(tmp_path)
    ev = p.events
    for i in range(5):
        ev.add("ticket.planned", item=f"ticket/old{i}", at=T0 + i)
        ev.add("ticket.started", item=f"ticket/old{i}", at=T0 + 10 + i)
        ev.add("ticket.done", item=f"ticket/old{i}", at=T0 + 10 + i + MEDIAN)
    for i in range(n):
        after = {"blocked_by": f"ticket/n{i - 1:03}"} if 0 < i < chain else {}
        ev.add("ticket.planned", item=f"ticket/n{i:03}", data=after, at=T0 + 2000)
    return p


def bars(g) -> list[tuple]:
    return [(x["id"], *seg) for x in g["items"] for seg in x.get("projected") or []]


def most_at_once(segs) -> int:
    ts = sorted([(t0, 1) for *_, t0, t1, _b, _k in segs] + [(t1, -1) for *_, t0, t1, _b, _k in segs])
    n = most = 0
    for _, d in ts:
        n += d
        most = max(most, n)
    return most


def test_forward_pass_levelled_by_capacity(tmp_path):
    """100 unblocked items on a block of capacity 6, a median of 20 min: done at about 100/6 x 20 min, not 20 min; and
    the same levelled bars at a moment travelled to (the Timeline's own path, relations_api.graph)."""
    p = seeded(tmp_path)
    now = T0 + 3000
    snap = {"at": now, "window": 3600}
    lanes = etamodel.capacities(p, snap)
    assert lanes["worker"]["lanes"] == 6 and lanes["worker"]["source"] == "its pool"
    g = pr.build(p.events, p.model.spec, ["ticket"], now, now - 3600, lanes=lanes)
    assert g["end"] - now == pytest.approx(17 * MEDIAN)                   # ceil(100 / 6) runs, one after another
    unlevelled = pr.build(p.events, p.model.spec, ["ticket"], now, now - 3600)
    assert unlevelled["end"] - now == pytest.approx(MEDIAN)               # what it was: every one at once
    b = bars(g)
    assert len(b) == 100 and all(seg[4] == "worker" for seg in b) and most_at_once(b) == 6
    assert max(seg[3] for seg in b) == pytest.approx(g["end"])            # the end said is the last bar's
    from ergostat.web.relations_api import graph
    past = graph(p, p.model, dict(snap), {"kinds": ["ticket"]})          # a moment travelled to (an hour ago, here)
    assert abs(time.time() - snap["at"]) >= 5
    assert past["end"] - now == pytest.approx(17 * MEDIAN) and most_at_once(bars(past)) == 6


def test_levelled_respects_dependencies(tmp_path):
    """A chain of 10 among 40: no block busier than its capacity, and each item starts after what it waits on ends."""
    p = seeded(tmp_path, n=40, chain=10)
    now = T0 + 3000
    g = pr.build(p.events, p.model.spec, ["ticket"], now, now - 3600, lanes=etamodel.capacities(p, {"at": now}))
    b = bars(g)
    assert most_at_once(b) <= 6 and len(b) == 40
    by = {x["id"]: x for x in g["items"]}
    for e in g["edges"]:
        assert by[e["from"]]["projected"][-1][2] <= by[e["to"]]["projected"][0][1] + 1e-6, e
    assert g["end"] - now == pytest.approx(10 * MEDIAN)          # the chain binds: 30 others fit in the 5 lanes beside it
    lanes = {}
    for _, _st, t0, t1, _blk, k in b:                            # one run at a time in each lane
        lanes.setdefault(k, []).append((t0, t1))
    assert all(a[1] <= c[0] + 1e-6 for v in lanes.values() for a, c in zip(sorted(v), sorted(v)[1:], strict=False))
    assert len(lanes) <= 6


def test_capacity_comes_from_one_function(tmp_path, monkeypatch):
    """etamodel.capacities is the one place: changed there, both the simulation's inputs and the levelled pass follow;
    worked out once per snapshot, and nothing read for it in precedence.build."""
    p = seeded(tmp_path, n=12)
    now = T0 + 3000
    calls = []
    real = etamodel._capacity
    monkeypatch.setattr(etamodel, "_capacity", lambda *a: calls.append(a) or {**real(*a), "lanes": 2})
    snap = {"at": now, "window": 3600}
    assert etamodel.capacities(p, snap) is etamodel.capacities(p, snap) and len(calls) == 1   # kept with the snapshot
    inp = etamodel.read(p, p.model.spec, ["ticket"], now)
    assert [b.capacity() for b in inp.blocks] == [2] and inp.blocks[0].capacity({"worker": 5}) == 5   # (a what-if)
    from ergostat.numbers import eta
    sim = eta.simulate(inp, runs=3, budget=2.0)
    assert sim["limit"] == {"worker": 2}
    monkeypatch.setattr(etamodel, "_capacity", lambda *a: pytest.fail("a record read in precedence.build"))
    g = pr.build(p.events, p.model.spec, ["ticket"], now, now - 3600, lanes=etamodel.capacities(p, snap))
    assert most_at_once(bars(g)) == 2 and g["end"] - now == pytest.approx(6 * MEDIAN)


REVIEWED = """
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [todo, doing, review, reviewing, done]
    events:
      ticket-started:
        when: type == 'ticket.started'
        '...': data
        state: set('doing')
      ticket-submitted:
        when: type == 'ticket.submitted'
        '...': data
        state: set('review')
      ticket-picked:
        when: type == 'ticket.picked'
        '...': data
        state: set('reviewing')
      ticket-done:
        when: type == 'ticket.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
messages:
  done: {ticket: [done]}
blocks:
  worker:
    type: program
    run: "true"
    takes: {projection: ticket, at: todo}
    pool: 6
  reviewer:
    type: program
    run: "true"
    takes: {projection: ticket, at: review}
    pool: 1
"""


def test_queue_wait_holds_no_lane(tmp_path):
    """A block that takes at a later state (review, its median wait 2 h) with capacity 1: the wait holds no lane, and
    the take is levelled from where the wait began (its median end, or later when the lane is busy then), so the
    contention is counted once. 12 tickets: doing ends at 20 and 40 min, waits at 2 h 20 and 2 h 40, then the 12
    reviews of 10 min one after another from 2 h 20: done at 4 h 20 (holding the lane through the wait: about 26 h)."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(REVIEWED))
    p = Project(mdl.load(tmp_path))
    ev = p.events
    for i in range(5):                                     # doing 20 min, the review wait 2 h, reviewing 10 min
        t = T0 + i
        for name, dt in (("planned", 0), ("started", 10), ("submitted", 10 + MEDIAN), ("picked", 10 + MEDIAN + 7200),
                         ("done", 10 + MEDIAN + 7800)):
            ev.add(f"ticket.{name}", item=f"ticket/old{i}", at=t + dt)
    for i in range(12):
        ev.add("ticket.planned", item=f"ticket/n{i:03}", at=T0 + 9000)
    now = T0 + 10_000
    lanes = etamodel.capacities(p, {"at": now})
    assert lanes["reviewer"]["lanes"] == 1 and lanes["worker"]["lanes"] == 6
    g = pr.build(p.events, p.model.spec, ["ticket"], now, now - 3600, lanes=lanes)
    b = bars(g)
    assert g["end"] - now == pytest.approx(4 * 3600 + 1200)
    assert max(seg[3] for seg in b) == pytest.approx(g["end"])
    assert sum(1 for seg in b if seg[1] == "review") == 12 and all(len(seg) == 4 for seg in b if seg[1] == "review")
    # (the wait: no block's lane; the first ticket's take at its median end, the others' later, the lane busy)
    laned = [s for s in b if len(s) == 6]
    assert most_at_once([s for s in laned if s[4] == "reviewer"]) == 1 and most_at_once([s for s in laned if s[4] == "worker"]) == 6
    for x in (x for x in g["items"] if x.get("projected")):                 # each one's take after its median wait
        segs = {s[0]: s for s in x["projected"]}
        assert segs["reviewing"][1] - segs["doing"][2] >= 7200 - 1e-6 and segs["review"][2] == segs["reviewing"][1]


@pytest.mark.serial
def test_levelling_600_items_is_quick():
    """The levelling alone, 600 items (chains of 5) on a block of 6: under 50 ms (the best of three)."""
    d = {f"i{n:03}": 600.0 + n % 7 * 60 for n in range(600)}
    edges = [(f"i{n - 1:03}", f"i{n:03}") for n in range(600) if n % 5]
    plan = pr.cpm(d, edges)
    steps = {n: [("b", [("doing", x)])] for n, x in d.items()}
    best = float("inf")
    for _ in range(3):
        t = time.perf_counter()
        got = pr.level(steps, edges, [], plan, {"b": 6})
        best = min(best, time.perf_counter() - t)
    assert len(got) == 600 and best < 0.05, best


def record(tmp_path, dep_at: str) -> Project:
    """Finished gaps (100 s doing, 100 s review, 300 s approved); gap/a moved to ``dep_at``; gap/b depends on it."""
    p = project(tmp_path, GAPS)
    ev = p.events
    for n in range(3):
        g = f"gap/old{n}"
        for e, dt in (("opened", 0), ("started", 10), ("reviewed", 110), ("approved", 210), ("merged", 510)):
            ev.add(f"gap.{e}", item=g, at=T0 + dt + n)
    t = T0 + 1000
    ev.add("gap.opened", item="gap/a", at=t)
    for e in ("started", "reviewed", "approved") + (("failed",) if dep_at == "fix" else ()):
        t += 1
        ev.add(f"gap.{e}", item="gap/a", at=t)
    ev.add("gap.opened", item="gap/b", data={"depends_on": "gap/a"}, at=t + 1)
    return p


def taken(p) -> list[str]:
    spec, b = p.model.spec, p.model.spec.blocks["dev"]
    got = [i for i in its.project(p.events, spec, "gap") if i.state in b.takes.at]
    return [i.id for i in unblocked(SimpleNamespace(p=p, spec=spec), b, got)]


def test_starts_at_lets_a_dependent_start_on_an_approved_target(tmp_path):
    p = record(tmp_path, "approved")
    assert p.model.spec.items["gap"].relations["depends_on"].starts_at == ["approved"]
    assert taken(p) == ["gap/b"]
    pr._CACHE.clear()
    assert taken(record(tmp_path / "fix", "fix")) == []                 # its dependency in fix: not taken


def test_starts_at_leaves_the_critical_path_finish_to_start(tmp_path):
    p = record(tmp_path, "approved")
    now = T0 + 1010
    g = pr.build(p.events, p.model.spec, ["gap"], now, now)
    by = {x["id"]: x for x in g["items"]}
    assert by["gap/b"]["status"] == "unblocked" and by["gap/b"]["waiting"] == []
    assert by["gap/a"]["ef"] - now == pytest.approx(293)               # 300 s in approved, 7 s of it gone
    assert by["gap/b"]["es"] - now == pytest.approx(293)               # the dependent is projected after it ends
    assert g["critical"] == ["gap/a", "gap/b"]
    assert g["projections"][0]["relations"]["depends_on"]["starts_at"] == ["approved"]
    q = record(tmp_path / "fix", "fix")
    by = {x["id"]: x for x in pr.build(q.events, q.model.spec, ["gap"], now, now)["items"]}
    assert by["gap/b"]["status"] == "blocked" and by["gap/b"]["waiting"] == ["gap/a"]


def test_a_leased_target_counts_by_the_state_it_was_taken_from(tmp_path):
    p = record(tmp_path, "approved")
    ev, spec = p.events, p.model.spec
    ev.add("gap.opened", item="gap/c", at=T0 + 1010)
    ev.add("gap.opened", item="gap/d", data={"depends_on": "gap/c"}, at=T0 + 1011)
    for it, block, back in (("gap/a", "queue", "approved"), ("gap/c", "dev", "ready")):
        ev.add("ergostat.lease.taken", item=it, source="ergostat", data={"item": it, "run": f"r-{it}", "block": block,
               "fence": 1, "ttl": 300, "max": 1, "back": back, "tier": "program", "attempt": 1})
    got = {i.id: i for i in its.project(ev, spec, "gap")}
    assert got["gap/a"].state == got["gap/c"].state == "leased"
    assert taken(p) == ["gap/b"]                       # held from approved: still approved; held from ready: blocks
    now = T0 + 1020
    by = {x["id"]: x for x in pr.build(ev, spec, ["gap"], now, now)["items"]}
    assert (by["gap/b"]["status"], by["gap/d"]["status"], by["gap/d"]["waiting"]) == ("unblocked", "blocked", ["gap/c"])
    assert its.related(ev, spec, got["gap/b"], spec.items["gap"])["waiting"] == []
    assert its.related(ev, spec, got["gap/d"], spec.items["gap"])["waiting"] == ["gap/c"]


@pytest.mark.parametrize("dep_at, waits", [("approved", []), ("fix", ["gap/a"])])
def test_starts_at_in_the_items_api_and_past_the_graph(tmp_path, monkeypatch, dep_at, waits):
    p = record(tmp_path, dep_at)
    spec = p.model.spec
    b = next(i for i in its.project(p.events, spec, "gap") if i.id == "gap/b")
    rel = its.related(p.events, spec, b, spec.items["gap"])
    assert rel["waiting"] == waits and rel["relations"]["depends_on"]["starts_at"] == ["approved"]
    monkeypatch.setattr(pr, "_cached", lambda *a: {"items": []})      # gap/b past the graph's caps: read alone
    assert taken(p) == ([] if waits else ["gap/b"])
