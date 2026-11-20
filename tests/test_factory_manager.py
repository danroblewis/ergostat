"""The pipeline manager (docs/roadmap/overnight/pipeline-manager.md): the watch's triggers and their deduplication
(dev/bin/watch.py), the tools and their checks (dev/bin/manage.py), the gated asks, and a whole run with the stand-in
AI (dev/bin/manager.py), on the fixture of tests/test_factory.py."""

from __future__ import annotations

import json
import subprocess
import sys
import time

from ergostat.spec import read
from tests.test_factory import BIN, ROOT, git, ready
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


def test_the_queue_blocked_is_raised_first_and_once(tmp_path):
    f = Pipe(tmp_path)
    (tmp_path / "instance" / "run").mkdir(exist_ok=True)
    (tmp_path / "instance" / "run" / "queue.json").write_text(json.dumps(
        {"blocked": {"why": "the push failed", "intervention": "intervention/queue-1", "at": f.now - 60}}))
    f.put("intervention/queue-1", "open", reason="the merge queue stopped", recorded_at=f.now - 60, **{"class": "queue"})
    f.put("gap/stopped", "parked", parked_at=f.now - H, branch="stopped")
    got = f.watch()
    assert got["trigger"] == "queue" and got["subject"] == "intervention/queue-1" and "push failed" in got["why"]
    assert f.watch() is None                                   # one at a time: nothing while it is raised
    f.handled(got["id"])
    assert f.watch()["trigger"] == "parked"                    # the queue's own intervention is not raised twice


def test_dead_and_parked_gaps_are_raised_but_not_old_or_carried_on_ones(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/just-died", "dead", entered=600, branch="just-died")               # dead-letters parks it first
    f.put("gap/old-park", "parked", parked_at=f.now - 72 * H, branch="old-park")
    f.put("gap/carried", "parked", parked_at=f.now - H, branch="carried")
    f.put("gap/carried-on", "open", continues="carried")
    f.put("gap/long-dead", "dead", entered=2 * H, branch="long-dead", last_error="RuntimeError: lost")
    got = f.watch()
    assert (got["trigger"], got["subject"], got["gap"]) == ("dead", "gap/long-dead", "gap/long-dead")
    f.handled(got["id"])
    assert f.watch()["trigger"] == "heartbeat"


def test_a_gap_stuck_in_its_state_from_its_moves_and_from_state_times(tmp_path):
    f = Pipe(tmp_path)
    bounces = [{"time": f.now - 8 * H, "from": "building", "to": "fix"},
               {"time": f.now - 600, "from": "fix", "to": "leased"}, {"time": f.now - 60, "from": "leased", "to": "fix"}]
    f.put("gap/slow", "fix", entered=60, moves=bounces, branch="slow")                   # 8 hours in fix, not 1 minute
    f.put("gap/fresh", "fix", entered=60, moves=bounces[1:], branch="fresh")             # in fix 10 minutes
    f.put("gap/timed", "built", entered=60, moves=bounces[1:], time_in={"built": {"hours": 3.0, "visits": 2}})
    assert f.tool("watch.py", "stuck").stdout.strip() == "2"
    got = f.watch()
    assert got["trigger"] == "stuck" and got["subject"] == "gap/slow" and "8.0h" in got["why"]
    f.handled(got["id"])
    assert f.watch()["subject"] == "gap/timed"                 # from state-times' time_in: 3h over its 2h threshold


def test_a_wait_the_pipeline_explains_is_not_stuck(tmp_path):
    f = Pipe(tmp_path)
    moves = [{"time": f.now - 9 * H, "from": "open", "to": "ready"}]
    f.put("gap/waiting", "ready", moves=moves, entered=9 * H)
    f.put("gap/busy", "building", entered=600)                 # the implementor's pool of one is full
    assert f.tool("watch.py", "stuck").stdout.strip() == "0"
    f.put("gap/busy", "merged")
    assert f.tool("watch.py", "stuck").stdout.strip() == "1"


def test_an_old_open_intervention_is_raised_but_never_the_managers_own(tmp_path):
    f = Pipe(tmp_path)
    f.put("intervention/mine", "open", recorded_at=f.now - 20 * H, by="pipeline-manager", **{"class": "flake"})
    f.put("intervention/recent", "open", recorded_at=f.now - H, by="claude-coordinator")
    f.put("intervention/old", "open", recorded_at=f.now - 13 * H, by="claude-coordinator", reason="seeded by hand",
          **{"class": "factory-missing-capability"})
    got = f.watch()
    assert got["trigger"] == "intervention" and got["subject"] == "intervention/old"


def test_the_heartbeat_comes_only_when_the_pipeline_changed_and_its_time_came(tmp_path):
    f = Pipe(tmp_path)
    got = f.watch()
    assert got["trigger"] == "heartbeat"
    f.handled(got["id"])
    assert f.watch() is None                                   # unchanged, and within its 30 minutes
    db = f.db()
    db["items"][got["id"]]["fields"]["raised_at"] = f.now - 31 * 60
    f.record.write_text(json.dumps(db))
    assert f.watch() is None                                   # its time came, but nothing changed: deduplicated
    f.put("gap/new", "ready", ago=60)
    assert f.watch()["trigger"] == "heartbeat"


def test_a_situation_is_raised_again_only_when_it_changed_and_never_while_paused(tmp_path):
    f = Pipe(tmp_path, manager="heartbeat_minutes = 100000\n")
    f.put("gap/p", "parked", parked_at=f.now - H, branch="p")
    first = f.watch()
    f.handled(first["id"])
    assert f.watch()["trigger"] == "heartbeat"                 # (the first heartbeat) and not the same park again
    f.handled(next(i for i in f.db()["items"] if "heartbeat" in i))
    assert f.watch() is None
    f.put("gap/p", "parked", parked_at=f.now - 60, branch="p")  # parked again: a new situation
    again = f.watch()
    assert again["subject"] == "gap/p" and again["id"] != first["id"]
    p = Pipe(tmp_path / "paused", manager="open = 0\n")
    p.put("gap/p", "parked", parked_at=p.now - H, branch="p")
    assert p.watch() is None and p.tool("watch.py", "open").stdout.strip() == "0"


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
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"',
                                                     "rerun = 'printf \"FAILED %s\\n\" {tests}; false'"))
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


def test_a_whole_run_briefs_the_situation_runs_the_calls_and_records_each_as_the_managers(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/p", "parked", title="P", branch="p", parked_at=f.now - H, where_it_stopped="main's own lease race",
          findings=["tests/test_leases.py::test_race failed"])
    f.put("gap/q", "fix", branch="q")
    sit = f.watch()["id"]
    answer = {"calls": [["continue", "gap/p", "--why", "main's own failure"], ["flake", "nope", "--why", "x"],
                        ["close", "gap/q", "--why", "done elsewhere"]], "summary": "continued p; q is done elsewhere"}
    said, _ = f.run("manager.py", sit, FACTORY_STANDIN_PIPELINE_MANAGER="```json\n" + json.dumps(answer) + "\n```")
    f.drain()
    assert said == ["situation.handled"]
    s = f.item(sit)
    assert s["state"] == "handled" and s["fields"]["summary"].startswith("continued p")
    assert [a["ok"] for a in s["fields"]["actions"]] == [True, False, True]
    assert f.item("gap/p-continued")["fields"]["requested_by"] == "pipeline-manager"
    assert {i["fields"]["action"] for i in f.interventions("pipeline-manager")} == {"continue", "close"}
    assert all(i["fields"]["situation"] == sit for i in f.interventions())
    text = (f.model / s["fields"]["context"]["brief"].removeprefix("file:")).read_text()
    for part in ("# The situation", "main's own lease race", "## The merge queue", "## Main's recent commits",
                 "The house rules", "continue GAP"):
        assert part in text
    (session,) = [i for i in f.db()["items"].values() if i["kind"] == "session"]
    assert session["fields"]["situation"] == [sit] and session["fields"]["role"] == "pipeline_manager"


def test_the_heartbeat_files_one_velocity_gap_when_the_queue_wait_is_off(tmp_path):
    f = Pipe(tmp_path)
    for n in range(3):
        f.put(f"gap/m{n}", "merged", merged_at=f.now - H, ready_at=f.now - 9 * H, queue_wait_hours=5.0)
    code = "import manager\nprint(json.dumps(manager.velocity(manager.fac.config())))"
    got = f.py(code)
    f.drain()
    assert got["queue-wait-hours"] == 5.0 and "gap/merge-batching requested" in got["filed"]
    g = f.item("gap/merge-batching")
    assert g["fields"]["velocity"] == "queue-wait-hours" and "## Definition of done" in (
        tmp_path / "instance" / "run" / "defs" / "merge-batching.md").read_text()
    for n in range(3, 6):
        f.put(f"gap/s{n}", "merged", merged_at=f.now - H, suites_queue={"unit": {"seconds": 3000}})
    again = f.py(code)
    assert "filed" not in again                                # one of the watch's open at a time
    (i,) = f.interventions()
    assert i["fields"]["class"] == "velocity"


def test_a_session_answer_without_calls_is_handled_and_a_bad_one_fails_on_its_last_attempt(tmp_path):
    f = Pipe(tmp_path)
    sit = f.watch()["id"]
    said, _ = f.run("manager.py", sit, lease={"attempt": 2, "attempts": 2}, FACTORY_STANDIN_PIPELINE_MANAGER="no json")
    assert said == ["situation.failed"] and f.item(sit)["state"] == "failed"
    sit2 = f.watch()
    assert sit2 is None or sit2["trigger"] == "heartbeat"
    r = subprocess.run([sys.executable, str(BIN / "manage.py")], capture_output=True, text=True, cwd=f.model, env=f.env)
    assert "reapprove GAP" in r.stdout
