"""A daemon that outlives its engine (SPEC §9.7, *A daemon that outlives its engine*): ``outlive-engine: true``, or
``runs: outlive_engine`` and not warm. It runs under a keeper of its own (``compute/worker/keeper.py``), as kept runs do,
through ``relay.py``: what the engine sends it is appended to its **inbox**, which the relay delivers from where it last
did, and what it prints goes to its **journal**, which the engine follows from a saved offset. So an engine stopped or
killed leaves it going: it is sent nothing meanwhile and goes on with what it holds.

Its folder is ``<state>/daemons/KEY/`` (KEY: its name's hash), with ``state.json``: its process (its keeper's run id,
its pid and start time), where its journal was read to, and each run it holds with the line that handed it over,
written before that line is sent and kept until the run's end is recorded (``acked``). A starting engine takes those
runs up (each still a run: its lease kept and renewed, its end recorded once, ``adopt.end_id``), reads the journal
from the offset to its end, then sends each run not yet answered again, with the same ``run`` id: delivery is at least
once, and a daemon drops a repeat by its id. A journal line's events have ids of its place (``store.LINE``), so a
line read again adds none. A process found ended is restarted, the runs it had not answered handed to the new one."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
import threading
import time
import uuid
from pathlib import Path

from .. import store
from ..compute.worker import keeper
from ..spec import adopt, runrecord
from .proc import LINE_MAX, Handle, Process

JOURNAL = 1                     # the format of its folder's files
LEFT = "its daemon goes on without this engine"
RELAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relay.py")
SOURCE = "ergostat"


def folder(state_dir, name: str) -> Path:
    return Path(state_dir).resolve() / "daemons" / hashlib.sha256(name.encode()).hexdigest()[:32]


def files(base: Path, proc: str) -> dict[str, Path]:
    return {"in": base / f"{proc}.in", "out": base / f"{proc}.out", "pos": base / f"{proc}.pos",
            "keeper": base / "runs" / proc, "state": base / "state.json"}


def read_state(base: Path, name: str) -> dict | None:
    """Its saved state, checked whole; None when there is none, it cannot be read, or it is not one (of another
    format, or another daemon's)."""
    try:
        st = json.loads((base / "state.json").read_text())
    except (OSError, ValueError, RecursionError):
        return None
    ok = (isinstance(st, dict) and st.get("journal") == JOURNAL and st.get("name") == name
          and isinstance(st.get("proc"), str) and keeper.RUN.fullmatch(st["proc"])
          and type(st.get("pid")) is int and st["pid"] > 0 and isinstance(st.get("start"), str | None)
          and type(st.get("offset")) is int and st["offset"] >= 0 and isinstance(st.get("held"), dict)
          and all(isinstance(v, dict) and v.get("run") == k for k, v in st["held"].items()))
    return st if ok else None


class Waiting(keeper.Kept):
    """A run taken up as the engine sees it in ``live``: going until its daemon answers it (the lease watchdog renews
    its lease meanwhile, ``seen: keeper``); never signalled itself (a cancel goes to its daemon)."""

    def __init__(self, h: Handle):
        super().__init__("", None, 0)
        self.h = h

    def poll(self) -> int | None:
        return 0 if self.h.done.is_set() else None


class KeptProcess(Process):
    kept = True

    def __init__(self, d, base: Path, cwd, env: dict, log, on_push, on_observe, old: dict | None = None):
        self.base, self.old = base, old
        self.saving = threading.RLock()          # (its state written whole, of the latest offset and runs held)
        self.lines: dict[str, dict] = {}         # each run held: the line that handed it over, till its end is recorded
        self.leaving = threading.Event()
        self.offset = old["offset"] if old else 0
        super().__init__(d, cwd, env, log, on_push, on_observe)

    def _begin(self, cwd, env: dict) -> None:
        if self.old:                             # (another engine's: known by its pid and start time)
            self.procid, self.rec = self.old["proc"], {"pid": self.old["pid"], "start": self.old["start"]}
            self.f = files(self.base, self.procid)
            self.proc = adopt.Adopted(str(self.f["keeper"]), self.rec)
        else:
            self.procid = uuid.uuid4().hex
            self.f = files(self.base, self.procid)
            self.base.mkdir(parents=True, exist_ok=True, mode=0o700)
            for k in ("in", "out"):
                os.close(os.open(self.f[k], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600))
            cmd = shlex.join([sys.executable, "-I", RELAY, str(self.f["in"]), str(self.f["pos"]), self.d.run])
            self.proc = keeper.launch(str(self.base), self.procid, "exec " + cmd, "", str(cwd), env, str(self.f["out"]),
                                      self.log.fileno())
            self.rec = {"pid": self.proc.pid, "start": runrecord.start_time(self.proc.pid)}
            self._save()
        self.pid = self.proc.pid
        threading.Thread(target=self._write, name=f"daemon-{self.d.name}-in", daemon=True).start()
        if not self.old:
            self.start_reader()

    def start_reader(self) -> None:
        threading.Thread(target=self._read, name=f"daemon-{self.d.name}-out", daemon=True).start()

    # ---- its state

    def _save(self) -> None:
        with self.saving:
            st = {"journal": JOURNAL, "name": self.d.name, "proc": self.procid, **self.rec, "offset": self.offset,
                  "held": dict(self.lines)}
            keeper.put(str(self.f["state"]), json.dumps(st))

    def hold(self, run: str, h: Handle, line: dict | None) -> bool:
        """As a daemon's, its line in its state before it is sent: a run handed over is never one a next engine
        does not know of."""
        with self.saving:
            self.lines[run] = line
            self._save()
        return super().hold(run, h, line)

    def acked(self, run: str) -> bool:
        """Its run's end recorded: no longer taken up or sent again."""
        with self.saving:
            if self.lines.pop(run, None) is None:
                return False
            self._save()
        return True

    # ---- in and out

    def _write(self) -> None:
        with open(self.f["in"], "ab", buffering=0) as f:     # (appended: never waited on, nothing to see unread)
            while (line := self.q.get()) is not None:
                f.write(line.encode())

    def _read(self) -> None:
        while not self.leaving.is_set():
            if self.take():
                continue
            if self.proc.poll() is not None:
                while self.take(eof=True):
                    pass
                break
            self.leaving.wait(0.05)
        else:
            return                               # (left going: never ended here)
        self.ended.set()

    def take(self, eof: bool = False) -> bool:
        """Its journal's next whole lines from the offset (at its end, a last line without a newline too), each taken
        with ids of its place, then the offset saved. Whether anything was read."""
        try:
            with open(self.f["out"], "rb") as fh:
                fh.seek(self.offset)
                data = fh.read(LINE_MAX + 1)
        except OSError:
            return False
        if not data:
            return False
        cut = data.rfind(b"\n")
        if self.skipping or cut < 0 and len(data) > LINE_MAX:   # (a line over 1 MiB: dropped to its newline)
            if not self.skipping:
                self.stray(data[:500].decode("utf-8", "replace"), "a line over 1 MiB", False)
            first = data.find(b"\n")
            self.skipping = first < 0
            self.offset += len(data) if first < 0 else first + 1
            self._save()
            return True
        if cut < 0 and not eof:
            return False
        cut = len(data) if cut < 0 else cut + 1
        pos = self.offset
        for raw in data[:cut].splitlines(keepends=True):
            pos += len(raw)
            token = store.LINE.set([f"{self.procid}:{pos}", 0])
            try:
                self.chunk(raw.rstrip(b"\n") + b"\n")
            finally:
                store.LINE.reset(token)
        self.offset = pos
        self._save()
        return True

    def leave(self) -> None:
        """The engine stopping: it goes on. Each run it holds ended here as left (``LEFT``: no end recorded, its lease
        kept for the next engine), its writer ended with no ``stop``, its journal no longer read."""
        self.leaving.set()
        with self.lock:
            runs, reqs = list(self.runs.values()), list(self.requests.values())
            self.runs.clear()
            self.requests.clear()
        for h in runs:
            h.left = True
            h.end(None, LEFT)
        for h in reqs:
            h.answer(None, "ergostat stopping")
        try:
            self.q.put_nowait(None)
        except Exception:
            pass

    def finish(self) -> None:
        """Ended and read: its keeper let go (it removes its own folder)."""
        if self.f["keeper"].is_dir():
            keeper.put(str(self.f["keeper"] / "done"), "")


def tidy(base: Path, keep: str) -> None:
    """Its earlier processes' inbox, journal and position removed: only files named for a run id, never another's."""
    for f in base.iterdir() if base.is_dir() else ():
        stem, _, ext = f.name.partition(".")
        if ext in ("in", "out", "pos") and keeper.RUN.fullmatch(stem) and stem != keep:
            f.unlink(missing_ok=True)


def spawn(sup, slot, cwd, env: dict, log, push, observe) -> tuple[KeptProcess, str | None]:
    """The slot's process: on this engine's first start of it, the one an engine before left going, taken up; one
    found ended is restarted, what it had not answered handed to the new one. Else a new one. Returns it, and why
    it is a restart (None: not one)."""
    eng, d = sup.e, slot.d
    base = folder(eng.p.dir, d.name)
    carried, why = {}, None
    if d.name not in sup.looked:
        sup.looked.add(d.name)
        st = read_state(base, d.name)
        if st is not None:
            old = KeptProcess(d, base, cwd, env, log, push, observe, old=st)
            take_up(sup, old, st["held"])
            gone = adopt.alive(old.rec) is False or keeper.ended(str(old.f["keeper"])) is not None
            while old.take(eof=gone):            # (its journal read to its end now, before anything is sent again)
                pass
            if not gone:
                for run in list(old.runs):       # (not answered: sent again, its id the same)
                    old.send(old.lines[run])
                old.start_reader()
                eng.say(f"daemon {d.name}: taken up, still going ({len(old.runs)} run(s) held)")
                return old, None
            with old.lock:
                carried = {r: h for r, h in old.runs.items()}
                old.runs.clear()
            carried = {r: (h, old.lines[r]) for r, h in carried.items()}
            old.finish()
            why = f"ended while no engine was up (exit {old.proc.poll()})"
        keeper.stop_all(str(base), 0)            # (none left going beside the new one, its state unread or not)
    p = KeptProcess(d, base, cwd, env, log, push, observe)
    tidy(base, p.procid)
    for run, (h, line) in carried.items():
        p.hold(run, h, line)
    return p, why


def take_up(sup, p: KeptProcess, held: dict) -> None:
    """Each run it held, by the line that handed it over, taken up: held again (its answer still to come, in its
    journal or later), its lease kept, its end recorded as the run's (``_through``)."""
    from ..costs import ai as costs_ai
    from ..library import bounds
    from ..spec.engine import Said
    eng = sup.e
    for run, line in held.items():
        begun = eng.p.events.get(run)
        b = eng.spec.blocks.get((begun or {}).get("item") or "")
        if not begun or begun.get("type") != "agent.started" or eng.p.events.get(adopt.end_id(run)):
            continue                             # (ended already, or no start of it in the record: never a run)
        if b is None or b.params.get("daemon") != p.d.name:
            eng.say(f"daemon {p.d.name}: its run {run[:8]}: its block is no longer this daemon's: not taken up")
            continue
        data = begun.get("data") or {}
        item, fence = data.get("item"), data.get("lease")
        said = Said(eng, b, run, item=item, fence=fence)
        usage = costs_ai.Usage(b.params.get("model"))
        h = Handle(lambda got, s=said, u=usage: s.lines(costs_ai.expand(u, got)), block=b.name)
        h.sent = True
        key = f"{b.name} {item}" if item else b.name
        with eng.lock:
            if key in eng.running:
                continue
            bounds.hold(eng, key, b)
            eng.live[run] = Waiting(h)
        with p.lock:
            p.runs[run] = h
        p.lines[run] = line
        if item:
            eng.dispatch.adopt(b, item, fence, run, True)
        threading.Thread(target=_through, args=(sup, b, begun, h, said, usage, item, fence, key), daemon=True,
                         name="daemon-run-taken-up").start()


def _through(sup, b, begun: dict, h: Handle, said, usage, item, fence, key: str) -> None:
    """A run taken up, to its end: recorded as the engine that handed it over would have (``agent.ran`` or
    ``agent.failed``, once: ``adopt.end_id``), then its lease's ack or nack. Its timeout counts from now."""
    from ..costs import record as costs_record
    from ..spec.engine import STOPPED_BY_OWNER
    eng, run, left = sup.e, begun["id"], False
    try:
        t0 = time.monotonic()
        while not h.done.wait(0.5):
            if b.timeout and time.monotonic() - t0 > b.timeout and h.cancelled is None:
                sup.cancel(run, "its timeout")
        left = getattr(h, "left", False)
        if left:
            return
        with eng.lock:
            killed = eng.killing.pop(run, None)
        code = h.code
        note = f"killed: {killed}" if killed else (STOPPED_BY_OWNER if h.asked and code else h.note) or (
            f"exited {code}" if code else "")
        if code == 0 and not note:
            said.finish()
        said.tally()
        d0 = begun.get("data") or {}
        data = {"exit": code, "seconds": round(max(0.0, time.time() - begun["time"]), 3), "why": d0.get("trigger"),
                **said.counts, "daemon": b.params["daemon"], **({"item": item} if item else {}),
                **({"note": note} if note else {}), **({"moved": said.moved} if said.moved else {}),
                "model": d0.get("model"), "taken_up": True, **({"ai": ai} if (ai := usage.record()) else {})}
        failed = bool(note) and note != STOPPED_BY_OWNER
        ended = eng.p.events.add("agent.failed" if failed else "agent.ran", item=b.name, source=SOURCE, causedby=run,
                                 data=data, id=adopt.end_id(run))
        sup.acked(run)
        costs_record.write_series(eng.p, b.name, data, ended["time"])
        eng.after_end(b, eng.spec, begun, data, said, failed, None, "", "", logged=False)
        if item:
            back = {"why": h.note, "count": False} if h.requeue else None
            eng.dispatch.finish(b, item, fence, run, {"exit": code, "note": note, "nack": back or said.nack,
                                                      "stopped": note == STOPPED_BY_OWNER})
        with eng.lock:
            eng._read_moved([k for k, v in said.moved.items() if v], run)
    except Exception as e:                       # (its lease expires as any other's)
        eng.say(f"{b.name}: its run {run[:8]} taken up from its daemon: {type(e).__name__}: {e}")
    finally:
        with eng.lock:
            eng.live.pop(run, None)
            eng.running.discard(key)
            eng.finished[b.name] = time.time()
        if not left:
            eng.dispatch.taken_up_ended(b.name, item, run)
        eng.poke(b.name)
