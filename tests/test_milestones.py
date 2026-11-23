"""milestone-kind-and-lifecycle: the item kind `milestone` (waiting, active, completed; completed final) and its block,
dev/bin/milestones.py: activation, the limit, completion, a parked gap holding it open, an empty one, no way out of
completed, the upkeep cycle, and the coordinator's refusals. The program runs in process over a record of the
factory's own gap and milestone kinds, as compiled from ergostat.yaml (its `ergostat item` and `event --add` calls
answered from that record)."""

from __future__ import annotations

import fcntl
import json
import sys
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.store import Project
from tests.test_factory import BIN, ROOT

DAY = 86400.0


def kinds_text() -> str:
    text = (ROOT / "ergostat.yaml").read_text()
    return text[text.index("\n  gap:\n"):text.index("\n  review:\n")]


@pytest.fixture
def ms(tmp_path, monkeypatch):
    """The program over a record of its own: ``ms.mod`` (milestones.py), ``ms.p`` (the project), ``ms.cfg``."""
    (tmp_path / "m").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "m" / "ergostat.yaml").write_text("name: t\nitems:" + kinds_text() + "\n")
    p = Project(mdl.load(tmp_path / "m"), directory=tmp_path / "state")
    monkeypatch.syspath_prepend(str(BIN))
    for name in ("fac", "milestones"):
        sys.modules.pop(name, None)
    import fac
    import milestones

    def items(kind, state=None):
        return [{"id": i.id, "state": i.state, "fields": json.loads(json.dumps(i.fields)), "entered": i.entered}
                for i in its.project(p.events, p.model.spec, kind) if state in (None, i.state)]

    def add(event, item, **data):
        p.events.add(event, item=item, data=json.loads(json.dumps(data, default=str)))

    monkeypatch.setattr(fac, "items", items)
    monkeypatch.setattr(fac, "add", add)

    class M:
        mod, cfg = milestones, {"paths": {"run": str(tmp_path / "run"), "live": str(tmp_path / "live")}, "milestones": {}}

        def state(self, iid):
            it = its.one(p.events, p.model.spec, iid)
            return it.state if it else None

        def fields(self, iid):
            return its.one(p.events, p.model.spec, iid).fields

        def gap(self, name, *moves, **fields):
            p.events.add("gap.found", item=f"gap/{name}", data=fields)
            for e in moves:
                p.events.add(e, item=f"gap/{name}")

        def passes(self, now=None):
            return [(e, i) for e, i, _ in milestones.run_pass(self.cfg, now)]
    m = M()
    m.p = p
    return m


def test_the_factory_model_declares_milestones():
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    found = [str(p) for p in problems if "milestone" in str(p).lower() and p.level != "note"]
    assert found == [], "\n".join(found)
    k = spec.items["milestone"]
    assert k.states == ["waiting", "active", "completed"] and set(k.final) == {"completed"}
    assert k.relations["depends_on"].precedence and k.relations["depends_on"].kinds == ["milestone"]
    r = spec.items["gap"].relations["milestone"]
    assert r.group and not r.precedence and r.kinds == ["milestone"] and spec.items["gap"].fold["milestone"] == "replace"
    b = spec.blocks["milestones"]
    assert b.every == 60 and "milestones.py pass" in str(b.params.get("run"))
    assert {"milestones-waiting", "milestones-active", "milestones-completed"} <= set(spec.stocks)


def test_a_final_state_must_be_one_of_its_states(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: t\nitems:\n  x:\n    id: x/*\n    states: [a, b]\n    final: [c]\n")
    _, problems = read(tmp_path / "ergostat.yaml")
    assert [p.code for p in problems if p.level == "error"] == ["bad-final"]


def test_a_waiting_milestone_becomes_active_once_its_dependencies_complete(ms):
    ms.mod.add(ms.cfg, "first")
    ms.mod.add(ms.cfg, "second", depends=["first"])
    assert ms.state("milestone/first") == ms.state("milestone/second") == "waiting"
    assert ms.passes() == [("milestone.activated", "milestone/first")]      # second waits on first
    assert ms.state("milestone/second") == "waiting"
    ms.gap("a", "gap.merged", milestone="milestone/first")
    assert ms.passes() == [("milestone.completed", "milestone/first"), ("milestone.activated", "milestone/second")]
    assert ms.state("milestone/first") == "completed" and ms.state("milestone/second") == "active"
    assert ms.passes() == []                                                    # nothing left to do: says nothing


def test_no_more_than_active_max_are_active_and_the_rest_wait_in_rank_order(ms):
    for name, rank in (("d", 4), ("b", 2), ("e", None), ("a", 1), ("c", 3)):
        ms.mod.add(ms.cfg, name, rank=rank)
    ms.passes()
    assert [m for m in "abcde" if ms.state(f"milestone/{m}") == "active"] == ["a", "b", "c"]   # the default, 3
    ms.cfg["milestones"]["active_max"] = 4                                      # read from [milestones] active_max
    ms.passes()
    assert [m for m in "abcde" if ms.state(f"milestone/{m}") == "active"] == ["a", "b", "c", "d"]   # by rank; e unranked
    assert "room under the limit (4 of 4 active)" in ms.mod.status(ms.cfg)


@pytest.mark.parametrize("bad", [0, 21, 2.5, "3", True, float("nan")])
def test_a_limit_past_its_bounds_is_refused_not_clamped(ms, bad):
    ms.cfg["milestones"]["active_max"] = bad
    with pytest.raises(ValueError, match="active_max"):
        ms.mod.run_pass(ms.cfg)
    ms.cfg["milestones"] = {"upkeep_days": 91}
    with pytest.raises(ValueError, match="upkeep_days"):
        ms.mod.run_pass(ms.cfg)


def test_an_active_milestone_completes_once_every_gap_is_merged_or_closed(ms):
    ms.mod.add(ms.cfg, "m")
    ms.gap("a", "gap.merged", milestone="milestone/m")
    ms.gap("b", "gap.started", milestone="milestone/m")
    ms.passes()
    assert ms.state("milestone/m") == "active"
    ms.passes()
    assert ms.state("milestone/m") == "active"                                # b is still building
    ms.p.events.add("gap.closed", item="gap/b")
    assert ms.passes() == [("milestone.completed", "milestone/m")]
    assert ms.fields("milestone/m")["gaps_n"] == 2


def test_a_parked_gap_holds_its_milestone_open(ms):
    ms.mod.add(ms.cfg, "m")
    ms.gap("a", "gap.merged", milestone="milestone/m")
    ms.gap("b", "gap.parked", milestone="milestone/m")
    ms.passes()
    ms.passes()
    assert ms.state("milestone/m") == "active"
    assert "parked 1 (b)" in ms.mod.status(ms.cfg)


def test_an_empty_milestone_never_completes(ms):
    ms.mod.add(ms.cfg, "m")
    ms.gap("elsewhere", "gap.merged", milestone="milestone/other")
    for k in range(3):
        ms.passes(time.time() + k * 30 * DAY)
    assert ms.state("milestone/m") == "active"
    assert "gaps: none (an empty milestone never completes)" in ms.mod.status(ms.cfg)


def test_no_event_moves_a_completed_milestone_out(ms):
    ms.mod.add(ms.cfg, "m")
    ms.gap("a", "gap.merged", milestone="milestone/m")
    ms.passes()
    ms.passes()
    assert ms.state("milestone/m") == "completed"
    for e in ("milestone.added", "milestone.activated", "ergostat.item.reopened"):
        ms.p.events.add(e, item="milestone/m", data={"reopened": {"to": "waiting"}} if "reopened" in e else {})
        assert ms.state("milestone/m") == "completed"
    it = its.one(ms.p.events, ms.p.model.spec, "milestone/m")
    assert [r["form"] for r in it.refused] == ["final"] * 3
    ms.gap("b", "gap.started", milestone="milestone/m")             # a gap that names it anyway leaves it completed
    ms.passes()
    assert ms.state("milestone/m") == "completed"


def test_an_upkeep_milestone_is_always_active_outside_the_limit_and_its_cycle_carries_what_is_left(ms):
    ms.cfg["milestones"] = {"active_max": 1, "upkeep_days": 7}
    ms.mod.add(ms.cfg, "a", rank=1)
    ms.mod.add(ms.cfg, "b", rank=2)
    ms.mod.add(ms.cfg, "fixes", upkeep_=True, depends=["b"])                 # always active: not held by b, nor the limit
    t0 = time.time()
    ms.passes(t0)
    assert [ms.state(f"milestone/{x}") for x in ("a", "b", "fixes")] == ["active", "waiting", "active"]
    ms.gap("done", "gap.merged", milestone="milestone/fixes")
    ms.gap("left", "gap.started", milestone="milestone/fixes")
    ms.gap("held", "gap.parked", milestone="milestone/fixes")
    assert ms.passes(t0 + 6 * DAY) == []                                     # every gap of it finished or not: its cycle
    got = ms.passes(t0 + 7 * DAY + 1)
    nxt = [i for e, i in got if e == "milestone.added"]
    assert len(nxt) == 1 and nxt[0].startswith("milestone/upkeep-")
    assert ms.state("milestone/fixes") == "completed" and ms.state(nxt[0]) == "active"
    assert ms.fields("milestone/fixes")["carried"] == ["gap/held", "gap/left"]
    assert [ms.fields(f"gap/{g}")["milestone"] for g in ("done", "left", "held")] == ["milestone/fixes", nxt[0], nxt[0]]
    f = ms.fields(nxt[0])
    assert f["upkeep"] is True and f["follows"] == "milestone/fixes"
    assert f["upkeep_ends"] == pytest.approx(t0 + 14 * DAY + 1)
    assert ms.state("milestone/b") == "waiting"                              # the upkeep one did not take a's room
    assert ms.passes(t0 + 7 * DAY + 60) == []                                # carried once


def test_an_upkeep_cycle_that_stopped_part_way_is_finished_with_the_same_successor(ms):
    ms.mod.add(ms.cfg, "fixes", upkeep_=True)
    t0 = time.time()
    ms.passes(t0)
    ms.gap("left", "gap.started", milestone="milestone/fixes")
    ms.p.events.add("milestone.added", item="milestone/upkeep-x", data={"upkeep": True, "follows": "milestone/fixes"})
    got = ms.passes(t0 + 8 * DAY)                                            # (as a pass that stopped after the add)
    assert not [i for e, i in got if e == "milestone.added"]                 # no second successor made
    assert ms.fields("gap/left")["milestone"] == "milestone/upkeep-x"
    assert [i for e, i in got if e == "milestone.activated"] == ["milestone/upkeep-x"]   # activated once


def test_an_upkeep_milestone_activated_by_hand_has_its_cycle_pinned_once(ms):
    ms.p.events.add("milestone.added", item="milestone/fixes", data={"upkeep": True})
    ms.p.events.add("milestone.activated", item="milestone/fixes")             # no upkeep_ends written
    began = ms.fields("milestone/fixes").get("upkeep_ends")
    assert began is None
    t0 = time.time()
    assert ms.passes(t0) == [("milestone.changed", "milestone/fixes")]
    ends = ms.fields("milestone/fixes")["upkeep_ends"]
    assert ends == pytest.approx(t0 + 7 * DAY, abs=60)
    assert ms.passes(t0 + DAY) == []                                         # pinned: not moved on by later passes
    assert ("milestone.completed", "milestone/fixes") in ms.passes(ends + 1)


def test_assign_refuses_a_completed_milestone(ms):
    ms.mod.add(ms.cfg, "m")
    ms.gap("a", "gap.merged", milestone="milestone/m")
    ms.gap("b")
    ms.passes()
    ms.passes()
    with pytest.raises(ms.mod.Refused, match="completed"):
        ms.mod.assign(ms.cfg, "b", "m")
    with pytest.raises(ms.mod.Refused, match="no such milestone"):
        ms.mod.assign(ms.cfg, "b", "nowhere")
    with pytest.raises(ms.mod.Refused, match="no such gap"):
        ms.mod.assign(ms.cfg, "nobody", "m")
    assert ms.fields("gap/b").get("milestone") is None


def test_depends_refuses_a_cycle(ms):
    for name in ("a", "b", "c"):
        ms.mod.add(ms.cfg, name)
    ms.mod.depends(ms.cfg, "b", ["a"])
    ms.mod.depends(ms.cfg, "c", ["b"])
    with pytest.raises(ms.mod.Refused, match="cycle: milestone/a -> milestone/c -> milestone/b -> milestone/a"):
        ms.mod.depends(ms.cfg, "a", ["c"])
    with pytest.raises(ms.mod.Refused, match="itself"):
        ms.mod.depends(ms.cfg, "a", ["a"])
    with pytest.raises(ms.mod.Refused, match="no such milestone"):
        ms.mod.depends(ms.cfg, "a", ["z"])
    assert ms.fields("milestone/a").get("depends_on") in (None, [])
    ms.p.events.add("milestone.added", item="milestone/d", data={"depends_on": ["milestone/e"]})   # names one not made
    with pytest.raises(ms.mod.Refused, match="cycle"):
        ms.mod.add(ms.cfg, "e", depends=["d"])


def test_assign_and_depends_refuse_a_cycle_through_gaps_and_milestones(ms):
    """Milestone b depends on a; gap x (in a) depends on gap y. Putting y in b closes y -> b -> a's end -> x -> y in
    the precedence graph (a milestone a summary of its gaps), and so does b depending on a once y is in b."""
    ms.mod.add(ms.cfg, "a")
    ms.mod.add(ms.cfg, "b", depends=["a"])
    ms.gap("x", milestone="milestone/a", depends_on=["gap/y"])
    ms.gap("y")
    with pytest.raises(ms.mod.Refused, match=r"gap/y in milestone/b would close a cycle: "
                                             r"gap/y -> milestone/b -> milestone/a \(its end\) -> gap/x -> gap/y"):
        ms.mod.assign(ms.cfg, "y", "b")
    assert ms.fields("gap/y").get("milestone") is None
    ms.mod.add(ms.cfg, "c")
    ms.mod.assign(ms.cfg, "y", "c")                                           # c depends on nothing: no cycle
    with pytest.raises(ms.mod.Refused, match="milestone/c depending on milestone/a would close a cycle"):
        ms.mod.depends(ms.cfg, "c", ["a"])
    assert ms.fields("milestone/c").get("depends_on") in (None, [])
    ms.p.events.add("gap.merged", item="gap/x")                               # a finished gap is on no cycle
    assert ms.mod.depends(ms.cfg, "c", ["a"]) == ["milestone/a"]


def test_a_cycle_already_there_does_not_refuse_an_unrelated_change(ms):
    ms.gap("p", depends_on=["gap/q"])
    ms.gap("q", depends_on=["gap/p"])                                         # (as deps.py may record)
    ms.mod.add(ms.cfg, "m")
    ms.gap("r")
    assert ms.mod.assign(ms.cfg, "r", "m") == "gap/r"
    assert "on a precedence cycle (never taken): gap/p, gap/q" in ms.mod.status(ms.cfg)


def test_add_refuses_a_milestone_made_again_and_a_bad_name(ms):
    ms.mod.add(ms.cfg, "m", title="the first")
    with pytest.raises(ms.mod.Refused, match="already a milestone"):
        ms.mod.add(ms.cfg, "m", title="again")
    with pytest.raises(ms.mod.Refused, match="not a milestone's name"):
        ms.mod.add(ms.cfg, "../Bad")
    assert ms.fields("milestone/m")["title"] == "the first"


def test_the_old_free_text_labels_stay_readable_until_assigned(ms):
    ms.gap("a", milestone="pages-answer-fast")
    ms.gap("b", milestone="pages-answer-fast")
    ms.p.events.add("gap.groomed", item="gap/b", data={"milestone": "items-page-readable"})    # replaced, as before
    assert ms.fields("gap/a")["milestone"] == "pages-answer-fast"
    assert ms.fields("gap/b")["milestone"] == "items-page-readable"
    ms.mod.add(ms.cfg, "m")
    ms.mod.assign(ms.cfg, "a", "m")
    assert ms.fields("gap/a")["milestone"] == "milestone/m"
    assert ms.fields("gap/a")["milestone_was"] == "pages-answer-fast"
    out = ms.mod.status(ms.cfg)
    assert "items-page-readable (1 gaps)" in out and "pages-answer-fast" not in out


def test_pull_and_unpull_mark_a_gap(ms):
    ms.mod.add(ms.cfg, "m")
    ms.gap("a", milestone="milestone/m")
    ms.mod.pull(ms.cfg, "gap/a", True)
    assert ms.fields("gap/a")["pulled"] is True and "open 1 (a (pulled))" in ms.mod.status(ms.cfg)
    ms.mod.pull(ms.cfg, "a", False)
    assert not ms.fields("gap/a").get("pulled")
    with pytest.raises(ms.mod.Refused, match="no such gap"):
        ms.mod.pull(ms.cfg, "nobody", True)


def test_status_prints_each_milestone_its_state_what_it_waits_on_and_its_gaps_by_state(ms):
    ms.mod.add(ms.cfg, "first", title="The first", rank=1)
    ms.mod.add(ms.cfg, "second", title="The second", rank=2, depends=["first"])
    ms.gap("a", "gap.merged", milestone="milestone/first")
    ms.gap("b", "gap.started", milestone="milestone/first")
    ms.gap("c", milestone="milestone/second")
    ms.passes()
    lines = ms.mod.status(ms.cfg).splitlines()
    assert lines[:6] == [
        "milestone/first  active rank 1  The first",
        "  waits on: nothing",
        "  gaps: building 1 (b); merged 1 (a)",
        "milestone/second  waiting rank 2  The second",
        "  waits on: milestone/first (active)",
        "  gaps: open 1 (c)",
    ]


def test_the_pass_holds_the_lock_across_its_read_and_write(ms):
    ms.mod.add(ms.cfg, "m")
    with open(ms.mod.fac.run_dir(ms.cfg) / "milestones.lock", "a") as f:       # a command holding it
        fcntl.flock(f, fcntl.LOCK_EX)
        t = threading.Thread(target=ms.passes)
        t.start()
        t.join(0.5)
        assert t.is_alive() and ms.state("milestone/m") == "waiting"           # it waits: nothing read or written
        fcntl.flock(f, fcntl.LOCK_UN)
    t.join(30)
    assert not t.is_alive() and ms.state("milestone/m") == "active"


def test_the_commands_answer_a_refusal_with_exit_2(ms, capsys, monkeypatch):
    monkeypatch.setattr(ms.mod.fac, "config", lambda: ms.cfg)
    monkeypatch.setenv("ERGOSTAT_CMD", "unused")
    assert ms.mod.main(["add", "m", "--rank", "2", "--title", "M"]) == 0
    assert ms.mod.main(["assign", "nobody", "m"]) == 2
    assert "no such gap" in capsys.readouterr().err
    assert ms.mod.main(["add", "n", "--rank", "nan"]) == 2
    assert ms.mod.main(["frobnicate"]) == 2
    assert ms.mod.main(["status"]) == 0 and "milestone/m  waiting rank 2  M" in capsys.readouterr().out


def test_the_milestone_model_raises_no_check_finding():
    """The milestones' parts are a system of their own (within factory, not a loose cluster of planning), and both
    flows between their stocks have equations, so check says nothing of them: no no-equation, no system-splits."""
    spec, problems = read(ROOT / "ergostat.yaml", extremes=False)
    assert [p for p in problems if p.level == "error"] == []
    assert spec.stocks["milestones-active"].system == "milestones" and spec.chain("milestones")[-1] == "factory"
    ours = ("flow.milestones-activated", "flow.milestones-completed", "system.planning", "system.milestones",
            "system.factory")
    assert [f"{p.code}@{p.about}" for p in problems if p.about in ours or "milestones-" in p.message] == []
