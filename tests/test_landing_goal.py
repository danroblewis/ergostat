"""landing-goal-reads-the-batch (dev/records/landing-goal-reads-the-batch.md): the merge pipeline's measures from its
batch items (dev/bin/landing.py, through measure.py), the goal main-moving and its reason, a waiting gap's place in
the why answer (ergostat/why/within.py), the pipeline manager reading the reason, and the goal drawn in both
diagrams. Each measure is checked against the hand-worked record below."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from functools import cache
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.leases import TAKEN
from ergostat.spec import read
from ergostat.store import Project
from ergostat.why import answer
from tests.test_factory_times import FAKE, load

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"
H = 3600.0
T0 = 1_800_000_000.0
NOW = T0 + 10 * H
landing = load("landing")


def run_(n: int, kind: str, outcome: str, minutes: float, **more) -> dict:
    return {"run": n, "kind": kind, "outcome": outcome, "minutes": minutes, **more}


def batch(iid: str, state: str, started: float, runs: list[dict], **fields) -> dict:
    return {"id": iid, "kind": "batch", "state": state, "first": started, "entered": started,
            "fields": {"started_at": started, "runs": runs, "run": len(runs), **fields}}


def gap(iid: str, state: str, approved: float | None = None, **fields) -> dict:
    return {"id": iid, "kind": "gap", "state": state, "first": T0, "entered": approved or T0,
            "fields": {**({"approved_at": approved} if approved is not None else {}), **fields}}


NO_SPACE = "OSError: [Errno 28] no space left on the temporary directory"
# The hand-worked record: three batches ended, the fourth on its sixth run, which crashed.
ENDED = [
    batch("batch/a-1", "landed", T0, [run_(1, "full", "passed", 30)], gaps=["gap/a", "gap/b"],
          landed=["gap/a", "gap/b"], landed_at=T0 + 0.5 * H, ended_at=T0 + 0.6 * H),
    batch("batch/c-2", "partial", T0 + 1 * H, [
        run_(1, "full", "failed", 40, failed=2, first_failing=["tests/t.py::x", "tests/t.py::y"]),
        run_(2, "named", "passed", 10), run_(3, "halves", "crashed", 25, crash="RuntimeError: docker went away")],
        gaps=["gap/c", "gap/d"], landed=["gap/c"], landed_at=T0 + 3 * H, ended_at=T0 + 3.1 * H),
    batch("batch/e-3", "given-back", T0 + 4 * H, [run_(1, "full", "crashed", 20, crash="ValueError: x")],
          gaps=["gap/e"], why="its run raised or was stopped before it settled", ended_at=T0 + 4.5 * H),
]
STALLED = batch("batch/f-4", "isolating", T0 + 5 * H, [
    run_(1, "full", "failed", 30, failed=1), run_(2, "named", "passed", 5), run_(3, "halves", "passed", 20),
    run_(4, "halves", "passed", 15), run_(5, "halves", "passed", 10), run_(6, "halves", "crashed", 12, crash=NO_SPACE)],
    gaps=["gap/f", "gap/g", "gap/h"], run_kind="halves", run_started_at=T0 + 8 * H)
WAITING = [gap("gap/f", "leased", T0 + 4.8 * H, lease={"block": "merge-queue", "holder": "r1"}),
           gap("gap/g", "approved", T0 + 4.9 * H), gap("gap/h", "approved", T0 + 6 * H)]
OTHERS = [gap("gap/a", "merged"), gap("gap/z", "building"),
          gap("gap/y", "leased", lease={"block": "implementor", "holder": "r2"})]


def measured(name: str, batches=None, gaps=None, now: float = NOW) -> float:
    return landing.reading(name, ENDED + [STALLED] if batches is None else batches,
                           WAITING + OTHERS if gaps is None else gaps, now, now - 14 * 86400)


@cache
def goal():
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [str(p) for p in problems if p.level == "error"] == []
    return spec, spec.goals["main-moving"]


def test_a_stalled_queue_turns_the_goal_off_and_its_reason_names_the_batch_run_and_cause():
    spec, g = goal()
    assert g.of.name == "main-stalled-minutes" and g.of.kind == "auxiliary"
    stalled = measured("main-stalled-minutes")
    assert stalled == 312.0                    # from gap/f's approval (4.8 h), later than main's last move (3 h)
    assert g.status(stalled, False) == "off"
    why = landing.reason(ENDED + [STALLED], WAITING + OTHERS, NOW)
    assert why == f"batch/f-4 (isolating, 3 gap(s)), run 6 (halves) crashed: {NO_SPACE}"


def test_an_empty_queue_does_not_turn_it_off():
    _, g = goal()
    idle = ENDED                                           # main last moved 7 h ago, and nothing waits
    assert measured("main-still-minutes", idle, OTHERS) == 420.0
    assert measured("main-stalled-minutes", idle, OTHERS) == 0.0
    assert g.status(0.0, False) == g.status(0.0, True) == "holding"
    fresh = [gap("gap/new", "approved", NOW - 300)]      # one approved 5 min ago: 5 min, not main's 7 h
    assert measured("main-stalled-minutes", idle, fresh + OTHERS) == 5.0
    assert g.status(5.0, False) == "holding"


def test_each_measure_against_the_hand_worked_record():
    assert measured("main-still-minutes") == 420.0        # batch/c-2 landed at 3 h; now is 10 h
    assert measured("batch-runs") == 1.667                 # the three ended: (1 + 3 + 1) / 3
    assert measured("batch-first-green") == 0.25           # a passed; c failed, e crashed, f failed
    assert measured("crash-lost-minutes") == 57.0          # c's run 3 (25), e's run 1 (20), f's run 6 (12)
    assert measured("gaps-landed-per-hour") == 0.125       # a's 2 and c's 1 within the day, over 24 hours
    later = NOW + 24 * H                                   # a day on: nothing landed in the day
    assert measured("gaps-landed-per-hour", now=later) == 0.0
    assert measured("crash-lost-minutes", now=NOW + 20 * 86400) == 0.0      # out of the window
    old = {**ENDED[1], "fields": {k: v for k, v in ENDED[1]["fields"].items() if k != "landed_at"}}
    assert measured("main-still-minutes", [ENDED[0], old]) == 540.0    # no landed_at: its start (1 h), never later


def test_a_landing_that_did_not_stand_does_not_move_main():
    # batch.landed said, then its push denied: failed, its merges undone, though the fold keeps landed and landed_at
    denied = batch("batch/d-7", "failed", T0 + 6 * H, [run_(1, "full", "passed", 20)], gaps=["gap/g", "gap/h"],
                   landed=["gap/g", "gap/h"], landed_at=T0 + 6.4 * H, ended_at=T0 + 6.5 * H, why="its push denied")
    pushing = batch("batch/p-8", "pushing", T0 + 7 * H, [run_(1, "full", "passed", 20)], gaps=["gap/g"],
                    landed=["gap/g"], landed_at=T0 + 7.4 * H)                  # its push not settled yet
    for b in (denied, pushing):
        batches = ENDED + [b]
        assert measured("main-still-minutes", batches) == 420.0              # batch/c-2's landing at 3 h stands
        assert measured("gaps-landed-per-hour", batches) == 0.125            # a's 2 and c's 1, not b's
        assert measured("main-stalled-minutes", batches, WAITING) == 312.0   # and the goal stays off
    stood = {**denied, "state": "partial"}
    assert measured("main-still-minutes", ENDED + [stood]) == 216.0          # one that stood: at 6.4 h


def test_a_measure_with_nothing_to_measure_has_no_value(tmp_path):
    for name in ("main-still-minutes", "batch-runs", "batch-first-green"):
        r = measure(tmp_path, name, [batch("batch/x-9", "testing", NOW - 60, [])], [])
        assert r.returncode == 1 and "no value" in r.stderr, (name, r.stdout, r.stderr)
    r = measure(tmp_path, "main-stalled-minutes", [], [])
    assert r.returncode == 0 and r.stdout.strip() == "0.0"


def test_a_run_under_way_and_no_batch_at_all_are_said():
    under = batch("batch/k-5", "testing", NOW - 2 * H, [run_(1, "full", "failed", 30, failed=3,
                                                                 first_failing=["tests/a.py::t"])],
                  gaps=["gap/k"], run_kind="named")
    under["fields"].update(run=2, run_started_at=NOW - 40 * 60)
    assert landing.reason([under], WAITING, NOW) == "batch/k-5 (testing, 1 gap(s)), run 2 (named) under way for 40 min"
    assert landing.run_said({**under, "fields": {**under["fields"], "run": 1}}, NOW) == \
        "run 1 (full) failed: 3 failed (tests/a.py::t)"
    assert landing.reason([], WAITING, NOW).startswith("no batch has run: 3 gap(s) wait")
    assert landing.reason(ENDED, WAITING, NOW).startswith(
        "no batch runs now (3 gap(s) wait): the last, batch/e-3, ended given-back: its run raised")


# measure.py as a script, its clock fixed at NOW: the record's windows never depend on the day the suite runs
CLOCKED = ("import runpy, sys, time; time.time = lambda: {now!r}; sys.path.insert(0, {bin!r}); "
           "sys.argv = [{script!r}, {name!r}]; runpy.run_path({script!r}, run_name='__main__')")


def measure(tmp_path: Path, name: str, batches: list[dict], gaps: list[dict],
            now: float = NOW) -> subprocess.CompletedProcess:
    (tmp_path / "fake.py").write_text(FAKE)
    (tmp_path / "record.json").write_text(json.dumps({"items": batches + gaps, "details": {}}))
    env = {**os.environ, "ERGOSTAT_CMD": f"{sys.executable} {tmp_path / 'fake.py'}"}
    code = CLOCKED.format(now=now,bin=str(BIN), script=str(BIN / "measure.py"), name=name)
    return subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=60)


def test_measure_py_reads_the_batch_items_and_prints_the_reason(tmp_path):
    items = ENDED + [STALLED]                              # (measure.py's clock is NOW: every batch in its window)
    r = measure(tmp_path, "main-stalled-why", items, WAITING + OTHERS)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"batch/f-4 (isolating, 3 gap(s)), run 6 (halves) crashed: {NO_SPACE}"
    r = measure(tmp_path, "crash-lost-minutes", items, WAITING + OTHERS)
    assert r.returncode == 0 and r.stdout.strip() == "57.0", r.stderr
    r = measure(tmp_path, "crash-lost-minutes", items, WAITING + OTHERS, now=NOW + 20 * 86400)
    assert r.returncode == 0 and float(r.stdout) == 0.0, r.stderr        # the clock given is the one read


def test_the_pipeline_manager_reads_the_reason_rather_than_the_queue_state(tmp_path):
    from tests.test_factory_manager import Pipe
    f = Pipe(tmp_path)
    (tmp_path / "instance" / "run").mkdir(exist_ok=True)
    (tmp_path / "instance" / "run" / "queue.json").write_text(json.dumps({"only-in-queue-json": "QJ-MARK"}))
    f.put("batch/f-4", "isolating", ago=5 * H, **{**STALLED["fields"], "started_at": f.now - 5 * H})
    f.put("gap/g", "approved", branch="g", approved_at=f.now - 4 * H)
    f.put("gap/old", "merged", branch="old", merged_at=f.now - 6 * H)
    sit = f.watch()
    reason = f"batch/f-4 (isolating, 3 gap(s)), run 6 (halves) crashed: {NO_SPACE}"
    assert sit["broken"]["no-merge"]["why"].endswith(f"while 1 approved gaps wait: {reason}")
    reply = {"calls": [], "answers": {t["print"]: "left" for t in sit["triggers"]}, "summary": "s"}
    f.run("manager.py", sit["id"], FACTORY_STANDIN_PIPELINE_MANAGER="```json\n" + json.dumps(reply) + "\n```")
    text = (f.model / f.item(sit["id"])["fields"]["context"]["brief"].removeprefix("file:")).read_text()
    assert f"## The merge queue\n\nThe goal main-moving's reason (`measure.py main-stalled-why`): {reason}" in text
    assert '"id": "batch/f-4"' in text and "QJ-MARK" not in text


# ---- a waiting gap's "why isn't this done?" names its batch and run, or how many batches are ahead of it

WHY = """
items:
  gap:
    id: gap/*
    states: [new, approved, queued, merged]        # (a gap arrives in its first state, as the factory's in open)
    on: {gap.opened: new, gap.approved: approved, gap.queued: queued, gap.merged: merged}
  batch:
    id: batch/*
    states: [testing, isolating, landed]
    final: [landed]
    on: {batch.started: testing, batch.run-started: testing, batch.run-finished: isolating, batch.ended-landed: landed}
    show: [size, run, outcome]
    relations:
      gaps: {kind: gap, precedence: false, inverse: batches}
messages:
  done: {gap: [merged], batch: [landed]}
blocks:
  queue:
    type: program
    run: "true"
    takes: {kind: gap, at: approved, to: [merged]}
    pool: 1
"""


def test_a_waiting_gap_s_why_names_its_batch_and_run_or_the_batches_ahead(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(WHY))
    p = Project(mdl.load(tmp_path))
    now = T0 + 100
    for g in ("gap/f", "gap/g", "gap/later"):
        p.events.add("gap.approved", item=g, at=T0)
    p.events.add("batch.started", item="batch/f-4", data={"gaps": ["gap/f", "gap/g"], "size": 2}, at=T0 + 10)
    p.events.add("batch.run-started", item="batch/f-4", data={"run": 6}, at=T0 + 20)
    p.events.add("batch.run-finished", item="batch/f-4", data={"outcome": "crashed"}, at=T0 + 30)
    up = {"running": True, "pid": os.getpid(), "beat": now, "said": "up"}
    a = answer(p, "gap/g", now=now, engine=up)
    assert a["place"]["in"] == [{"item": "batch/f-4", "kind": "batch", "state": "isolating",
                                 "shown": {"size": 2, "run": 6, "outcome": "crashed"}}]
    assert "It is in batch/f-4 (isolating; size 2; run 6; outcome crashed)." in a["summary"]
    b = answer(p, "gap/later", now=now, engine=up)
    assert b["place"] == {"in": [], "ahead": {"batch": {"n": 1, "latest": a["place"]["in"][0]}}}
    assert "ahead of it: 1 unfinished batch item, the latest batch/f-4 (isolating; size 2; run 6" in b["summary"]
    p.events.add("batch.ended-landed", item="batch/f-4", at=T0 + 40)
    c = answer(p, "gap/later", now=now, engine=up)
    assert c["place"] == {"in": [], "ahead": {}} and "batch" not in c["summary"]
    p.events.add("gap.queued", item="gap/q", at=T0 + 50)                         # a gap in another state: no batch
    p.events.add("batch.started", item="batch/q-5", data={"gaps": ["gap/q"], "size": 1}, at=T0 + 60)
    assert answer(p, "gap/later", now=now, engine=up)["place"]["ahead"] == {}   # it waits on no gap in approved
    # The queue's own batch of one: its gap taken from approved under a lease (as queue.py's merge-queue holds it)
    p.events.add("gap.approved", item="gap/r", at=T0 + 70)
    p.events.add(TAKEN, item="gap/r", source="ergostat", at=T0 + 75,
                 data={"run": "r1", "block": "queue", "fence": 1, "ttl": 1800, "max": 3})
    p.events.add("batch.started", item="batch/r-6", data={"gaps": ["gap/r"], "size": 1}, at=T0 + 80)
    d = answer(p, "gap/later", now=now, engine=up)
    assert answer(p, "gap/r", now=now, engine=up)["now"]["state"] == "leased"
    assert d["place"]["ahead"] == {"batch": {"n": 1, "latest": {"item": "batch/r-6", "kind": "batch",
                                                                 "state": "testing", "shown": {"size": 1}}}}
    assert "ahead of it: 1 unfinished batch item, the latest batch/r-6 (testing; size 1)" in d["summary"]
    # ... and then moved on to queued (queue.py's take(): gap.queued), as the real queue's head gap always is
    p.events.add("gap.queued", item="gap/r", at=T0 + 85)
    assert answer(p, "gap/r", now=now, engine=up)["now"]["state"] == "queued"
    e = answer(p, "gap/later", now=now, engine=up)
    assert e["place"]["ahead"] == d["place"]["ahead"]
    assert "ahead of it: 1 unfinished batch item, the latest batch/r-6 (testing; size 1)" in e["summary"]
    assert answer(p, "gap/q", now=now, engine=up)["place"]["in"][0]["item"] == "batch/q-5"   # (its own batch)
    # A gap in an earlier state, not waiting for the queue: gap/r left `new` too, but was never taken from it
    p.events.add("gap.opened", item="gap/early", at=T0 + 90)
    early = answer(p, "gap/early", now=now, engine=up)
    assert early["now"]["state"] == "new"
    assert early["place"] == {"in": [], "ahead": {}} and "ahead of it" not in early["summary"]
    assert answer(p, "gap/later", now=now, engine=up)["place"]["ahead"] == d["place"]["ahead"]   # (still ahead)
    # Taken from approved, then back in approved (its lease given back): counted by its state, as before, not twice
    p.events.add("gap.approved", item="gap/r", at=T0 + 95)
    assert answer(p, "gap/later", now=now, engine=up)["place"]["ahead"]["batch"]["n"] == 1
    assert answer(p, "gap/early", now=now, engine=up)["place"]["ahead"] == {}


def test_a_kind_no_relation_names_has_no_place(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(WHY))
    p = Project(mdl.load(tmp_path))
    p.events.add("batch.started", item="batch/x-1", data={"gaps": []}, at=T0)
    a = answer(p, "batch/x-1", now=T0 + 10, engine={"running": True, "pid": os.getpid(), "beat": T0, "said": "up"})
    assert a["place"] is None


# ---- the factory's model: checked, the goal read by the pipeline watch, drawn in both diagrams, and charted

def test_the_goal_is_in_the_factory_model_read_by_the_watch_and_charted():
    spec, g = goal()
    assert g.hold.value == 120 and g.tolerance == 30
    assert g.system == spec.auxiliaries["main-stalled-minutes"].system == "merging"   # beside its measure: no read
    assert "landing" in spec.chain(g.system)                                       # across managing's boundary
    assert "main-moving" not in {r.name for r in spec.blocks["pipeline-watch"].reads() if r.kind == "goal"}
    assert "main-moving" in {r.name for r in spec.blocks["merge-queue"].reads() if r.kind == "goal"}
    assert "merge-queue" in spec.loop("main-moving").controllers                # its loop closes inside landing
    for m in ("main-still-minutes", "batch-runs", "batch-first-green", "crash-lost-minutes", "gaps-landed-per-hour"):
        (s,) = spec.auxiliaries[m].sensors.values()
        assert s.run == f"python3 dev/bin/measure.py {m}", m
    d = spec.dashboards["landing.merge-pipeline"]
    (panel,) = d.panels
    refs = panel.params["refs"]
    refs = refs.split(",") if isinstance(refs, str) else refs
    assert panel.panel == "chart" and {str(r) for r in refs} >= {
        "auxiliary.main-stalled-minutes", "auxiliary.main-still-minutes", "auxiliary.batch-runs",
        "auxiliary.batch-first-green", "auxiliary.crash-lost-minutes", "auxiliary.gaps-landed-per-hour"}


NEW = ("main-moving", "main-stalled-minutes", "main-still-minutes", "batch-runs", "batch-first-green",
       "crash-lost-minutes", "gaps-landed-per-hour", "merge-pipeline")


@pytest.mark.slow
def test_ergostat_check_passes_on_the_factory_model_and_says_nothing_of_the_new_parts(tmp_path, capsys, monkeypatch):
    from ergostat.cli import main, spec_cmds
    from ergostat.numbers import extremes_cache
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(spec_cmds, "CHECK_WAIT", None)
    monkeypatch.setattr(extremes_cache, "BOUND", 900.0)
    main(["-C", str(ROOT), "check", "--json"])
    got = json.loads(capsys.readouterr().out)
    assert got["ok"], [x for x in got["found"] if x["level"] == "error"]
    said = [x for x in got["found"] if any(n in str(x.get("about")) for n in NEW)
            or (x["level"] != "note" and any(n in json.dumps(x) for n in NEW))]   # (a note on a whole system lists
    assert said == [], [x["message"] for x in said]                                # its parts: system-splits)


@pytest.mark.slow
def test_the_goal_renders_in_both_diagrams(tmp_path):
    from ergostat.web.server import Live, api
    (tmp_path / "state").mkdir()
    live = Live(Project(mdl.load(ROOT), directory=tmp_path / "state"))
    for view in ("dynamics", "blocks"):
        g = api(live, "graph", {"view": [view], "open": ["*"]})
        ids = {n["id"] for n in g["nodes"]}
        assert any("main-moving" in i for i in ids), (view, sorted(i for i in ids if "goal" in i)[:20])
