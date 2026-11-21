"""The pipeline manager (docs/roadmap/overnight/pipeline-manager.md): the watch's triggers and their deduplication
(dev/bin/watch.py), the tools and their checks (dev/bin/manage.py), the gated asks, and a whole run with the stand-in
AI (dev/bin/manager.py), on the fixture of tests/test_factory.py."""

from __future__ import annotations

import json
import time

from ergostat.spec import read
from tests.test_factory import ROOT, git, ready
from tests.test_factory_knowledge import Instance

H = 3600.0


class Pipe(Instance):
    """The knowledge fixture with the pipeline manager's settings, and items put straight into the record."""

    def __init__(self, tmp, manager: str = ""):
        super().__init__(tmp)
        self.config.write_text(self.config.read_text().replace(
            "[ai]\n", '[ai]\npipeline_manager_model = "opus"\npipeline_manager_session_usd = 1.0\n')
            + "[manager]\n" + manager)
        self.now = time.time()

    def put(self, iid: str, state: str, ago: float = 10 * H, entered: float | None = None, moves=None, **fields):
        db = self.db()
        kind = iid.split("/", 1)[0]
        db["items"][iid] = {"id": iid, "kind": kind, "state": state, "fields": fields, "first": self.now - ago,
                            "entered": self.now - (ago if entered is None else entered), "last": self.now - 60,
                            "moves": moves or []}
        self.record.write_text(json.dumps(db))

    def watch(self, *argv: str) -> dict | None:
        """One run of the watch: the situation it raised (its data, with its id), or None."""
        said, lines = self.run("watch.py", argv=argv)
        got = [x for x in lines if x.get("event") == "situation.raised"]
        assert len(got) <= 1 and said == ["situation.raised"] * len(got)
        return {"id": got[0]["item"], **got[0]["data"]} if got else None

    def handled(self, sid: str) -> None:
        self.fold([{"event": "situation.handled", "item": sid, "data": {}}], None)

    def manage(self, *argv: str, ok: bool = True) -> str:
        r = self.tool("manage.py", *argv, ok=ok)
        self.drain()
        return (r.stdout + r.stderr).strip()

    def interventions(self, by: str | None = None) -> list[dict]:
        return [i for i in self.db()["items"].values() if i["kind"] == "intervention"
                and (by is None or i["fields"].get("by") == by)]


def test_the_model_has_the_block_its_kind_triggers_and_gated_actions():
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    b = spec.blocks["pipeline-manager"]
    assert b.type == "ai" and b.pool == 1 and b.takes.kind == "situation"
    assert {"pipeline-watch", "manage-when"} <= set(spec.blocks)
    assert {"no-stuck-gaps", "situations-looked-at"} <= set(spec.goals)
    assert {"manager-close", "manager-park", "manager-pool", "manager-change"} <= set(spec.actions)
    assert all(spec.actions[a].gate == "approve" for a in ("manager-close", "manager-park", "manager-pool", "manager-change"))
    assert "closed" in spec.items["gap"].states and "situation" in spec.items["session"].relations
    for goal in ("no-stuck-gaps", "merge-pipeline-flowing", "situations-looked-at"):
        assert spec.loop(goal).closes, goal
    assert "minutes-since-manager" not in {g.of.name for g in spec.goals.values()}   # (a measure: it grows while idle)
    when = spec.blocks["manage-when"]
    assert set(when.inputs) == {"waiting", "open", "over"}      # it reads only what its expression uses
    assert {"stuck", "broken"} <= set(spec.blocks["pipeline-watch"].inputs) and spec.blocks["pipeline-watch"].every
    assert spec.goals["merge-pipeline-flowing"].hold.value == 0  # (minutes past [manager] broken_minutes)


def test_a_wait_the_pipeline_explains_is_not_stuck(tmp_path):
    f = Pipe(tmp_path)
    moves = [{"time": f.now - 9 * H, "from": "open", "to": "ready"}]
    f.put("gap/waiting", "ready", moves=moves, entered=9 * H)
    f.put("gap/busy", "building", entered=600)                 # the implementor's pool of one is full
    assert f.tool("watch.py", "stuck").stdout.strip() == "0"
    f.put("gap/busy", "merged")
    assert f.tool("watch.py", "stuck").stdout.strip() == "1"
    f.put("gap/waiting", "ready", moves=moves, entered=9 * H, waits_on_main="a" * 40)   # main-broken's wait
    assert f.tool("watch.py", "stuck").stdout.strip() == "0"


def subjects(sit: dict) -> list[str]:
    return [t["subject"] for t in sit["triggers"]]


def test_one_session_carries_every_standing_trigger_and_answers_each(tmp_path):
    f = Pipe(tmp_path)
    (tmp_path / "instance" / "run").mkdir(exist_ok=True)
    (tmp_path / "instance" / "run" / "queue.json").write_text(json.dumps(
        {"blocked": {"why": "the push failed", "intervention": "intervention/queue-1", "at": f.now - 60}}))
    f.put("intervention/queue-1", "open", reason="the merge queue stopped", recorded_at=f.now - 60, **{"class": "queue"})
    f.put("gap/p", "parked", title="P", branch="p", parked_at=f.now - H, where_it_stopped="main's own lease race")
    f.put("gap/long-dead", "dead", entered=2 * H, branch="long-dead", last_error="RuntimeError: lost")
    f.put("intervention/old", "open", recorded_at=f.now - 13 * H, reason="seeded by hand",
          **{"class": "factory-missing-capability"})
    sit = f.watch()
    assert sit["reason"] == "scheduled" and subjects(sit)[0] == "intervention/queue-1"
    assert set(subjects(sit)) == {"intervention/queue-1", "gap/p", "gap/long-dead", "intervention/old"}
    assert f.watch() is None                                   # one session at a time
    by = {t["subject"]: t["print"] for t in sit["triggers"]}
    answer = {"calls": [["continue", "gap/p", "--why", "main's own failure"], ["flake", "nope", "--why", "x"],
                        ["close", "gap/long-dead", "--why", "done elsewhere"]],
              "answers": {by["gap/p"]: "continued", by["gap/long-dead"]: "close asked", by["intervention/old"]: "left",
                          by["intervention/queue-1"]: "the push is the coordinator's"},
              "summary": "continued p; the queue needs its push"}
    said, _ = f.run("manager.py", sit["id"], FACTORY_STANDIN_PIPELINE_MANAGER="```json\n" + json.dumps(answer) + "\n```")
    f.drain()
    assert said == ["situation.handled"]
    s = f.item(sit["id"])
    assert s["state"] == "handled" and s["fields"]["triggers_n"] == 4 and s["fields"]["actions_n"] == 2
    assert [a["ok"] for a in s["fields"]["actions"]] == [True, False, True]
    assert {a["subject"]: a["answer"] for a in s["fields"]["answers"]}["gap/p"] == "continued"
    assert f.item("gap/p-continued")["fields"]["requested_by"] == "pipeline-manager"
    assert {i["fields"]["action"] for i in f.interventions("pipeline-manager")} == {"continue", "close"}
    assert all(i["fields"]["situation"] == sit["id"] for i in f.interventions("pipeline-manager"))
    text = (f.model / s["fields"]["context"]["brief"].removeprefix("file:")).read_text()
    for part in ("# This session", by["gap/p"], "main's own lease race", "## The merge queue", "## Main's recent commits",
                 "The velocity record", "The house rules", "continue GAP"):
        assert part in text
    (session,) = [i for i in f.db()["items"].values() if i["kind"] == "session"]
    assert session["fields"]["situation"] == [sit["id"]] and session["fields"]["role"] == "pipeline_manager"
    db = f.db()
    db["items"][sit["id"]]["fields"]["raised_at"] = f.now - 3 * H
    f.record.write_text(json.dumps(db))
    f.put("gap/new-park", "parked", branch="new-park", parked_at=f.now - 60)
    assert subjects(f.watch()) == ["gap/new-park"]             # what was answered is not carried again


def test_a_trigger_left_unanswered_or_a_failed_session_comes_back(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/a", "parked", branch="a", parked_at=f.now - H)
    f.put("gap/b", "parked", branch="b", parked_at=f.now - H)
    sit = f.watch()
    by = {t["subject"]: t["print"] for t in sit["triggers"]}
    reply = "```json\n" + json.dumps({"calls": [], "answers": {by["gap/a"]: "left"}, "summary": "s"}) + "\n```"
    f.run("manager.py", sit["id"], FACTORY_STANDIN_PIPELINE_MANAGER=reply)
    db = f.db()
    db["items"][sit["id"]]["fields"]["raised_at"] = f.now - 3 * H
    f.record.write_text(json.dumps(db))
    again = f.watch()
    assert subjects(again) == ["gap/b"]
    f.run("manager.py", again["id"], lease={"attempt": 2, "attempts": 2}, FACTORY_STANDIN_PIPELINE_MANAGER="no json")
    assert f.item(again["id"])["state"] == "failed"
    db = f.db()
    db["items"][again["id"]]["fields"]["raised_at"] = f.now - 3 * H
    f.record.write_text(json.dumps(db))
    f.put("gap/c", "ready", ago=60)                            # (the pipeline changed)
    assert subjects(f.watch()) == ["gap/b"]


def test_situations_of_the_one_trigger_watch_are_read_and_an_old_raised_one_is_superseded(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/a", "parked", branch="a", parked_at=f.now - H)
    f.put("gap/b", "parked", branch="b", parked_at=f.now - H)
    prints = f.py("import watch\nprint(json.dumps({g: watch.sit('parked', g, '', t)['print'] "
                  f"for g, t in (('gap/a', {f.now - H!r}), ('gap/b', {f.now - H!r}))}}))")
    f.put("situation/parked-a-1234", "handled", ago=3 * H, trigger="parked", subject="gap/a", print=prints["gap/a"],
          raised_at=f.now - 3 * H)
    f.put("situation/parked-b-5678", "raised", ago=3 * H, trigger="parked", subject="gap/b", print=prints["gap/b"],
          raised_at=f.now - 3 * H)
    assert f.watch() is None                                   # the old raised one is first closed
    said, _ = f.run("manager.py", "situation/parked-b-5678", FACTORY_STANDIN_PIPELINE_MANAGER="never asked")
    f.drain()
    assert said == ["situation.superseded"] and f.item("situation/parked-b-5678")["state"] == "superseded"
    assert [i for i in f.db()["items"].values() if i["kind"] == "session"] == []      # never run
    assert subjects(f.watch()) == ["gap/b"]                     # the old handled one is handled; the superseded is not


def test_each_situation_raised_has_its_own_id(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/a", "parked", branch="a", parked_at=f.now - H)
    code = ("import watch\ncfg = watch.fac.config()\nwatch.fac.items = lambda kind, *s: [] if kind == 'situation' else "
            "ITEMS(kind, *s)\nids = [watch.raise_one(cfg, 1.8e9)['id'] for _ in range(2)]\nprint(json.dumps(ids))")
    a, b = f.py("ITEMS = __import__('fac').items\n" + code)
    assert a != b and a.startswith("situation/scheduled-")


def test_nothing_changed_means_no_session(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/r", "ready", ago=60, branch="r")
    first = f.watch()
    assert first["reason"] == "scheduled" and first["triggers"] == []
    f.handled(first["id"])
    assert f.watch() is None                                   # not due
    db = f.db()
    db["items"][first["id"]]["fields"]["raised_at"] = f.now - 3 * H
    f.record.write_text(json.dumps(db))
    assert f.watch() is None                                   # due, and nothing changed
    f.put("gap/new", "ready", ago=60, branch="new")
    assert f.watch()["reason"] == "scheduled"                  # due, and it changed


def after_a_session(f: Pipe) -> str:
    """A session just handled, so the schedule is not due."""
    first = f.watch()
    f.handled(first["id"])
    db = f.db()
    db["items"][first["id"]]["fields"]["raised_at"] = f.now - 31 * 60        # (past the least time between sessions)
    f.record.write_text(json.dumps(db))
    return first["id"]


def queue_json(f: Pipe, **st) -> None:
    (f.model / "run").mkdir(exist_ok=True)
    (f.model / "run" / "queue.json").write_text(json.dumps(st))


def test_a_broken_pipeline_starts_a_session_at_once(tmp_path):
    f = Pipe(tmp_path)
    after_a_session(f)
    queue_json(f, pending={"sha": "a" * 40, "gaps": ["gap/x"], "at": f.now - 10 * 60})
    assert f.watch() is None                                   # younger than broken_minutes
    queue_json(f, pending={"sha": "a" * 40, "gaps": ["gap/x"], "at": f.now - 40 * 60})
    got = f.watch()
    assert got["reason"] == "broken" and list(got["broken"]) == ["push"]
    f.handled(got["id"])
    db = f.db()
    db["items"][got["id"]]["fields"]["raised_at"] = f.now - 31 * 60
    f.record.write_text(json.dumps(db))
    assert f.watch() is None                                   # the same break, already looked at
    queue_json(f, pending={"sha": "b" * 40, "gaps": ["gap/y"], "at": f.now - 35 * 60})
    assert f.watch()["reason"] == "broken"                     # another push, its own clock


def test_a_break_that_persists_never_relaunches_a_failing_session_every_run(tmp_path):
    f = Pipe(tmp_path)
    after_a_session(f)
    queue_json(f, blocked={"why": "push failed", "intervention": "intervention/q", "at": f.now - 40 * 60})
    got = f.watch()
    f.fold([{"event": "situation.failed", "item": got["id"], "data": {}}], None)
    assert f.watch() is None                                   # raised a moment ago: not again at once
    db = f.db()
    db["items"][got["id"]]["fields"]["raised_at"] = f.now - 31 * 60
    f.record.write_text(json.dumps(db))
    assert f.watch()["reason"] == "broken"                     # it failed: not handled, so it comes back


def test_each_broken_condition(tmp_path):
    f = Pipe(tmp_path)
    old = f.now - 2 * H
    f.put("gap/m", "merged", merged_at=old)
    f.put("gap/a", "approved", approved_at=old + 60)
    f.put("intervention/main-1", "open", main="a" * 12, tests=["tests/t.py::x"], **{"class": "main-broken"})
    f.put("intervention/main-2", "open", main="b" * 12, tests=["tests/t.py::x", "tests/t.py::y"], **{"class": "main-broken"})
    queue_json(f, blocked={"why": "w", "intervention": "intervention/q", "at": old})
    code = ("import watch\nwatch.load.reading = lambda w: {'suites': 99}.get(w, 0)\ncfg = watch.fac.config()\n"
            "cfg['load']['wait'] = True\ngaps = {g['id']: g for g in watch.fac.items('gap')}\n"
            "print(json.dumps(sorted(watch.broken(cfg, gaps, [], time.time()))))\nprint(json.dumps(sorted(watch.broken("
            "cfg, gaps, [], time.time() + 3600))))")
    got = f.py("import time\n" + code)
    assert got == ["blocked", "interlock", "main-twice", "no-merge"]   # (the interlock's own clock, an hour on)
    f.put("intervention/main-1", "remedied", main="a" * 12, tests=["tests/t.py::x"], remedy="fixed in c0ffee",
          **{"class": "main-broken"})
    assert "main-twice" not in f.py("import time\n" + code)            # remedied: once on one main commit only


def test_the_broken_reading_is_the_minutes_past_broken_minutes(tmp_path):
    f = Pipe(tmp_path, manager="broken_minutes = 20\n")
    queue_json(f, pending={"sha": "a" * 40, "gaps": ["gap/x"], "at": f.now - 50 * 60})
    assert 29.5 <= float(f.tool("watch.py", "broken").stdout) <= 31             # 50 minutes broken, 20 of them allowed
    queue_json(f, pending={"sha": "a" * 40, "gaps": ["gap/x"], "at": f.now - 10 * 60})
    assert float(f.tool("watch.py", "broken").stdout) == 0                     # within broken_minutes: flowing


def test_deferred_and_cancelled_parks_are_not_triggers(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/d", "parked", branch="d", parked_at=f.now - H, deferred=True)
    f.put("gap/c", "parked", branch="c", parked_at=f.now - H, cancelled=True)
    f.put("gap/old", "parked", branch="old", parked_at=f.now - 72 * H)
    f.put("gap/carried", "parked", branch="carried", parked_at=f.now - H)
    f.put("gap/carried-on", "open", continues="carried")
    f.put("gap/p", "parked", branch="p", parked_at=f.now - H)
    assert subjects(f.watch()) == ["gap/p"]


def test_a_gap_stuck_in_its_state_from_its_moves_and_from_state_times(tmp_path):
    f = Pipe(tmp_path)
    bounces = [{"time": f.now - 8 * H, "from": "building", "to": "fix"},
               {"time": f.now - 600, "from": "fix", "to": "leased"}, {"time": f.now - 60, "from": "leased", "to": "fix"}]
    f.put("gap/slow", "fix", entered=60, moves=bounces, branch="slow")                   # 8 hours in fix, not 1 minute
    f.put("gap/fresh", "fix", entered=60, moves=bounces[1:], branch="fresh")             # in fix 10 minutes
    f.put("gap/timed", "built", entered=60, moves=bounces[1:], time_in={"built": {"hours": 3.0, "visits": 2}})
    assert f.tool("watch.py", "stuck").stdout.strip() == "2"
    sit = f.watch()
    assert subjects(sit) == ["gap/slow", "gap/timed"] and "8.0h" in sit["triggers"][0]["why"]


def test_only_unremedied_defects_are_triggers_and_never_the_managers_own(tmp_path):
    f = Pipe(tmp_path)
    old = f.now - 20 * H
    f.put("intervention/mine", "open", recorded_at=old, by="pipeline-manager", **{"class": "flake"})
    f.put("intervention/recent", "open", recorded_at=f.now - H, by="claude-coordinator")
    f.put("intervention/pools-raised", "open", recorded_at=old, **{"class": "operator-decision"})
    f.put("intervention/tuned", "open", recorded_at=old, **{"class": "factory-tuning"})
    f.put("intervention/not-ours", "open", recorded_at=old, factory=False, **{"class": "environment-defect"})
    f.put("intervention/said-remedied", "open", recorded_at=old, remedy="fixed", **{"class": "main-broken"})
    f.put("intervention/d0", "open", recorded_at=old, **{"class": "scope-creep"})
    f.put("intervention/d1", "open", recorded_at=old + 1, **{"class": "something-new"})
    assert subjects(f.watch()) == ["intervention/d0", "intervention/d1"]


def test_paused_raises_nothing(tmp_path):
    f = Pipe(tmp_path, manager="open = 0\n")
    f.put("gap/p", "parked", parked_at=f.now - H, branch="p")
    assert f.watch() is None and f.tool("watch.py", "open").stdout.strip() == "0"


def test_most_actions_a_session_is_held(tmp_path):
    f = Pipe(tmp_path, manager="most_actions = 1\n")
    f.put("gap/p", "parked", branch="p", parked_at=f.now - H)
    sit = f.watch()
    calls = [["flake", f"tests/test_x.py::t{n}", "--why", "w"] for n in range(2)]
    reply = "```json\n" + json.dumps({"calls": calls, "answers": {}, "summary": "s"}) + "\n```"
    f.run("manager.py", sit["id"], FACTORY_STANDIN_PIPELINE_MANAGER=reply)
    f.drain()
    acts = f.item(sit["id"])["fields"]["actions"]
    assert [a["ok"] for a in acts] == [True, False] and "at most 1" in acts[1]["said"]


def test_most_actions_has_a_floor_and_a_ceiling(tmp_path):
    """A negative most_actions would run all but the last calls ([:-5]); a huge one lets one session start many gaps."""
    read = "import watch\nprint(json.dumps(watch.settings(watch.fac.config())['most']))"
    for said, held in (("-5", 1), ("0", 1), ("500", 12), ("8", 8)):
        assert Pipe(tmp_path / said, manager=f"most_actions = {said}\n").py(read) == held, said


def test_a_goal_the_watch_or_the_review_cannot_find_never_passes_silently(tmp_path):
    """The interlock's limits and the review's goals are read from the model by name: one renamed or reworded is a
    broken condition (the interlock's) or the binding constraint (the review's), said, never left out."""
    f = Pipe(tmp_path)
    renamed = "{'suites': 'machine-quiet-renamed', 'threads': 'suite-threads-within', 'memory': 'suite-memory-within'}"
    code = ("import time, watch\nwatch.load.reading = lambda w: 0\ncfg = watch.fac.config()\n"
            "watch.INTERLOCK = {INTERLOCK}\nprint(json.dumps(watch.conditions(cfg, {}, [], time.time())))")
    assert "interlock" not in f.py(code.replace("{INTERLOCK}", "watch.INTERLOCK"))    # every limit found, none over
    got = f.py(code.replace("{INTERLOCK}", renamed))
    assert "machine-quiet-renamed" in got["interlock"] and "no hold" in got["interlock"]
    f.put("gap/m0", "merged", merged_at=f.now - H, approved_at=f.now - 8 * H, queued_at=f.now - 2 * H,
          queue_wait_hours=5.0, batch_id="b1", batch_runs=1, queue_minutes=30.0)      # queue-wait-short off by 2.5
    read = ("import manager\nmanager.GOALS = ({GOALS})\n"
            "print(json.dumps(manager.velocity(manager.fac.config()), default=str))")
    assert f.py(read.replace("{GOALS}", "manager.GOALS"))["binding"] == "queue-wait-short"
    got = f.py(read.replace("{GOALS}", "('queue-wait-hours', 'queue-wait-short'), ('suite-minutes', 'suites-renamed')"))
    assert got["binding"] == "suites-renamed" and got["goals"]["suites-renamed"]["off"] is None
    assert "no hold" in got["goals"]["suites-renamed"]["unknown"]


DEFINITION = "# {b}: a change\n\ndepends-on: []\n\n## Definition of done\n\nIt holds.\n\n## Size budget\n\n50 net lines.\n"


def test_the_review_proposes_at_most_one_gap_and_asks_at_most_one_question(tmp_path):
    f = Pipe(tmp_path)
    assert "requested" in f.manage("propose", "--title", "Test selection", "--branch", "test-selection",
                                   "--definition-text", DEFINITION.format(b="test-selection"), "--why", "suites bind")
    assert f.item("gap/test-selection")["fields"]["velocity"] is True
    assert "one at a time" in f.manage("propose", "--title", "Sharding", "--branch", "sharding", "--definition-text",
                                       DEFINITION.format(b="sharding"), ok=False)
    f.put("gap/test-selection", "merged", velocity=True, branch="test-selection")
    assert "requested" in f.manage("propose", "--title", "Sharding", "--branch", "sharding", "--definition-text",
                                   DEFINITION.format(b="sharding"))
    assert " asked" in f.manage("ask", "How much would selecting tests by changed files save?", "--why", "suites bind")
    assert "one at a time" in f.manage("ask", "Would caching the environments save time?", "--why", "x", ok=False)
    (r,) = [i for i in f.db()["items"].values() if i["kind"] == "research"]
    assert r["state"] == "asked" and r["fields"]["asked_by"] == "coordinator"
    assert {"velocity", "velocity-research"} <= {i["fields"]["class"] for i in f.interventions()}


def test_the_velocity_record_reads_batches_goals_and_the_researchers_answers(tmp_path):
    f = Pipe(tmp_path)
    for n, (batch, runs) in enumerate((("b1", 1), ("b1", 1), ("b2", 3))):
        f.put(f"gap/m{n}", "merged", merged_at=f.now - H, ready_at=f.now - 9 * H, approved_at=f.now - 8 * H, queued_at=f.now - 2 * H,
              queue_wait_hours=5.0, batch_id=batch, batch_size=2, batch_runs=runs, queue_minutes=30.0)
    f.put("research/r1", "answered", asked_by="pipeline-manager", question="q?", summary="select by changed files")
    f.put("research/other", "answered", asked_by="coordinator", question="other?", summary="no")
    got = f.py("import manager\nprint(json.dumps(manager.velocity(manager.fac.config()), default=str))")
    assert got["batches"]["n"] == 2 and got["batches"]["bisected"] == 1 and got["batches"]["minutes-per-merge"] == 20.0
    assert got["binding"] == "queue-wait-short" and got["goals"]["queue-wait-short"]["off"] == 2.5
    assert [r["summary"] for r in got["research"]] == ["select by changed files"]


def test_a_first_pass_yield_of_zero_is_the_worst_case_and_binds(tmp_path):
    """first-pass-good holds `>= 0.6`: a yield of 0 is furthest off, not on target; one between 0 and the setpoint is
    off by the setpoint over it, and one above the setpoint is on the right side (off under 1)."""
    f = Pipe(tmp_path)
    f.put("gap/m0", "merged", merged_at=f.now - H, approved_at=f.now - 8 * H, queued_at=f.now - 2 * H,
          queue_wait_hours=5.0, batch_id="b1", batch_runs=1, queue_minutes=30.0)      # queue-wait-short off by 2.5
    read = "import manager\nprint(json.dumps(manager.velocity(manager.fac.config()), default=str))"
    for verdicts, off, binding in ((["fix", "fix"], 60.0, "first-pass-good"), (["merge", "fix"], 1.2, "queue-wait-short"),
                                   (["merge", "merge"], 0.6, "queue-wait-short")):
        for n, v in enumerate(verdicts):
            f.put(f"review/r{n}", "written", written_at=f.now - H, round=1, verdict=v, gap=f"gap/g{n}")
        got = f.py(read)
        assert got["goals"]["first-pass-good"]["off"] == off and got["binding"] == binding, (verdicts, got["goals"])
    f.put("gap/m0", "merged", merged_at=f.now - H, queue_wait_hours=0.5, batch_id="b1", queue_minutes=30.0)
    f.put("review/r0", "written", written_at=f.now - H, round=1, verdict="merge", gap="gap/g0")
    f.put("review/r1", "written", written_at=f.now - H, round=1, verdict="fix", gap="gap/g1")
    assert f.py(read)["binding"] == "first-pass-good"                  # 0.5 against 0.6: the goal furthest off now


def test_the_sessions_are_measured(tmp_path):
    f = Pipe(tmp_path)
    for n, (t, a) in enumerate(((4, 2), (2, 0))):
        f.put(f"situation/s{n}", "handled", handled_at=f.now - H, triggers_n=t, actions_n=a)
    assert f.py("import measure\nprint(measure.reading('manager-triggers-per-session'))") == 3.0
    assert f.py("import measure\nprint(measure.reading('manager-actions-per-session'))") == 1.0


def test_continue_asks_for_a_gap_on_the_parked_branch_once(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/p", "parked", title="P", branch="p", parked_at=f.now)
    f.put("gap/r", "ready", branch="r")
    f.put("gap/fix-it", "open", branch="fix-it")
    assert "gap/p-continued requested" in f.manage("continue", "gap/p", "--depends-on", "fix-it", "--why", "main's own")
    g = f.item("gap/p-continued")
    assert g["fields"]["continues"] == "p" and g["fields"]["depends_on"] == ["gap/fix-it"] and g["state"] == "open"
    assert "held by gap/p-continued" in f.manage("continue", "gap/p", ok=False)     # one gap per branch
    assert "only a parked" in f.manage("continue", "gap/r", ok=False)
    (i,) = f.interventions()
    assert i["fields"]["class"] == "parked-continued" and i["fields"]["by"] == "coordinator" and i["state"] == "open"


def failed_in_the_queue(f: Pipe) -> str:
    gid = ready(f)
    f.run("implement.py", gid)
    f.run("review.py", gid)
    g = f.db()
    g["items"][gid]["state"] = "queue-failed"
    g["items"][gid]["fields"].update(failed_suite="unit", failed_tests=["tests/test_x.py::test_a"])
    f.record.write_text(json.dumps(g))
    return gid


def test_reapprove_is_refused_unless_the_tests_fail_on_main_too(tmp_path):
    f = Pipe(tmp_path)
    gid = failed_in_the_queue(f)
    assert "not environmental" in f.manage("reapprove", gid, "--why", "looks like main's", ok=False)
    assert f.item(gid)["state"] == "queue-failed" and f.interventions() == []
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"',
                                                     "rerun = 'printf \"FAILED %s\\n\" {tests}; false'"))
    assert "back to approved" in f.manage("reapprove", gid, "--why", "the socket test fails on main")
    g = f.item(gid)
    assert g["state"] == "approved" and g["fields"]["approved_by"] == "manager-reapprove"
    assert g["fields"]["reapproved"]["where"] == "checkout" and (tmp_path / "wt" / ".manager").is_dir()
    (i,) = f.interventions()
    assert i["fields"]["class"] == "environment-defect" and i["fields"]["tests"] == ["tests/test_x.py::test_a"]


def test_reapprove_takes_a_fast_suite_failure_to_built_and_refuses_a_moved_branch(tmp_path):
    f = Pipe(tmp_path)
    gid = failed_in_the_queue(f)
    db = f.db()
    fields = db["items"][gid]["fields"]
    db["items"][gid]["state"] = "fix"
    fields.update(failed_tests=[], suites_fast={"failed": "unit", "tests": ["tests/test_y.py::test_b"]})
    f.record.write_text(json.dumps(db))
    assert "not environmental" in f.manage("reapprove", gid, "--why", "fails on main?", ok=False)  # (passes there)
    f.config.write_text(f.config.read_text().replace('alone = "true {tests}"',
                                                     "alone = 'printf \"FAILED %s\\n\" {tests}; false'"))
    assert "back to built" in f.manage("reapprove", gid, "--why", "fails only in the container, on main too")
    assert f.item(gid)["state"] == "built" and f.item(gid)["fields"]["head"] == fields["head"]
    db = f.db()
    db["items"][gid]["state"] = "fix"
    db["items"][gid]["fields"]["head"] = "0" * 40
    f.record.write_text(json.dumps(db))
    assert "moved since" in f.manage("reapprove", gid, "--why", "again", ok=False)
    f.put("gap/plain", "fix", branch="plain")
    assert "no failure of named tests" in f.manage("reapprove", "gap/plain", "--why", "x", ok=False)


def test_flake_and_file_gap(tmp_path):
    f = Pipe(tmp_path)
    assert "recorded as a flake" in f.manage("flake", "tests/test_x.py::test_a", "--why", "passes alone, thrice")
    assert f.item("flake/tests-test-x-py-test-a")["fields"]["by"] == "coordinator"
    assert "not a test id" in f.manage("flake", "rm -rf", "--why", "x", ok=False)
    text = "# lease-race: a fix\n\ndepends-on: []\n\n## Definition of done\n\nIt holds.\n\n## Size budget\n\n50 net lines.\n"
    assert "gap/lease-race requested" in f.manage("file-gap", "--title", "Lease race", "--branch", "lease-race",
                                                   "--definition-text", text, "--why", "parked two gaps")
    g = f.item("gap/lease-race")
    assert g["fields"]["definition"] == "run/defs/lease-race.md" and g["fields"]["requested_by"] == "coordinator"
    assert (tmp_path / "instance" / "run" / "defs" / "lease-race.md").read_text().startswith("# lease-race")
    assert "exists" in f.manage("file-gap", "--title", "Lease race", "--branch", "lease-race", "--definition-text", text,
                                ok=False)
    assert "Definition of done" in f.manage("file-gap", "--title", "Vague", "--definition-text", "do it", ok=False)
    assert sorted(i["fields"]["class"] for i in f.interventions()) == ["flake", "missing-gap"]


def test_remedy_and_a_queue_one_only_once_main_is_not_ahead(tmp_path):
    f = Pipe(tmp_path)
    f.put("intervention/old", "open", **{"class": "environment-defect"})
    f.put("intervention/queue-1", "open", **{"class": "queue"})
    assert "remedied" in f.manage("remedy", "intervention/old", "--why", "gitident landed (9444ac1)")
    assert f.item("intervention/old")["state"] == "remedied"
    assert "not open" in f.manage("remedy", "intervention/old", "--why", "again", ok=False)
    (f.checkout / "more.py").write_text("x = 1\n")
    git(f.checkout, "add", "-A")
    git(f.checkout, "commit", "-q", "-m", "an unpushed merge")
    assert "ahead of origin" in f.manage("remedy", "intervention/queue-1", "--why", "pushed", ok=False)
    git(f.checkout, "push", "-q", "origin", "main")
    assert "remedied" in f.manage("remedy", "intervention/queue-1", "--why", "the coordinator pushed it")
    assert [i["fields"]["action"] for i in f.interventions("coordinator")] == ["remedy", "remedy"]


def test_gated_asks_are_held_and_their_commands_run_once_approved(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/dup", "open", branch="dup", title="Dup")
    f.put("gap/stuck", "fix", branch="stuck")
    for argv in (["close", "gap/dup"], ["park", "gap/stuck"], ["pool", "implementor", "2"],
                 ["change", "--what", "suite_fix_rounds = 2 in factory.local.toml"]):
        assert "held for the coordinator" in f.manage(*argv, "--why", "the evidence")
    assert [a[1] for a in f.db()["acts"]] == ["manager-close", "manager-park", "manager-pool", "manager-change"]
    assert f.item("gap/dup")["state"] == "open" and f.item("gap/stuck")["state"] == "fix"    # nothing moved
    assert all(i["fields"]["held"] for i in f.interventions())
    assert sorted(i["fields"]["class"] for i in f.interventions()) == ["factory-change", "groom", "operator-decision",
                                                                       "stuck"]
    for argv in (["closed", "gap/dup", "a", "duplicate"], ["parked", "gap/stuck", "held", "by", "main"]):
        f.tool("manage.py", *argv)
    f.drain()
    assert f.item("gap/dup")["state"] == "closed" and f.item("gap/dup")["fields"]["closed_by"] == "pipeline-manager"
    assert f.item("gap/stuck")["state"] == "parked" and f.item("gap/stuck")["fields"]["parked_in"] == "manager"
    db = f.db()
    db["act_reply"] = {"rc": 2, "id": False}                    # (asked outside the block's run: refused)
    f.record.write_text(json.dumps(db))
    assert "was not asked" in f.manage("pool", "reviewer", "2", "--why", "x", ok=False)
    assert "refused" in f.manage("pool", "reviewer", "--why", "x", ok=False)          # (no N: does not parse)
    assert len(f.interventions()) == 4                           # nothing recorded for an ask that was not made
