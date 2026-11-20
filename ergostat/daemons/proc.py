"""One daemon's process (SPEC §9.7). What is written to it goes through a bounded queue to a writer thread of its own,
so nothing that hands it work waits on it (a full queue, or a write waiting too long, is the supervisor's to see). A
reader thread gives each line it prints to what it is tagged for: a run's lines to that run, ``done`` (strict) ends
it, a reading answers its request or is pushed for its sensor; every line says it lives. A line tagged with nothing,
or with a run or request it does not hold, is written to its log and dropped: never given to another run."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time

from ..costs.sampler import Measured
from . import usage

QUEUE = 1000                 # lines waiting for its standard input, at most
SHARED = {"ERGOSTAT_CMD", "ERGOSTAT_PROJECT", "ERGOSTAT_STATE_DIR", "ERGOSTAT_SOCKET", "ERGOSTAT_HOME"}


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
    def __init__(self, d, cwd, env: dict, log, on_push):
        self.d, self.log, self.on_push = d, log, on_push
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
        log.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} starting: {d.run}\n")
        log.flush()
        env = {k: v for k, v in env.items() if not k.startswith("ERGOSTAT_") or k in SHARED}   # (an item's: in its line)
        self.proc = Measured(d.run, shell=True, cwd=cwd, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=log, start_new_session=True)
        self.pid = self.proc.pid
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
        self.send({"op": "stop"})
        try:
            self.q.put_nowait(None)
        except queue.Full:
            pass

    # ---- out

    def _read(self) -> None:
        for raw in self.proc.stdout:
            self.last_out = time.monotonic()
            try:
                self.line(raw.decode(errors="replace").strip())
            except Exception as err:                 # (a run ended meanwhile, its log closed): never the reader's end
                self.stray(raw.decode(errors="replace").strip(), f"{type(err).__name__}: {err}", False)
        self.proc.wait()
        self.ended.set()

    def stray(self, text: str, why: str, fault: bool = True) -> None:
        self.log.write(f"dropped ({why}): {text[:500]}\n")
        self.log.flush()
        if fault and self.d.warm and self.recycle is None:     # it said something no run of its own: not to be trusted
            self.recycle = (f"printed a line for no run it holds ({why})", True)

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
                if self.d.warm:
                    self.charge(h)
                with self.lock:
                    self.runs.pop(run, None)
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
        if "sensor" in obj and "reading" in obj and self.on_push(obj["sensor"], obj["reading"]):
            return None
        return self.stray(text, "tagged with no run, request or push sensor of its own")

    # ---- runs and readings

    def charge(self, h: Handle) -> None:
        """(warm) The CPU its group used while it held the run; what it left running, or a cancelled run, and it is
        replaced before it is handed another (it holds one run at a time, so nothing else's CPU is in it)."""
        cpu, left = usage.charge(self.before, self.pid)
        h.resources = {"cpu": round(cpu, 3), "method": "warm", **({"left_running": len(left)} if left else {})}
        if left:
            self.recycle = self.recycle or (f"left {len(left)} process(es) of its group running after its run", True)
        elif h.cancelled is not None:
            self.recycle = self.recycle or ("its run was cancelled", False)
        elif self.served + 1 >= self.d.recycle:
            self.recycle = self.recycle or (f"served {self.served + 1} runs (recycle: {self.d.recycle})", False)

    def hold(self, run: str, h: Handle, line: dict) -> bool:
        if self.d.warm:
            self.before = usage.snapshot(self.pid)
        with self.lock:
            self.runs[run] = h
            self.idle_since = None
        return self.send(line)

    def ask(self, request: str, h: Handle, line: dict) -> bool:
        with self.lock:
            self.requests[request] = h
        return self.send(line)

    def fail_all(self, note: str, requeue: bool) -> None:
        with self.lock:
            runs, reqs = list(self.runs.values()), list(self.requests.values())
            self.runs.clear()
            self.requests.clear()
        for h in runs:
            h.end(None, note, requeue and h.cancelled is None)
        for h in reqs:
            h.answer(None, note)

