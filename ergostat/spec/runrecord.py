"""A machine block's run, held by nothing the engine owns (SPEC §9.1, *A run outlives its engine*).

A run starts in its own session. Its input is a file, its output goes to its run log file (``runs/RUN.out`` in the
state folder), and the engine follows that file: no pipe ties the run to the engine, so killing the engine never
kills the run. A small ``sh`` wrapper (POSIX: bash 3.2 and dash alike) writes the run's exit code to ``RUN.exit``
when it ends, whoever is watching. ``RUN.json`` is the run's record: the format of its files (``JOURNAL``), its pid,
its process's start time, its run id, its lease and its block. A pid alone names a process only until it is reused;
the pid and its start time together name one process, once. The files are removed once the run's end is recorded.

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
# The format of a run's files (its record, a kept run's journal, offset and keeper's folder), stated in its record as
# ``journal``: an engine takes up only a run of a format it reads (``adopt.refuse``). A record with none was written
# before it was stated, in format 1. Raise it with any change an engine before it could not read.
JOURNAL = 1
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


def write(f: dict[str, Path], pid: int, run_id: str, block: str, item: str | None, fence: int | None,
          more: dict | None = None) -> dict:
    """``more``: what a kept run's end needs from its start, should another engine end it (``adopt.settle``)."""
    rec = {"journal": JOURNAL, "pid": pid, "start": start_time(pid), "run": run_id, "block": block,
           "lease": {"item": item, "fence": fence} if item else None, **(more or {})}
    tmp = f["json"].with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec))
    os.replace(tmp, f["json"])
    return rec


def state(rec: dict) -> str:
    """Whether the run's process is still the one its record names: ``alive``; ``gone`` when no process has its pid,
    the one there has ended (a zombie) or is another process (its start time differs: the pid reused); ``unknown``
    when that cannot be told (no start time recorded, a pid that is not one, the process table unreadable), which is
    never taken as gone."""
    pid, start = rec.get("pid"), rec.get("start")
    if type(pid) is not int or pid <= 1 or not isinstance(start, str) or not start:
        return "unknown"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "gone"
    except PermissionError:
        pass                                                  # (there, another user's: its start time tells)
    except OSError:
        return "unknown"
    if sys.platform.startswith("linux"):
        try:
            text = Path(f"/proc/{pid}/stat").read_text()
        except (FileNotFoundError, ProcessLookupError):
            return "gone"
        except OSError:
            return "unknown"
        rest = text[text.rfind(")") + 2:].split()                 # (the name in brackets may hold spaces)
        if len(rest) < 20:
            return "unknown"
        return "gone" if rest[0] in ("Z", "X") or rest[19] != start else "alive"
    now = start_time(pid)
    if now is None:                                           # (ended since, or ps failed: told apart once more)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "gone"
        except OSError:
            pass
        return "unknown"
    return "alive" if now == start else "gone"


def alive(rec: dict) -> bool:
    return state(rec) == "alive"


def look(state_dir: Path, run_id: str) -> str:
    """The run's process now, from its record (``state``): ``none`` when it has no record (never started here, or its
    end read and its files removed); ``unknown`` when the record cannot be read or is not this run's, or when it has
    none yet but its input or output is there (its process may have started before its record was written): ``RUN.in``
    or ``RUN.out``, or a kept run's journal ``RUN.jsonl`` or its keeper's folder ``RUN/``."""
    if not SAFE.match(run_id or ""):
        return "unknown"
    runs = Path(state_dir) / "runs"
    try:
        rec = json.loads((runs / f"{run_id}.json").read_text())
    except FileNotFoundError:
        try:
            begun = any((runs / n).exists() for n in (f"{run_id}.in", f"{run_id}.out", f"{run_id}.jsonl", run_id))
        except OSError:
            return "unknown"
        return "unknown" if begun else "none"
    except (OSError, ValueError):
        return "unknown"
    if not isinstance(rec, dict) or rec.get("run") != run_id:
        return "unknown"
    return state(rec)


def remove(f: dict[str, Path]) -> None:
    for p in f.values():
        p.unlink(missing_ok=True)
