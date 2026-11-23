"""measure-runs (docs/roadmap/overnight/dod-measured-runs.md): a gap's named acceptance measurement run by the
factory, N watched runs on its branch head (dev/bin/runs.py, manage.py measure-runs), with stand-in suites and a
stand-in load (a sleep, never a real one) on the pipeline manager's fixture."""

from __future__ import annotations

import json
import os
import re
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
    for until, why in ((None, "needs nothing said"), ({"action": "the owner's approval"}, "the owner's approval")):
        f.set_state("parked", parked_for="needs", resumed_as=None, parked_until=until)   # a need no measurement meets
        assert why in f.measure("pass", "--runs", "1", "--tests", "tests/test_x.py", ok=False), until
    assert len(f.ran()) == 1 and f.item(f.gid)["state"] == "parked"
    f.set_state("parked", parked_for="needs", parked_until={"action": "30 loaded runs (manage.py measure-runs)"})
    assert "back to built" in f.measure("pass", "--runs", "1", "--tests", "tests/test_x.py")


def approved_through_the_gate(f: Measured, act, args: dict, monkeypatch) -> tuple[dict, float, int]:
    """The model's manager-measure, asked and approved in a real ergostat project by gate.approve (as the inbox or
    `actions --approve` does): (the action after, the seconds approve took, the detached measurement's pid or 0)."""
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project
    home = f.tmp / f"approver-{time.monotonic_ns()}"
    home.mkdir()
    run = act.run.replace("python3 dev/bin/manage.py", f"{sys.executable} {BIN / 'manage.py'}")
    (home / "ergostat.yaml").write_text(json.dumps({
        "name": "t", "items": {"ticket": {"id": "ticket/*", "states": ["open"]}},
        "actions": {"measure": {"run": f"cd {f.model} && {run}", "gate": "approve", "args": dict.fromkeys(args, "x")}},
        "blocks": {"dev": {"type": "ai", "prompt": "Work.", "tools": ["Read"], "actions": ["measure"], "every": "1h"}}}))
    p = Project(mdl.load(home))
    for k, v in f.env.items():
        monkeypatch.setenv(k, v)
    a = gate.request(p, p.model.spec, "measure", args, {"block": "dev", "run": "r", "session": "session/dev-1",
                                                         "item": "ticket/1", "workdir": str(home)})
    assert a["state"] == "requested"
    began = time.monotonic()
    a = gate.approve(p, p.model.spec, a["id"])
    took = time.monotonic() - began
    pid = int(m.group(1)) if (m := re.search(r"pid (\d+)", a.get("output") or "")) else 0
    return a, took, pid


def test_the_manager_s_measurement_is_asked_not_run_inside_its_block(tmp_path, monkeypatch):
    from ergostat.spec import read
    spec, _ = read(ROOT / "ergostat.yaml")
    act, block = spec.actions["manager-measure"], spec.blocks["pipeline-manager"]
    assert act.gate == "approve" and act.timeout < block.timeout < runs_module().WALL    # (it only starts it, detached)
    assert "manager-measure" in block.params["actions"] and "--detach" in act.run
    f = Measured(tmp_path)
    head = f.tip()
    sit = f.watch()
    answer = {"calls": [["measure-runs", f.gid, "--runs", "2", "--tests", "-n 8 tests/test_leases.py", "--load", "2",
                         "--why", "its 30 loaded runs"]], "answers": {}, "summary": "asked for the measurement"}
    said, _ = f.run("manager.py", sit["id"], FACTORY_STANDIN_PIPELINE_MANAGER="```json\n" + json.dumps(answer) + "\n```")
    f.drain()
    (done,) = f.item(sit["id"])["fields"]["actions"]
    assert done["ok"] and "manager-measure: held for the coordinator" in done["said"], done
    assert f.ran() == [] and not f.pid.exists() and f.item(f.gid)["state"] == "built"      # nothing ran in the block
    (asked,) = [a for a in f.db()["acts"] if a[1] == "manager-measure"]
    args = dict(x.split("=", 1) for x in asked[asked.index("--arg"):][1::2])
    assert args == {"gap": f.gid, "runs": "2", "tests": "-n 8 tests/test_leases.py", "load": "2",
                    "why": "its 30 loaded runs"}
    f.plan.write_text("wait wait")                                 # approved through the gate: started, not waited for
    a, took, pid = approved_through_the_gate(f, act, args, monkeypatch)
    assert a["state"] == "ran" and "measure-runs started" in a["output"] and took < 30, a
    assert not gone(pid, 0.1) and os.getsid(pid) == pid != os.getsid(0)   # still running, in a session of its own
    assert gone(pid, 120)                                          # it ends on its own and records its counts
    f.drain()
    assert [x["argv"][-3:] for x in f.ran()] == [["-n", "8", "tests/test_leases.py"]] * 2
    (m,) = f.item(f.gid)["fields"]["measured_runs"]
    assert (m["head"], m["passed"], m["load"]) == (head, 2, 2) and f.item(f.gid)["state"] == "built"
    (i,) = [x for x in f.interventions("pipeline-manager") if x["fields"].get("asked_as")]
    assert i["fields"]["asked_as"] == a["id"] and i["fields"]["passed"] == 2          # by its asker, the action named
    f.set_state("parked", parked_for="defect", resumed_as="gap/alpha-thing-continued")   # refused at its start:
    a, _, _ = approved_through_the_gate(f, act, args, monkeypatch)                    # the action said so, nothing run
    assert a["state"] == "failed" and "resumed already" in a["output"] and len(f.ran()) == 2, a
    f.set_state("parked", parked_for="defect", resumed_as=None)    # refused when its runs end: its end recorded too
    f.plan.write_text("resume")
    a, _, pid = approved_through_the_gate(f, act, {**args, "runs": "1"}, monkeypatch)
    assert a["state"] == "ran" and gone(pid, 120)
    f.drain()
    (i,) = [x for x in f.interventions("pipeline-manager") if x["fields"].get("ended")]
    assert "recorded alone" in i["fields"]["reason"] and i["fields"]["asked_as"] == a["id"]
    assert f.item(f.gid)["state"] == "parked"
    f.set_state("parked", parked_for="kill-rule", resumed_as=None)  # refused when asked, as it would be when run
    done = f.py("import fac, manage\nmanage.BY[0] = 'pipeline-manager'\nprint(json.dumps(manage.run(fac.config(), "
                "['measure-runs', sys.argv[1], '--runs', '1', '--tests', 'tests/test_x.py'])))", f.gid)
    assert not done["ok"] and "kill-rule" in done["said"]
    assert len([a for a in f.db()["acts"] if a[1] == "manager-measure"]) == 1


def test_a_sigterm_to_the_detached_measurement_records_its_end(tmp_path, monkeypatch):
    from ergostat.spec import read
    act = read(ROOT / "ergostat.yaml")[0].actions["manager-measure"]
    f = Measured(tmp_path)
    f.plan.write_text("hang")
    args = {"gap": f.gid, "runs": "1", "tests": "tests/test_x.py", "load": "1", "why": "stopped by hand"}
    a, _, pid = approved_through_the_gate(f, act, args, monkeypatch)
    try:
        assert a["state"] == "ran" and pid, a
        for _ in range(600):
            if f.ran() and f.pid.exists() and f.pid.read_text():
                break
            time.sleep(0.1)
        suite, load = f.ran()[0]["pid"], int(f.pid.read_text().split()[0])
        os.kill(pid, signal.SIGTERM)                # the pid the action's output gives, the obvious way to stop it
        assert gone(pid, 40) and gone(suite, 5) and gone(load, 5)
        f.drain()
        (i,) = [x for x in f.interventions("pipeline-manager") if x["fields"].get("ended")]
        assert i["fields"]["ended"] == "stopped" and i["fields"]["asked_as"] == a["id"]
        assert "SIGTERM" in i["fields"]["reason"]
        log = f.model / re.search(r"its log (\S+?);", a["output"]).group(1)
        assert "does not parse" not in log.read_text()            # (a SIGTERM is not said as a call refused)
        assert f.item(f.gid)["state"] == "built" and not f.item(f.gid)["fields"].get("measured_runs")
    finally:
        for p in [pid, *(r["pid"] for r in f.ran())]:
            try:
                if p > 0:                           # (never 0: that is this test's own group)
                    os.kill(p, signal.SIGKILL)
            except ProcessLookupError:
                pass


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


def test_the_load_stops_with_its_caller_on_sigterm(tmp_path):
    f = Measured(tmp_path)
    deaf = tmp_path / "deaf.py"                     # a load that never reads its beat: only the stop can end it
    deaf.write_text("import os, sys, time\nopen(sys.argv[1], 'w').write(f'{os.getpid()} 1')\ntime.sleep(120)\n")
    f.config.write_text(f.config.read_text().replace(str(tmp_path / "burn.py"), str(deaf)))
    f.plan.write_text("hang")
    p = subprocess.Popen([sys.executable, str(BIN / "manage.py"), "measure-runs", f.gid, "--runs", "1", "--tests",
                          "tests/test_x.py", "--load", "1"], cwd=f.model, env=f.env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    try:
        for _ in range(600):
            if f.pid.exists() and f.pid.read_text() and f.ran():
                break
            time.sleep(0.1)
        load, suite = int(f.pid.read_text().split()[0]), f.ran()[0]["pid"]
        assert not gone(load, 2)
        p.send_signal(signal.SIGTERM)               # its finally runs: the load's group stopped at once
        p.wait(timeout=40)
        assert gone(load, 5) and gone(suite, 5)
    finally:
        p.kill()
        if f.pid.exists() and f.pid.read_text():
            try:
                os.kill(int(f.pid.read_text().split()[0]), signal.SIGKILL)   # (the deaf load, if this test failed)
            except ProcessLookupError:
                pass
        for r in f.ran():
            try:
                os.kill(r["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_no_run_starts_past_the_wall_bound(tmp_path):
    f = Measured(tmp_path)
    f.plan.write_text("wait wait wait")
    got = f.py("import fac, manage, runs\ncfg = fac.config()\nruns.WALL = 1.5\n"
               "m = runs.measure(cfg, manage.item(sys.argv[1]), 3, ['tests/test_x.py'])\n"
               "print(json.dumps([[r['passed'], r.get('why')] for r in m['runs']] + [m['passed'], m['failed']]))", f.gid)
    late = "not started: past the 1.5 s wall bound"
    assert got == [[True, None], [False, late], [False, late], 1, 2] and len(f.ran()) == 1


def test_a_run_that_hangs_is_stopped_at_the_wall_bound(tmp_path):
    f = Measured(tmp_path)
    f.plan.write_text("hang pass")                  # (the stand-in sleeps 60 s: only the wall can end it sooner)
    began = time.monotonic()
    got = f.py("import fac, manage, runs\ncfg = fac.config()\nruns.WALL = 2\n"
               "m = runs.measure(cfg, manage.item(sys.argv[1]), 2, ['tests/test_x.py'])\n"
               "print(json.dumps([[r['passed'], r.get('rc'), r.get('why')] for r in m['runs']] + [m['failed']]))", f.gid)
    assert got == [[False, None, "stopped: past the 2 s wall bound"], [False, None, "not started: past the 2 s wall bound"], 2]
    assert time.monotonic() - began < 40 and len(f.ran()) == 1 and gone(f.ran()[0]["pid"])   # its group stopped
    f.plan.write_text("pass")                       # off the main thread no SIGALRM bounds a run: refused, none made
    got = f.py("import fac, manage, runs, threading\ncfg, said = fac.config(), []\n"
               "def go():\n    try:\n        runs.measure(cfg, manage.item(sys.argv[1]), 1, ['tests/test_x.py'])\n"
               "    except ValueError as e:\n        said.append(str(e))\n"
               "t = threading.Thread(target=go)\nt.start()\nt.join()\nprint(json.dumps(said))", f.gid)
    assert got and "no wall bound" in got[0] and len(f.ran()) == 1


def test_the_load_survives_another_process_s_sweep(tmp_path, monkeypatch):
    runs = runs_module()
    agents, made, listing = runs.agents, [], [""]
    real = agents.contained

    def contained(cfg, cmd, work, role="suite"):
        name, _ = real(cfg, cmd, work, role)
        made.append(name)
        return name, "sleep 30"                     # (no docker: a sleeper stands in for the load's container)
    monkeypatch.setattr(agents, "contained", contained)
    monkeypatch.setattr(agents, "docker", lambda *a, **k: subprocess.CompletedProcess(a, 0, listing[0], ""))
    monkeypatch.setattr(agents, "killed", lambda name: None)
    (tmp_path / ".git").mkdir()
    cfg = {"suites": {"load": "unused", "load_stale_s": 3}, "ai": {"mode": "claude"}, "agents": {}}

    def made_ago(name: str, hours: float) -> str:
        return f"{name}\t{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - hours * 3600))} +0000 UTC\n"
    with runs.loaded(cfg, tmp_path, 1, tmp_path / "load.txt") as busy:
        (name,) = made
        assert name.startswith(agents.PREFIX + "measure-load-")
        agents.RUNNING.discard(name)                # another process's sweep: the load is not in its RUNNING
        other = agents.PREFIX + "suite-0123456789"
        listing[0] = made_ago(name, runs.WALL / 3600 - 0.5) + made_ago(other, 2)
        assert agents.sweep(cfg) == [other]         # a suite past its 70 min is swept; the load, inside WALL, is not
        listing[0] = made_ago(name, runs.WALL / 3600 + 1)
        assert agents.sweep(cfg) == [name]          # past WALL and its slack: a leftover, swept
    assert gone(busy.pid)


def flake_rate(f) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BIN / "measure.py"), "flake-rate"], cwd=f.model, env=f.env,
                          capture_output=True, text=True)


def a_green_run_lands(f, name: str) -> None:
    """A gap merged by a queue run of its own that excused nothing (gap.merged as queue.py says it)."""
    now = time.time()
    f.fold([{"event": "gap.merged", "item": f"gap/{name}", "data": {
        "merged_at": now, "queued_at": now, "queue_attempts": 1, "batch_id": f"{name}-run", "suites_queue": {
            "unit": {"rc": 0, "seconds": 60}}, "queue_runs": [{"run": f"{name}-run", "minutes": 5, "at": now}]}}], None)


def test_a_run_excused_in_the_queue_moves_flake_rate(tmp_path):
    from tests.test_factory import approved_gaps, flaky_stand_ins
    f = flaky_stand_ins(tmp_path, ["tests/test_b.py::test_b"])
    approved_gaps(f, {"a": 1}, bad="a")
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"]                     # red, excused, landed
    assert f.flakes_said() == ["flake.seen"]                                          # (said by event --add)
    assert f.item("gap/a")["fields"]["suites_queue"]["excused"]
    r = flake_rate(f)
    assert r.returncode == 0 and float(r.stdout) == 1.0, r.stderr                     # one run, one flake
    a_green_run_lands(f, "b")
    r = flake_rate(f)
    assert r.returncode == 0 and float(r.stdout) == 0.5, r.stderr                     # two runs, one flake


def test_an_excused_batch_counts_once(tmp_path):
    from tests.test_factory import approved_gaps, flaky_stand_ins
    f = flaky_stand_ins(tmp_path, ["tests/test_b.py::test_b"])
    approved_gaps(f, {"p": 1, "q": 2, "r": 3}, bad="q", batch=3)
    said, _ = f.run("queue.py", "gap/p")
    assert said.count("gap.merged") == 3 and f.flakes_said() == ["flake.seen"]        # (said by event --add)
    landed = [f.item(f"gap/{g}")["fields"] for g in "pqr"]
    assert all(g["suites_queue"].get("excused") for g in landed)                    # each of the three carries it
    assert len({g["batch_id"] for g in landed}) == 1
    r = flake_rate(f)
    assert r.returncode == 0 and float(r.stdout) == 1.0, r.stderr                     # one run excused, never three
    a_green_run_lands(f, "s")
    assert float(flake_rate(f).stdout) == 0.5


def test_flake_rate_with_no_runs_has_no_value(tmp_path):
    from tests.test_factory import Factory
    f = Factory(tmp_path)
    old = time.time() - 30 * 86400                                                    # a run before the window
    f.fold([{"event": "gap.queued", "item": "gap/t", "data": {"queued_at": time.time(), "queue_attempts": 1}},
            {"event": "gap.retried", "item": "gap/t", "data": {"approved_by": "flake-retry", "retries": 1}},
            {"event": "gap.merged", "item": "gap/old", "data": {"merged_at": old, "queue_runs": [
                {"run": "old-run", "minutes": 5, "at": old}]}}], None)
    r = flake_rate(f)
    assert r.returncode == 1 and r.stdout.strip() == "" and "no value" in r.stderr    # never 0.0
    a_green_run_lands(f, "u")                                                         # triage's retry counts as before
    r = flake_rate(f)
    assert r.returncode == 0 and float(r.stdout) == 1.0, r.stderr
