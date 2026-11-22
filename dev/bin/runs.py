"""measure-runs: a definition's named acceptance measurement that a session cannot run (dev/README.md, *The pipeline
manager*): N runs of a pytest selection on a gap's branch head, each `[suites] measure` (under
scripts/suite_watch.py) in the shared suite slot, optionally with the CPU loaded by `[suites] load`: K busy processes
under a watchdog of their own (killed past 1,500 threads or 6 GB), stopped, their whole process group, when the runs end
(normally, on an error or a SIGTERM), and ending on their own within [suites] load_stale_s of this program's death
(a heartbeat it stops touching). A run during which the load had ended is a failure. Each in a suite container like
the fast suites' (the load in one of its own, role measure-load, which other processes' sweeps leave for WALL), but
with the stand-in AI. No run starts that would end past WALL by the longest run so far; those not started fail.

Hard maximums, at parse time (manage.py) and again here: N 1-50, K 1-8, the selection's `-n` 1-8. A run passes only on
exit 0 with the watchdog's own last line saying pytest's rc 0 and nothing killed: a run killed, or one whose log or
watchdog line cannot be read, is a failure, never a pass. manage.py records the counts and moves the gap."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import agents
import fac

MOST_RUNS, MOST_LOAD, MOST_WORKERS = 50, 8, 8
TEST = re.compile(r"tests/[\w/.-]+\.py(::[\w\[\].-]+)*")
TAIL = 1500                 # characters of a failing run's log kept: its traceback's tail
BEAT = ".git/measure-beat"  # the load's heartbeat, relative to the clone (loaded)
WALL = agents.TIMEOUTS["measure-load"]   # s: no run starts that would end past it (by the longest so far), so the load's
                                         # container (role measure-load) is never swept by another process mid-run


def bounded(n, most: int, what: str) -> int:
    if not 1 <= int(n) <= most:
        raise ValueError(f"{what} {n}: 1 to {most}")
    return int(n)


def count(text: str) -> int:
    """`--runs` at parse time."""
    return bounded(int(text), MOST_RUNS, "--runs")


def procs(text: str) -> int:
    """`--load` at parse time."""
    return bounded(int(text), MOST_LOAD, "--load")


def selection(text: str) -> list[str]:
    """The pytest selection: test files or ids under tests/, and at most one `-n K` (K 1-8). Anything else raises."""
    words, out = shlex.split(text), []
    while words:
        w = words.pop(0)
        if w == "-n" and words and words[0].isdigit() and "-n" not in out:
            out += [w, str(bounded(words.pop(0), MOST_WORKERS, "-n"))]
        elif TEST.fullmatch(w) and ".." not in w:
            out.append(w)
        else:
            raise ValueError(f"{w!r}: the selection is test files or ids under tests/ and one -n of 1-{MOST_WORKERS}")
    if not any(w.startswith("tests/") for w in out):
        raise ValueError("the selection names no test")
    return out


def outcome(rc: int, log: Path) -> dict:
    """One run, read from its log: passed only on exit 0 and the watchdog's last line saying rc 0, nothing killed."""
    try:
        text = log.read_text(errors="replace")
    except OSError as e:
        return {"rc": rc, "passed": False, "why": f"its log cannot be read ({type(e).__name__})"}
    watch = None
    for line in reversed(text.splitlines()):
        try:
            watch = json.loads(line) if line.startswith('{"rc"') else None
        except ValueError:
            watch = None
        if isinstance(watch, dict):
            break
    if not isinstance(watch, dict):
        why = "no watchdog line: the run cannot be read"
    elif watch.get("killed") or watch.get("workers_killed"):
        why = f"killed by the watchdog ({watch.get('killed') or 'a worker'})"
    elif rc or watch.get("rc") != 0:
        why = f"exit {rc} (pytest {watch.get('rc')})"
    else:
        return {"rc": rc, "passed": True}
    return {"rc": rc, "passed": False, "why": why, "tail": text[-TAIL:]}


@contextmanager
def loaded(cfg: dict, work: Path, k: int, log: Path):
    """``k`` busy processes (`[suites] load`) while the body runs, yielding its process (None for no load); their
    process group (and container) stopped after. The load also ends on its own: `{beat}` (BEAT, in the clone's .git,
    seen at /work in a container) is touched here every stale/6 s, and the load stops once it is gone or unchanged for
    `{stale}` s ([suites] load_stale_s, 1-300), so a caller killed past this finally (SIGKILL) leaves nothing busy."""
    if not k:
        yield None
        return
    stale, beat, stop = bounded(cfg["suites"].get("load_stale_s", 30), 300, "load_stale_s"), work / BEAT, threading.Event()
    beat.touch()

    def beating():
        while not stop.wait(stale / 6):
            beat.touch()
    threading.Thread(target=beating, daemon=True).start()
    cmd, name = cfg["suites"]["load"].format(procs=bounded(k, MOST_LOAD, "--load"), beat=BEAT, stale=stale), None
    if cfg["ai"]["mode"] != "standin":
        name, cmd = agents.contained(cfg, cmd, work, role="measure-load")
    with log.open("w") as out:
        p = subprocess.Popen(cmd, shell=True, cwd=work, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        yield p
    finally:
        stop.set()
        for sig in (signal.SIGTERM, signal.SIGKILL):        # (the watchdog stops what it watches on SIGTERM)
            if sig == signal.SIGKILL and p.returncode is not None:   # its leader reaped by the wait: the group id
                break                                                 # may be another's now
            try:
                os.killpg(p.pid, sig)
                p.wait(timeout=15)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
        if name:
            agents.killed(name)


def tip(cfg: dict, branch: str) -> str:
    ref = f"refs/heads/{fac.git_branch(branch)}"
    return fac.git(agents.drop(cfg), "rev-parse", "--verify", "-q", ref, check=False)


def measure(cfg: dict, gap: dict, n: int, tests: list[str], load: int = 0) -> dict:
    """The N runs on the branch head, in a clone of the drop at it (removed after): {head, n, passed, failed, tests,
    load, at, runs: each run's rc, whether it passed, and for a failure why, its log and its tail}."""
    n, load = bounded(n, MOST_RUNS, "--runs"), load and bounded(load, MOST_LOAD, "--load")
    tests = selection(shlex.join(tests))
    if gap["state"] not in ("parked", "built"):
        raise ValueError(f"{gap['id']} is {gap['state']}: only a parked or built gap is measured")
    branch = fac.branch_of(gap)
    head = tip(cfg, branch)
    if not head:
        raise ValueError(f"{gap['id']} has no branch {fac.git_branch(branch)} in the drop")
    cmd = cfg["suites"]["measure"].format(tests=shlex.join(tests))
    home, work = agents.clone(cfg, branch, "measure", at=head)
    logs, tag, runs = fac.run_dir(cfg, "measure"), fac.run_tag(branch, time.time()), []
    try:
        fac.wait_quiet(cfg)
        with loaded(cfg, work, load, logs / f"{tag}-load.txt") as busy:
            began, longest = time.monotonic(), 0.0
            for i in range(1, min(n, MOST_RUNS) + 1):
                if time.monotonic() - began + longest > WALL:     # never started: a failure, as any run not made
                    runs += [{"run": j, "rc": None, "passed": False, "why": f"not started: past the {WALL} s wall bound"}
                             for j in range(i, n + 1)]
                    break
                log, c, name, at = logs / f"{tag}-{i}.txt", cmd, None, time.monotonic()
                if cfg["ai"]["mode"] != "standin":
                    name, c = agents.contained(cfg, cmd, work)
                try:
                    rc, _ = fac.suite(cfg, "measure", work, log, command=c)
                finally:
                    if name:
                        agents.killed(name)
                longest = max(longest, time.monotonic() - at)
                got = outcome(rc, log)
                if busy is not None and busy.poll() is not None:     # the load ended: this run was not loaded
                    got = {**got, "passed": False, "why": f"the load had ended (exit {busy.returncode})"}
                runs.append({"run": i, **got, "log": fac.rel(log)})
    finally:
        shutil.rmtree(home, ignore_errors=True)
    passed = sum(r["passed"] for r in runs)
    return {"head": head, "n": n, "passed": passed, "failed": n - passed, "tests": tests, "load": load,
            "at": time.time(), "runs": runs}
