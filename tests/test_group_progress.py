"""milestone-progress-per-group (dev/records/milestone-progress-per-group.md): each milestone's progress, counted from
the item index (ergostat/spec/grouptally.py) over a hand-worked record of the factory's own gap and milestone kinds
(compiled from ergostat.yaml): done, in progress, waiting, stopped, of its total; a split gap counted as its parts, a
gap closed as a duplicate (or with no end said) leaving the total, a parked one stopped; each row's link the set of
exactly its gaps; the answer a category-by-stack table any chart reads (`/api/items-groups`); and
`milestones.py status` saying it."""

from __future__ import annotations

import json
import re
import sys
import textwrap
import urllib.error
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat.spec import grouptally as gt
from ergostat.spec import item_sets, read
from ergostat.spec.item_sets import BadSet
from ergostat.store import Project
from tests.ports import free_port
from tests.test_factory import BIN, ROOT

T0 = 1_700_000_000.0


def factory_text() -> str:
    text = (ROOT / "ergostat.yaml").read_text()
    kinds = text[text.index("\n  gap:\n"):text.index("\n  review:\n")]
    said = text[text.index("\nmessages:\n"):text.index("\nagents:\n")]
    done, paused = (", ".join(re.findall(r"\b(?:gap|milestone): \[[^\]]*\]", said.split(f"  {k}:")[1].split("\n  ")[0]))
                    for k in ("done", "paused"))
    return f"name: t\nitems:{kinds}\nmessages:\n  done: {{{done}}}\n  paused: {{{paused}}}\n"


def project(tmp_path, text: str) -> Project:
    (tmp_path / "m").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "m" / "ergostat.yaml").write_text(text)
    m = mdl.load(tmp_path / "m")
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m, directory=tmp_path / "state")


# the hand-worked record: each gap, its milestone, its events, and what it counts as (by hand, from the definition)
GAPS = {
    "a1": ("milestone/m-a", ["gap.merged"], {}, "done"),
    "a2": ("milestone/m-a", ["gap.closed"], {"end": "done"}, "done"),             # done on main already: done work
    "a3": ("milestone/m-a", ["gap.closed"], {"end": "duplicate", "duplicates": ["gap/a1"]}, "left"),
    "a4": ("milestone/m-a", ["gap.closed"], {}, "left"),                          # no end said: not known as done work
    "a5": ("milestone/m-a", ["gap.started", "gap.parked"], {}, "stopped"),
    "a6": ("milestone/m-a", ["gap.started"], {}, "in progress"),
    "a7": ("milestone/m-a", [], {}, "waiting"),
    "a8": ("milestone/m-a", ["gap.started", "gap.built", "gap.review-started"], {}, "in progress"),
    "s": ("milestone/m-a", ["gap.split"], {}, "split"),                           # its work is its parts'
    "s-1": ("milestone/m-a", ["gap.started", "gap.merged"], {"parent": ["gap/s"]}, "done"),
    "s-2": ("milestone/m-a", [], {"parent": ["gap/s"]}, "waiting"),
    "s-3": (None, [], {"parent": ["gap/s"]}, "waiting"),                          # a part in no milestone: in none
    "b1": ("milestone/m-b", [], {}, "waiting"),
    "c1": ("milestone/m-c", ["gap.merged"], {}, "done"),
    "l1": ("release-1", ["gap.started"], {}, "in progress"),                     # an old label, no milestone item
    "n1": (None, [], {}, "waiting"),
    "n2": (None, ["gap.merged"], {}, "done"),
    "n3": ("", ["gap.started", "gap.parked"], {}, "stopped"),                      # an empty name is none
    "o1": (["milestone/m-a"], [], {}, "odd"),                                     # not one id: no where= names it
}


@pytest.fixture
def rec(tmp_path):
    p = project(tmp_path, factory_text())
    ev = p.events
    t = T0
    for mid, moves, deps in (("m-a", ["milestone.activated"], []), ("m-b", [], ["milestone/m-a"]),
                             ("m-c", ["milestone.activated", "milestone.completed"], []), ("m-empty", [], [])):
        ev.add("milestone.added", item=f"milestone/{mid}", data={"title": mid.upper(), "depends_on": deps}, at=t)
        for e in moves:
            t += 10
            ev.add(e, item=f"milestone/{mid}", at=t)
    for name, (ms, moves, fields, _) in GAPS.items():
        t += 10
        ev.add("gap.found", item=f"gap/{name}", data={**({} if ms is None else {"milestone": ms}), **fields}, at=t)
        for e in moves:
            t += 10
            ev.add(e, item=f"gap/{name}", data=fields if e == "gap.closed" else {}, at=t)
    p.t_end, p.tmp = t, tmp_path
    return p


def answer(p, **kw):
    now = p.t_end + 100
    return gt.progress(p.events, p.model.spec, "gap", "milestone", now, kw.pop("since", T0 - 100), **kw)


def by_hand(row_id):
    out = {"done": 0, "in progress": 0, "waiting": 0, "stopped": 0, "left": 0, "split": 0}
    for ms, _, _, said in GAPS.values():
        if (ms or None) == row_id and said != "odd":
            out[said if said != "split" else "split"] += 1
    return out


def test_a_hand_worked_record_gives_the_right_counts_per_milestone(rec):
    """Done item 1: split, closed-as-duplicate (and closed with no end), parked, an old label and none, each by hand."""
    got = answer(rec)
    rows = {r["id"]: r for r in got["rows"]}
    assert [r["id"] for r in got["rows"]] == ["milestone/m-a", "milestone/m-empty", "milestone/m-b", "milestone/m-c",
                                              "release-1", None]      # active first; old labels, then none, last
    for rid, r in rows.items():
        want = by_hand(rid)
        assert r["counts"] == {k: want[k] for k in gt.STACKS}, rid
        assert (r["left"], r["summaries"]) == (want["left"], want["split"]), rid
        assert r["total"] == sum(want[k] for k in gt.STACKS), rid
    a = rows["milestone/m-a"]
    assert a["counts"] == {"done": 3, "in progress": 2, "waiting": 2, "stopped": 1} and a["total"] == 8
    assert (a["left"], a["summaries"], a["state"], a["status"], a["waits_on"]) == (2, 1, "active", "active", [])
    b = rows["milestone/m-b"]
    assert (b["state"], b["status"], b["waits_on"], b["total"]) == ("waiting", "blocked", ["milestone/m-a"], 1)
    assert (rows["milestone/m-c"]["state"], rows["milestone/m-c"]["counts"]["done"]) == ("completed", 1)
    assert rows["milestone/m-empty"]["total"] == 0 and rows["milestone/m-empty"]["item"]
    assert not rows["release-1"]["item"] and rows["release-1"]["counts"]["in progress"] == 1
    assert rows[None]["counts"] == {"done": 1, "in progress": 0, "waiting": 2, "stopped": 1}
    assert (got["odd_n"], got["odd"]) == (1, ["gap/o1"])
    counted = sum(r["total"] + r["left"] + r["summaries"] for r in got["rows"]) + got["odd_n"]
    assert counted == len(GAPS)                                                # every gap once


def test_a_milestones_completion_over_time_comes_from_the_moves(rec):
    """Each row's done count at each moment: none before its gaps finished, its done count by the end."""
    got = answer(rec, points=5)
    rows = {r["id"]: r for r in got["rows"]}
    assert len(got["times"]) == 5 and got["times"][-1] == rec.t_end + 100
    assert rows["milestone/m-a"]["done"][0] == 0 and rows["milestone/m-a"]["done"][-1] == 3
    assert rows[None]["done"][-1] == 1 and rows["milestone/m-empty"]["done"] == [0] * 5
    assert all(a <= b for a, b in zip(rows["milestone/m-a"]["done"], rows["milestone/m-a"]["done"][1:], strict=False))


def test_a_milestones_row_links_to_exactly_its_gaps(rec):
    """Done item 2: each row's params, read as the Items page reads its address, are exactly the gaps naming it."""
    got = answer(rec)
    for r in got["rows"]:
        s = item_sets.parse(r["params"])
        listed = {i["id"] for i in item_sets.select(rec.events, rec.model.spec, s)["items"]}
        want = {f"gap/{n}" for n, (ms, *_) in GAPS.items() if isinstance(ms, str | None) and (ms or None) == r["id"]}
        assert listed == want, r["id"]
        assert len(listed) == r["total"] + r["left"] + r["summaries"], r["id"]


def test_what_is_not_one_is_refused(rec):
    with pytest.raises(BadSet, match="not a group relation"):
        gt.progress(rec.events, rec.model.spec, "gap", "parent", T0, T0 - 1)     # (parent folds as a set of ids)
    with pytest.raises(BadSet, match="no such kind"):
        gt.progress(rec.events, rec.model.spec, "nothing", "milestone", T0, T0 - 1)
    for bad in ("1", "201", "x", "²"):
        with pytest.raises(BadSet, match="points="):
            gt.progress(rec.events, rec.model.spec, "gap", "milestone", T0, T0 - 1, bad)


def test_past_its_bound_it_is_refused_never_cut(rec, monkeypatch):
    """More gaps than it reads: refused, never counts from part of them; as many as it reads, answered."""
    monkeypatch.setattr(gt, "MOST", len(GAPS))
    assert answer(rec, since=T0 - 50)["rows"]
    monkeypatch.setattr(gt, "MOST", len(GAPS) - 1)
    with pytest.raises(BadSet, match="gap: more than"):
        answer(rec, since=T0 - 60)                                               # (another window: not the cached one)


def test_done_when_is_a_groups_map_of_its_states(tmp_path):
    base = """
    items:
      epic: {id: epic/*, states: [open, done]}
      ticket:
        id: ticket/*
        states: [open, done, dropped]
        relations:
          epic: {kind: epic, group: true, done_when: %s}
        fold: {epic: replace}
    """
    for ok, v in ((True, "{done: {why: [fixed, shipped]}}"), (False, "{nowhere: {why: x}}"), (False, "{done: {}}"),
                  (False, "{done: {why: {a: 1}}}"), (False, "[done]"), (False, "null"), (False, "[]"),
                  (False, "false"), (False, "0"), (False, '""'), (False, "{}")):
        d = tmp_path / str(len(list(tmp_path.iterdir())))
        d.mkdir()
        (d / "ergostat.yaml").write_text(textwrap.dedent(base % v))
        _, problems = read(d / "ergostat.yaml")                       # refused at the key: never a crash
        errors = [str(x) for x in problems if x.level == "error"]
        assert (not errors) is ok, (v, errors)
        assert ok or any("done_when" in e for e in errors), (v, errors)


TICKETS = """
name: t
items:
  epic:
    id: epic/*
    states: [open, doing, done]
    on: {epic.started: doing, epic.done: done}
  ticket:
    id: ticket/*
    states: [todo, doing, done]
    on: {ticket.started: doing, ticket.done: done}
    relations:
      epic: {kind: epic, group: true}
    fold: {epic: replace}
messages:
  done: {epic: [done], ticket: [done]}
"""


def test_a_dashboard_panel_charts_any_kind_by_its_group_stacked_by_status_group(rec, tmp_path):
    """Done item 4: ``/api/items-groups?kind=K&by=REL`` is a table (rows the categories, ``stacks`` the series) for
    the factory's gaps by milestone and, the same with no code of its own, for any model's group relation: the
    Items listing names the relations it is offered for."""
    from ergostat.web import serve
    (tmp_path / "other").mkdir()
    other = project(tmp_path / "other", TICKETS)
    for i, st in enumerate(("todo", "doing", "done", "done")):
        other.events.add("ticket.planned", item=f"ticket/{i}", data={"epic": "epic/e1" if i else None}, at=T0 + i)
        if st != "todo":
            other.events.add(f"ticket.{'started' if st == 'doing' else 'done'}", item=f"ticket/{i}", at=T0 + 10 + i)
    other.events.add("epic.started", item="epic/e1", at=T0)
    for p, kind, by, want in ((rec, "gap", "milestone", {"milestone/m-a": [3, 2, 2, 1]}),
                              (other, "ticket", "epic", {"epic/e1": [2, 1, 0, 0], None: [0, 0, 1, 0]})):
        server, url = serve(p, free_port())
        try:
            with urllib.request.urlopen(f"{url}/api/items-groups?kind={kind}&by={by}", timeout=30) as r:
                got = json.loads(r.read())
            with urllib.request.urlopen(f"{url}/api/items?kind={kind}", timeout=30) as r:
                listed = json.loads(r.read())
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(f"{url}/api/items-groups?kind={kind}&by=nothing", timeout=30)
            assert e.value.code == 400
        finally:
            server.shutdown()
            server.server_close()
        assert got["stacks"] == ["done", "in progress", "waiting", "stopped"]
        table = {r["id"]: [r["counts"][s] for s in got["stacks"]] for r in got["rows"]}
        assert {k: table[k] for k in want} == want
        assert all(len(r["done"]) == len(got["times"]) for r in got["rows"])     # each category's series over time
        assert next(k for k in listed["kinds"] if k["name"] == kind)["progress"] == [by]


def test_milestones_status_says_each_milestones_progress(rec, monkeypatch):
    """milestones.py status prints each milestone's progress as ergostat counts it, and the gaps naming none."""
    monkeypatch.syspath_prepend(str(BIN))
    for name in ("fac", "milestones"):
        sys.modules.pop(name, None)
    import fac
    import milestones

    def items(kind, state=None):
        from ergostat.spec import items as its
        return [{"id": i.id, "state": i.state, "fields": json.loads(json.dumps(i.fields)), "entered": i.entered}
                for i in its.project(rec.events, rec.model.spec, kind) if state in (None, i.state)]

    def ergostat(*args, check=True):
        from types import SimpleNamespace
        got = answer(rec)
        assert list(args) == ["item", "--kind", "gap", "--groups", "milestone", "--json"]
        return SimpleNamespace(stdout=json.dumps(got), returncode=0)

    monkeypatch.setattr(fac, "items", items)
    monkeypatch.setattr(fac, "ergostat", ergostat)
    cfg = {"paths": {"run": str(rec.tmp / "run"), "live": str(rec.tmp / "live")}, "milestones": {}}
    lines = milestones.status(cfg).splitlines()
    at = lines.index("milestone/m-a  active  M-A")
    assert lines[at + 3] == ("  progress: 3 done, 2 in progress, 2 waiting, 1 stopped, of 8 (2 closed as no work done "
                             "(left the total); 1 split (counted as its parts))")
    at = lines.index("milestone/m-b  waiting  M-B")
    assert lines[at + 3] == "  progress: 0 done, 0 in progress, 1 waiting, 0 stopped, of 1"
    assert "gaps naming no milestone, progress: 1 done, 0 in progress, 2 waiting, 1 stopped, of 4" in lines

    def unset(*a, **k):
        raise FileNotFoundError("ERGOSTAT_CMD is not set")
    monkeypatch.setattr(fac, "ergostat", unset)
    lines = milestones.status(cfg).splitlines()
    assert "progress: not read (ERGOSTAT_CMD is not set)" in lines                # said once, never as zero
    assert not any(ln.startswith(("  progress:", "gaps naming no milestone")) for ln in lines)
