"""A machine block's run, held by nothing the engine owns (SPEC §9.1, *A run outlives its engine*).

A run starts in its own session. Its input is a file, its output goes to its run log file (``runs/RUN.out`` in the
state folder), and the engine follows that file: no pipe ties the run to the engine, so killing the engine never
kills the run. A small ``sh`` wrapper (POSIX: bash 3.2 and dash alike) writes the run's exit code to ``RUN.exit``
when it ends, whoever is watching. ``RUN.json`` is the run's record: its pid, its process's start time, its run id,
its lease and its block. A pid alone names a process only until it is reused; the pid and its start time together
name one process, once. The files are removed once the run's end is recorded.

With ``runs: outlive_engine`` the run is started by a keeper of its own instead (``compute/worker/keeper.py``), the
same wrapper inside it, and its output file is its journal, ``runs/RUN.jsonl``: stopping the engine leaves it going."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import uuid
from pathlib import Path

SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# $1: the run's command, $2: where its exit code goes (a line; an empty file is not yet an exit). A signal to the group
# (a timeout, a stop, a lease's SIGTERM) leaves the wrapper waiting for its command (a caught signal is the default
# again in the command); a command ended by a signal ends the wrapper by the same one, so its exit reads as before.
# Only signals that end a process plainly are raised again (an allowlist): a stop signal would leave the wrapper
# stopped, its run never ending, and one that dumps core (ABRT, SEGV...) would crash the wrapper's sh, leaving a core
# file or a crash report; those exit with the code instead (so a run killed by SEGV reads 139, not -11).
WRAP = ('trap : INT TERM; rc=0; /bin/sh -c "$1" || rc=$?; printf "%s\\n" "$rc" > "$2"; '
        'if [ "$rc" -gt 128 ] && s=$(kill -l "$rc" 2>/dev/null); then case "$s" in '
        '*HUP|*INT|*PIPE|*ALRM|*TERM|*USR1|*USR2|*KILL) trap - INT TERM; kill -s "$s" $$ ;; esac; fi; exit "$rc"')
CORE = {int(getattr(signal, n)) for n in ("SIGQUIT", "SIGILL", "SIGTRAP", "SIGABRT", "SIGBUS", "SIGFPE", "SIGSEGV",
                                          "SIGSYS", "SIGXCPU", "SIGXFSZ") if hasattr(signal, n)}


def by_signal(code) -> bool:
    """Whether a run's exit code says a signal ended it: -N, or 128+N for a signal that dumps core (the wrapper exits
    with that code instead of raising it; a plain ``exit 139`` reads the same and is taken as a signal too)."""
    return isinstance(code, int) and not isinstance(code, bool) and (code < 0 or code - 128 in CORE)


def files(state_dir: Path, run_id: str) -> dict[str, Path]:
    """The run's four files, named by its run id (a fresh name when the id is not a plain file name)."""
    d = Path(state_dir).resolve() / "runs"                      # (absolute: the wrapper writes its exit from the run's cwd)
    d.mkdir(exist_ok=True)
    name = run_id if SAFE.match(run_id or "") else uuid.uuid4().hex
    return {k: d / f"{name}.{k}" for k in ("json", "in", "out", "exit")}


def command(cmd: str, f: dict[str, Path]) -> list[str]:
    return ["/bin/sh", "-c", WRAP, "ergostat-run", cmd, str(f["exit"])]


def start_time(pid: int) -> str | None:
    """When process ``pid`` started, as the system says it (None: no such process, or it has ended). Linux: its start
    in clock ticks since boot (``/proc/PID/stat``, field 22); elsewhere (macOS): ``ps -o lstart=``."""
    if sys.platform.startswith("linux"):
        try:
            text = Path(f"/proc/{int(pid)}/stat").read_text()
        except (OSError, ValueError):
            return None
        rest = text[text.rfind(")") + 2:].split()                 # (the name in brackets may hold spaces)
        return None if len(rest) < 20 or rest[0] in ("Z", "X") else rest[19]
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))], capture_output=True, text=True, timeout=5)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def write(f: dict[str, Path], pid: int, run_id: str, block: str, item: str | None, fence: int | None) -> dict:
    rec = {"pid": pid, "start": start_time(pid), "run": run_id, "block": block,
           "lease": {"item": item, "fence": fence} if item else None}
    tmp = f["json"].with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec))
    os.replace(tmp, f["json"])
    return rec


def alive(rec: dict) -> bool:
    """Whether the run's process is still the one its record names: a pid now held by another process (its start time
    differs), or unread, counts as gone."""
    start = start_time(rec.get("pid") or 0) if rec.get("start") else None
    return start is not None and start == rec["start"]


def remove(f: dict[str, Path]) -> None:
    for p in f.values():
        p.unlink(missing_ok=True)
