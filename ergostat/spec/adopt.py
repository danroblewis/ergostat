"""Runs left going by an engine that stopped, taken up by the next (SPEC §9.1, *Runs taken up again*).

A run its keeper holds (``runs: outlive_engine``) writes its lines to its journal, ``runs/RUN.jsonl``. The engine
taking them saves, after each batch, where it has read to and what the lines came to by then (``RUN.offset``: the
counts, what it moved, its nack, its AI usage), written whole or not at all. Each event a line makes has an id of the
line's place in the journal (``store.line_id``), and the record keeps an id once: a line taken again, after a crash
between its events and the offset saved after them, adds nothing. So each line is in the record once.

A starting engine (``scan``) takes up each run in ``runs/`` with a keeper's folder or a journal, from its saved offset.
While the run is alive (its pid, and that process's start time: a pid reused by another process is gone) its lease
is kept with its fence and renewed; once it has ended it is ended from its journal and its keeper's exit as if the
engine had been there: ``agent.ran`` (or ``agent.failed``; its id made from the run's, so written once) at the time it
really ended (its exit file's), its costs at that time, then its lease's ack or nack."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import threading
import time
from pathlib import Path

from .. import store
from ..compute.worker import keeper
from ..costs import ai as costs_ai
from ..costs import record as costs_record
from ..library import bounds
from . import runrecord, stream

WAIT = 3.0              # seconds a run gone with no exit written waits for its keeper's last write, then reads killed
SOURCE = "ergostat"


def end_id(run: str) -> str:
    """The id of a kept run's ``agent.ran``/``agent.failed``: one end, whichever engine writes it, however often."""
    return hashlib.sha256(f"ended:{run}".encode()).hexdigest()[:32]


def files(state_dir, name: str) -> dict[str, Path]:
    """A kept run's files: its record, input, exit (``runrecord``), its journal and its saved offset."""
    f = runrecord.files(state_dir, name)
    f["out"] = f["out"].with_suffix(".jsonl")
    f["offset"] = f["out"].with_suffix(".offset")
    return f


# ---- the saved offset: where its journal was read to, and what its lines came to by then

def save(path: Path, said, usage, offset: int) -> None:
    st = {"offset": offset, "counts": said.counts, "moved": said.moved, "nack": said.nack, "bare": said.bare,
          "json_lines": said.json_lines, "fence_why": said.fence_why, "refused": said.refused[:5], "usage": usage.parts}
    tmp = path.with_suffix(".offset.tmp")
    tmp.write_text(json.dumps(st, default=str))
    os.replace(tmp, path)


def _num(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def load(path: Path, size: int) -> dict:
    """The saved offset, checked whole; {} (read from the start) when there is none, or it cannot be read or is not
    one: its lines then make the ids they made before, so the record still has each once."""
    try:
        st = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    ok = (isinstance(st, dict) and type(st.get("offset")) is int and 0 <= st["offset"] <= size
          and isinstance(st.get("counts"), dict) and all(type(v) is int for v in st["counts"].values())
          and isinstance(st.get("moved"), dict) and all(_num(v) for v in st["moved"].values())
          and isinstance(st.get("usage"), list) and all(isinstance(x, dict) for x in st["usage"])
          and (st.get("nack") is None or isinstance(st["nack"], dict)) and (st.get("bare") is None or _num(st["bare"]))
          and type(st.get("json_lines")) is int and isinstance(st.get("refused"), list))
    return st if ok else {}


def restore(said, usage, st: dict) -> None:
    if not st:
        return
    said.counts.update(st["counts"])
    said.moved.update(st["moved"])
    said.nack, said.bare, said.json_lines = st["nack"], st["bare"], st["json_lines"]
    said.fence_why = st.get("fence_why") if isinstance(st.get("fence_why"), str) else None
    said.refused += [str(x) for x in st["refused"]]
    usage.parts += st["usage"]


def taker(said, usage, path: Path, also=None):
    """The ``take`` of a kept run's journal (``stream.follow`` with a start): its lines, their AI usage counted, the
    events they make given their place's ids, and the offset saved after them. ``also(lines, parts before)``: the
    engine's own (its run log, its spend cap)."""
    def take(got: list[str], ends: list[int]) -> None:
        n = len(usage.parts)
        pairs = [(x, end) for raw, end in zip(got, ends, strict=True) for x in costs_ai.expand(usage, [raw])]
        lines = [x for x, _ in pairs]
        if also is not None:
            also(lines, n)
        said.lines(lines, [e for _, e in pairs])
        save(path, said, usage, ends[-1])
    return take


def let_go(f: dict, proc) -> None:
    """Its end recorded: its files removed, and its keeper told it may go."""
    runrecord.remove(f)
    proc.release()


# ---- a run taken up

def alive(rec: dict | None) -> bool | None:
    """Whether the run's process is the one its record names: False when its pid is gone or held by another process
    (another start time); None when that cannot be read (its start never read, or not readable now: never taken
    for gone)."""
    pid = rec.get("pid") if isinstance(rec, dict) else None
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:                                     # (another user's: there all the same)
        pass
    now = runrecord.start_time(pid) if rec.get("start") else None
    return None if now is None else now == rec["start"]


class Adopted(keeper.Kept):
    """A kept run another engine started: its keeper is not ours to wait on, so it is alive by its record (``alive``),
    ended by its exit file, or, gone with none written for ``WAIT``, killed (-9: an exit unknown is never success)."""

    def __init__(self, d: str, rec: dict | None):
        pid = rec.get("pid") if isinstance(rec, dict) else None
        super().__init__(d, None, pid if type(pid) is int and pid > 0 else None)
        self.rec, self.gone = rec, None

    def poll(self) -> int | None:
        if self.returncode is None:
            got = keeper.ended(self.dir)
            if got is None and alive(self.rec) is False:
                self.gone = self.gone or time.monotonic()
                if time.monotonic() - self.gone >= WAIT:
                    got = keeper.ended(self.dir)
                    got = -signal.SIGKILL if got is None else got
            elif got is None:
                self.gone = None
            self.returncode = got
        return self.returncode

    def ended_at(self) -> float | None:
        """When it ended: its keeper's exit file's time (written as it ended), or None."""
        try:
            return os.stat(os.path.join(self.dir, "exit")).st_mtime
        except OSError:
            return None

    def release(self) -> None:
        if os.path.isdir(self.dir):
            keeper.put(os.path.join(self.dir, "done"), "")


def scan(eng) -> list[threading.Thread]:
    """Each run in ``runs/`` with a keeper's folder or a journal, taken up (one thread each, returned)."""
    root = eng.p.dir.resolve() / "runs"
    try:
        names = os.listdir(root)
    except FileNotFoundError:
        return []
    found = {n for n in names if keeper.RUN.fullmatch(n) and os.path.isdir(root / n)}
    found |= {n[:-6] for n in names if n.endswith(".jsonl") and keeper.RUN.fullmatch(n[:-6])}
    out = []
    for name in sorted(found):
        try:
            t = take_up(eng, root, name)
        except Exception as e:                           # (one run's trouble takes up no less of the others)
            eng.say(f"runs: {name[:8]}: not taken up: {type(e).__name__}: {e}")
            continue
        if t is not None:
            out.append(t)
    return out


def _json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def take_up(eng, root: Path, name: str) -> threading.Thread | None:
    f, d = files(eng.p.dir, name), root / name
    if (d / "done").exists():
        return None                                      # (read to its end and let go already)
    if d.is_dir():
        kept = _json(d / "run.json")
        if not isinstance(kept, dict) or kept.get("out") != str(f["out"]):
            return None                                  # (not one of the engine's runs, or its keeper still making it)
    rec = _json(f["json"])
    if not isinstance(rec, dict):                        # (none written: its keeper's group id, its start unknown,
        pgid = _json(d / "pgid")                         # so never taken for gone while that pid is there)
        rec = {"pid": pgid, "start": None} if type(pgid) is int else None
    run = rec["run"] if rec and isinstance(rec.get("run"), str) else name
    begun = eng.p.events.get(run)
    if not begun or begun.get("type") != "agent.started":
        eng.say(f"runs: {name[:8]}: no start of it in the record: left as it is")
        return None
    if not eng.own(f"block.{begun.get('item')}"):
        return None                                      # (another shard's to take up, SPEC §9.8)
    b = eng.spec.blocks.get(begun.get("item") or "")
    if b is None:
        eng.say(f"runs: {run[:8]}: its block {begun.get('item')} is no longer in the model: left as it is")
        return None
    data = begun.get("data") or {}
    item, fence = data.get("item"), data.get("lease")
    proc = Adopted(str(d), rec)
    live = proc.pid is not None and keeper.ended(str(d)) is None and alive(rec) is not False   # (signalled only by
    live = live and bool(rec.get("start"))                                                  # a pid it is known by)
    key = f"{b.name} {item}" if item else b.name
    with eng.lock:
        if run in eng.live or key in eng.running:
            return None                                  # (being followed here already)
        bounds.hold(eng, key, b)
        if live:                                         # (its stop, a lease's kill, reach it: SPEC §9.5)
            eng.live[run] = proc
            eng.procs[b.name] = proc
    if item:
        eng.dispatch.adopt(b, item, fence, run, live)
    eng.say(f"{b.name}: its run {run[:8]} taken up ({'still going' if live else 'ended'})")
    t = threading.Thread(target=_through, args=(eng, b, begun, proc, f, item, fence, key), daemon=True,
                         name="run-taken-up")
    t.start()
    return t


def _through(eng, b, begun: dict, proc: Adopted, f: dict, item, fence, key: str) -> None:
    from .engine import Said
    run, moved, left = begun["id"], [], False
    try:
        said = Said(eng, b, run, item=item, fence=fence)
        usage = costs_ai.Usage(b.params.get("model") or (eng.spec.agents[b.agent].model if b.agent in eng.spec.agents
                                                         else None))
        size = f["out"].stat().st_size if f["out"].exists() else 0
        st = load(f["offset"], size)
        restore(said, usage, st)
        done = eng.p.events.get(end_id(run))
        if done is None:
            if f["out"].exists():                        # (its keeper's own deadline is its timeout: SPEC §9.1)
                left = stream.follow(proc, f["out"], None, taker(said, usage, f["offset"]), eng.stop,
                                     start=st.get("offset", 0)) is None
            else:
                while proc.poll() is None and not eng.stop.wait(keeper.TICK):
                    pass
                left = proc.poll() is None
            if left:
                return
            done = settle(eng, b, begun, said, usage, proc)
        elif not eng.p.measurements.range(f"run/{b.name}/seconds", done["time"] - 0.001, done["time"] + 0.001):
            costs_record.write_series(eng.p, b.name, done["data"], done["time"])   # (ended, its costs not yet)
        moved = [k for k, v in (done["data"].get("moved") or {}).items() if v]
        if item:
            note = done["data"].get("note") or ""
            out = {"exit": done["data"].get("exit"), "note": note, "nack": said.nack,
                   "stopped": note == "stopped as the owner asked"}
            eng.dispatch.finish(b, item, fence, run, out)
        let_go(f, proc)
    except Exception as e:                               # (its lease expires as any other; its files stay for the next)
        eng.say(f"{b.name}: its run {run[:8]} taken up: {type(e).__name__}: {e}")
    finally:
        with eng.lock:
            if eng.procs.get(b.name) is proc:
                del eng.procs[b.name]
            eng.live.pop(run, None)
            eng.running.discard(key)
            eng.finished[b.name] = time.time()
            eng._read_moved(moved, run)
        if not left:
            eng.dispatch.taken_up_ended(b.name, item, run)
        eng.poke(b.name)


def settle(eng, b, begun: dict, said, usage, proc: Adopted) -> dict:
    """Its end, as the engine would have recorded it had it been there: at the time it ended."""
    from .engine import STOPPED_BY_OWNER
    run, code, how = begun["id"], proc.returncode, proc.how()
    with eng.lock:
        killed = eng.killing.pop(run, None)
        asked = b.name in eng.stopping_runs
        eng.stopping_runs.discard(b.name)
    note = (f"killed: {killed}" if killed else f"stopped after its timeout of {b.timeout:g}s" if how == "timeout"
            and b.timeout else STOPPED_BY_OWNER if code and asked else f"exited {code}" if code else "")
    if code == 0 and not note:                           # (a bare number: its events of the end's own place)
        token = store.LINE.set([f"{run}:end", 0])
        try:
            said.finish()
        finally:
            store.LINE.reset(token)
    at = proc.ended_at() or time.time()
    d0 = begun.get("data") or {}
    data = {"exit": code, "seconds": round(max(0.0, at - begun["time"]), 3), "why": d0.get("trigger"), **said.counts,
            **({"item": d0["item"]} if d0.get("item") else {}), **({"note": note} if note else {}),
            **({"moved": said.moved} if said.moved else {}), "model": d0.get("model"), "taken_up": True,
            **({"ai": ai} if (ai := usage.record()) else {})}
    failed = bool(note) and note != STOPPED_BY_OWNER
    ended = eng.p.events.add("agent.failed" if failed else "agent.ran", item=b.name, source=SOURCE, causedby=run,
                             data=data, at=at, id=end_id(run))
    costs_record.write_series(eng.p, b.name, data, at)
    if failed:
        eng.say(f"{b.name}: {note}")
    return {**ended, "data": data, "time": at}
