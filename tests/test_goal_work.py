"""The Goals (Loops) page's one answer: each goal's performance worked out in the background within a budget per pass
(ergostat/web/goal_work.py), carried by /api/loops?perf=1 with each stock's points; the answer cache an LRU."""

from __future__ import annotations

import time

from ergostat import model as mdl
from ergostat.store import Project
from ergostat.web import server
from ergostat.web.goal_work import GoalWork
from tests.test_control import TUNE, tune_project


def test_the_answer_cache_keeps_the_most_recently_used(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(TUNE)
    live = server.Live(Project(mdl.load(tmp_path)))
    live.work.stop()
    for i in range(40):
        live.keep(("a", i), {"i": i})
    assert all(live.cached(("a", i)) == {"i": i} for i in range(40)), "under 256 entries, nothing is dropped"
    for i in range(20, 40):                              # the later twenty used again: the first twenty are the oldest
        live.cached(("a", i))
    for i in range(server.KEPT_MOST - 40 + 20):          # 20 past the most
        live.keep(("b", i), i)
    assert len(live._kept) == server.KEPT_MOST
    assert [i for i in range(40) if live.cached(("a", i)) is None] == list(range(20))
    assert all(live.cached(("a", i)) == {"i": i} for i in range(20, 40))


def test_a_pass_keeps_within_its_budget_with_a_slow_identification():
    w = GoalWork(budget=1.0, background=False)
    worked: list[str] = []

    def slow(goal, window):
        time.sleep(0.3)
        worked.append(goal)
        return {"goal": goal}
    goals = [f"g{i}" for i in range(10)]
    assert set(w.ask("performance", goals, None, 1, slow, 300).values()) == {None}
    t0 = time.monotonic()
    n = w.run_pass()
    took = time.monotonic() - t0
    assert n == len(worked) and 1 <= n <= 3 and took <= 1.0, (n, took)
    passes = 1
    while len(worked) < len(goals):                      # each later pass as bounded, until every goal is worked out
        t0 = time.monotonic()
        w.run_pass()
        assert time.monotonic() - t0 <= 1.0
        passes += 1
    assert passes >= 4 and sorted(worked) == sorted(goals)
    assert w.ask("performance", goals, None, 1, slow, 300) == {g: {"goal": g} for g in goals}
    assert w.run_pass() == 0, "nothing younger than its life is worked out again"
    assert set(w.ask("performance", goals, None, 2, slow, 300).values()) == {None}, "another model: not the old answer"


def test_one_goal_slower_than_the_budget_is_its_pass_alone():
    w = GoalWork(budget=0.2, background=False)
    w.ask("performance", ["a", "b"], None, 1, lambda g, _w: time.sleep(0.3) or g, 300)
    assert w.run_pass() == 1 and w.run_pass() == 1 and w.run_pass() == 0


def test_a_later_asked_window_fills_before_an_earlier_one():
    w = GoalWork(budget=0.0, background=False)          # one goal a pass
    worked: list = []
    work = lambda g, win: worked.append((g, win)) or g   # noqa: E731
    goals = ["a", "b", "c"]
    w.ask("performance", goals, 100.0, 1, work, 300)     # a moment picked on the slider, then another,
    w.ask("performance", goals, 200.0, 1, work, 300)
    w.ask("performance", goals, None, 1, work, 300)      # then back to live
    for _ in range(3):
        w.run_pass()
    assert worked == [("a", None), ("b", None), ("c", None)], "live first, its goals in the order asked"
    w.ask("performance", goals, 200.0, 1, work, 300)     # the moment asked again comes before the one left
    w.run_pass()
    assert worked[-1] == ("a", 200.0)
    worked.clear()
    w.ask("performance", goals, None, 1, work, 0)        # life 0: live is due again, and asked last, so first
    w.run_pass()
    assert worked == [("a", None)]


def test_a_window_no_longer_asked_is_let_go():
    w = GoalWork(budget=0.0, background=False, forsake=0.2, windows=2)
    worked: list = []
    work = lambda g, win: worked.append((g, win)) or g   # noqa: E731
    for at in (1.0, 2.0, 3.0):                           # three moments: the first is past the most wanted
        w.ask("performance", ["a"], at, 1, work, 300)
    while w.run_pass():
        pass
    assert sorted(worked) == [("a", 2.0), ("a", 3.0)]
    w.ask("performance", ["a", "b"], 4.0, 1, work, 300)
    time.sleep(0.3)                                      # nobody asks any more: nothing is worked out
    worked.clear()
    assert w.run_pass() == 0 and worked == [] and not w._wanted
    assert w.ask("performance", ["a"], 3.0, 1, work, 300) == {"a": "a"}, "what was worked out is still kept"


def test_work_under_way_when_a_decision_is_made_is_not_kept():
    w = GoalWork(background=False)
    calls = []

    def racing(goal, window):                            # the owner accepts a proposal while this one is worked out
        calls.append(goal)
        if len(calls) == 1:
            w.forget("performance")
        return {"read": len(calls)}
    w.ask("performance", ["a"], None, 1, racing, 300)
    w.run_pass()
    assert w.ask("performance", ["a"], None, 1, racing, 300) == {"a": {"read": 2}}


def test_a_failed_identification_says_so_rather_than_being_worked_out_for_ever():
    w = GoalWork(background=False)
    w.ask("performance", ["a"], None, 1, lambda g, _w: 1 / 0, 300)
    w.run_pass()
    assert "ZeroDivisionError" in w.ask("performance", ["a"], None, 1, lambda g, _w: 1 / 0, 300)["a"]["failed"]


def test_the_loops_answer_carries_points_and_the_same_performance_as_loop_control(tmp_path):
    from ergostat.web.control_api import summary
    live = server.Live(tune_project(tmp_path))
    first = server.api(live, "loops", {"perf": ["1"]})
    lp = first["level-held"]
    assert lp["perf"] == {"working": True} or "performance" in lp["perf"]
    snap = live.snapshot(live.get(), server._window({}), None)
    assert len(lp["points"]) > 1 and lp["points"] == snap["stocks"][lp["stock"]]["points"]
    assert "perf" not in server.api(live, "loops", {})["level-held"], "asked for only with perf=1"
    at = {"at": [str(time.time())]}                      # one moment, so both read the same record
    deadline = time.monotonic() + 60
    while (got := server.api(live, "loops", {"perf": ["1"], **at})["level-held"]["perf"]).get("working"):
        assert time.monotonic() < deadline, "never worked out"
        time.sleep(0.2)
    live.work.stop()
    assert got == summary(server.api(live, "loop-control", {"goal": ["level-held"], **at}))
    assert got["performance"]["harris"]
