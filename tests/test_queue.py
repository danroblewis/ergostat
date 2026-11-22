"""The merge queue's empty batch (dev/bin/queue.py picks() and emptied()): a run whose batch comes back empty says
why, and a gap that keeps coming back empty is sent back, not taken forever (docs/roadmap/overnight/
a-queue-run-that-lands-nothing.md)."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time

from tests.test_factory import BIN, ROOT, Factory, approved_gaps, main_moves, merges, module, set_action, suite_runs

RED = "echo run >> {runs}"

# git's dry merge as it once came back for a gap (gap/a's commit, argv[2]): a conflict that names no file, which the
# walk reads as one with batch-mates only, on both walks; every other dry merge is git's own
NO_FILE = ("import sys; sys.path[:0] = [sys.argv[1]]; import queue\n"
           "real, own = queue.dry, sys.argv[2]\n"
           "queue.dry = lambda repo, onto, sha, msg: (None, []) if sha == own else real(repo, onto, sha, msg)\n")


def run_queue(f: Factory, iid: str, own_sha: str) -> tuple[list[str], list[dict]]:
    """queue.py for ``iid`` as Factory.run runs it, with NO_FILE's dry merge for ``own_sha``."""
    it = f.item(iid)
    given = {"trigger": "item", "item": it, "lease": {"fence": 1, "back": it["state"]}}
    code = NO_FILE + "sys.exit(queue.main())"
    r = subprocess.run([sys.executable, "-c", code, str(BIN), own_sha], input=json.dumps(given), cwd=f.model,
                       capture_output=True, text=True, timeout=120,
                       env={**f.env, "ERGOSTAT_ITEM": iid, "ERGOSTAT_LEASE": "1"})
    assert r.returncode == 0, r.stderr
    lines = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    return f.fold(lines, iid), lines


def given_back(f: Factory, iid: str) -> None:
    """The lease's nack played: the gap back at approved."""
    db = f.db()
    db["items"][iid]["state"] = "approved"
    f.record.write_text(json.dumps(db))


def test_an_empty_batch_nacks_its_gap_with_the_reason(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    shas = approved_gaps(f, {"a": 1})
    said, lines = run_queue(f, "gap/a", shas["a"])
    assert said == ["gap.queued", "gap.measured"] and merges(f) == [] and suite_runs(f) == 0
    nacks = [x["nack"] for x in lines if "nack" in x]
    assert len(nacks) == 1 and nacks[0]["count"] is False and nacks[0]["after"] == "10m"
    assert "came back empty (1 of 3)" in nacks[0]["why"]
    assert "failed only with batch-mates on both walks" in nacks[0]["why"]
    got = f.item("gap/a")["fields"]
    assert got["empty_batches"] == {"head": shas["a"], "n": 1} and got["empty_batch"] in nacks[0]["why"]


def test_a_gap_whose_batch_is_empty_past_the_ceiling_is_sent_back(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    shas = approved_gaps(f, {"a": 1})
    for k in (1, 2):
        said, lines = run_queue(f, "gap/a", shas["a"])
        assert said == ["gap.queued", "gap.measured"] and f.item("gap/a")["fields"]["empty_batches"]["n"] == k
        given_back(f, "gap/a")
    said, lines = run_queue(f, "gap/a", shas["a"])
    assert said == ["gap.queued", "gap.measured", "gap.sent-back"] and not [x for x in lines if "nack" in x]
    a = f.item("gap/a")
    assert a["state"] == "fix" and a["fields"]["failed_gates"] == 1
    assert a["fields"]["findings"][0].startswith("its queue batch came back empty 3 times: its dry merge failed only")
    assert a["fields"]["empty_batches"] == {"head": shas["a"], "n": 0}          # counted again from nothing
    # a count kept for another reviewed commit is not this one's (the same id, made again: lesson-5)
    db = f.db()
    db["items"]["gap/a"]["state"] = "approved"
    db["items"]["gap/a"]["fields"]["empty_batches"] = {"head": "0" * 40, "n": 2}
    f.record.write_text(json.dumps(db))
    said, lines = run_queue(f, "gap/a", shas["a"])
    assert said == ["gap.queued", "gap.measured"] and f.item("gap/a")["fields"]["empty_batches"]["n"] == 1


def test_picks_says_why_its_batch_is_empty(tmp_path):
    f = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs"))
    shas = approved_gaps(f, {"a": 1, "b": 2, "c": 3}, edits={"b": "app.py"})
    main_moves(f, "app.py")                                                    # b conflicts with main
    db = f.db()
    db["items"]["gap/c"]["fields"]["reviewed_head"] = "f" * 40                 # c's branch moved after its review
    f.record.write_text(json.dumps(db))
    code = NO_FILE + ("import fac, json; cfg = fac.config(); repo = fac.path(cfg, 'checkout')\n"
                      "fac.git(repo, 'fetch', '-q', 'origin', 'main'); fac.git(repo, 'merge', '-q', '--ff-only', "
                      "'origin/main'); pre = fac.git(repo, 'rev-parse', 'HEAD')\n"
                      "gaps = {g['id']: g for g in fac.items('gap', 'approved')}; out = {}\n"
                      "for gid in ('gap/a', 'gap/b', 'gap/c'):\n"
                      "    batch, head, why = queue.picks(cfg, repo, gaps[gid], 1, pre)\n"
                      "    out[gid] = [[g['id'] for g, _ in batch], why]\n"
                      "queue.dry = real\n"
                      "batch, head, why = queue.picks(cfg, repo, gaps['gap/a'], 1, pre)\n"
                      "out['merging'] = [[g['id'] for g, _ in batch], why]\n"
                      "print(json.dumps(out))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), shas["a"]], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.splitlines()[-1])
    assert out["gap/a"] == [[], "its dry merge failed only with batch-mates on both walks (no file)"]
    assert out["gap/b"] == [[], "it was sent back: conflicts with main: app.py"]
    assert out["gap/c"][0] == [] and out["gap/c"][1].startswith("it was sent back: not merged: its branch moved")
    assert out["merging"] == [["gap/a"], ""]                                   # a batch that is not empty: no why


class Engine:
    """The factory's own model (ergostat.yaml and dev/model) in a project of its own, where a run's lines are recorded
    under its lease and the lease is ended as the engine's dispatcher ends it, so its end can be seen (the fixture's
    fold alone plays no lease)."""

    def __init__(self, tmp):
        from ergostat import model as mdl
        from ergostat.spec.engine import Engine as Eng
        from ergostat.store import Project
        d = tmp / "engine"
        d.mkdir()
        (d / "ergostat.yaml").symlink_to(ROOT / "ergostat.yaml")
        (d / "dev").symlink_to(ROOT / "dev")
        self.p = Project(mdl.load(d))
        self.spec, self.eng, self.n = self.p.model.spec, Eng(self.p, say=lambda s: None), 0

    def approved(self, iid: str) -> None:
        self.p.events.add("gap.approved", item=iid, source="t", data={"approved_by": "review"})

    def run(self, lines: list[dict], iid: str | None = None) -> None:
        """A run's lines: under a merge-queue lease on ``iid`` (ended as the dispatcher ends it), or holding none."""
        from ergostat.leases import TAKEN
        from ergostat.spec.engine import nack_of
        self.n += 1
        run = f"run-{self.n}"
        if iid:
            self.p.events.add(TAKEN, item=iid, source="ergostat", data={
                "item": iid, "run": run, "block": "merge-queue", "fence": self.n, "ttl": 1800, "max": 3,
                "back": "approved", "tier": "program"})
        for x in lines:
            if "event" in x:
                self.p.events.add(x["event"], item=x.get("item") or iid, source="merge-queue", causedby=run,
                                  data=x.get("data") or {})
        if iid:
            nack = next((nack_of(x["nack"]) for x in lines if "nack" in x), None)
            self.eng.dispatch.finish(self.spec.blocks["merge-queue"], iid, self.n, run, {"exit": 0, "nack": nack})

    def item(self, iid: str):
        from ergostat.spec import items as its
        return its.one(self.p.events, self.spec, iid)

    def sent_back_by_queue(self) -> float:
        from ergostat.spec import items as its
        sensor = next(iter(self.spec.flows["sent-back-by-queue"].sensors.values()))
        return its.measure(self.p.events, self.spec, sensor)[0] or 0.0


def test_a_conflicting_own_gap_ends_in_fix_not_approved(tmp_path):
    f, e = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs")), Engine(tmp_path)
    approved_gaps(f, {"a": 1}, edits={"a": "app.py"})
    main_moves(f, "app.py")                                                    # a, the run's only gap, conflicts
    e.approved("gap/a")
    said, lines = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.sent-back"] and merges(f) == ["main changes app.py"] and suite_runs(f) == 0
    assert not [x for x in lines if "nack" in x]
    assert e.sent_back_by_queue() == 0
    e.run(lines, "gap/a")                                                      # its lease ends after its lines
    a = e.item("gap/a")
    assert a.state == "fix" and a.fields["lease"]["history"][-1]["how"] == "ack"   # not nacked back to approved
    assert a.fields["sent_back_by"] == "queue" and a.fields["findings"] == ["conflicts with main: app.py"]
    assert e.sent_back_by_queue() > 0                                          # the landing model's flow counts it


def test_a_held_send_back_reaches_fix_after_the_run(tmp_path):
    f, e = Factory(tmp_path, unit=RED.format(runs=tmp_path / "runs")), Engine(tmp_path)
    approved_gaps(f, {"a": 1, "b": 2, "c": 3}, batch=2, edits={"c": "app.py"})
    main_moves(f, "app.py")                                                    # the run's own c conflicts with main
    for g in "abc":
        e.approved(f"gap/{g}")
    said, lines = f.run("queue.py", "gap/c")
    assert said == ["gap.queued"] + ["gap.merged"] * 2 + ["gap.push-asked"] * 2 + ["gap.push-pending"]
    e.run(lines, "gap/c")                                                      # its send-back held for the push
    c = e.item("gap/c")
    assert c.state == "push-pending" and c.fields["lease"]["history"][-1]["how"] == "ack"
    assert "sent_back_by" not in c.fields and e.sent_back_by_queue() == 0
    set_action(f, "ran")                                                       # the push ran: settled by the settler
    r = subprocess.run([sys.executable, str(BIN / "queue.py"), "settle"], cwd=f.model, env=f.env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    settled = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
    e.run(settled)                                                             # (a run that holds no lease on c)
    c = e.item("gap/c")
    assert c.state == "fix" and c.fields["sent_back_by"] == "queue"
    assert c.fields["findings"] == ["conflicts with main: app.py"] and c.fields["failed_gates"] == 1
    assert e.sent_back_by_queue() > 0


# ---- a suite that stops making progress (fac.suite's limits, for the queue and triage: fac.limits())

SUITE = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import fac; from pathlib import Path\n"
         "cfg = fac.config()\n"
         "try:\n"
         "    rc, secs = fac.suite(cfg, 'unit', Path('.'), Path(sys.argv[2]), slot=False, box='queue')\n"
         "    print(json.dumps({'rc': rc, 'seconds': secs}))\n"
         "except fac.Stalled as e:\n"
         "    print(json.dumps({'stalled': e.suite, 'why': e.why, 'test': e.test, 'tail': e.tail}))\n")


def limited(f: Factory, **limits) -> None:
    """[suites] limits for the fixture's factory ([suites] is its settings' last table)."""
    f.config.write_text(f.config.read_text() + "".join(f"{k} = {v}\n" for k, v in limits.items()))


def one_suite(f: Factory) -> dict:
    """fac.suite's unit suite as the queue runs it (box "queue"), from the model's folder."""
    r = subprocess.run([sys.executable, "-c", SUITE, str(BIN), str(f.tmp / "suite.log")], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.splitlines()[-1])


def gone(pid: int) -> bool:
    """The process ended (no such process, or a zombie only)."""
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return not out or out.startswith("Z")


def hangs(tmp_path) -> str:
    """A stand-in suite that names a test, then sleeps (in a process of its own, its pid written) and prints no more."""
    return f"echo $$ > {tmp_path / 'group'}; echo tests/test_x.py::test_hangs; sleep 600 & echo $! > {tmp_path / 'sleeper'}; wait"


def test_a_suite_whose_log_stops_growing_is_stopped_as_a_stall(tmp_path):
    f, e = Factory(tmp_path, unit=hangs(tmp_path)), Engine(tmp_path)
    limited(f, stall_minutes=0.05)                                             # 3 s
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    for g in "ab":
        e.approved(f"gap/{g}")
    began = time.time()
    try:
        said, lines = f.run("queue.py", "gap/a")
        assert time.time() - began < 60
        assert gone(int((tmp_path / "sleeper").read_text()))                  # its process group stopped
    finally:
        reaped(tmp_path / "group")
    assert said == ["gap.queued", "gap.measured"] and merges(f) == []         # main undone; nothing to fix or triage
    nacks = [x["nack"] for x in lines if "nack" in x]
    assert len(nacks) == 1 and nacks[0]["count"] is False and "did not grow" in nacks[0]["why"]
    a = f.item("gap/a")["fields"]
    assert a["stalled"] == "unit" and a["stalled_test"] == "tests/test_x.py::test_hangs"
    assert "test_hangs" in a["stalled_tail"] and a["stalled_batch"] == ["gap/a", "gap/b"]
    assert "failed_gates" not in a and "findings" not in a
    assert f.item("gap/b")["state"] == "approved"
    e.run(lines, "gap/a")                                                      # its lease ends after its lines
    assert e.item("gap/a").state == "approved" and e.item("gap/b").state == "approved"


def test_a_suite_past_its_wall_limit_is_stopped(tmp_path):
    f = Factory(tmp_path, unit=f"echo $$ > {tmp_path / 'sh'}; while true; do echo tick; sleep 0.2; done")
    limited(f, stall_minutes=1, wall_minutes=0.05)                             # it keeps printing; 3 s in all
    began = time.time()
    try:
        got = one_suite(f)
        assert time.time() - began < 30
        assert got["stalled"] == "unit" and got["why"] == "it ran past 0.05 min" and got["test"] is None
        assert gone(int((tmp_path / "sh").read_text())) and "tick" in got["tail"]
    finally:
        reaped(tmp_path / "sh")


def reaped(pidfile) -> None:
    """The stand-in's group stopped by the test itself when the code under test failed to (never left running)."""
    try:
        os.killpg(int(pidfile.read_text()), signal.SIGKILL)
    except (OSError, ValueError):
        pass


def test_stall_limits_have_a_ceiling(tmp_path):
    f = Factory(tmp_path)
    text, load = f.config.read_text(), f"import sys; sys.path[:0] = [{str(BIN)!r}]; import fac; from pathlib import Path\n"
    for bad in ("stall_minutes = 1000", "wall_minutes = 500", "stall_minutes = 0", "wall_minutes = -1"):
        f.config.write_text(text + bad + "\n")
        r = subprocess.run([sys.executable, "-c", load + "fac.config()"], cwd=f.model, env=f.env, capture_output=True,
                           text=True, timeout=60)
        assert r.returncode != 0 and f"[suites] {bad.split()[0]} =" in r.stderr, (bad, r.stderr)
    f.config.write_text(text)                  # again at run time: settings changed after they were read are refused
    code = load + ("cfg = fac.config(); cfg['suites']['stall_minutes'] = 1000\n"
                   "try:\n    fac.suite(cfg, 'unit', Path('.'), Path('log'), slot=False, box='queue')\n"
                   "except ValueError as e:\n    print('refused', e)\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=f.model, env=f.env, capture_output=True, text=True, timeout=60)
    assert r.stdout.startswith("refused [suites] stall_minutes = 1000"), r.stderr
    assert not (f.model / "log").exists()                                     # (the suite never started)
    # the wall limit's default is three times the suites-in-time goal, as the model states the goal
    goal = re.search(r"suites-in-time:\n\s+auxiliary: suite-minutes\n\s+hold: \"<= (\d+)\"",
                     (ROOT / "dev" / "model" / "measures.yaml").read_text())
    assert goal and int(goal[1]) == module("fac").SUITE_GOAL_MINUTES


def test_a_slow_but_progressing_suite_is_left_running(tmp_path):
    f = Factory(tmp_path, unit="for i in 1 2 3 4 5 6; do echo tick; sleep 1; done; exit 3")
    limited(f, stall_minutes=0.05, wall_minutes=0.5)                           # 3 s without a line; 30 s in all
    got = one_suite(f)
    assert got["rc"] == 3 and got["seconds"] >= 5                              # its own rc: it ran to its end
