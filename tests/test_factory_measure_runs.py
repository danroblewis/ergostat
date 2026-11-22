"""measure-runs (docs/roadmap/overnight/dod-measured-runs.md): a gap's named acceptance measurement run by the
factory, N watched runs on its branch head (dev/bin/runs.py, manage.py measure-runs), with stand-in suites and a
stand-in load (a sleep, never a real one) on the pipeline manager's fixture."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
import tomllib
from pathlib import Path

import pytest

from tests.test_factory import BIN, ROOT, git, ready
from tests.test_factory_manager import Pipe

pytestmark = pytest.mark.slow                                     # (each about 20 s, the fixture's build: started first)

STAND = textwrap.dedent("""\
    import json, os, subprocess, sys, time
    from pathlib import Path
    plan, heads, drop = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    step, *rest = plan.read_text().split()
    plan.write_text(" ".join(rest))
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    with heads.open("a") as f:
        f.write(json.dumps({"head": sha, "argv": sys.argv[4:], "pid": os.getpid()}) + "\\n")
    watch = {"rc": 0, "wall_s": 1.0, "killed": None, "workers_killed": 0, "left_behind": 0}
    if step == "move":                     # (another writer moves the branch while the runs run)
        main = subprocess.run(["git", "-C", drop, "rev-parse", "main"], capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", drop, "update-ref", "refs/heads/factory/alpha-thing", main], check=True)
    if step == "resume":                   # (the park is continued while the runs run)
        rec = heads.parent / "record.json"
        db = json.loads(rec.read_text())
        db["items"]["gap/alpha-thing"]["fields"]["resumed_as"] = "gap/alpha-thing-continued"
        rec.write_text(json.dumps(db))
    if step in ("wait", "hang"):
        time.sleep(1 if step == "wait" else 60)
    if step in ("pass", "move", "resume", "wait"):
        print("1 passed"); print(json.dumps(watch)); sys.exit(0)
    if step == "fail":
        print("    def test_a():\\n>       assert 1 == 2\\nE       assert 1 == 2\\nFAILED tests/test_x.py::test_a")
        print(json.dumps({**watch, "rc": 1})); sys.exit(1)
    if step == "killed":
        print("suite_watch: past the limits (1600 threads, 300 MB); killing 9 processes")
        print(json.dumps({**watch, "rc": -9, "killed": "1600 threads, 300 MB"})); sys.exit(3)
    print("1 passed")                      # silent: exit 0, but no watchdog line to read
    """)
BURN = textwrap.dedent("""\
    import os, sys, time
    open(sys.argv[1], "w").write(f"{os.getpid()} {sys.argv[2]}")
    beat, stale = sys.argv[3], float(sys.argv[4])
    seen, at = None, time.monotonic()
    while time.monotonic() - at < stale:   # (as the real load: ends once its beat is gone or stale, but sleeping)
        time.sleep(0.1)
        try:
            m = os.stat(beat).st_mtime_ns
        except OSError:
            break
        if m != seen:
            seen, at = m, time.monotonic()
    """)


class Measured(Pipe):
    def __init__(self, tmp: Path):
        super().__init__(tmp)
        (tmp / "stand.py").write_text(STAND)
        (tmp / "burn.py").write_text(BURN)
        self.plan, self.heads, self.pid = tmp / "plan", tmp / "heads", tmp / "load.pid"
        self.config.write_text(self.config.read_text().replace("[suites]\n", (
            f"[suites]\nmeasure = \"{sys.executable} {tmp / 'stand.py'} {self.plan} {self.heads} "
            f"{tmp / 'live' / 'drop.git'} {{tests}}\"\nload = \"{sys.executable} {tmp / 'burn.py'} {self.pid} {{procs}} "
            "{beat} {stale}\"\nload_stale_s = 3\n")))
        self.gid = ready(self)
        self.run("implement.py", self.gid)
        assert self.item(self.gid)["state"] == "built"

    def tip(self) -> str:
        return git(self.tmp / "live" / "drop.git", "rev-parse", "factory/alpha-thing")

    def measure(self, plan: str, *argv: str, ok: bool = True) -> str:
        self.plan.write_text(plan)
        return self.manage("measure-runs", self.gid, *argv, ok=ok)

    def ran(self) -> list[dict]:
        return [json.loads(x) for x in self.heads.read_text().splitlines()] if self.heads.exists() else []

    def set_state(self, state: str, **fields) -> None:
        db = self.db()
        db["items"][self.gid]["state"] = state
        db["items"][self.gid]["fields"].update(fields)
        self.record.write_text(json.dumps(db))


def gone(pid: int, seconds: float = 5) -> bool:
    """The process is gone (or only a zombie waiting to be reaped), within ``seconds``."""
    for _ in range(int(seconds * 10)):
        try:
            os.kill(pid, 0)
            stat = Path(f"/proc/{pid}/stat")
            if stat.exists() and stat.read_text().rsplit(")", 1)[1].split()[0] == "Z":
                return True
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def test_counts_recorded_and_sent_to_review_when_all_pass(tmp_path):
    f = Measured(tmp_path)
    head = f.tip()
    said = f.measure("pass pass pass", "--runs", "3", "--tests", "-n 8 tests/test_leases.py", "--load", "2",
                     "--why", "the definition's 30 loaded runs, made small")
    assert "back to built" in said and "3 of 3 runs passed" in said
    g = f.item(f.gid)
    assert g["state"] == "built" and g["fields"]["head"] == head == f.tip()          # unchanged: review again
    (m,) = g["fields"]["measured_runs"]
    assert (m["head"], m["n"], m["passed"], m["failed"], m["load"]) == (head, 3, 3, 0, 2)
    assert [r["rc"] for r in m["runs"]] == [0, 0, 0] and all(r["passed"] for r in m["runs"])
    assert "3 of 3 runs passed" in g["fields"]["findings"][-1] and head[:12] in g["fields"]["findings"][-1]
    assert [r["head"] for r in f.ran()] == [head] * 3                                 # on the branch head
    assert all(r["argv"][-3:] == ["-n", "8", "tests/test_leases.py"] for r in f.ran())
    pid, procs = f.pid.read_text().split()
    assert procs == "2" and gone(int(pid))                                            # the load stopped with the runs
    (i,) = f.interventions()
    assert i["fields"]["action"] == "measure-runs" and (i["fields"]["passed"], i["fields"]["failed"]) == (3, 0)
    f.set_state("parked", parked_for="defect")                                        # a parked gap too
    assert "back to built" in f.measure("pass", "--runs", "1", "--tests", "tests/test_leases.py")
    assert f.item(f.gid)["state"] == "built" and len(f.item(f.gid)["fields"]["measured_runs"]) == 2


def test_a_failing_run_sends_the_gap_to_fix_with_its_traceback(tmp_path):
    f = Measured(tmp_path)
    said = f.measure("pass fail pass", "--runs", "3", "--tests", "tests/test_leases.py::test_a")
    assert "back to fix" in said and "2 of 3 runs passed, 1 failed" in said
    g = f.item(f.gid)
    assert g["state"] == "fix" and g["fields"]["sent_back_by"] == "measure-runs"
    summary, failing = g["fields"]["findings"]
    assert "1 failed" in summary and failing.startswith("run 2 of 3: exit 1")
    assert "E       assert 1 == 2" in failing                                          # the traceback is its input
    runs = g["fields"]["measured_runs"][0]["runs"]
    assert [r["passed"] for r in runs] == [True, False, True] and "assert 1 == 2" in runs[1]["tail"]
    assert "only a parked or built gap" in f.measure("pass", "--runs", "1", "--tests", "tests/test_x.py", ok=False)
    assert len(f.ran()) == 3                                                          # (a gap in fix is not run)


def test_n_above_the_cap_is_refused(tmp_path):
    f = Measured(tmp_path)
    for argv in (["--runs", "51", "--tests", "tests/test_x.py"], ["--runs", "0", "--tests", "tests/test_x.py"],
                 ["--runs", "3", "--tests", "tests/test_x.py", "--load", "9"],
                 ["--runs", "3", "--tests", "-n 9 tests/test_x.py"],
                 ["--runs", "3", "--tests", "tests/test_x.py; rm -rf /"], ["--runs", "3", "--tests", "-n 2"]):
        assert "refused" in f.measure("pass", *argv, ok=False), argv
    got = f.py("import argparse, fac, manage\ncfg = fac.config()\n"            # past the parser: refused at run time
               "a = argparse.Namespace(gap=sys.argv[1], runs=51, tests='tests/test_x.py', load=0, why='', cls='')\n"
               "try:\n    manage.do_measure_runs(cfg, a); print(json.dumps('ran'))\n"
               "except ValueError as e:\n    print(json.dumps(str(e)))", f.gid)
    assert got == "--runs 51: 1 to 50"
    got = f.py("import fac, manage, runs\ncfg = fac.config()\ntry:\n"
               "    runs.measure(cfg, manage.item(sys.argv[1]), 2, ['tests/test_x.py'], load=9); print(json.dumps('ran'))\n"
               "except ValueError as e:\n    print(json.dumps(str(e)))", f.gid)
    assert got == "--load 9: 1 to 8"
    assert f.ran() == [] and f.item(f.gid)["state"] == "built" and f.interventions() == []


def runs_module():
    from tests.test_factory import BIN
    sys.path[:0] = [str(BIN)]
    try:
        import runs
        return runs
    finally:
        sys.path.remove(str(BIN))


def test_a_killed_or_unreadable_run_counts_as_failed(tmp_path):
    f = Measured(tmp_path)
    said = f.measure("killed silent pass", "--runs", "3", "--tests", "tests/test_leases.py")
    assert "back to fix" in said and "1 of 3 runs passed, 2 failed" in said
    runs = f.item(f.gid)["fields"]["measured_runs"][0]["runs"]
    assert [r["passed"] for r in runs] == [False, False, True]
    assert runs[0]["rc"] == 3 and "killed by the watchdog" in runs[0]["why"]
    assert runs[1]["rc"] == 0 and "cannot be read" in runs[1]["why"]                  # exit 0, yet never a pass
    m = runs_module()
    assert m.outcome(0, tmp_path / "no-such-log.txt")["passed"] is False
    log = tmp_path / "one.txt"
    for text, passed in (('{"rc": 0, "killed": null, "workers_killed": 0}\n', True),
                         ('{"rc": 0, "killed": null, "workers_killed": 1}\n', False),
                         ('{"rc": 1, "killed": null}\n', False), ('{"rc": 0, "killed": nu', False)):
        log.write_text("1 passed\n" + text)
        assert m.outcome(0, log)["passed"] is passed, text
    f.set_state("built")                                                              # a load that ended: not loaded
    f.config.write_text(f.config.read_text().replace(f"{f.tmp / 'burn.py'} {f.pid}", "-c pass"))
    said = f.measure("wait", "--runs", "1", "--tests", "tests/test_leases.py", "--load", "1")
    assert "back to fix" in said and "0 of 1 runs passed" in said
    (r,) = f.item(f.gid)["fields"]["measured_runs"][-1]["runs"]
    assert r["rc"] == 0 and not r["passed"] and r["why"] == "the load had ended (exit 0)"


def test_a_branch_moved_during_the_runs_keeps_the_gap_where_it_is(tmp_path):
    f = Measured(tmp_path)
    head = f.tip()
    said = f.measure("move pass", "--runs", "2", "--tests", "tests/test_leases.py", ok=False)
    assert "recorded alone" in said and "2 of 2 runs passed" in said
    g = f.item(f.gid)
    assert g["state"] == "built" and g["fields"]["measured_runs"][0]["head"] == head != f.tip()
    assert not any("measure-runs" in x for x in g["fields"].get("findings") or []) and f.interventions() == []


def test_a_park_a_measurement_cannot_clear_is_refused(tmp_path):
    f = Measured(tmp_path)
    for fields, why in (({"parked_for": "deferred"}, "parked for deferred"), ({"parked_for": "kill-rule"}, "kill-rule"),
                        ({"parked_for": "cancelled"}, "cancelled"), ({}, "no kind said"),
                        ({"parked_for": "defect", "deferred": True}, "parked for defect"),
                        ({"parked_for": "defect", "resumed_as": "gap/alpha-thing-continued"}, "resumed already")):
        f.set_state("parked", **{"parked_for": None, "deferred": None, "resumed_as": None, **fields})
        assert why in f.measure("pass", "--runs", "1", "--tests", "tests/test_leases.py", ok=False), fields
    f.set_state("parked", resumed_as=None, deferred=None)
    f.put("gap/alpha-thing-continued", "building", continues="factory/alpha-thing")    # its branch held by another
    assert "held by gap/alpha-thing-continued" in f.measure("pass", "--runs", "1", "--tests", "tests/test_x.py", ok=False)
    assert f.ran() == [] and f.item(f.gid)["state"] == "parked" and f.interventions() == []
    db = f.db()
    db["items"].pop("gap/alpha-thing-continued")
    f.record.write_text(json.dumps(db))
    said = f.measure("resume", "--runs", "1", "--tests", "tests/test_x.py", ok=False)  # continued while the runs ran
    assert "recorded alone" in said and "resumed already" in said and len(f.ran()) == 1
    assert f.item(f.gid)["state"] == "parked" and f.interventions() == []
    f.set_state("parked", parked_for="needs", resumed_as=None)
    assert "back to built" in f.measure("pass", "--runs", "1", "--tests", "tests/test_x.py")


def test_the_load_ends_on_its_own_when_its_caller_is_killed(tmp_path):
    f = Measured(tmp_path)
    f.plan.write_text("hang")
    p = subprocess.Popen([sys.executable, str(BIN / "manage.py"), "measure-runs", f.gid, "--runs", "1", "--tests",
                          "tests/test_x.py", "--load", "1"], cwd=f.model, env=f.env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    try:
        for _ in range(600):
            if f.pid.exists() and f.pid.read_text() and f.ran():
                break
            time.sleep(0.1)
        load = int(f.pid.read_text().split()[0])
        assert not gone(load)                       # 5 s, past its 3 s stale: the beat keeps it while the caller lives
        p.kill()                                    # SIGKILL: no finally runs
        p.wait(timeout=10)
        assert gone(load, 10)                       # its beat stopped: it ended on its own
    finally:
        p.kill()
        for r in f.ran():
            try:
                os.kill(r["pid"], signal.SIGKILL)   # (the hanging stand-in suite this test started)
            except ProcessLookupError:
                pass


def test_the_real_load_ends_without_its_beat(tmp_path):
    cmd = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["suites"]["load"]
    beat = tmp_path / "beat"
    for touched in (False, True):                   # gone; then there but never touched again
        if touched:
            beat.touch()
        began = time.monotonic()
        p = subprocess.Popen(cmd.format(procs=2, beat=beat, stale=1), shell=True, cwd=ROOT, start_new_session=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            out, _ = p.communicate(timeout=20)
        finally:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
        took = time.monotonic() - began
        assert p.returncode == 0 and '"rc": 0' in out, out
        assert took < 10 and (took >= 1 or not touched), took
