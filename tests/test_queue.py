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

from tests.test_factory import BIN, ROOT, Factory, approved_gaps, main_moves, merges, module, set_action, settle, suite_runs

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
    assert a.fields["conflicts"] == 1                                          # what the gap's risk score reads
    assert e.sent_back_by_queue() > 0                                        # the landing model's flow counts it


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
    assert a["stalls"] == 0                                                    # not alone: no gap's stall counted,
    assert json.loads((f.model / "run" / "queue.json").read_text())["cap"] == 1   # but the next batch is halved
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
    """The stand-in's group stopped by the test itself when the code under test failed to (never left running). Only
    while it is alive and still leads its own group: a pid gone and reused is never signalled (it is not ours)."""
    try:
        pid = int(pidfile.read_text())
        if not gone(pid) and os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
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


def test_a_hung_pytest_names_the_test_it_was_on(tmp_path):
    # a real pytest -q under xdist, as the queue's unit suite runs: -q prints no test ids while tests run, so the test
    # is read from the stack pytest's faulthandler dumps at half the stall limit (fac.suite sets its timeout)
    hung = tmp_path / "hung" / "tests"
    hung.mkdir(parents=True)
    (hung / "test_hangs.py").write_text("import time\n\n\ndef test_quick():\n    pass\n\n\n"
                                        "def test_hangs():\n    time.sleep(600)\n")
    f = Factory(tmp_path, unit=f"echo $$ > {tmp_path / 'group'}; exec {sys.executable} -m pytest -q -n 2 "
                               f"-p no:randomly -p no:cacheprovider {hung}")
    limited(f, stall_minutes=0.2)                                              # 12 s; its stack dumped at 6 s
    try:
        got = one_suite(f)
        assert got["stalled"] == "unit" and "did not grow" in got["why"]
        assert got["test"] == "tests/test_hangs.py::test_hangs", got["tail"]
        assert gone(int((tmp_path / "group").read_text()))
    finally:
        reaped(tmp_path / "group")


def test_a_gap_that_stalls_alone_again_and_again_goes_to_triage(tmp_path):
    stalls_most = module("fac").STALLS_MOST
    f, e = Factory(tmp_path, unit=hangs(tmp_path)), Engine(tmp_path)
    limited(f, stall_minutes=0.05)
    approved_gaps(f, {"a": 1})
    e.approved("gap/a")
    for n in (1, stalls_most):
        try:
            said, lines = f.run("queue.py", "gap/a")
        finally:
            reaped(tmp_path / "group")
        e.run(lines, "gap/a")
        a = f.item("gap/a")["fields"]
        assert a["stalls"] == n and json.loads((f.model / "run" / "queue.json").read_text())["cap"] == 1
        if n == 1:                                                             # counted, given back uncounted
            assert said == ["gap.queued", "gap.measured"] and [x["nack"]["count"] for x in lines if "nack" in x] == [False]
            assert e.item("gap/a").state == "approved"
            given_back(f, "gap/a")
            db = f.db()
            db["items"]["gap/a"]["fields"]["stalls"] = stalls_most - 1         # (the stalls between)
            f.record.write_text(json.dumps(db))
    assert said == ["gap.queued", "gap.measured", "gap.queue-failed"] and not [x for x in lines if "nack" in x]
    assert a["failed_tests"] == ["tests/test_x.py::test_hangs"] and f"stalled {stalls_most} times" in a["findings"][0]
    assert e.item("gap/a").state == "queue-failed" and merges(f) == []


def test_a_triage_rerun_that_keeps_stalling_is_the_branchs(tmp_path):
    from tests.test_factory import queue_failed
    f, gid = queue_failed(tmp_path)
    f.config.write_text(re.sub(r"^rerun = .*$", f'rerun = "{hangs(tmp_path)}"', f.config.read_text(), flags=re.M))
    limited(f, stall_minutes=0.05)
    for n in (1, module("fac").STALLS_MOST):
        try:
            said, lines = f.run("triage.py", gid)
        finally:
            reaped(tmp_path / "group")
        assert f.item(gid)["fields"]["stalls"] == n
        if n == 1:                                                             # tried again later, uncounted
            assert said == ["gap.measured"] and [x["nack"]["count"] for x in lines if "nack" in x] == [False]
            db = f.db()
            db["items"][gid]["fields"]["stalls"] = module("fac").STALLS_MOST - 1
            f.record.write_text(json.dumps(db))
    assert said == ["gap.measured", "gap.sent-back"] and not [x for x in lines if "nack" in x]
    assert f"stalled {n} times" in f.item(gid)["fields"]["findings"][-1]


def test_a_slow_but_progressing_suite_is_left_running(tmp_path):
    f = Factory(tmp_path, unit="for i in 1 2 3 4 5 6; do echo tick; sleep 1; done; exit 3")
    limited(f, stall_minutes=0.05, wall_minutes=0.5)                           # 3 s without a line; 30 s in all
    got = one_suite(f)
    assert got["rc"] == 3 and got["seconds"] >= 5                              # its own rc: it ran to its end


def test_a_wait_for_the_suite_slot_is_not_a_stall(tmp_path):
    # triage's suites run inside [suites] slot: a slot held elsewhere past both limits is the machine's time, so the
    # clocks start once the slot is held, and the suite then runs to its own rc
    slot = tmp_path / "slot.sh"
    slot.write_text('echo waiting for a slot; sleep 8; exec "$@"\n')
    f = Factory(tmp_path, unit="for i in 1 2; do echo tick; sleep 1; done; exit 3")
    limited(f, stall_minutes=0.05, wall_minutes=0.1, slot=json.dumps(f"sh {slot}"))   # 3 s and 6 s; the wait 8 s
    r = subprocess.run([sys.executable, "-c", SUITE.replace("slot=False, box='queue'", "box='triage'"), str(BIN),
                        str(tmp_path / "suite.log")], cwd=f.model, env=f.env, capture_output=True, text=True,
                       timeout=120)
    got = json.loads(r.stdout.splitlines()[-1])
    assert got.get("rc") == 3 and got["seconds"] >= 9, got                    # never stopped while it waited
    assert not (tmp_path / "suite.log.held").exists()


# ---- each suite's pytest counts (dev/records/regression-queue-test-counts.md)

def counted(p=0, f=0, s=0, d=0, e=0) -> dict:
    return {"passed": p, "failed": f, "skipped": s, "deselected": d, "errors": e}


def test_counts_reads_every_summary_form_pytest_prints_and_none_without_one():
    counts, c = module("fac").counts, counted
    assert counts("..F\n1 failed, 2 passed in 0.12s\n") == c(2, 1)                          # -q
    assert counts("==== 3 passed, 1 skipped, 2 deselected, 4 warnings in 1.50s ====\n") == c(3, s=1, d=2)
    assert counts("1 failed, 5 passed, 1 xfailed, 1 xpassed, 1 warning, 2 errors in 70.01s (0:01:10)\n") == c(5, 1, e=2)
    assert counts("!!! Interrupted: 1 error during collection !!!\n1 error in 0.30s\n") == c(e=1)
    assert counts("no tests ran in 0.01s\n") == c() and counts("7 deselected in 0.02s\n") == c(d=7)
    xdist = ("created: 8/8 workers\n8 workers [120 items]\n" + "." * 120 + " [100%]\n"
             "=========== 118 passed, 2 skipped in 31.27s ===========\n")
    assert counts(xdist) == c(118, s=2)
    assert counts("\x1b[32m\x1b[1m4 passed\x1b[0m\x1b[32m in 0.05s\x1b[0m\n") == c(4)              # coloured
    assert counts("1 failed in 0.1s\nlater\n9 passed in 2.0s\ntrailing output\n") == c(9)           # the last one
    for none in ("", "tests/test_x.py::test_hangs\n", "8 workers [120 items]\n", "Interrupted: 1 error during collection",
                 "All checks passed!\n", "3 passed\n"):                                      # killed, ruff, cut short
        assert counts(none) is None, none


def test_a_landed_run_records_each_pytest_suites_counts_and_their_sum(tmp_path):
    (tmp_path / "unit.sh").write_text("echo '....s'; echo '4 passed, 1 skipped, 2 deselected in 3.10s'\n")
    (tmp_path / "browser.sh").write_text("echo '2 workers [3 items]'; echo '== 2 passed, 1 error, 1 warning in 9.00s =='\n")
    f = Factory(tmp_path, unit=f"sh {tmp_path / 'unit.sh'}")
    f.config.write_text(f.config.read_text().replace('\nbrowser = "true"', f'\nbrowser = "sh {tmp_path / "browser.sh"}"'))
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
    a = f.item("gap/a")["fields"]
    got = a["suites_queue"]
    assert got["unit"]["counts"] == counted(4, s=1, d=2) and got["browser"]["counts"] == counted(2, e=1)
    assert "counts" not in got["ruff"] and "counts" not in got["demo"] and "skipped" not in got["browser"]
    run = a["queue_runs"][-1]
    assert run["counts"] == counted(6, s=1, d=2, e=1) and run["suites"] == ["unit", "browser"]   # host off: not one


def test_a_suite_whose_log_cannot_say_records_unknown_never_zeros(tmp_path):
    f = Factory(tmp_path, unit="echo ....")                                    # no summary line: unknown
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
    a = f.item("gap/a")["fields"]
    assert a["suites_queue"]["unit"]["counts"] == "unknown"
    assert a["queue_runs"][-1]["counts"] == "unknown" and a["queue_runs"][-1]["suites"] == ["unit", "browser"]
    # a suite stopped by its failing sibling: unknown, even had it printed a summary before it was killed
    (tmp_path / "b").mkdir()
    (tmp_path / "b.sh").write_text("echo '1 passed in 0.1s'; sleep 60\n")
    g = Factory(tmp_path / "b", unit="echo FAILED tests/test_x.py::test_x - boom; echo 1 failed in 0.1s; exit 1")
    g.config.write_text(g.config.read_text().replace('\nbrowser = "true"', f'\nbrowser = "sh {tmp_path / "b.sh"}"'))
    approved_gaps(g, {"a": 1})
    began = time.time()
    said, _ = g.run("queue.py", "gap/a")
    assert "gap.queue-failed" in said and time.time() - began < 50
    got = g.item("gap/a")["fields"]["suites_queue"]
    assert got["browser"]["stopped_by"] == "unit" and got["browser"]["counts"] == "unknown"
    assert got["unit"]["counts"] == counted(f=1)


# ---- a seen flake fixed after green queue runs (dev/records/regression-flake-fixed-after-green.md)

FLAKY = "tests/test_x.py::test_y"


def seen_flake(f: Factory) -> str:
    iid = f"flake/{module('fac').slug(FLAKY, 80)}"
    db = f.db()
    db["items"][iid] = {"id": iid, "kind": "flake", "state": "seen", "fields": {"test": FLAKY, "times": 1,
                                                                                 "green_passes": 0}}
    f.record.write_text(json.dumps(db))
    return iid


def test_a_green_landing_counts_each_seen_flake_it_says_passed(tmp_path):
    (tmp_path / "unit.sh").write_text(f"echo 'PASSED {FLAKY}'; echo '1 passed in 0.1s'\n")
    f = Factory(tmp_path, unit=f"sh {tmp_path / 'unit.sh'}")
    f.config.write_text(f.config.read_text().replace("[gates]\n", "[gates]\nflake_fixed_after = 2\n"))
    iid = seen_flake(f)
    for n, gap in ((1, "a"), (2, "b")):
        approved_gaps(f, {gap: 1})
        said, _ = f.run("queue.py", f"gap/{gap}")
        assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
        assert f.item(f"gap/{gap}")["fields"]["suites_queue"]["unit"]["log"].endswith("-unit.txt")
        assert f.item(iid)["fields"]["green_passes"] == n
        db = f.db()                                                           # (its push lands: the next run goes)
        db["actions"] = dict.fromkeys(db["actions"], "ran")
        f.record.write_text(json.dumps(db))
        assert settle(f)[0] == ["gap.pushed"]
    fl = f.item(iid)
    assert fl["state"] == "fixed" and fl["fields"]["fixed_by"] == "green-runs"
    assert fl["fields"]["fixed_on"] == f.item("gap/b")["fields"]["main_sha"]
    assert f"fixed after green runs: {iid}" in f.stderr


def test_a_failure_counting_the_flakes_never_fails_the_landing(tmp_path):
    (tmp_path / "unit.sh").write_text(f"echo 'PASSED {FLAKY}'; echo '1 passed in 0.1s'\n")
    f = Factory(tmp_path, unit=f"sh {tmp_path / 'unit.sh'}")
    f.config.write_text(f.config.read_text().replace("[gates]\n", "[gates]\nflake_fixed_after = 99\n"))   # (refused)
    iid = seen_flake(f)
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
    assert "the flakes' green runs not counted (ValueError: [gates] flake_fixed_after" in f.stderr
    assert f.item(iid)["fields"]["green_passes"] == 0


def test_a_runs_sum_is_over_the_suites_that_ran_unknown_if_any_is():
    from tests.test_queue_host import queue_module
    summed, c = queue_module().summed, counted
    ruff = {"rc": 0, "seconds": 1}
    assert summed({"ruff": ruff, "unit": {"counts": c(5)}, "host": {"counts": c(2, 1)}}) == \
        {"counts": c(7, 1), "suites": ["unit", "host"]}
    not_run = {"unit": {"counts": c(5)}, "browser": {"counts": "not_run"}}    # not run by rule: neither unknown nor 0
    assert summed(not_run) == {"counts": c(5), "suites": ["unit"]}
    for unknown in ({"unit": {"counts": c(5)}, "browser": {"counts": "unknown"}}, {"unit": {"counts": c(5)}, "browser": {}}):
        assert summed(unknown) == {"counts": "unknown", "suites": ["unit", "browser"]}
