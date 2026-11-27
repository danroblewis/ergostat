"""What holds the work up (SPEC §5a, *What holds the work up*; ergostat/why/held.py): every unfinished item grouped by
its root, the roots ranked by what they hold, a stall told from normal queueing, the goals off because of a root folded
under it, and an answer quick on a factory-size record. The fixtures are why-is-it-not-done's (tests/test_why.py)."""

from __future__ import annotations

import json
import os
import time

import pytest

from ergostat.why import held
from tests.test_why import DOWN, FACTORY, MODEL, NOW, UP, dead_pid, gap, gate_open, project, readings, take, why


def held_up(p, engine=UP):
    return held.answer(p, now=NOW, engine=engine)


def holds(r, item) -> bool:
    return r["item"] == item or item in r["first"]


# ---- 1. on why-is-it-not-done's fixtures, the true constraint ranks first

def chain(p):
    gap(p, "a", "defined", "started")
    take(p, "gap/a", "implementor")
    gap(p, "b", "defined", depends_on="gap/a")
    gap(p, "c", "defined", depends_on="gap/b")
    return "gap/c"


def dead_queue(p):
    gap(p, "q", "defined", "started", "built", "approved")
    take(p, "gap/q", "queue", pid=dead_pid())
    gap(p, "r", "defined", "started", "built", "approved", at=NOW - 1800)
    return "gap/r"


def budget(p):
    for n in ("x", "y"):
        gap(p, n, "defined")
    for i in range(5):
        p.events.add("budget.refused", item="implementor", source="ergostat", at=NOW - 300 + 60 * i,
                     data={"why": "38.00 spent and 4.00 reserved of 40 today; this run reserves 4"})
    return "gap/y"


def parked(p):
    gap(p, "z", "defined", "started", "parked")
    gap(p, "y", "defined", depends_on="gap/z")
    return "gap/y"


def parked_alone(p):
    gap(p, "z", "defined", "started", "parked")
    return "gap/z"


def put_off(p):
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 300)
    take(p, "ticket/1", "worker", at=NOW - 200)
    p.events.add("ergostat.lease.ended", item="ticket/1", source="ergostat", at=NOW - 100,
                 data={"run": "r1", "fence": 1, "how": "nack", "why": "tests failed", "after": 3600})
    return "ticket/1"


def pool(p):
    gate_open(p)
    for i in (1, 2):
        p.events.add("ticket.opened", item=f"ticket/{i}", at=NOW - 100 + i)
    take(p, "ticket/1", "worker")
    return "ticket/2"


def by_hand(p):
    readings(p, o=0.0)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    return "ticket/1"


def failing(p):
    gate_open(p)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    for i in range(3):
        p.events.add("agent.failed", item="worker", source="ergostat", at=NOW - 50 + i, data={"note": f"exited {i + 1}"})
    return "ticket/1"


def cycle(p):
    p.events.add("ticket.opened", item="ticket/a", at=NOW - 100, data={"blocked_by": "ticket/b"})
    p.events.add("ticket.opened", item="ticket/b", at=NOW - 90, data={"blocked_by": "ticket/a"})
    return "ticket/a"


def missing(p):
    p.events.add("ticket.opened", item="ticket/a", at=NOW - 100, data={"blocked_by": "ticket/never"})
    return "ticket/a"


def nothing(p):
    p.events.add("note.opened", item="note/1", at=NOW - 100)
    return "note/1"


CASES = [(chain, FACTORY, UP, "work", "queue"), (dead_queue, FACTORY, UP, "lease", "stall"),
         (budget, FACTORY, UP, "gate", "stall"), (parked, FACTORY, UP, "parked", "stall"),
         (parked_alone, FACTORY, UP, "parked", "held"), (put_off, MODEL, UP, "lease", "queue"),
         (pool, MODEL, UP, "pool-full", "queue"), (by_hand, MODEL, UP, "person", "held"),
         (failing, MODEL, UP, "block", "stall"), (pool, MODEL, DOWN, "block", "stall"),
         (cycle, MODEL, UP, "cycle", "stall"), (missing, MODEL, UP, "missing", "stall"),
         (nothing, MODEL, UP, "nothing", "stall")]


@pytest.mark.parametrize("make,model,engine,kind,klass", CASES, ids=[f"{c[0].__name__}-{c[3]}" for c in CASES])
def test_on_the_fixtures_of_why_the_true_constraint_ranks_first(tmp_path, make, model, engine, kind, klass):
    p = project(tmp_path, model)
    asked = make(p)
    w = why(p, asked, engine)["root"]
    a = held_up(p, engine)
    first = a["roots"][0]
    assert (first["kind"], first["class"]) == (kind, klass) == (w["kind"], klass), (first, w)
    assert first["owner"] == w["owner"]
    if kind == "cycle":                                   # (said, and its link to remove, from where the walk came in)
        assert first["holds"] == 2 and ("ticket/a → ticket/b" in first["says"] or "ticket/b → ticket/a" in first["says"])
        assert first["command"].startswith("ergostat event --add ITEM.changed --item ticket/"), first["command"]
    else:
        assert first["says"] == w["says"] and first["command"] == w["command"] and holds(first, asked), first
    assert a["stall"] is (klass == "stall") and a["line"].startswith("Stalled: ") is (klass == "stall"), a["line"]


def test_a_stall_outranks_a_bigger_queue_and_each_item_counts_once_under_its_root(tmp_path):
    p = project(tmp_path, FACTORY)
    for i in range(9):                                   # the implementor's pool full of live runs, 12 more waiting
        gap(p, f"w{i}", "defined", "started")
        take(p, f"gap/w{i}", "implementor", run=f"w{i}")
    for i in range(12):
        gap(p, f"r{i}", "defined", at=NOW - 7200 + i)
    dead_queue(p)
    a = held_up(p)
    kinds = [(x["kind"], x["class"], x["waiting"]) for x in a["roots"]]
    assert kinds[0] == ("lease", "stall", 1) and kinds[1] == ("pool-full", "queue", 12), kinds
    assert sum(x["kind"] == "work" for x in a["roots"]) == 9 and a["unfinished"] == 9 + 12 + 2
    assert a["roots"][1]["first"][0] == "gap/r0", "the items its block would take first come first"


# ---- 2. the budget-guard stall and the dead-lease stall are each the first line; a healthy busy system has no stall

def busy(p, approved=5, dead=False):
    for i in range(9):
        gap(p, f"w{i}", "defined", "started")
        take(p, f"gap/w{i}", "implementor", run=f"w{i}")
    for i in range(20):
        gap(p, f"r{i}", "defined", at=NOW - 7200 + i)
    gap(p, "q", "defined", "started", "built", "approved")
    take(p, "gap/q", "queue", run="qq", pid=dead_pid() if dead else os.getpid())
    for i in range(approved):
        gap(p, f"a{i}", "defined", "started", "built", "approved", at=NOW - 5000 + i)


def test_the_dead_lease_stall_is_the_first_line(tmp_path):
    p = project(tmp_path, FACTORY)
    busy(p, approved=60, dead=True)
    a = held_up(p)
    assert a["stall"] is True and a["nothing_stuck"] is False
    assert a["line"].startswith("Stalled: queue's pool is full (1 of 1), and gap/q holds a place in it: "), a["line"]
    assert "60 items wait on it (60 gap in approved)" in a["line"] and "is gone" in a["line"], a["line"]
    assert "Next: the running engine's watchdog" in a["line"] and "ERGOSTAT_ITEM=gap/q " in a["line"], a["line"]
    assert "--nack" in a["roots"][0]["command"]


def test_the_budget_guard_stall_is_the_first_line(tmp_path):
    p = project(tmp_path, FACTORY)
    busy(p)
    for i in range(9):                                   # the runs ended, and every build since is refused
        p.events.add("ergostat.lease.ended", item=f"gap/w{i}", source="ergostat", at=NOW - 400,
                     data={"run": f"w{i}", "fence": 1, "how": "ack"})
        p.events.add("gap.built", item=f"gap/w{i}", at=NOW - 400)
    p.events.add("budget.refused", item="implementor", source="ergostat", at=NOW - 30,
                 data={"why": "38.00 spent and 4.00 reserved of 40 today; this run reserves 4"})
    a = held_up(p)
    assert a["line"].startswith("Stalled: the day's AI budget refuses implementor's runs: 38.00 spent"), a["line"]
    assert "20 items wait on it (20 gap in ready)" in a["line"] and "Next: the owner to raise budget" in a["line"]
    assert [x["class"] for x in a["roots"]].count("stall") == 1


def test_a_healthy_busy_system_reports_no_stall(tmp_path):
    p = project(tmp_path, FACTORY)
    busy(p)
    a = held_up(p)
    assert a["stall"] is False and a["nothing_stuck"] is True, a["roots"][:2]
    assert {x["class"] for x in a["roots"]} == {"queue"} and a["unfinished"] == 9 + 20 + 1 + 5
    assert a["line"].startswith("Nothing is stuck: 35 unfinished items are being worked, queueing or held on purpose. "
                                "The most held: implementor's pool is full: 9 of 9 runs"), a["line"]


def test_nothing_is_stuck_is_not_said_when_a_cause_is_not_known(tmp_path):
    p = project(tmp_path, FACTORY.replace("budget: {daily: 40, max-cost: 4}\n", ""))
    gap(p, "q", "defined", "started", "built", "approved")
    take(p, "gap/q", "queue", budgeted=False)            # no pid recorded: whether its run is alive is not known
    a = held_up(p)
    assert a["stall"] is False and a["nothing_stuck"] is False and a["roots"][0]["class"] == "unknown"
    assert a["line"].startswith("No stall found, but what holds 1 item is not known: "), a["line"]


def test_at_most_twenty_roots_are_listed_and_the_rest_counted(tmp_path):
    p = project(tmp_path, FACTORY)
    for i in range(25):                                  # each in progress outside ergostat: a root of its own
        gap(p, f"b{i}", "defined", "started", at=NOW - 3600 + i)
    a = held_up(p)
    assert len(a["roots"]) == 20 and a["more"] == 5 and a["unfinished"] == 25 and a["nothing_stuck"] is True


def test_the_most_held_is_found_and_listed_past_twenty_roots_ranked_above_it(tmp_path):
    p = project(tmp_path, FACTORY)
    busy(p, approved=60)                                 # the merge queue's pool full, 60 approved gaps waiting
    for i in range(25):                                  # each parked, nothing waits on it: held, ranked above queue
        gap(p, f"z{i}", "defined", "started", "parked", at=NOW - 3600 + i)
    a = held_up(p)
    assert a["stall"] is False and [x["class"] for x in a["roots"][:20]].count("held") == 20, a["roots"][:2]
    x = a["roots"][a["most"]]
    assert x["kind"] == "pool-full" and x["waiting"] == 60, x
    assert "The most held: queue's pool is full" in a["line"] and "60 items wait on it" in a["line"], a["line"]
    text = "\n".join(held.lines(a))
    assert "queue's pool is full" in text and "none holding more than the most held" in text
    assert len(a["roots"]) == 21 and a["more"] > 0 and a["most"] == 20


def test_roots_waited_on_within_a_rounding_of_each_other_rank_by_the_longer_wait(tmp_path):
    p = project(tmp_path, FACTORY)
    gap(p, "b1", "defined", "started", at=NOW - 3615)     # 10 s longer than b0: the same hours, rounded (0.97)
    gap(p, "b0", "defined", "started", at=NOW - 3605)
    a = held_up(p)
    assert [x["hours"] for x in a["roots"]] == [0.97, 0.97] and [x["item"] for x in a["roots"]] == ["gap/b1", "gap/b0"]


def test_items_whose_root_is_not_known_are_counted_past_twenty_roots(tmp_path):
    p = project(tmp_path, FACTORY.replace("budget: {daily: 40, max-cost: 4}\n", ""))
    for i in range(25):
        gap(p, f"q{i}", "defined", "started", "built", "approved")
        take(p, f"gap/q{i}", "queue", budgeted=False, run=f"q{i}")   # no pid: whether each run is alive is not known
    a = held_up(p)
    assert a["roots"][0]["class"] == "unknown" and a["unknown"] == 25 and len(a["roots"]) <= 21, a["roots"][:2]
    assert a["line"].startswith("No stall found, but what holds 25 items is not known: "), a["line"]


def test_an_empty_record_has_nothing_stuck(tmp_path):
    a = held_up(project(tmp_path, FACTORY))
    assert a["roots"] == [] and a["nothing_stuck"] is True and a["line"] == "Nothing is stuck: no item is unfinished."


# ---- 3. eighteen goals off with one root: one root, the goals folded under it

def goals_model(n: int) -> str:
    stocks = "".join(f"  approved-{i}:\n    unit: gaps\n    sensor: {{projection: gap, state: approved, where: {{area: a{i}}}, "
                     "every: 1m}\n" for i in range(n))
    goals = "".join(f"  few-approved-{i}:\n    stock: approved-{i}\n    hold: \"<= 0\"\n" for i in range(n))
    return FACTORY + f"stocks:\n{stocks}goals:\n{goals}"


def test_eighteen_goals_off_with_one_root_show_one_root_with_the_rest_folded_under_it(tmp_path):
    p = project(tmp_path, goals_model(18))
    gap(p, "q", "defined", "started", "built", "approved")
    take(p, "gap/q", "queue", pid=dead_pid())
    for i in range(18):
        gap(p, f"g{i}", "defined", "started", "built", "approved", at=NOW - 4000 + i, area=f"a{i}")
        p.events.add("loop.off", item=f"few-approved-{i}", source="ergostat", at=NOW - 3000, data={})
    a = held_up(p)
    assert len(a["goals"]["off"]) == 18 and a["goals"]["untraced"] == []
    assert len(a["roots"]) == 1, [x["says"] for x in a["roots"]]
    r = a["roots"][0]
    assert r["kind"] == "lease" and r["item"] == "gap/q" and r["goals"] == sorted(f"few-approved-{i}" for i in range(18))
    assert "18 items wait on it" in a["line"] and "18 goals off because of it" in a["line"], a["line"]
    p.events.add("loop.holding", item="few-approved-3", source="ergostat", at=NOW - 10, data={})
    p.events.add("loop.off", item="few-approved-4", source="ergostat", at=NOW - 10, data={})
    b = held_up(p)
    assert "few-approved-3" not in b["roots"][0]["goals"] and len(b["roots"][0]["goals"]) == 17, "by its last crossing"


def test_a_goal_off_with_nothing_unfinished_in_it_is_said_untraced(tmp_path):
    p = project(tmp_path, goals_model(2))
    p.events.add("loop.off", item="few-approved-0", source="ergostat", at=NOW - 3000, data={})
    a = held_up(p)
    assert a["goals"]["untraced"] == ["few-approved-0"]
    assert a["line"] == ("Nothing is stuck: no item is unfinished. 1 goal off, not traced to an unfinished item: "
                         "few-approved-0.")


# ---- the CLI, the API, MCP and the page's line answer the same; a failure is said, never raised

def test_cli_json_mcp_and_the_status_line_agree(tmp_path, capsys, monkeypatch):
    from ergostat.cli import main
    from ergostat.mcp import Server
    p = project(tmp_path, MODEL)
    nothing(p)
    assert main(["-C", str(tmp_path), "held-up", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["roots"][0]["kind"] == "nothing" and got["line"].startswith("Stalled: nothing takes note items")
    via = json.loads(Server(tmp_path).call("held_up", {})["content"][0]["text"])
    assert via["line"] == got["line"] and via["roots"][0]["says"] == got["roots"][0]["says"]
    assert main(["-C", str(tmp_path), "held-up"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == got["line"] and "stall" in out[2] and "nothing: nothing takes note items" in out[2]
    assert held.headline(p)["line"] == got["line"]
    held._LAST.clear()
    monkeypatch.setattr(held, "answer", lambda *a, **k: 1 / 0)
    said = held.headline(p)
    assert said["stall"] is None and said["line"].startswith("What holds the work up could not be worked out: "
                                                             "ZeroDivisionError")
    monkeypatch.setattr(held, "answer", lambda *a, **k: pytest.fail("worked out again with nothing new"))
    assert held.headline(p) == said, "the failure is kept like an answer, not tried on every poll"
    p.events.add("note.opened", item="note/2")
    monkeypatch.setattr(held, "answer", lambda *a, **k: {"line": "again", "stall": False, "nothing_stuck": True})
    assert held.headline(p)["line"] == "again", "worked out again once the record moves"
    held._LAST.clear()


def test_the_api_answers_and_status_carries_the_line(tmp_path):
    from ergostat.web.server import Live, _answer
    p = project(tmp_path, MODEL)
    nothing(p)
    held._LAST.clear()
    live = Live(p)
    got = _answer(live, "/held-up", {})
    assert got["roots"][0]["kind"] == "nothing" and got["stall"] is True
    st = _answer(live, "/status", {})
    assert st["held_up"]["stall"] is True and st["held_up"]["line"].startswith("Stalled: nothing takes note items")
    held._LAST.clear()


# ---- 4. quick on a factory-size record

@pytest.mark.serial
def test_factory_size_answer_under_200_ms(tmp_path):
    p = project(tmp_path, goals_model(18))
    rows = []
    for i in range(3000):
        moves = ["gap.found", "gap.defined", "gap.started", "gap.built", "gap.approved", "gap.merged"][: 2 + i % 5]
        rows += [{"type": t, "item": f"gap/g{i}", "at": NOW - 86400 + i * 20 + k * 3, "source": "t",
                  "data": ({"depends_on": f"gap/g{i - 1}"} if i % 7 else {}) | {"area": f"a{i % 18}"} if k == 0 else {}}
                 for k, t in enumerate(moves)]
    rows += [{"type": "loop.off", "item": f"few-approved-{i}", "at": NOW - 100, "source": "ergostat", "data": {}}
             for i in range(18)]
    p.events.add_many(rows)
    for i in range(9):
        take(p, f"gap/g{5 * i + 2}", "implementor", run=f"w{i}")
    take(p, "gap/g3", "queue", run="qq", pid=dead_pid())
    first = held_up(p)                                   # (the index built and caught up)
    assert first["stall"] is True and first["roots"][0]["item"] == "gap/g3", first["roots"][0]
    assert first["unfinished"] > 2000 and len(first["goals"]["off"]) == 18, first["roots"][0]
    best = min(_timed(lambda: held_up(p)) for _ in range(5))
    assert best < 0.200, f"{best * 1000:.0f} ms"


def _timed(f) -> float:
    t = time.perf_counter()
    f()
    return time.perf_counter() - t
