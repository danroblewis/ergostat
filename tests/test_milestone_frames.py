"""The Items page's Graph and Timeline show milestones with their gaps (dev/records/milestone-shown-in-the-graph.md):
the generated answer the browser tests run the page's own ``rgModel``, ``relGraph`` and ``relTimeline`` on
(tests/test_items_page.py), and a real record's answer, which must have the shape the generated one assumes: each
gap's milestone a group edge from a kind not asked, and a milestone's dependency a precedence edge between them."""

from __future__ import annotations

import textwrap
import time

from ergostat import model as mdl
from ergostat.store import Project
from ergostat.web import relations_api

T0 = 1_700_000_000.0


def milestone_answer(n_extra: int = 0, per: int = 6) -> dict:
    """An ``/api/items-graph`` answer of the factory's shape, kind ``gap`` asked. Four milestones: ``m0`` completed (its
    six gaps merged), ``m1`` active after it (one leased, one in review, one ready, the rest waiting on earlier ones,
    the first on a gap of ``m0``), ``m2`` waiting on ``m1`` (its gaps waiting on gaps of ``m1``: lines across
    frames), ``m3`` active with a split (``gap/s`` and its sub-gap ``gap/s-1``, which waits on a gap of ``m2``); three
    gaps in no milestone, one waiting on a gap of ``m1``. ``n_extra`` more active milestones of ``per`` gaps each,
    starting later, for the Timeline's bound."""
    items, edges = [], []

    def item(a, kind, state, status, at, waiting=(), title="", done_at=None):
        x = {"id": a, "projection": kind, "state": state, "status": status, "title": title, "first": at, "last": at,
             "group": None, "waiting": list(waiting), "segments": [[state, at, done_at or at + 600]]}
        if status != "done":
            x.update(es=at + 600, ef=at + 1200, projected=[["building", at + 600, at + 1200]])
        items.append(x)
        return x

    def prec(a, b, rel="depends_on"):
        edges.append({"from": a, "to": b, "rel": rel, "kind": "precedence"})

    def member(m, g, rel="milestone"):
        edges.append({"from": m, "to": g, "rel": rel, "kind": "group"})
        by[g]["group"] = by[g]["group"] or m

    ms = [("milestone/m0", "completed", "done", []), ("milestone/m1", "active", "active", []),
          ("milestone/m2", "waiting", "blocked", ["milestone/m1"]), ("milestone/m3", "active", "active", [])]
    ms += [(f"milestone/x{i}", "active", "active", []) for i in range(n_extra)]
    for n, (a, st, status, waits) in enumerate(ms):
        item(a, "milestone", st, status, T0 + n * 100, waits, title=f"release {n}")
    prec("milestone/m0", "milestone/m1")
    prec("milestone/m1", "milestone/m2")
    gaps = {
        "milestone/m0": [(f"gap/d{i}", "merged", "done", []) for i in range(6)],
        "milestone/m1": [("gap/a0", "leased", "active", []), ("gap/a1", "in-review", "queued", []),
                         ("gap/a2", "ready", "unblocked", []), ("gap/a3", "ready", "blocked", ["gap/a0"]),
                         ("gap/a4", "ready", "blocked", ["gap/a3", "gap/a2"])],
        "milestone/m2": [("gap/b0", "ready", "blocked", ["gap/a4"]), ("gap/b1", "ready", "blocked", ["gap/a1"]),
                         ("gap/b2", "ready", "blocked", ["gap/b0"])],
        "milestone/m3": [("gap/s", "split", "active", []), ("gap/s-1", "ready", "blocked", ["gap/b2"]),
                         ("gap/milestones-shown-in-graph-and-timeline", "building", "active", [])],
        None: [("gap/n0", "ready", "unblocked", []), ("gap/n1", "ready", "blocked", ["gap/a2"]),
               ("gap/n2", "merged", "done", [])],
    }
    for i in range(n_extra):
        gaps[f"milestone/x{i}"] = [(f"gap/x{i}-{j}", "ready", "unblocked", []) for j in range(per)]
    by = {}
    at = T0 + 1000
    for m, gs in gaps.items():
        for a, st, status, waits in gs:
            by[a] = item(a, "gap", st, status, at, waits, title=a.split("/")[1] + " work")
            at += 50
            for w in waits:
                prec(w, a)
        for a, *_ in gs:
            if m:
                member(m, a)
    prec("gap/d5", "gap/a0")                                  # from a completed milestone's gap, across frames
    prec("gap/n2", "gap/n0")
    member("gap/s", "gap/s-1", rel="parent")
    by["gap/s-1"]["group"] = "gap/s"                          # its first group may be the split parent
    by["gap/s-1"]["segments"][0][1] = by["gap/s"]["first"] - 10   # the sub-gap started first: the schedule's order is not the tree's
    for e in edges:                                           # what each milestone holds
        if e["kind"] == "group" and e["rel"] == "milestone":
            x = next(x for x in items if x["id"] == e["from"])
            x.setdefault("children", {"total": 0, "done": 0})["total"] += 1
            x["children"]["done"] += by[e["to"]]["status"] == "done"
    kinds = [{"name": "gap", "asked": True, "states": ["ready", "building", "merged"]},
             {"name": "milestone", "asked": False, "states": ["waiting", "active", "completed"]}]
    return {"items": items, "edges": edges, "projections": kinds, "asked": ["gap"], "now": T0 + 2000, "since": T0 - 100,
            "end": T0 + 5000, "critical": [], "cycles": [], "capped": {}, "assumed": None}


MODEL = """
projections:
  gap:
    id: gap/*
    states: [ready, building, merged]
    on: {gap.defined: ready, gap.started: building, gap.merged: merged}
    relations:
      depends_on: gap
      parent: gap
      milestone: {projection: milestone, group: true, precedence: false, inverse: gaps}
  milestone:
    id: milestone/*
    states: [waiting, active, completed]
    on: {milestone.added: waiting, milestone.activated: active, milestone.completed: completed}
    relations:
      depends_on: milestone
messages:
  done: {gap: [merged], milestone: [completed]}
"""


def test_a_real_answer_has_the_shape_the_frames_are_read_from(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    p = Project(m)
    now = time.time()
    ev = p.events
    ev.add("milestone.added", item="milestone/a", at=now - 90)
    ev.add("milestone.added", item="milestone/b", data={"depends_on": "milestone/a"}, at=now - 89)
    ev.add("milestone.activated", item="milestone/a", at=now - 88)
    ev.add("gap.defined", item="gap/1", data={"milestone": "milestone/a"}, at=now - 80)
    ev.add("gap.defined", item="gap/2", data={"milestone": "milestone/b", "depends_on": "gap/1"}, at=now - 70)
    ev.add("gap.defined", item="gap/3", data={"milestone": "milestone/b", "parent": "gap/2"}, at=now - 60)
    ev.add("gap.started", item="gap/1", at=now - 50)
    ans = relations_api.graph(p, m, {"at": now, "window": 3600}, {"projections": ["gap"]})
    by = {x["id"]: x for x in ans["items"]}
    kinds = {k["name"]: k.get("asked") for k in ans["projections"]}
    assert kinds["gap"] and not kinds["milestone"]                     # the frame's kind is not asked
    groups = {(e["from"], e["to"], e["rel"]) for e in ans["edges"] if e["kind"] == "group"}
    assert {("milestone/a", "gap/1", "milestone"), ("milestone/b", "gap/2", "milestone"),
            ("milestone/b", "gap/3", "milestone"), ("gap/2", "gap/3", "parent")} <= groups
    prec = {(e["from"], e["to"]) for e in ans["edges"] if e["kind"] == "precedence"}
    assert {("milestone/a", "milestone/b"), ("gap/1", "gap/2")} <= prec
    assert by["milestone/b"]["status"] == "blocked" and by["milestone/b"]["waiting"] == ["milestone/a"]
    assert by["gap/1"]["status"] == "active" and by["gap/2"]["waiting"] == ["gap/1"]
    assert by["milestone/b"]["children"] == {"total": 2, "done": 0}
