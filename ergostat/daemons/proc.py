"""One daemon's process (SPEC §9.7). What is written to it goes through a bounded queue to a writer thread of its own,
so nothing that hands it work waits on it (a full queue, or a write waiting too long, is the supervisor's to see). A
reader thread gives each line it prints to what it is tagged for: a run's lines to that run (those read together, in
batches: ``lines.py``), ``done`` (strict) ends it, a reading answers its request or is pushed for its sensor, an
observation goes to its sensor (``observe.py``); every line says it lives. A line tagged with nothing,
or with a run or request it does not hold, is written to its log and dropped: never given to another run."""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import signal
import subprocess
import threading
import time

from ..costs.sampler import Measured
from . import lines, observe, usage

QUEUE = 1000                 # lines waiting for its standard input, at most
CHUNK = 65536                # bytes read from its standard output at once
LINE_MAX = 1 << 20           # a line longer than this (1 MiB) is dropped, never held
SHARED = {"ERGOSTAT_CMD", "ERGOSTAT_PROJECT", "ERGOSTAT_STATE_DIR", "ERGOSTAT_SOCKET", "ERGOSTAT_HOME"}
GROUPS: set[int] = set()         # every daemon's process group not yet seen gone (``supervise.killpg``, ``end_all``)
GROUPS_LOCK = threading.Lock()   # held for the set's own operations only: never across a wait, a signal or I/O
CLOSING = False                  # set by ``supervise.end_all`` (ergostat starting itself again): a new group kills itself


# not run by ``exec``: a shell's keywords and the builtins that are not programs (``exec cd`` fails)
_NOT_PROGRAMS = {"!", "{", "}", "[[", "case", "for", "function", "if", "select", "until", "while", "time", ".", ":",
                 "alias", "bg", "break", "builtin", "cd", "command", "continue", "eval", "exec", "exit", "export",
                 "fg", "jobs", "local", "readonly", "return", "set", "shift", "source", "trap", "ulimit", "umask",
                 "unalias", "unset", "wait", "read", "pushd", "popd", "let", "getopts", "type", "hash", "declare",
                 "typeset", "dirs", "disown", "enable", "shopt", "suspend", "times", "caller", "mapfile", "readarray"}
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def execd(run: str) -> str:
    """The daemon's command for ``sh -c``, with ``exec`` before its program when it is one simple command, so the
    shell becomes the program and the pid recorded is the program's on every OS: macOS's ``sh`` (bash) does that by
    itself, Debian's (dash) forks and waits. Anything else (a pipeline, a list, a redirection, a keyword, a builtin,
    several lines, a command that begins with an assignment) is left as it is: its shell stays, and the pid is the
    shell's. Either way that pid leads a session of its own, so signals reach the whole group, the program in it
    (``supervise.killpg``)."""
    run = run.strip()                                # (a YAML block scalar ends in a newline)
    if "\n" in run or "`" in run:
        return run
    try:
        lex = shlex.shlex(run, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""                          # (``prog a#b; other``: never a comment that hides the ``;``)
        words = list(lex)
    except ValueError:                               # (unbalanced quotes: the shell's to report)
        return run
    if not words or any(w and all(c in lex.punctuation_chars for c in w) for w in words):
        return run
    if _ASSIGNMENT.match(words[0]) or words[0] in _NOT_PROGRAMS:   # (``A=1 exec prog`` may not export A)
        return run
    return "exec " + run


class Handle:
    """A run, or a reading asked for, that the daemon holds."""

    def __init__(self, take=None, answer=None, block: str | None = None, deadline: float | None = None):
        self.take, self._answer, self.block, self.deadline = take, answer, block, deadline
        self.done = threading.Event()
        self.code: int | None = None
        self.note = ""
        self.requeue = False             # given back uncounted: its daemon restarted for something else's fault
        self.cancelled: float | None = None
        self.asked = False               # the owner's stop
        self.sent = False                # its line queued for the daemon (a cancel is sent only after it)
        self.resources: dict | None = None   # a warm process's run: the CPU its group used while it held it

    def answer(self, v, why: str) -> None:
        if not self.done.is_set():
            self.done.set()
            self._answer(v, why)

    def end(self, code: int | None, note: str = "", requeue: bool = False) -> None:
        if not self.done.is_set():
            self.code, self.note, self.requeue = code, note, requeue
            self.done.set()


class Process:
    def __init__(self, d, cwd, env: dict, log, on_push, on_observe=lambda sensor, obj, now: False):
        self.d, self.log, self.on_push, self.on_observe = d, log, on_push, on_observe
        self.partial, self.skipping = b"", False     # (the reader's: a line not yet whole; one over LINE_MAX)
        self.read_at: float | None = None            # (the reader's: when this read came, on observe's clock)
        self.q: queue.Queue = queue.Queue(QUEUE)
        self.lock = threading.Lock()
        self.runs: dict[str, Handle] = {}
        self.requests: dict[str, Handle] = {}
        self.writing_since: float | None = None
        self.full = False
        self.last_out = time.monotonic()
        self.idle_since: float | None = None      # (draining: when its last run ended)
        self.served = 0
        self.ended = threading.Event()
        self.before: dict[int, float] = {}       # (warm) its group's CPU when it was handed its run
        self.recycle: tuple[str, bool] | None = None   # (warm) why it is replaced once it holds nothing; counted?
        self.stopping = False                    # ``stop`` queued: nothing more is handed to it
        log.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} starting: {d.run}\n")
        log.flush()
        env = {k: v for k, v in env.items() if not k.startswith("ERGOSTAT_") or k in SHARED}   # (an item's: in its line)
        self.proc = Measured(execd(d.run), shell=True, cwd=cwd, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=log, start_new_session=True)
        self.pid = self.proc.pid                     # the program's (``execd``), or its shell's; either way the
                                                     # session's leader, so its group's id (``supervise.killpg``)
        with GROUPS_LOCK:                            # checked and added under one lock: in end_all's snapshot, or
            closing = CLOSING                        # killed here, never spawned past it unseen
            if not closing:
                GROUPS.add(self.pid)
        if closing:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except OSError:
                pass
        threading.Thread(target=self._write, name=f"daemon-{d.name}-in", daemon=True).start()
        threading.Thread(target=self._read, name=f"daemon-{d.name}-out", daemon=True).start()

    # ---- in

    def send(self, obj: dict) -> bool:
        """Queued for its standard input, never waited on: False (and ``full``) when its queue is full."""
        try:
            self.q.put_nowait(json.dumps(obj) + "\n")
            return True
        except queue.Full:
            self.full = True
            return False

    def _write(self) -> None:
        f = self.proc.stdin
        while (line := self.q.get()) is not None:
            self.writing_since = time.monotonic()
            try:
                f.write(line.encode())
                f.flush()
            except (OSError, ValueError):            # it is gone: its reader sees it end
                break
            finally:
                self.writing_since = None
        try:
            f.close()
        except (OSError, ValueError):
            pass

    def stop(self) -> None:
        """Asked to finish what it holds and end: ``stop``, then its standard input closed."""
        with self.lock:                              # (with ``hand``'s: a run's line is queued before it, or never)
            self.stopping = True
            self.send({"op": "stop"})
            try:
                self.q.put_nowait(None)
            except queue.Full:
                pass

    # ---- out

    def _read(self) -> None:
        fd = self.proc.stdout.fileno()
        while True:
            try:
                data = os.read(fd, CHUNK)
            except OSError:
                data = b""
            if not data:
                break
            self.chunk(data)
        self.chunk(b"", eof=True)
        self.proc.wait()
        self.ended.set()

    def chunk(self, data: bytes, eof: bool = False) -> None:
        """One read's bytes: its whole lines (UTF-8, what is not replaced) taken in ``lines.plan``'s order, a run's
        together; a partial line kept for the rest of it (at the end of the output, taken as it is). A line over
        ``LINE_MAX`` is dropped up to its newline, said once, never held."""
        self.last_out, self.read_at = time.monotonic(), observe._now()   # (its observations judged at one time)
        if self.skipping:                            # (the rest of a line over LINE_MAX, up to its newline)
            cut = data.find(b"\n")
            if cut < 0:
                return
            data, self.skipping = data[cut + 1:], False
        *whole, self.partial = (self.partial + data).split(b"\n")
        if eof and self.partial:
            whole.append(self.partial)
            self.partial = b""
        if len(self.partial) > LINE_MAX:
            self.stray(self.partial[:500].decode("utf-8", "replace"), "a line over 1 MiB", False)
            self.partial, self.skipping = b"", True
        texts = []
        for raw in whole:
            if len(raw) > LINE_MAX:
                self.stray(raw[:500].decode("utf-8", "replace"), "a line over 1 MiB", False)
            else:
                texts.append(raw.decode("utf-8", "replace").strip())
        for step in lines.plan(texts):
            if step[0] == "one":
                try:
                    self.line(step[1])
                except Exception as err:             # (a run ended meanwhile, its log closed): never the reader's end
                    self.stray(step[1], f"{type(err).__name__}: {err}", False)
                continue
            _, run, got = step
            with self.lock:
                h = self.runs.get(run)
            if h is None:
                for x in got:
                    self.stray(f"(run {run}) {x}", "no run of that id held")
                continue
            try:
                h.take(got)
            except Exception as err:                 # (the batch as a whole: each of its lines said dropped)
                for x in got:
                    self.stray(f"(run {run}) {x}", f"{type(err).__name__}: {err}", False)

    def stray(self, text: str, why: str, fault: bool = True) -> None:
        self.log.write(f"dropped ({why}): {text[:500]}\n")
        self.log.flush()
        if fault and self.d.warm:                    # it said something no run of its own: not to be trusted
            with self.lock:
                self.recycle = self.recycle or (f"printed a line for no run it holds ({why})", True)

    def line(self, text: str) -> None:
        if not text:
            return
        try:
            obj = json.loads(text)
        except ValueError:
            obj = None
        if not isinstance(obj, dict):
            return self.stray(text, "not a JSON object")
        if obj == {"heartbeat": True}:
            return None
        if "run" in obj:
            run = obj["run"]
            with self.lock:
                h = self.runs.get(run) if isinstance(run, str) else None
            if h is None:
                return self.stray(text, "no run of that id held")
            if "done" in obj:                        # strict: exactly {"done": EXIT, "run": ID}, EXIT a whole number
                if set(obj) != {"done", "run"} or type(obj["done"]) is not int:
                    return self.stray(text, 'done is exactly {"done": EXIT, "run": ID}, EXIT a whole number')
                res, why = self.charge(h) if self.d.warm else (None, None)
                with self.lock:                      # (the run is charged by whichever takes it: this, or fail_all)
                    if self.runs.pop(run, None) is not h:
                        return None
                    h.resources, self.recycle = res, self.recycle or why
                    self.served += 1
                    if not self.runs:
                        self.idle_since = time.monotonic()
                return h.end(obj["done"])
            h.take([json.dumps({k: v for k, v in obj.items() if k != "run"})])
            return None
        if "request" in obj:
            with self.lock:
                h = self.requests.pop(obj["request"], None) if isinstance(obj["request"], str) else None
            if h is None:
                return self.stray(text, "no reading of that id asked for")
            v = obj.get("reading")
            if isinstance(v, bool) or not isinstance(v, int | float):
                return h.answer(None, str(obj.get("error") or "its daemon answered with no number (reading:)")[:200])
            return h.answer(float(v), "")
        if "sensor" in obj and ("event" in obj or "message" in obj):
            if "reading" in obj:
                return self.stray(text, "a reading or an observation, not both")
            if self.on_observe(obj["sensor"], obj, self.read_at):
                return None
            return self.stray(text, "an observation for no sensor of its own, not one in shape "
                                    "(an event, or a message object), or after ergostat stopped")
        if "sensor" in obj and "reading" in obj and self.on_push(obj["sensor"], obj["reading"]):
            return None
        return self.stray(text, "tagged with no run, request or push sensor of its own")

    # ---- runs and readings

    def charge(self, h: Handle) -> tuple[dict, tuple[str, bool] | None]:
        """(warm) The CPU its group used while it held the run, at its ``done`` or when it failed (crashed: its
        leader's from its ``wait4``); unknown, never zero, when that cannot be read. And why it is replaced before it
        is handed another: what it left running, a cancelled run (it holds one run at a time, so nothing else's CPU
        is in it)."""
        ru = self.proc.rusage
        cpu, left, dead = usage.charge(self.before, self.pid, ru.ru_utime + ru.ru_stime if ru else None)
        res = {**({"cpu": round(cpu, 3)} if cpu is not None else {"unmeasured": "its group's CPU could not be read when "
               + ("it was handed the run" if self.pid not in self.before else "the run ended")}),
               "method": "warm", **({"left_running": len(left)} if left else {}),
               **({"unreaped": len(dead)} if dead else {})}
        why = (f"left {len(left)} process(es) of its group running after its run", True) if left else \
            ("its run was cancelled", False) if h.cancelled is not None else \
            (f"served {self.served + 1} runs (recycle: {self.d.recycle})", False) if self.served + 1 >= self.d.recycle \
            else None
        return res, why

    def hold(self, run: str, h: Handle, line: dict | None) -> bool:
        """The run held; its line sent now, or (None: a warm process's) by ``hand``, outside the supervisor's lock."""
        with self.lock:
            self.runs[run] = h
            self.idle_since = None
            h.sent = line is not None
            return self.send(line) if line is not None else True

    def hand(self, run: str, line: dict) -> bool:
        """(warm) Its group's CPU noted, then the run's line sent: what it uses from here is the run's. Refused once
        it was asked to stop (drained, replaced, ergostat stopping) after the run was held: the run given back,
        uncounted, never left held by a process that will not be sent it. Refused too once it was cancelled (the
        owner's stop, its lease killed) before it was sent: ended so, never sent, the process not blamed."""
        before = usage.snapshot(self.pid)
        with self.lock:
            h = self.runs.get(run)
            if h is not None and not self.stopping and h.cancelled is None:
                self.before, h.sent = before, True
                return self.send(line)
            self.runs.pop(run, None)
            if not self.runs:
                self.idle_since = time.monotonic()
        if h is not None and h.cancelled is not None:
            h.end(None, "stopped as the owner asked" if h.asked else "cancelled before it was handed over")
        elif h is not None:
            h.end(None, f"its daemon {self.d.name} was stopping before the run was handed over", requeue=True)
        return False

    def ask(self, request: str, h: Handle, line: dict) -> bool:
        with self.lock:
            self.requests[request] = h
        return self.send(line)

    def fail_all(self, note: str, requeue: bool) -> None:
        with self.lock:
            runs, reqs = list(self.runs.values()), list(self.requests.values())
            self.runs.clear()
            self.requests.clear()
        for h in runs:                               # (warm: a run sent, crashed or hung, charged what it used)
            if self.d.warm and h.sent:
                h.resources = self.charge(h)[0]
            h.end(None, note, requeue and h.cancelled is None)
        for h in reqs:
            h.answer(None, note)

