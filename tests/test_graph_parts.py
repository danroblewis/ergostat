"""The Items page's Graph draws every dependency of the unfinished work (graph_parts.py, relations.js ``rgModel``):
the items of the kinds asked, what they wait on and their parents, never a record that only names one (a review of a
gap); past the bound, whole connected groups (precedence links), and only the first that does not fit cut inside,
by status, with every line left out counted. On a generated answer of the factory's shape:
about 375 unfinished gaps, 340 dependency lines into them, 340 review records. The page's own ``rgModel`` is run on
the same answer in tests/test_items_page.py (the browser suite); these hold without a browser."""

from __future__ import annotations

import random
import textwrap
import time

from ergostat import model as mdl
from ergostat.store import Project
from ergostat.web import graph_parts, relations_api

NODES = 600                              # relations.js RG.NODES


def factory_answer(n_open: int = 375, n_done: int = 80, n_reviews: int = 340, seed: int = 7) -> dict:
    """An ``/api/items-graph`` answer shaped like the factory's, kind ``gap`` asked: the first 15 unfinished gaps
    active, the next 45 unblocked (25 of them after a finished gap), the rest each waiting on an earlier unfinished
    gap (chains and fans); reviews of gaps, every one active (a review in ``merge``), each naming a gap."""
    rnd = random.Random(seed)
    t0 = 1_700_000_000.0
    items, edges = [], []
    done = [f"gap/d{i}" for i in range(n_done)]
    for i, a in enumerate(done):
        items.append({"id": a, "projection": "gap", "state": "merged", "status": "done", "first": t0 + i, "group": None})
    open_ = [f"gap/o{i}" for i in range(n_open)]
    for i, a in enumerate(open_):
        st = "active" if i < 15 else "unblocked" if i < 60 else "blocked"
        items.append({"id": a, "projection": "gap", "state": "todo", "status": st, "first": t0 + 1000 + i,
                      "es": t0 + 5000 + i, "group": None})
        if i >= 60:
            edges.append({"from": open_[rnd.randrange(i)], "to": a, "rel": "depends_on", "kind": "precedence"})
        elif i < 25:
            edges.append({"from": done[rnd.randrange(n_done)], "to": a, "rel": "depends_on", "kind": "precedence"})
    for i in range(n_reviews):
        r = f"review/r{i}"
        items.append({"id": r, "projection": "review", "state": "merge", "status": "active", "first": t0 + 2000 + i,
                      "group": None})
        edges.append({"from": r, "to": open_[rnd.randrange(n_open)], "rel": "of", "kind": "other"})
    kinds = [{"name": "gap", "asked": True}, {"name": "review", "asked": False}]
    return {"items": items, "edges": edges, "projections": kinds, "asked": ["gap"]}


def drawn(ans: dict, bound: int = NODES) -> tuple[set, set, int]:
    """What rgModel draws of a marked answer, frontier on, nothing collapsed: (its scope, the items drawn, the
    dependency lines not drawn). The same rule as relations.js: the asked kinds' unfinished items and what they wait
    on, their parents; past the bound, whole parts in their order, each with its parents, and the first part that
    does not fit cut inside by status."""
    by = {x["id"]: x for x in ans["items"]}
    asked = {k["name"] for k in ans["projections"] if k.get("asked")}
    preds: dict[str, list[str]] = {}
    for e in ans["edges"]:
        if e["kind"] == "precedence":
            preds.setdefault(e["to"], []).append(e["from"])
    scope: set[str] = set()
    todo = [x["id"] for x in ans["items"] if x["projection"] in asked and x["status"] != "done"]
    while todo:
        a = todo.pop()
        if a in by and a not in scope:
            scope.add(a)
            todo += preds.get(a, [])
    for a in list(scope):
        g = by[a].get("group")
        while g in by and g not in scope:
            scope.add(g)
            g = by[g].get("group")
    keep = set(scope)
    if len(scope) > bound:
        groups: dict[int, list[str]] = {}
        for a in scope:
            groups.setdefault(by[a]["part"], []).append(a)
        keep = set()

        def up(a: str | None) -> list[str]:          # an item and its parents not yet kept
            out: list[str] = []
            while a in scope and a not in keep and a not in out:
                out.append(a)
                a = by[a].get("group")
            return out
        room = bound
        for p in sorted(groups):
            need = {b for a in groups[p] for b in up(a)}
            if len(need) <= room:
                keep |= need
                room -= len(need)
                continue
            for a in sorted(groups[p], key=lambda a: (graph_parts.ORDER.index(by[a]["status"]),
                                                       by[a].get("es") or by[a].get("first") or 0.0, a)):
                n = up(a)
                if len(n) <= room:
                    keep.update(n)
                    room -= len(n)
            break
    lost = sum(1 for a in scope for p in preds.get(a, []) if p in scope and not (a in keep and p in keep))
    return scope, keep, lost


def test_no_dependency_line_of_an_unfinished_gap_is_lost():
    ans = graph_parts.mark(factory_answer())
    by = {x["id"]: x for x in ans["items"]}
    into = [e for e in ans["edges"] if e["kind"] == "precedence" and by[e["to"]]["status"] != "done"]
    assert len(into) == 340
    for e in into:                                    # both ends drawable, in one part: no cut can separate them
        assert "part" in by[e["from"]] and by[e["from"]]["part"] == by[e["to"]]["part"], e
    scope, keep, lost = drawn(ans)
    unfinished = {a for a, x in by.items() if x["projection"] == "gap" and x["status"] != "done"}
    assert len(unfinished) == 375 and unfinished <= keep and lost == 0
    assert all(e["from"] in keep and e["to"] in keep for e in into)
    assert len(keep) <= NODES


def test_a_review_record_is_not_drawn():
    ans = graph_parts.mark(factory_answer())
    reviews = [x for x in ans["items"] if x["projection"] == "review"]
    assert len(reviews) == 340 and all("part" not in x for x in reviews)   # active, but it only names a gap
    assert not any(a.startswith("review/") for a in drawn(ans)[1])


def test_another_kind_is_drawn_when_waited_on_or_a_parent():
    t = 1_700_000_000.0
    ans = graph_parts.mark({
        "projections": [{"name": "gap", "asked": True}, {"name": "review", "asked": False}, {"name": "epic", "asked": False}],
        "items": [{"id": "gap/a", "projection": "gap", "status": "blocked", "first": t, "group": "epic/e"},
                  {"id": "review/w", "projection": "review", "status": "active", "first": t, "group": None},
                  {"id": "review/n", "projection": "review", "status": "active", "first": t, "group": None},
                  {"id": "epic/e", "projection": "epic", "status": "active", "first": t, "group": "epic/top"},
                  {"id": "epic/top", "projection": "epic", "status": "active", "first": t, "group": None}],
        "edges": [{"from": "review/w", "to": "gap/a", "kind": "precedence", "rel": "after"},
                  {"from": "review/n", "to": "gap/a", "kind": "other", "rel": "of"}]})
    part = {x["id"]: x.get("part") for x in ans["items"]}
    assert part["review/n"] is None                           # it names the gap: not drawn
    assert part["gap/a"] == part["review/w"]                  # waited on: one part with the gap
    assert None not in (part["epic/e"], part["epic/top"])     # parents: drawable, but a parent link joins nothing
    assert len({part["gap/a"], part["epic/e"], part["epic/top"]}) == 3


def test_with_no_kind_asked_every_item_is_drawable():
    ans = graph_parts.mark({"projections": [{"name": "gap"}], "edges": [],
                            "items": [{"id": "gap/a", "projection": "gap", "status": "done", "first": 1.0}]})
    assert ans["items"][0]["part"] == 0


def test_a_status_not_known_ranks_last():
    ans = graph_parts.mark({"projections": [{"name": "gap", "asked": True}], "edges": [],
                            "items": [{"id": "gap/a", "projection": "gap", "status": None, "first": 1.0},
                                      {"id": "gap/b", "projection": "gap", "status": "done", "first": 2.0}]})
    assert [x["part"] for x in ans["items"]] == [1, 0]


def cut_parts(ans: dict, scope: set, keep: set) -> set:
    """The parts the cut drew only some of."""
    by = {x["id"]: x for x in ans["items"]}
    return {by[a]["part"] for a in keep} & {by[a]["part"] for a in scope - keep}


def unreported(ans: dict, scope: set, keep: set, lost: int) -> int:
    """How many lines with a drawn end the note's count misses: each drawn item's dependency in the scope, not drawn,
    and each line of an item not drawn, must be in ``lost``."""
    preds = [(e["from"], e["to"]) for e in ans["edges"] if e["kind"] == "precedence"]
    return sum(1 for a, b in preds if b in scope and a in scope and not (a in keep and b in keep)) - lost


def test_a_cut_past_the_bound_keeps_whole_groups_active_work_first():
    ans = graph_parts.mark(factory_answer(n_open=1200, seed=11))
    by = {x["id"]: x for x in ans["items"]}
    scope, keep, lost = drawn(ans)
    assert len(scope) > NODES and 0 < len(keep) <= NODES
    cut = cut_parts(ans, scope, keep)
    assert len(cut) <= 1                              # at most one group cut inside, the first that does not fit
    preds = [(e["from"], e["to"]) for e in ans["edges"] if e["kind"] == "precedence"]
    for a, b in preds:                                # elsewhere a drawn item's dependency is drawn, both ways
        if by[b]["part"] not in cut:
            assert (a in keep) == (b in keep), (a, b)
    assert lost > 0 and unreported(ans, scope, keep, lost) == 0   # every line not drawn is counted for the note
    active = {a for a, x in by.items() if x["projection"] == "gap" and x["status"] == "active"}
    assert len(active) == 15 and active <= keep       # the groups with active work, kept
    left = {by[a]["part"] for a in scope - keep} - cut
    assert all(p > q for p in left for q in {by[a]["part"] for a in keep})   # only lower-ranked groups left out


def fan_answer() -> dict:
    """One group of 701 (700 gaps, 20 active and 20 unblocked, all waiting on one paused root) and 3 paused gaps."""
    t = 1_700_000_000.0
    items = [{"id": "gap/root", "projection": "gap", "status": "paused", "first": t, "group": None}]
    edges = []
    for i in range(700):
        st = "active" if i < 20 else "unblocked" if i < 40 else "blocked"
        items.append({"id": f"gap/f{i:03}", "projection": "gap", "status": st, "first": t + i, "group": None})
        edges.append({"from": "gap/root", "to": f"gap/f{i:03}", "kind": "precedence", "rel": "after"})
    items += [{"id": f"gap/p{i}", "projection": "gap", "status": "paused", "first": t, "group": None} for i in range(3)]
    return {"items": items, "edges": edges, "projections": [{"name": "gap", "asked": True}]}


def epic_answer() -> dict:
    """600 active gaps under one paused epic (a parent link, no dependency), and 3 paused gaps."""
    t = 1_700_000_000.0
    items = [{"id": "gap/epic", "projection": "gap", "status": "paused", "first": t, "group": None}]
    items += [{"id": f"gap/t{i:03}", "projection": "gap", "status": "active", "first": t + i, "group": "gap/epic"}
              for i in range(600)]
    items += [{"id": f"gap/p{i}", "projection": "gap", "status": "paused", "first": t, "group": None} for i in range(3)]
    return {"items": items, "edges": [], "projections": [{"name": "gap", "asked": True}]}


def test_a_group_bigger_than_the_bound_is_cut_by_status_not_dropped():
    ans = graph_parts.mark(fan_answer())
    by = {x["id"]: x for x in ans["items"]}
    assert len({by[f"gap/f{i:03}"]["part"] for i in range(700)} | {by["gap/root"]["part"]}) == 1
    scope, keep, lost = drawn(ans)
    assert len(keep) == NODES                         # the big group's most active 600, not the 3 paused
    assert {a for a in by if by[a]["status"] in ("active", "unblocked")} <= keep
    assert not any(a.startswith("gap/p") for a in keep) and "gap/root" not in keep   # the paused root: cut
    assert lost == 700 and unreported(ans, scope, keep, lost) == 0   # 600 drawn waiting on it, 100 not drawn


def test_an_epic_over_more_than_the_bound_draws_its_active_work():
    ans = graph_parts.mark(epic_answer())
    by = {x["id"]: x for x in ans["items"]}
    assert len({x["part"] for x in ans["items"]}) == 604   # a parent link joins nothing
    scope, keep, lost = drawn(ans)
    assert len(keep) == NODES and "gap/epic" in keep            # paused, but drawn with its children
    assert all(by[a]["status"] == "active" for a in keep - {"gap/epic"})
    assert lost == 0


MODEL = """
projections:
  epic:
    match:
      key: epic/*
    states: [planned, underway, shipped]
    events:
      epic.started:
        state: set('underway')
      epic.shipped:
        state: set('shipped')
    otherwise: rest
  ticket:
    match:
      key: ticket/*
    states: [todo, doing, done]
    events:
      ticket.started:
        state: set('doing')
      ticket.done:
        state: set('done')
    otherwise: rest
    relations:
      blocked_by: ticket
      parent: epic
  note:
    match:
      key: note/*
    states: [open]
    relations:
      about: ticket
messages:
  done: {ticket: [done], epic: [shipped]}
"""


def test_the_answer_marks_its_parts(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    p = Project(m)
    now = time.time()
    ev = p.events
    ev.add("epic.planned", item="epic/a", at=now - 50)
    ev.add("ticket.planned", item="ticket/1", data={"parent": "epic/a"}, at=now - 40)
    ev.add("ticket.planned", item="ticket/2", data={"blocked_by": "ticket/1"}, at=now - 30)
    ev.add("note.opened", item="note/x", data={"about": "ticket/2"}, at=now - 20)
    ans = relations_api.graph(p, m, {"at": now, "window": 3600}, {"projections": ["ticket"]})
    part = {x["id"]: x.get("part") for x in ans["items"]}
    assert "note/x" in part and part["note/x"] is None            # in the answer (a relation reaches it), not drawn
    assert part["ticket/1"] == part["ticket/2"] is not None and part["epic/a"] is not None
    assert part["epic/a"] != part["ticket/1"]                     # the parent: drawable, in a part of its own
