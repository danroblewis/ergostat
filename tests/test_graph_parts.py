"""The Items page's Graph draws every dependency of the unfinished work (graph_parts.py, relations.js ``rgModel``):
the items of the kinds asked, what they wait on and their parents, never a record that only names one (a review of a
gap); past the bound, whole connected groups, so no line is cut in half. On a generated answer of the factory's shape:
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
        items.append({"id": a, "kind": "gap", "state": "merged", "status": "done", "first": t0 + i, "group": None})
    open_ = [f"gap/o{i}" for i in range(n_open)]
    for i, a in enumerate(open_):
        st = "active" if i < 15 else "unblocked" if i < 60 else "blocked"
        items.append({"id": a, "kind": "gap", "state": "todo", "status": st, "first": t0 + 1000 + i,
                      "es": t0 + 5000 + i, "group": None})
        if i >= 60:
            edges.append({"from": open_[rnd.randrange(i)], "to": a, "rel": "depends_on", "kind": "precedence"})
        elif i < 25:
            edges.append({"from": done[rnd.randrange(n_done)], "to": a, "rel": "depends_on", "kind": "precedence"})
    for i in range(n_reviews):
        r = f"review/r{i}"
        items.append({"id": r, "kind": "review", "state": "merge", "status": "active", "first": t0 + 2000 + i,
                      "group": None})
        edges.append({"from": r, "to": open_[rnd.randrange(n_open)], "rel": "of", "kind": "other"})
    kinds = [{"name": "gap", "asked": True}, {"name": "review", "asked": False}]
    return {"items": items, "edges": edges, "kinds": kinds, "asked": ["gap"]}


def drawn(ans: dict, bound: int = NODES) -> tuple[set, set, int]:
    """What rgModel draws of a marked answer, frontier on, nothing collapsed: (its scope, the items drawn, the
    dependency lines not drawn). The same rule as relations.js: the asked kinds' unfinished items and what they wait
    on, their parents; past the bound, whole parts in their order while they fit."""
    by = {x["id"]: x for x in ans["items"]}
    asked = {k["name"] for k in ans["kinds"] if k.get("asked")}
    preds: dict[str, list[str]] = {}
    for e in ans["edges"]:
        if e["kind"] == "precedence":
            preds.setdefault(e["to"], []).append(e["from"])
    scope: set[str] = set()
    todo = [x["id"] for x in ans["items"] if x["kind"] in asked and x["status"] != "done"]
    while todo:
        a = todo.pop()
        if a in by and a not in scope:
            scope.add(a)
            todo += preds.get(a, [])
    scope |= {by[a]["group"] for a in list(scope) if by[a].get("group") in by}
    keep = scope
    if len(scope) > bound:
        size: dict[int, int] = {}
        for a in scope:
            size[by[a]["part"]] = size.get(by[a]["part"], 0) + 1
        room, kept = bound, set()
        for p in sorted(size):
            if size[p] <= room:
                kept.add(p)
                room -= size[p]
        keep = {a for a in scope if by[a]["part"] in kept}
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
    unfinished = {a for a, x in by.items() if x["kind"] == "gap" and x["status"] != "done"}
    assert len(unfinished) == 375 and unfinished <= keep and lost == 0
    assert all(e["from"] in keep and e["to"] in keep for e in into)
    assert len(keep) <= NODES


def test_a_review_record_is_not_drawn():
    ans = graph_parts.mark(factory_answer())
    reviews = [x for x in ans["items"] if x["kind"] == "review"]
    assert len(reviews) == 340 and all("part" not in x for x in reviews)   # active, but it only names a gap
    assert not any(a.startswith("review/") for a in drawn(ans)[1])


def test_another_kind_is_drawn_when_waited_on_or_a_parent():
    t = 1_700_000_000.0
    ans = graph_parts.mark({
        "kinds": [{"name": "gap", "asked": True}, {"name": "review", "asked": False}, {"name": "epic", "asked": False}],
        "items": [{"id": "gap/a", "kind": "gap", "status": "blocked", "first": t, "group": "epic/e"},
                  {"id": "review/w", "kind": "review", "status": "active", "first": t, "group": None},
                  {"id": "review/n", "kind": "review", "status": "active", "first": t, "group": None},
                  {"id": "epic/e", "kind": "epic", "status": "active", "first": t, "group": "epic/top"},
                  {"id": "epic/top", "kind": "epic", "status": "active", "first": t, "group": None}],
        "edges": [{"from": "review/w", "to": "gap/a", "kind": "precedence", "rel": "after"},
                  {"from": "review/n", "to": "gap/a", "kind": "other", "rel": "of"}]})
    part = {x["id"]: x.get("part") for x in ans["items"]}
    assert part["review/n"] is None                           # it names the gap: not drawn
    assert part["gap/a"] == part["review/w"] == part["epic/e"] == part["epic/top"] == 0


def test_with_no_kind_asked_every_item_is_drawable():
    ans = graph_parts.mark({"kinds": [{"name": "gap"}], "edges": [],
                            "items": [{"id": "gap/a", "kind": "gap", "status": "done", "first": 1.0}]})
    assert ans["items"][0]["part"] == 0


def test_a_status_not_known_ranks_last():
    ans = graph_parts.mark({"kinds": [{"name": "gap", "asked": True}], "edges": [],
                            "items": [{"id": "gap/a", "kind": "gap", "status": None, "first": 1.0},
                                      {"id": "gap/b", "kind": "gap", "status": "done", "first": 2.0}]})
    assert [x["part"] for x in ans["items"]] == [1, 0]


def test_a_cut_past_the_bound_keeps_whole_groups_active_work_first():
    ans = graph_parts.mark(factory_answer(n_open=1200, seed=11))
    by = {x["id"]: x for x in ans["items"]}
    scope, keep, lost = drawn(ans)
    assert len(scope) > NODES and 0 < len(keep) <= NODES
    preds = [(e["from"], e["to"]) for e in ans["edges"] if e["kind"] == "precedence"]
    for a, b in preds:                                # a drawn item's dependency is drawn, both ways
        assert (a in keep) == (b in keep), (a, b)
    crossing = sum(1 for a, b in preds if b in scope and not (a in keep and b in keep))
    assert lost == crossing > 0                       # and every line not drawn is counted for the note
    active = {a for a, x in by.items() if x["kind"] == "gap" and x["status"] == "active"}
    assert len(active) == 15 and active <= keep       # the groups with active work, kept
    ranks = sorted({by[a]["part"] for a in keep})
    first = {by[a]["part"] for a in keep if by[a]["status"] in ("active", "unblocked")}
    assert min(ranks) == 0 and first


MODEL = """
items:
  epic:
    id: epic/*
    states: [planned, underway, shipped]
    on: {epic.started: underway, epic.shipped: shipped}
  ticket:
    id: ticket/*
    states: [todo, doing, done]
    on: {ticket.started: doing, ticket.done: done}
    relations:
      blocked_by: ticket
      parent: epic
  note:
    id: note/*
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
    ans = relations_api.graph(p, m, {"at": now, "window": 3600}, {"kinds": ["ticket"]})
    part = {x["id"]: x.get("part") for x in ans["items"]}
    assert "note/x" in part and part["note/x"] is None            # in the answer (a relation reaches it), not drawn
    assert part["ticket/1"] == part["ticket/2"] == part["epic/a"] == 0
