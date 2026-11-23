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


def test_assign_and_depends_refuse_a_cycle_through_a_split_parent(ms):
    """A split parent p (in m1) is a summary of its sub-gap s (`parent` is a group by default), so with s in m2,
    m2 depending on m1 closes m2 -> s -> p's end -> m1's end -> m2: s would never be taken, and m1 never complete."""
    ms.mod.add(ms.cfg, "m1")
    ms.mod.add(ms.cfg, "m2")
    ms.gap("p", milestone="milestone/m1")
    ms.gap("s", parent="gap/p")
    assert ms.mod.assign(ms.cfg, "s", "m2") == "gap/s"                        # m2 depends on nothing yet
    with pytest.raises(ms.mod.Refused, match=r"milestone/m2 depending on milestone/m1 would close a cycle: milestone/m2 -> "
                                             r"milestone/m1 \(its end\) -> gap/p \(its end\) -> gap/s -> milestone/m2"):
        ms.mod.depends(ms.cfg, "m2", ["m1"])
    assert ms.fields("milestone/m2").get("depends_on") in (None, [])
    ms.mod.add(ms.cfg, "m3", depends=["m1"])
    ms.gap("t", parent="gap/p")
    with pytest.raises(ms.mod.Refused, match=r"gap/t in milestone/m3 would close a cycle"):
        ms.mod.assign(ms.cfg, "t", "m3")


def test_the_relations_the_cycle_check_reads_are_the_models():
    """milestones.py's PRECEDENCE and GROUPS are every precedence and group relation of the gap and milestone kinds,
    as compiled (a group added to the gap kind fails this until the check reads it)."""
    spec, _ = read(ROOT / "ergostat.yaml")
    for kind in ("gap", "milestone"):
        rels = spec.items[kind].relations.values()
        sys.path.insert(0, str(BIN))
        try:
            import milestones
        finally:
            sys.path.remove(str(BIN))
        assert sorted(r.name for r in rels if r.precedence) == sorted(milestones.PRECEDENCE.get(kind, ())), kind
        assert sorted(r.name for r in rels if r.group) == sorted(milestones.GROUPS.get(kind, ())), kind


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


# ---- milestone-limits-what-is-built: the planner and the implementor take only the work of active milestones

HELD_BY = ("planner", "implementor")             # their takes: where asks waits_on_milestone empty
NOT_HELD = ("reviewer", "merge-queue", "flake-triage")


@pytest.fixture(scope="module")
def blocks():
    """The compiled blocks only: read() would also run the model's findings (about a minute), once per xdist worker."""
    from ergostat.spec.compile import compile_doc
    from ergostat.spec.load import load as load_doc
    spec, problems = compile_doc(load_doc(ROOT / "ergostat.yaml"))
    assert [p for p in problems if p.level == "error"] == []
    return spec.blocks


def takes(ms, blocks, name: str, gid: str) -> bool:
    """Whether block ``name`` may take the gap as the dispatcher reads it: its state among the block's `at`, and the
    block's compiled `where` matched against the folded item (its.matches, as dispatch.py does)."""
    t = blocks[name].takes
    it = its.one(ms.p.events, ms.p.model.spec, gid)
    return it.state in t.at and its.matches(it, t.where)


def two_milestones(ms):
    """a active (after a pass); b waiting on a. Gaps: x (ready) in a; y (ready) and z (open) in b; u (ready) in none;
    w (ready) with an old free-text label."""
    ms.mod.add(ms.cfg, "a", rank=1)
    ms.mod.add(ms.cfg, "b", rank=2, depends=["a"])
    ms.gap("x", "gap.defined", milestone="milestone/a")
    ms.gap("y", "gap.defined", milestone="milestone/b")
    ms.gap("z", milestone="milestone/b")
    ms.gap("u", "gap.defined")
    ms.gap("w", "gap.defined", milestone="an-old-label")


def test_the_planner_and_the_implementor_ask_waits_on_milestone_empty_and_review_and_the_queue_do_not(blocks):
    for name in HELD_BY:
        assert blocks[name].takes.kind == "gap" and blocks[name].takes.where.get("waits_on_milestone", 0) is None, name
    for name in NOT_HELD:
        assert blocks[name].takes.kind == "gap" and "waits_on_milestone" not in (blocks[name].takes.where or {}), name


def test_enforcement_off_changes_nothing(ms, blocks):
    two_milestones(ms)
    got = ms.mod.run_pass(ms.cfg)
    assert [e for e, _, _ in got] == ["milestone.activated"]                    # a only; no gap event at all
    assert all(takes(ms, blocks, "implementor", f"gap/{g}") for g in "xyuw")
    assert takes(ms, blocks, "planner", "gap/z")
    ms.mod.pull(ms.cfg, "y", True)
    ms.mod.assign(ms.cfg, "u", "b")
    for g in "xyzuw":                                                           # nor from the commands
        assert "waits_on_milestone" not in ms.fields(f"gap/{g}"), g
    ms.cfg["milestones"]["enforce"] = True                                      # on, then off again: cleared
    ms.passes()
    assert ms.fields("gap/z")["waits_on_milestone"] == "milestone/b"
    ms.cfg["milestones"]["enforce"] = False
    ms.passes()
    assert all(not ms.fields(f"gap/{g}").get("waits_on_milestone") for g in "xyzuw")
    assert takes(ms, blocks, "planner", "gap/z") and takes(ms, blocks, "implementor", "gap/u")


def test_with_enforcement_an_inactive_milestones_gap_is_held_and_an_active_ones_is_taken(ms, blocks):
    ms.cfg["milestones"]["enforce"] = True
    two_milestones(ms)
    ms.passes()                                                                 # a activates, in the same pass
    f = {g: ms.fields(f"gap/{g}").get("waits_on_milestone") for g in "xyzuw"}
    assert f == {"x": None, "y": "milestone/b", "z": "milestone/b", "u": "unassigned", "w": "an-old-label"}
    assert takes(ms, blocks, "implementor", "gap/x")
    assert not any(takes(ms, blocks, "implementor", f"gap/{g}") for g in "yuw")
    assert not takes(ms, blocks, "planner", "gap/z")
    ms.p.events.add("gap.sent-back", item="gap/y")                              # a fix round is the implementor's too
    assert ms.state("gap/y") == "fix" and not takes(ms, blocks, "implementor", "gap/y")
    assert ms.passes() == []                                                    # nothing changed: nothing said again
    ms.p.events.add("gap.merged", item="gap/x")                                 # a completes, b activates: released
    assert ms.passes() == [("milestone.completed", "milestone/a"), ("milestone.activated", "milestone/b"),
                           ("gap.milestone-held", "gap/y"), ("gap.milestone-held", "gap/z")]
    assert takes(ms, blocks, "implementor", "gap/y") and takes(ms, blocks, "planner", "gap/z")
    ms.mod.add(ms.cfg, "c")                                                     # (room under the limit: c activates)
    ms.mod.assign(ms.cfg, "u", "c")
    assert ms.fields("gap/u")["waits_on_milestone"] == "milestone/c"           # said by assign itself, not a pass later
    ms.passes()
    assert takes(ms, blocks, "implementor", "gap/u")
    assert "enforced ([milestones] enforce): 1 gaps wait for their milestone" in ms.mod.status(ms.cfg)   # w


def test_a_pulled_gap_in_an_inactive_milestone_is_taken_as_if_it_were_active(ms, blocks):
    ms.cfg["milestones"]["enforce"] = True
    two_milestones(ms)
    ms.passes()
    ms.mod.pull(ms.cfg, "y", True)
    assert not ms.fields("gap/y").get("waits_on_milestone")                     # at once, by pull itself
    assert takes(ms, blocks, "implementor", "gap/y")
    ms.mod.pull(ms.cfg, "y", False)
    assert ms.fields("gap/y")["waits_on_milestone"] == "milestone/b" and not takes(ms, blocks, "implementor", "gap/y")
    ms.gap("s", "gap.defined", parent="gap/z")                                  # a sub-gap of z's split: b's
    ms.passes()
    assert ms.fields("gap/s")["waits_on_milestone"] == "milestone/b"
    ms.mod.pull(ms.cfg, "z", True)
    assert takes(ms, blocks, "implementor", "gap/s") and takes(ms, blocks, "planner", "gap/z")


def test_review_and_the_queue_are_not_held_by_an_inactive_milestone(ms, blocks):
    ms.cfg["milestones"]["enforce"] = True
    ms.mod.add(ms.cfg, "a")
    ms.mod.add(ms.cfg, "b", depends=["a"])
    ms.gap("r", "gap.defined", "gap.started", "gap.built", milestone="milestone/b")
    ms.gap("q", "gap.defined", "gap.started", "gap.built", "gap.approved", milestone="milestone/b")
    ms.gap("t", "gap.defined", "gap.started", "gap.built", "gap.approved", "gap.queue-failed", milestone="milestone/b")
    ms.passes()
    assert ms.state("milestone/b") == "waiting"
    assert all(ms.fields(f"gap/{g}")["waits_on_milestone"] == "milestone/b" for g in "rqt")
    assert takes(ms, blocks, "reviewer", "gap/r")
    assert takes(ms, blocks, "merge-queue", "gap/q")
    assert takes(ms, blocks, "flake-triage", "gap/t")
    ms.p.events.add("gap.merged", item="gap/q")                                 # a finished gap: its field cleared
    ms.passes()
    assert not ms.fields("gap/q").get("waits_on_milestone")


def test_a_dependency_on_a_gap_of_a_milestone_finishing_later_is_refused(ms):
    """b depends on a; x (in a) depends on y. y in b would leave x waiting on y, y on b, b on a, a on x: refused by
    assign, and by depends once y is in c and c is made to depend on a; pulling y does not lift it (the take's graph
    holds the link as a cycle, pulled or not); status lists one recorded around the commands."""
    ms.cfg["milestones"]["enforce"] = True
    ms.mod.add(ms.cfg, "a")
    ms.mod.add(ms.cfg, "b", depends=["a"])
    ms.gap("x", milestone="milestone/a", depends_on=["gap/y"])
    ms.gap("y")
    ms.mod.pull(ms.cfg, "y", True)
    with pytest.raises(ms.mod.Refused, match=r"gap/y in milestone/b would close a cycle: .*; and would leave gap/x "
                                             r"depending on gap/y, in milestone/b, which can only finish after "
                                             r"milestone/a: both would wait forever \(pulling gap/y does not lift it\)"):
        ms.mod.assign(ms.cfg, "y", "b")
    assert ms.fields("gap/y").get("milestone") is None
    ms.mod.add(ms.cfg, "c")
    ms.mod.add(ms.cfg, "d", depends=["c"])
    ms.mod.assign(ms.cfg, "y", "c")
    with pytest.raises(ms.mod.Refused, match=r"milestone/c depending on milestone/a would close a cycle: .*; and "
                                             r"would leave gap/x depending on gap/y, in milestone/c, which can only "
                                             r"finish after milestone/a"):
        ms.mod.depends(ms.cfg, "c", ["a"])
    ms.mod.depends(ms.cfg, "a", ["d"])          # a after d after c: y's milestone finishes first, as it should
    ms.gap("v", milestone="milestone/c", depends_on=["gap/x"])                  # as deps.py may record: c's v on a's x
    out = ms.mod.status(ms.cfg)
    assert ("depends on a gap of a milestone that can only finish later (both wait forever): "
            "gap/v on gap/x (milestone/a, after milestone/c)") in out
    assert "on a precedence cycle (never taken)" in out                         # the take's graph holds it too


@pytest.mark.parametrize("bad", ["true", 1, None])
def test_an_enforce_not_true_or_false_is_refused(ms, bad):
    ms.cfg["milestones"]["enforce"] = bad
    with pytest.raises(ValueError, match="enforce"):
        ms.mod.run_pass(ms.cfg)
    with pytest.raises(ValueError, match="enforce"):
        ms.mod.pull(ms.cfg, "nobody", True)


# ---- milestone-every-gap-has-one: with [milestones] enforce on, the pass places every unfinished gap

def three(ms, t0=None):
    """Two active milestones (a rank 1, b rank 2) and an active upkeep one (fixes), with enforcement on."""
    ms.cfg["milestones"] = {"enforce": True}
    ms.mod.add(ms.cfg, "b", rank=2)
    ms.mod.add(ms.cfg, "a", rank=1)
    ms.mod.add(ms.cfg, "fixes", upkeep_=True)
    ms.passes(t0)
    assert [ms.state(f"milestone/{x}") for x in ("a", "b", "fixes")] == ["active"] * 3


def requested(ms, name, **data):
    ms.p.events.add("gap.requested", item=f"gap/{name}", data={"title": name, "branch": name, **data})


def test_a_requested_gap_joins_the_first_active_milestone(ms):
    ms.mod.add(ms.cfg, "a", rank=1)
    ms.passes()
    requested(ms, "asked", source="request", requested_by="coordinator")
    ms.gap("listed", source="gaps")                                         # docs/GAPS.md, by the intake
    ms.gap("labelled", milestone="pages-answer-fast")                        # an old label is no milestone
    assert ms.passes() == []                                                 # enforcement off: left as they are
    assert "unfinished gaps with no milestone (none, an old label, or a completed one): 3" in ms.mod.status(ms.cfg)
    ms.mod.add(ms.cfg, "b", rank=2)
    ms.mod.add(ms.cfg, "fixes", upkeep_=True)
    ms.cfg["milestones"] = {"enforce": True}
    got = ms.passes()
    assert [i for e, i in got if e == "gap.milestone-set"] == ["gap/asked", "gap/labelled", "gap/listed"]
    for g in ("asked", "listed", "labelled"):
        assert ms.fields(f"gap/{g}")["milestone"] == "milestone/a"
        assert ms.fields(f"gap/{g}")["assigned_for"] == "requested: the first active milestone"
    assert ms.fields("gap/labelled")["milestone_was"] == "pages-answer-fast"
    assert ms.passes() == []                                                 # placed once
    assert ms.mod.status(ms.cfg).splitlines()[-1] == \
        "unfinished gaps with no milestone (none, an old label, or a completed one): 0"


def test_a_gap_the_factory_filed_joins_the_current_upkeep_milestone(ms):
    t0 = time.time()
    three(ms, t0)
    ms.p.events.add("milestone.added", item="milestone/aa-fixes", data={"upkeep": True})   # its cycle ends after fixes'
    ms.p.events.add("milestone.activated", item="milestone/aa-fixes", data={"upkeep_ends": t0 + 10 * DAY})
    requested(ms, "simplify-x", source="simplifier")
    requested(ms, "filed", source="request", requested_by="pipeline-manager")
    requested(ms, "knowledge-lesson-9", source="request")
    requested(ms, "by-hand", source="request", requested_by="coordinator")
    ms.passes(t0 + 60)
    assert ms.fields("gap/by-hand")["milestone"] == "milestone/a"
    up = {ms.fields(f"gap/{g}")["milestone"] for g in ("simplify-x", "filed", "knowledge-lesson-9")}
    assert up == {"milestone/aa-fixes"}                                      # the upkeep one whose cycle ends last
    assert ms.fields("gap/filed")["assigned_for"] == "filed by the factory: the current upkeep milestone"


def test_a_sub_gap_of_a_split_keeps_its_parents_milestone(ms):
    three(ms)
    ms.gap("whole", milestone="milestone/b")
    ms.p.events.add("gap.split", item="gap/whole", data={"children": ["gap/part-1", "gap/part-2"]})
    requested(ms, "part-1", source="plan", parent=["gap/whole"])
    requested(ms, "part-2", source="groom", parent=["gap/whole"])
    requested(ms, "join-short", source="join", parent=["gap/whole"])
    ms.gap("loose")                                                          # its parent with no milestone either
    requested(ms, "loose-part", source="plan", parent=["gap/loose"])
    ms.passes()
    assert ms.state("gap/whole") == "split"
    for g in ("part-1", "part-2", "join-short"):
        assert ms.fields(f"gap/{g}")["milestone"] == "milestone/b"           # not the first active (a)
        assert ms.fields(f"gap/{g}")["assigned_for"] == "kept from gap/whole"
    assert ms.fields("gap/loose")["milestone"] == ms.fields("gap/loose-part")["milestone"] == "milestone/a"


def test_a_continued_gap_keeps_its_parents_milestone_or_joins_upkeep_once_it_completed(ms):
    three(ms)
    ms.gap("stuck", "gap.parked", milestone="milestone/b")
    requested(ms, "stuck-continued", source="request", continues="stuck", requested_by="coordinator")
    ms.p.events.add("gap.resumed", item="gap/stuck", data={"resumed_as": "gap/stuck-continued"})
    ms.mod.add(ms.cfg, "c", rank=0)
    ms.gap("c-done", "gap.merged", milestone="milestone/c")
    ms.passes()
    ms.passes()
    assert ms.state("milestone/c") == "completed"
    assert ms.fields("gap/stuck-continued")["milestone"] == "milestone/b"
    assert ms.fields("gap/stuck-continued")["assigned_for"] == "kept from gap/stuck"
    ms.gap("old", "gap.parked")                                              # its milestone completed since
    ms.p.events.add("gap.milestone-set", item="gap/old", data={"milestone": "milestone/c"})
    requested(ms, "old-continued", source="request", continues="old", requested_by="park-resume")
    ms.p.events.add("gap.resumed", item="gap/old", data={"resumed_as": "gap/old-continued"})
    ms.passes()
    assert ms.fields("gap/old")["milestone"] == "milestone/fixes"
    assert ms.fields("gap/old")["assigned_for"] == "its milestone completed: the current upkeep milestone"
    assert ms.fields("gap/old-continued")["milestone"] == "milestone/fixes"
    assert ms.state("milestone/c") == "completed"


def test_no_path_assigns_a_completed_milestone(ms):
    t0 = time.time()
    three(ms, t0)
    ms.gap("a-done", "gap.merged", milestone="milestone/a")
    ms.passes(t0)
    assert ms.state("milestone/a") == "completed"
    ms.gap("b-gap", "gap.started", milestone="milestone/b")
    with pytest.raises(ms.mod.Refused, match="completed"):                   # the coordinator's assign
        ms.mod.assign(ms.cfg, "b-gap", "a")
    requested(ms, "named-it", source="request", milestone="milestone/a")     # a request naming it
    ms.p.events.add("gap.milestone-set", item="gap/b-gap", data={"milestone": "milestone/a"})   # a raw event
    ms.passes(t0 + 60)
    assert ms.fields("gap/named-it")["milestone"] == ms.fields("gap/b-gap")["milestone"] == "milestone/fixes"
    assert ms.fields("gap/b-gap")["milestone_was"] == "milestone/a"
    # an upkeep cycle never carries to a successor that completed: a new one is made
    ms.p.events.add("milestone.added", item="milestone/upkeep-old", data={"upkeep": True, "follows": "milestone/fixes"})
    ms.p.events.add("milestone.completed", item="milestone/upkeep-old")
    got = ms.passes(t0 + 8 * DAY)
    nxt = [i for e, i in got if e == "milestone.added"]
    assert len(nxt) == 1 and nxt[0] != "milestone/upkeep-old" and ms.state(nxt[0]) == "active"
    assert ms.fields("gap/b-gap")["milestone"] == nxt[0]
    assert ms.state("milestone/upkeep-old") == "completed"
    assert not ms.mod.gaps_of("milestone/upkeep-old", {g["id"]: g for g in ms.mod.fac.items("gap")})


def test_with_no_milestone_to_go_to_a_gap_is_left_and_counted(ms):
    ms.cfg["milestones"] = {"enforce": True}
    ms.mod.add(ms.cfg, "m")
    ms.gap("m-done", "gap.merged", milestone="milestone/m")
    ms.passes()
    ms.passes()
    assert ms.state("milestone/m") == "completed"
    ms.gap("late", milestone="milestone/m")
    assert ms.passes() == []                                                 # never the completed one
    assert ms.fields("gap/late")["milestone"] == "milestone/m"
    assert ms.mod.status(ms.cfg).splitlines()[-1] == ("unfinished gaps with no milestone (none, an old label, or a "
                                                      "completed one): 1 (late; the next pass places 0 of them)")
    ms.gap("new")
    ms.mod.add(ms.cfg, "n")
    assert ms.mod.status(ms.cfg).splitlines()[-1] == ("unfinished gaps with no milestone (none, an old label, or a "
                                                      "completed one): 2 (late, new; the next pass places 1 of them)")


def test_a_placement_that_would_close_a_cycle_goes_to_upkeep_or_is_left(ms):
    """Milestone a active, b waiting on a, gap y in b; gap x requested depending on y. x in a would close
    a's end -> b -> y -> x -> a's end: x never taken, a never completed, b never active. So x is not put in a."""
    ms.cfg["milestones"] = {"enforce": True}
    ms.mod.add(ms.cfg, "a", rank=1)
    ms.mod.add(ms.cfg, "b", rank=2, depends=["a"])
    ms.passes()
    assert (ms.state("milestone/a"), ms.state("milestone/b")) == ("active", "waiting")
    ms.gap("y", milestone="milestone/b")
    requested(ms, "x", source="request", requested_by="coordinator", depends_on=["gap/y"])
    assert ms.passes() == []                                                 # no upkeep one: left, not put on a cycle
    assert ms.fields("gap/x").get("milestone") is None
    assert ms.mod.status(ms.cfg).splitlines()[-1] == ("unfinished gaps with no milestone (none, an old label, or a "
                                                      "completed one): 1 (x; the next pass places 0 of them)")
    ms.mod.add(ms.cfg, "fixes", upkeep_=True)
    ms.passes()
    assert ms.fields("gap/x")["milestone"] == "milestone/fixes"
    assert ms.fields("gap/x")["assigned_for"] == "the current upkeep milestone (milestone/a would close a cycle)"
    assert "on a precedence cycle" not in ms.mod.status(ms.cfg)
    requested(ms, "z", source="request", requested_by="coordinator")       # one with no dependency still joins a
    ms.passes()
    assert ms.fields("gap/z")["milestone"] == "milestone/a"


def test_two_placements_of_one_pass_that_together_close_a_cycle_are_checked_together(ms):
    """x (requested, depending on y) goes to a; y continues a parked gap in c (c waits on a), so it would keep c. Each
    alone closes nothing; both close a's end -> c -> y -> x -> a's end. The second is checked against the first."""
    three(ms)
    ms.p.events.add("milestone.added", item="milestone/c", data={"depends_on": ["milestone/a"]})
    ms.gap("q", "gap.parked", milestone="milestone/c")
    requested(ms, "x", source="request", requested_by="coordinator", depends_on=["gap/y"])
    requested(ms, "y", source="request", continues="q", requested_by="park-resume")
    ms.p.events.add("gap.resumed", item="gap/q", data={"resumed_as": "gap/y"})
    ms.passes()
    assert ms.fields("gap/x")["milestone"] == "milestone/a"                  # placed first (by name)
    assert ms.fields("gap/y")["milestone"] == "milestone/fixes"
    assert ms.fields("gap/y")["assigned_for"] == "the current upkeep milestone (milestone/c would close a cycle)"
    assert "on a precedence cycle" not in ms.mod.status(ms.cfg)


@pytest.mark.parametrize("bad", [1, "true", None])
def test_enforce_is_true_or_false(ms, bad):
    ms.cfg["milestones"] = {"enforce": bad}
    with pytest.raises(ValueError, match="enforce"):
        ms.mod.run_pass(ms.cfg)
