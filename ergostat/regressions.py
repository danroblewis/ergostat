"""The reader behind ``use: regressions``' passing counts (dev/records/regression-template.md): ``python -m
ergostat.regressions counts`` runs the model's own ``claims: tests`` command (SPEC §12g) and prints how many of its
tests failed (failed and errors), read from the pytest-style summary it ends with. A run it cannot read gives no
value (exit 1, nothing printed), never 0: no command declared, a model that does not load, its `in:` folder not there
(waited for, within its time), a run past its time, no summary, a summary that counts nothing, or a run that exited
non-zero with no failure counted."""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

BEGAN = time.monotonic()                                  # the reader's start, as near as it can see it

SUMMARY = re.compile(r"^=*\s*(.*?)\s+in\s+[\d.]+\s*s(?:econds)?\b.*?=*$")   # "== 3 passed, 1 failed in 0.52s =="
COUNT = re.compile(r"^(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?|rerun)$")
RAN = {"passed", "failed", "errors", "xfailed", "xpassed"}


def parse(text: str) -> dict[str, int] | None:
    """The counts of the last pytest-style summary line in ``text`` (``error`` and ``warning`` folded into their
    plurals), or None when there is none or no test ran ("no tests ran", only skipped: not a pass)."""
    for line in reversed(text.splitlines()):
        m = SUMMARY.match(line.strip())
        if not m:
            continue
        parts = [COUNT.match(x.strip()) for x in m.group(1).split(",")]
        if None in parts:
            continue                                      # "done in 3s", "no tests ran in 0.01s": not counts
        got: dict[str, int] = {}
        for c in parts:
            word = {"error": "errors", "warning": "warnings"}.get(c.group(2), c.group(2))
            got[word] = got.get(word, 0) + int(c.group(1))
        return got if RAN & set(got) else None            # only skipped or deselected: nothing ran
    return None


def failing(counts: dict[str, int]) -> int:
    return counts.get("failed", 0) + counts.get("errors", 0)


def guard(group: int) -> int:
    """A child that outlives this reader: if the reader ends before saying the run is over (the sensor's own timeout
    kills only it), the guard kills the run's whole process group. Returns the pipe to say so on."""
    r, w = os.pipe()
    if os.fork():
        os.close(r)
        return w
    os.close(w)
    for fd in (0, 1, 2):                                  # the sensor's pipes: not held open past the reader
        os.close(fd)
    try:
        if not os.read(r, 1):                             # nothing said: the reader is gone, the run may not be
            os.killpg(group, signal.SIGKILL)
    finally:
        os._exit(0)


def counts(within: float) -> tuple[int | None, str]:
    """The model's tests run once: how many failed, or None and why not."""
    from .spec import SpecError, find, load
    main = find(Path.cwd())
    try:
        spec = load(main) if main else None
    except SpecError as e:
        return None, f"the model does not load: {e}"
    if spec is None or (c := spec.claims.get("tests")) is None:
        return None, "no model here, or it declares no claims: tests command"
    env = {**os.environ, "ERGOSTAT_ROOT": str(spec.root)}
    where, parent, end = Path(spec.root) / c.in_, os.getppid(), time.monotonic() + min(c.timeout, within)
    while not where.is_dir():                             # made by the model's own first run, maybe not yet
        if time.monotonic() >= end or os.getppid() != parent:
            return None, f"no folder {c.in_} to run the tests in"
        time.sleep(0.2)
    p = subprocess.Popen(c.run, shell=True, cwd=where, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
    said = guard(p.pid)
    try:
        while True:                                       # until the run ends, its time is up, or the sensor's
            try:                                          # shell above this reader is killed (its timeout)
                out, _ = p.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= end or os.getppid() != parent:
                    os.killpg(p.pid, signal.SIGKILL)      # the whole run, not only its shell
                    p.communicate()
                    return None, f"no answer within {min(c.timeout, within):g}s"
    finally:
        os.write(said, b"x")                              # the run is over and reaped: the guard kills nothing
        os.close(said)
    got = parse(out)
    if got is None:
        return None, f"exited {p.returncode} with no test summary"
    if p.returncode != 0 and not failing(got):
        return None, f"exited {p.returncode} with no failure counted"
    return failing(got), ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ergostat.regressions")
    ap.add_argument("what", choices=["counts"])
    ap.add_argument("--within", type=float, default=600.0, help="seconds the run may take, at most")
    a = ap.parse_args(argv)
    left = a.within - max(2.0, 0.05 * a.within) - (time.monotonic() - BEGAN)   # before the sensor's own timeout
    n, why = counts(max(left, 0.1))
    print(why if n is None else n, file=sys.stderr if n is None else sys.stdout)
    return 1 if n is None else 0


if __name__ == "__main__":
    sys.exit(main())
