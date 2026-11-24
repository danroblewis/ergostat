"""Time in each state, the build-review loop and the gates, per gap (dev/bin/times.py), its measures (measure.py) and
the per-state table (status.py). docs/roadmap/overnight/state-times.md names these tests."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"
H = 3600.0
T0 = 1_800_000_000.0

FAKE = r'''
import json, sys
from pathlib import Path
db = json.loads(Path(__file__).with_name("record.json").read_text())
args = sys.argv[1:]
if args[0] == "item" and "--kind" in args:
    kind = args[args.index("--kind") + 1]
    got = [i for i in db["items"] if i["kind"] == kind]
    print(json.dumps({"items": got, "total": len(got)}))
elif args[0] == "item":
    print(json.dumps(db["details"][args[1]]))
else:
    sys.exit(f"the fake ergostat does not know {args}")
'''


def load(name: str):
    sys.path.insert(0, str(BIN))
    try:
        spec = importlib.util.spec_from_file_location(f"factory_{name}", BIN / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(BIN))


times = load("times")


def moves(*steps: tuple[str, float]) -> list[dict]:
    """The fold's moves: (state, hours from T0), in the record's order; a lease's take from the state before it."""
    out, was = [], None
    for i, (to, h) in enumerate(steps):
        out.append({"time": T0 + h * H, "from": was, "to": to, "event": f"e{i}",
                    "type": "ergostat.lease.taken" if to == "leased" else f"gap.{to}"})
        was = to
    return out


# open, ready, then built and reviewed three times: sent back to fix twice, parked by the third review
FIXED_TWICE = moves(("open", 0), ("ready", 1), ("leased", 2), ("building", 2.5), ("built", 4), ("in-review", 5),
                    ("fix", 6), ("leased", 7), ("building", 7.5), ("built", 9), ("in-review", 9.5),
                    ("fix", 10), ("leased", 12), ("building", 12.5), ("built", 14), ("in-review", 14.5),
                    ("parked", 15))


def run(tmp_path: Path, program: str, *argv: str, items=(), details=None) -> subprocess.CompletedProcess:
    (tmp_path / "fake.py").write_text(FAKE)
    (tmp_path / "record.json").write_text(json.dumps({"items": list(items), "details": details or {}}))
    env = {**os.environ, "ERGOSTAT_CMD": f"{sys.executable} {tmp_path / 'fake.py'}"}
    r = subprocess.run([sys.executable, str(BIN / program), *argv], cwd=tmp_path, env=env, capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r


def test_time_in_each_state_sums_visits_for_any_end(tmp_path):
    t = times.visits(FIXED_TWICE)
    assert t["fix"] == {"hours": 3.0, "visits": 2, "left": T0 + 12 * H}      # 1h, then 2h
    assert t["building"]["hours"] == 4.5 and t["building"]["visits"] == 3
    assert t["in-review"] == {"hours": 2.0, "visits": 3, "left": T0 + 15 * H}
    assert t["leased"]["visits"] == 3 and t["open"]["hours"] == 1.0
    assert "parked" not in t                     # the visit it is in now is not counted until it ends
    dead = times.visits(moves(("open", 0), ("ready", 1), ("leased", 3), ("dead", 4), ("parked", 4.25)))
    assert dead["dead"] == {"hours": 0.25, "visits": 1, "left": T0 + 4.25 * H} and dead["ready"]["hours"] == 2.0
    assert times.visits(moves(("open", 0))) == {}                       # still open: nothing closed yet

    gap = {"id": "gap/x", "kind": "gap", "state": "parked", "events": 40, "entered": T0 + 15 * H, "fields": {}}
    detail = {"id": "gap/x", "events": 40, "moves": FIXED_TWICE, "record": [], "record_total": 0}
    lines = [json.loads(x) for x in run(tmp_path, "times.py", items=[gap], details={"gap/x": detail}).stdout.splitlines()]
    assert [(x["event"], x["item"]) for x in lines] == [("gap.timed", "gap/x")]
    said = lines[0]["data"]
    assert said["time_in"]["fix"]["visits"] == 2 and said["loop_rounds"] == 3 and "timed_n" not in said
    assert json.loads((tmp_path / "run" / "times.json").read_text()) == {"gap/x": 41}   # its own gap.timed counted
    gap["events"], gap["fields"] = 41, said                       # timed, and nothing since: not read or said again
    assert run(tmp_path, "times.py", items=[gap], details={}).stdout == ""


def test_an_event_that_changes_no_timing_is_read_once(tmp_path):
    """review/state-times-1: the bookmark is kept outside the record and moves on every read, so a later event that
    changes no timing (gap.dependencies on a parked gap) is read once, and never holds a slot from an untimed gap."""
    marks = tmp_path / "times.json"
    detail = {"id": "gap/x", "events": 40, "moves": FIXED_TWICE, "record": [], "record_total": 0}
    timed = {"id": "gap/x", "kind": "gap", "state": "parked", "events": 40, "fields": {}}
    said, read = [], []
    was = times.fac.ergostat, times.fac.say, times.MOST

    def item(*args, **_):
        read.append(args[1])
        return type("R", (), {"stdout": json.dumps(details[args[1]])})()
    times.fac.ergostat, times.fac.say = item, lambda event, gid, **data: said.append((gid, data))
    try:
        details = {"gap/x": detail}
        times.write([timed], marks)
        timed["fields"], timed["events"] = said[0][1], 42           # its gap.timed, then a gap.dependencies
        details["gap/x"] = {**detail, "events": 42}
        assert times.write([timed], marks) == 1 and len(said) == 1  # read once, nothing changed: nothing said
        assert times.write([timed], marks) == 0                     # and not read again
        times.MOST = 1                                              # an untimed gap gets the run's one slot first
        new = {"id": "gap/a", "kind": "gap", "state": "open", "events": 3, "fields": {}}
        details["gap/a"] = {"id": "gap/a", "events": 3, "moves": FIXED_TWICE[:2], "record": [], "record_total": 0}
        timed["events"] = 43
        times.write([timed, new], marks)
        assert read[-1] == "gap/a" and said[-1][0] == "gap/a"
        new["fields"] = said[-1][1]
        marks.write_text("not json")                              # unreadable: read again, no change said twice
        times.MOST = 50
        assert times.write([timed, new], marks) == 2 and len(said) == 2
    finally:
        times.fac.ergostat, times.fac.say, times.MOST = was


def test_the_build_review_loop_counts_rounds_and_its_span():
    assert times.loop(FIXED_TWICE) == {"loop_rounds": 3, "loop_hours": 13.0, "loop_ended": T0 + 15 * H}
    # approved, then sent back by the queue (a conflict) and approved again: one loop to the last approval
    again = moves(("ready", 0), ("leased", 1), ("building", 1.25), ("built", 2), ("in-review", 2.5), ("approved", 3),
                  ("leased", 4), ("queued", 4.1), ("fix", 4.5), ("leased", 5), ("building", 5.25), ("built", 6),
                  ("in-review", 6.5), ("approved", 7), ("leased", 7.5), ("queued", 7.6), ("merged", 8))
    assert times.loop(again) == {"loop_rounds": 2, "loop_hours": 6.0, "loop_ended": T0 + 7 * H}
    going = moves(("ready", 0), ("leased", 1), ("building", 1.5), ("built", 3), ("in-review", 3.5), ("fix", 4))
    assert times.loop(going) == {"loop_rounds": 1, "loop_hours": 3.0, "loop_ended": None}     # still going round
    # sent back by the queue after its approval, not rebuilt yet: going round again, then parked from fix
    reopened = again[:9]
    assert times.loop(reopened) == {"loop_rounds": 1, "loop_hours": 3.5, "loop_ended": None}
    parked = reopened + moves(("parked", 6))[:1]
    assert times.loop(parked) == {"loop_rounds": 1, "loop_hours": 5.0, "loop_ended": T0 + 6 * H}
    assert times.loop(moves(("open", 0), ("ready", 1)))["loop_hours"] is None                 # never taken
    # a reviewer's lease (from built) does not start the loop; the implementor's (from ready) does
    assert times.loop(moves(("built", 0), ("leased", 1), ("in-review", 1.1), ("approved", 2)))["loop_hours"] is None


def test_gate_times_from_the_lease_and_queue_events():
    def ev(kind: str, h: float, **data) -> dict:
        return {"type": f"gap.{kind}", "time": T0 + h * H, "data": data}
    fast = {"ruff": {"rc": 0, "seconds": 30}, "unit": {"rc": 0, "seconds": 90}}
    got = times.gates([
        ev("measured", 1, build_failures=1, build_hours=0.25, suites_fast={**fast, "failed": "unit"}),
        ev("built", 2, build_hours=0.5, suites_fast=fast),
        ev("approved", 3, review_hours=0.25),
        ev("queue-failed", 4, suites_queue={"ruff": {"seconds": 5}, "unit": {"rc": 1, "seconds": 60}, "failed": "unit"}),
        ev("retried", 4.5),
        ev("merged", 5, suites_queue={"unit": {"seconds": 120}, "browser": {"seconds": 360}, "demo": {"seconds": 60}}),
        ev("push-asked", 5, push="held"),
        ev("pushed", 5 + 10 / 60, push="pushed"),
        ev("push-settled", 6, push="settled by the coordinator"),           # (its merge's push counted once)
    ])
    assert got["implementor"] == {"minutes": 45.0, "at": T0 + 2 * H}
    assert got["fast"]["minutes"] == 4.0 and got["review"]["minutes"] == 15.0
    assert got["unit"] == {"minutes": 3.0, "at": T0 + 5 * H}                 # both queue runs: 1 + 2
    assert got["browser"]["minutes"] == 6.0 and got["demo"]["minutes"] == 1.0
    assert got["push-wait"]["minutes"] == 10.0
    pushed_at_once = times.gates([ev("merged", 1), ev("push-asked", 1.5, push="pushed")])
    assert pushed_at_once == {"push-wait": {"minutes": 30.0, "at": T0 + 1.5 * H}}
    assert times.gates([ev("merged", 1), ev("push-asked", 1.1, push="held")]) == {}             # not pushed yet
    # the implementor's every try in a round (fast_seconds), not only the last suites_fast
    tries = times.gates([ev("built", 1, suites_fast=fast, fast_seconds=480)])
    assert tries["fast"]["minutes"] == 8.0
    assert set(times.WAITING) & set(times.WORKING) == set() and "queued" in times.WORKING
    assert {"queue-failed", "dead", "planned", "replan", "split"} <= set(times.WAITING)


def test_gates_survive_the_roll_up_of_a_gaps_record():
    """review/state-times-3: a record rolled up starts with a snapshot; the gate events are archived, so the gates
    start from the snapshot's (its last gap.timed) and only later events are added, the same on every re-read."""
    def ev(kind: str, h: float, **data) -> dict:
        return {"type": f"gap.{kind}", "time": T0 + h * H, "data": data}
    before = {"implementor": {"minutes": 45.0, "at": T0 + 2 * H}, "review": {"minutes": 15.0, "at": T0 + 3 * H}}
    snap = {"type": times.SNAPSHOT, "time": T0 + 5 * H, "set": {"gates": before},
            "data": {"rollup": {"state": "merged", "entered": T0 + 5 * H}}}
    later = [ev("dependencies", 200), ev("push-settled", 200.5, push="settled")]
    d = {"id": "gap/x", "moves": FIXED_TWICE, "record": [snap, *later], "record_total": 3}
    got = times.timing(d)["gates"]
    assert got["implementor"] == before["implementor"] and got["review"] == before["review"]
    assert got["push-wait"] == {"minutes": 195.5 * 60, "at": T0 + 200.5 * H}     # its merge was in the snapshot
    assert times.timing(d)["gates"] == got and before == snap["set"]["gates"]    # a re-read says the same
    pushed = {**before, "push-wait": {"minutes": 5.0, "at": T0 + 6 * H}}         # pushed before the roll-up
    d2 = {**d, "record": [{**snap, "set": {"gates": pushed}}, *later]}
    assert times.timing(d2)["gates"] == pushed                                   # not counted twice
    # added on: a build after the snapshot (a long record, read whole through `ergostat events`)
    was = times.fac.ergostat
    whole = [snap, ev("built", 201, build_hours=0.5), {"type": "ergostat.lease.renewed", "time": T0 + 201 * H}]
    times.fac.ergostat = lambda *a, **k: type("R", (), {"stdout": json.dumps(whole)})()
    try:
        long = times.timing({**d, "record": whole[1:], "record_total": 900})["gates"]
    finally:
        times.fac.ergostat = was
    assert long["implementor"]["minutes"] == 75.0 and long["review"] == before["review"]
    # rolled up before it was ever timed: unknown, not zero, and in no gate's measure
    blind = times.timing({**d, "record": [{**snap, "set": {}}, *later]})
    assert blind["gates"] is None and blind["loop_rounds"] == 3
    assert times.values("gate-review-minutes", [{"fields": blind}], 0) == []


def sent(kind: str, h: float, **data) -> dict:
    return {"type": f"gap.{kind}", "time": T0 + h * H, "data": data}


# a fixture's send-backs: two reviews, the queue, triage, measure-runs, the plan lint, a stray refusal; a build that
# failed its suites (no strays) and a gap.retried are no catch
CAUGHT = [sent("plan-sent-back", 1, plan_sent_back_by="lint"), sent("sent-back", 2, sent_back_by="review"),
          sent("measured", 3, build_failures=1, suites_fast={"failed": "unit", "tests": ["t"]}),
          sent("measured", 4, build_failures=1, suites_fast={"failed": "scratch files", "stray": ["x.py"]}),
          sent("sent-back", 5, sent_back_by="review"), sent("sent-back", 6, sent_back_by="queue"),
          sent("retried", 7), sent("sent-back", 8, sent_back_by="triage"),
          sent("sent-back", 9, sent_back_by="measure-runs")]


def test_catches_counted_per_gate_from_sent_back(tmp_path):
    d = {"id": "gap/x", "moves": FIXED_TWICE, "record": CAUGHT, "record_total": len(CAUGHT)}
    got = times.timing(d)
    assert got["catches"] == {"lint": 1, "review": 2, "strays": 1, "queue": 1, "triage": 1, "measure-runs": 1}
    assert got["catch_times"]["review"] == [T0 + 2 * H, T0 + 5 * H]
    assert times.timing({**d, "record": [], "record_total": 0})["catches"] == {}                  # nothing sent back: none, known
    # rolled up: the snapshot's catches kept, the later ones added; one timed before catches were counted is unknown
    snap = {"type": times.SNAPSHOT, "time": T0 + 10 * H, "set": {"gates": {}, "catch_times": got["catch_times"]}}
    again = times.timing({**d, "record_total": 2, "record": [snap, sent("sent-back", 11, sent_back_by="review")]})
    assert again["catches"] == {**got["catches"], "review": 3}
    old = times.timing({**d, "record_total": 2, "record": [{**snap, "set": {"gates": {}}}, sent("sent-back", 11, sent_back_by="review")]})
    assert old["catches"] is None and old["catch_times"] is None
    # measure.py gate-catches-GATE: the catches in the last 14 days, by each catch's own time, over every gap
    real = time.time()
    live = [{"id": "gap/a", "kind": "gap", "state": "merged", "events": 1, "entered": real,
             "fields": {"catch_times": {"review": [real - 86400, real - 20 * 86400], "queue": [real - 3600]}}},
            {"id": "gap/b", "kind": "gap", "state": "fix", "events": 1, "entered": real,
             "fields": {"catch_times": {"review": [real - 60]}}},
            {"id": "gap/c", "kind": "gap", "state": "open", "events": 1, "entered": real, "fields": {}}]
    r = run(tmp_path, "measure.py", "gate-catches-review", items=live)
    assert r.stdout.strip() == "2.0" and "1 gap(s) whose catches are unknown" in r.stderr
    assert run(tmp_path, "measure.py", "gate-catches-lint", items=live).stdout.strip() == "0.0"
    assert {f"gate-catches-{g}" for g in (*times.CATCHING, "unlisted")} <= set(times.measures())
    # the auxiliaries: one per listed gate, each sensed by its measure, with no goal; check finds no error
    from ergostat.spec import read
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    assert [p for p in problems if "gate-catches" in f"{p.about} {p.message}"] == []      # nor any other finding
    for g in (*times.CATCHING, "unlisted"):
        a = spec.auxiliaries[f"gate-catches-{g}"]
        assert a.system == "guarantees" and f"measure.py gate-catches-{g}" in str(a.sensors), g
    held = {(x.of.kind, x.of.name) for x in spec.goals.values()}
    assert not {n for k, n in held if k == "auxiliary" and n.startswith("gate-catches-")}


def test_an_unlisted_gate_is_counted_and_named(capsys):
    evs = [sent("sent-back", 1, sent_back_by="review"), sent("sent-back", 2, sent_back_by="stack-forward"),
           sent("sent-back", 3), sent("plan-sent-back", 4, plan_sent_back_by="someone-new")]
    got = times.timing({"id": "gap/x", "moves": FIXED_TWICE, "record": evs, "record_total": 4})
    assert got["catches"] == {"review": 1, "unlisted": 3}
    err = capsys.readouterr().err
    assert "gap/x: gap.sent-back by an unlisted sender 'stack-forward'" in err
    assert "gap.sent-back by an unlisted sender None" in err and "'someone-new'" in err
    assert times.caught("unlisted", [{"fields": got}], T0) == 3.0
    try:
        times.caught("nobody", [{"fields": got}], T0)
        raise AssertionError("a gate off the allowlist was read")
    except SystemExit as e:
        assert "no gate 'nobody'" in str(e)


def test_a_quiet_gate_reaches_the_simplifier_brief():
    simplify = load("simplify")
    now = T0 + 100 * 86400
    gaps = [{"id": "gap/a", "fields": {"catch_times": {"review": [now - 86400], "queue": [now - 40 * 86400]}}},
            {"id": "gap/b", "fields": {"catch_times": {"strays": [now - 29 * 86400]}}}]
    brief = simplify.definition("simplify-x-1", "dev/bin/x.py", 1.0, {"module": "dev/bin/x.py"}, gaps, now)
    line = brief[brief.index("## The quiet gates"):brief.index("## The rules")]
    assert "`queue`, `triage`, `lint`, `measure-runs`" in line                 # the queue's catch is 40 days old
    assert "`review`" not in line and "`strays`" not in line and "never to remove unasked" in line
    assert "{quiet_gates}" not in brief
    none = simplify.definition("simplify-x-1", "dev/bin/x.py", 1.0, {}, [{"id": "gap/c", "fields": {}}], now)
    assert "unknown (no gap's catches counted yet)" in none                    # never read as every gate quiet
    every = [{"id": "gap/d", "fields": {"catch_times": {g: [now - 60] for g in times.CATCHING}}}]
    assert "):\nnone. Each" in simplify.definition("s", "m", 1.0, {}, every, now)
    # some known, some unknown (rolled up or not timed before catches were counted): quiet only among the known,
    # with the unknown ones counted in the brief, never stated as plain 'no catch'
    mixed = simplify.definition("s", "m", 1.0, {}, [*gaps, {"id": "gap/c", "fields": {}},
                                                    {"id": "gap/e", "fields": {"catch_times": None}}], now)
    line = mixed[mixed.index("## The quiet gates"):mixed.index("## The rules")]
    assert "`queue`, `triage`, `lint`, `measure-runs`" in line
    assert "among the 2 gap(s) whose catches are counted; 2 gap(s) whose catches are unknown are left out" in line
    assert "unknown are left out" not in brief                                  # all known: no such clause


def gap(gid: str, state: str, ready_hours: float | None, left: float, **fields) -> dict:
    t = {"ready": {"hours": ready_hours, "visits": 1, "left": left}} if ready_hours is not None else {}
    return {"id": gid, "kind": "gap", "state": state, "events": 1, "entered": left,
            "fields": {"time_in": t, **fields}}


def test_a_measure_per_state_counts_gaps_that_left_it_not_only_merged_ones(tmp_path):
    now = T0 + 30 * 86400
    gaps = [gap("gap/a", "merged", 1, now - 86400), gap("gap/b", "parked", 2, now - 86400),
            gap("gap/c", "fix", 10, now - 3600),                     # still open, and it left ready in the window
            gap("gap/d", "merged", 3, now - 20 * 86400),            # left ready before the window: not counted
            gap("gap/e", "ready", None, now)]                       # in it now: not counted until it leaves
    since = now - 14 * 86400
    assert sorted(times.values("in-ready-hours", gaps, since)) == [1, 2, 10]
    assert times.reading("in-ready-hours", gaps, since) == 2 and times.reading("in-ready-hours-p90", gaps, since) == 10
    assert times.reading("in-fix-hours", gaps, since) == 0.0                                  # nothing: 0, as the medians
    # through measure.py, the factory's sensor, on the record's gaps (the window is the last 14 days)
    real = time.time()
    live = [gap("gap/a", "merged", 1, real - 86400), gap("gap/b", "parked", 4, real - 3600),
            gap("gap/c", "open", 7, real - 60, loop_rounds=2, loop_hours=5, loop_ended=real - 60)]
    assert run(tmp_path, "measure.py", "in-ready-hours", items=live).stdout.strip() == "4.0"
    assert run(tmp_path, "measure.py", "in-ready-hours-p90", items=live).stdout.strip() == "7.0"
    assert run(tmp_path, "measure.py", "loop-rounds", items=live).stdout.strip() == "2.0"
    # every goal in the model is on a measure's median (state-times-in-the-loop: the p90s are plain measures)
    held = times.goals()
    assert "in-ready-hours" in held and set(held) <= set(times.measures())
    # setpoints: each goal set to today's reading, where the window has one; the rest keep their own
    copy = tmp_path / "times.yaml"
    copy.write_text(times.GOALS.read_text())
    was = times.GOALS, times.fac.items
    times.GOALS, times.fac.items = copy, lambda kind, state=None: live
    try:
        times.setpoints(real)
        now_held = times.goals()
    finally:
        times.GOALS, times.fac.items = was
    assert now_held["in-ready-hours"] == 4 and "in-ready-hours-p90" not in now_held
    assert now_held["in-queued-hours"] == held["in-queued-hours"]


def test_status_prints_the_per_state_table(tmp_path):
    real = time.time()
    gaps = [gap("gap/a", "merged", 1, real - 86400), gap("gap/b", "parked", 3, real - 3600),
            gap("gap/c", "ready", None, real - 2 * 3600)]
    out = run(tmp_path, "status.py", items=gaps).stdout
    table = out[out.index("Time in each state"):].splitlines()
    assert table[1].split()[:4] == ["now", "(oldest)", "median", "p90"]
    ready = next(x for x in table if x.split()[:1] == ["ready"]).split()
    assert ready[:7] == ["ready", "1", "(2.0h)", "2", "3", "2", "2/-"], ready      # median 2, p90 3, of 2 that left
    rows = [x.strip().split()[0] for x in table[2:]]
    assert rows.index("waiting") < rows.index("open") < rows.index("working") < rows.index("building")
    assert {"loop", "span", "rounds", "gates", "unit", "push-wait"} <= set(rows)
