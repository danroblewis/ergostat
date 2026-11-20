"""The load interlock's sensor: `load.py suites | threads | memory` prints one reading.

  suites    test suites running on this machine now: processes whose command is `python -m pytest` (anyone's: the
            coordinator's, a block's, another agent's), the same test the coordinator's wait uses, and the factory's
            suite containers
  threads   the threads of those suites' process trees, with every process scripts/suite_watch.py tagged
  memory    their resident memory, in GB

scripts/suite_watch.py kills a suite past 1,500 threads or 6 GB: that is the hard rule. These readings are what the
goals read to hold the suite-running blocks while the machine is busy."""

from __future__ import annotations

import re
import subprocess
import sys

TAG = "ERGOSTAT_SUITE_WATCH="
SUITE = re.compile(r"^[^ ]*python[0-9.]* -m pytest")         # the coordinator's own wait: the same test as fac.py's


def processes() -> dict[int, tuple[int, int, str]]:
    """pid -> (ppid, RSS in KB, command with its environment where ps gives it)."""
    flags = ["-A", "-ww", "-o", "pid=,ppid=,rss=,command="]
    if sys.platform == "darwin":
        flags.insert(1, "-E")
    out = subprocess.run(["ps", *flags], capture_output=True, text=True, timeout=30).stdout
    rows = {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[0].isdigit():
            rows[int(parts[0])] = (int(parts[1]), int(parts[2]), parts[3] if len(parts) > 3 else "")
    return rows


def docker_suites() -> int:
    """The factory's suite containers (ergostat-factory-suite-*): their processes run in Docker's VM, not here."""
    try:
        got = subprocess.run(["docker", "ps", "-q", "--filter", "name=ergostat-factory-suite-"], capture_output=True,
                             text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    return len(got.stdout.split())


def suite_trees(rows: dict) -> set[int]:
    kids: dict[int, list[int]] = {}
    for pid, (ppid, _, _) in rows.items():
        kids.setdefault(ppid, []).append(pid)
    roots = [p for p, (_, _, cmd) in rows.items() if SUITE.match(cmd.strip()) or TAG in cmd]
    mine, todo = set(), list(roots)
    while todo:
        p = todo.pop()
        if p not in mine:
            mine.add(p)
            todo.extend(kids.get(p, []))
    return mine


def threads(pids: set[int]) -> int:
    if not pids:
        return 0
    flag = "-L" if sys.platform.startswith("linux") else "-M"
    out = subprocess.run(["ps", flag, "-p", ",".join(map(str, sorted(pids)))], capture_output=True, text=True,
                         timeout=30).stdout
    return max(0, len(out.splitlines()) - 1)


def reading(what: str) -> float:
    rows = processes()
    if what == "suites":
        return float(sum(1 for _, _, cmd in rows.values() if SUITE.match(cmd.strip())) + docker_suites())
    pids = suite_trees(rows)
    if what == "threads":
        return float(threads(pids))
    if what == "memory":
        return round(sum(rows[p][1] for p in pids) / 1024 / 1024, 2)
    raise SystemExit(f"load.py: suites, threads or memory, not {what!r}")


if __name__ == "__main__":
    print(reading(sys.argv[1]))
