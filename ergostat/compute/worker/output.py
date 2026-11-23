"""A node run's output by offset (SPEC §12s.3): one follower thread for every run reads each run's ``out`` and ``err``
files and sends what is new as ``out`` frames, each with the byte offset of its first byte, so a resend is recorded
once (ordered by offset, never by time). ``attach`` resends from given offsets; ``ack`` says what the engine has
taken, and at most ``AHEAD`` bytes go unacknowledged over all runs. A stream past its ``limits.log``
stops its run. ``ended`` follows the run's last ``out``; ``done`` writes the folder's ``done``."""

import json
import os
import sys
import threading
import traceback

import keeper

LINE = 1 << 16              # the most bytes one out frame carries
AHEAD = 4 << 20             # the most bytes sent and not acknowledged, over all runs
LOG = 64 << 20              # a stream's cap when the run's limits name none
MOST_LOG = keeper.MOST_LOG
STREAMS = ("out", "err")
FIRST, SLOW = 0.001, 0.05   # seconds before the files are looked at again: soon after output, then less often
CAP = "log over its cap"


class Stream:
    def __init__(self, at: int):
        self.pos = self.acked = at              # the next byte to send; the engine's taken offset


class Run:
    def __init__(self, d: str, cap: int, at: dict):
        self.d, self.cap, self.ended = d, cap, False
        self.s = {k: Stream(at.get(k, 0)) for k in STREAMS}
        self.final: dict = {}                   # each file's size once the exit was seen: nothing past it is sent
        self.said: set = set()                  # the streams whose fault was said (once, until they read again)


class Output:
    def __init__(self, root: str, w):
        self.runs_dir, self.w = os.path.join(root, "runs"), w
        self.runs: dict[str, Run] = {}
        self.lock = threading.Lock()            # held across each read, its sends and its offsets moved

    def offsets(self) -> dict:
        """Each followed run's offsets taken (its last ``attach`` or ``ack``), for the worker's ``beat``."""
        with self.lock:
            return {run: {k: s.acked for k, s in r.s.items()} for run, r in self.runs.items()}

    def _ahead(self) -> int:
        return sum(s.pos - s.acked for r in self.runs.values() for s in r.s.values())

    def _add(self, run, at: dict) -> str | None:
        """Follows ``run`` from ``at`` (under the lock); else why not."""
        d = os.path.join(self.runs_dir, run) if isinstance(run, str) and keeper.RUN.fullmatch(run) else None
        try:
            with open(os.path.join(d, "run.json"), encoding="utf-8") as f:
                cap = (json.load(f).get("limits") or {}).get("log", LOG)
        except (TypeError, OSError, ValueError, AttributeError):
            return "no such run"                # (no folder or no readable record: never followed on a guess)
        if not keeper._num(cap, MOST_LOG):
            return "no such run"
        for k, v in at.items():
            try:
                size = os.path.getsize(os.path.join(d, k))
            except FileNotFoundError:
                size = 0
            if v > size:
                return "offset past the output"
        self.runs[run] = Run(d, int(cap), at)
        return None

    def follow(self, stop: threading.Event) -> None:
        wait = FIRST
        try:
            while not stop.is_set():
                with self.lock:
                    moved = [self._step(run, r) for run, r in list(self.runs.items())]
                wait = FIRST if any(moved) else min(SLOW, wait * 2)
                stop.wait(wait)
        except (OSError, ValueError):
            stop.set()                          # (a send failed, the session gone: a file's fault is caught per run)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            stop.set()
            self.w.send("error", id=None, why="the output follower failed")

    def _step(self, run: str, r: Run) -> bool:
        if not os.path.isdir(r.d):
            del self.runs[run]
            return False
        ended = os.path.exists(os.path.join(r.d, "exit"))     # (looked at before the sizes: nothing written before
        moved = left = False                                 # the exit is missed)
        for name, s in r.s.items():
            path = os.path.join(r.d, name)
            try:
                try:
                    size = os.path.getsize(path)
                except FileNotFoundError:
                    size = 0
                if size > r.cap and not ended:
                    self._over(r)
                if ended:
                    r.final.setdefault(name, size)  # (what a process left behind writes after it: never sent)
                end = min(size, r.cap, r.final.get(name, size))
                if s.pos < end and AHEAD - self._ahead() >= LINE:
                    moved |= self._send(run, name, s, path, end, ended)
            except OSError as e:                # (this run's file: said once, the other runs followed still)
                left = True
                if name not in r.said:
                    r.said.add(name)
                    self.w.send("error", id=None, run=run, stream=name,
                                why=f"{name} can't be followed: {e.strerror or type(e).__name__}")
                continue
            r.said.discard(name)
            left |= s.pos < end
        if ended and not left and not r.ended and (how := self._how(r)) is not None:
            self.w.send("ended", run=run, **how)
            r.ended = moved = True
        return moved

    def _send(self, run: str, name: str, s: Stream, path: str, end: int, ended: bool) -> bool:
        """The whole lines of the next chunk; a chunk of no line end is sent whole once it fills ``LINE`` or the run
        has ended. Its text is UTF-8, bytes that are not as surrogate escapes, so the text rejoins to the bytes."""
        try:
            with open(path, "rb") as f:
                f.seek(s.pos)
                chunk = f.read(min(LINE, end - s.pos))
        except FileNotFoundError:
            return False
        cut = chunk.rfind(b"\n") + 1
        if not cut and (len(chunk) == LINE or ended):
            cut = len(chunk)
        at = 0
        while at < cut:
            nl = chunk.find(b"\n", at, cut) + 1 or cut
            self.w.send("out", run=run, stream=name, offset=s.pos,
                        text=chunk[at:nl].decode("utf-8", "surrogateescape"))
            s.pos += nl - at
            at = nl
        return cut > 0

    def _over(self, r: Run) -> None:
        stop = os.path.join(r.d, "stop")
        if not os.path.exists(stop):
            try:
                keeper.put(stop, json.dumps({"grace": 1, "why": CAP}))
            except FileNotFoundError:
                pass                            # (the folder removed meanwhile: its run has ended)

    def _how(self, r: Run) -> dict | None:
        """The exit as ``ended`` says it; unreadable, None (waited for, never read as ended)."""
        try:
            with open(os.path.join(r.d, "exit"), encoding="utf-8") as f:
                ex = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(ex, dict):
            return None
        try:
            with open(os.path.join(r.d, "stop"), encoding="utf-8") as f:
                why = json.load(f).get("why")
        except (OSError, ValueError, AttributeError):
            why = None
        how = CAP if why == CAP and ex.get("how") in ("TERM", "KILL") else ex.get("how")
        return {"code": ex.get("code"), "how": how}

    def handlers(self, start) -> dict:
        """``start`` (the keeper's, its run followed from 0 once ``started``), ``attach``, ``ack`` and ``done``."""

        def started(req: dict, w) -> None:
            said = []

            class Heard:
                def send(self, type, **fields):
                    said.append(type)
                    w.send(type, **fields)
            start(req, Heard())
            if said == ["started"]:
                with self.lock:
                    self._add(req["run"], {})

        def offsets(req: dict) -> dict:
            at = {k: req.get(k) for k in STREAMS}
            if not all(type(v) is int and v >= 0 for v in at.values()):
                raise ValueError(f"{req['type']}: out and err are byte offsets")
            return at

        def attach(req: dict, w) -> None:
            at = offsets(req)
            with self.lock:
                why = self._add(req.get("run"), at)
            if why:
                w.send("refused", id=req["id"], run=req.get("run"), why=why)

        def ack(req: dict, w) -> None:
            at = offsets(req)
            with self.lock:
                r = self.runs.get(req.get("run"))
                for k, s in r.s.items() if r is not None else ():
                    if s.acked < at[k] <= s.pos:        # (below what was taken, or past what was sent: no room)
                        s.acked = at[k]
            if r is None:
                w.send("refused", id=req["id"], run=req.get("run"), why="no such run")

        def done(req: dict, w) -> None:
            run = req.get("run")
            d = os.path.join(self.runs_dir, run) if isinstance(run, str) and keeper.RUN.fullmatch(run) else None
            if d is None or not os.path.isdir(d):
                return w.send("refused", id=req["id"], run=run, why="no such run")
            with self.lock:
                self.runs.pop(run, None)
            keeper.put(os.path.join(d, "done"), "")

        return {"start": started, "attach": attach, "ack": ack, "done": done}
