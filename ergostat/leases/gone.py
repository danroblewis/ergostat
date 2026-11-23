"""A lease whose run is gone is released (SPEC §9.5, *A run gone*): on each watchdog pass, a lease held by a run this
engine is not following (a previous engine's, left behind by a restart or a crash) is ended, given back uncounted,
when its run's record (``runs/RUN.json``: its pid and that pid's start time, ``spec/runrecord.py``) says its process
is gone: no such pid, a zombie, or another process under that pid. On the engine's first pass a lease whose run has no
record at all is ended too: the run no longer exists (its end was read and its files removed, or it never started);
one whose input or output is there without its record may have started before the record was written, and is left.
Left alone: a run this engine follows (its own end ends it), a block's daemon's run and a block this engine does not
run (remote, or no longer in the model: no record of theirs is here), a live run, and one whose record or process
cannot be read (unknown is never gone). And only when the engine that took the lease is gone too (``owner_gone``:
the lease names it, ``engine`` on its taken event): another engine (``ergostat block NAME --now``, a trial) ends its
own runs, and its run's process is gone a moment before that end is written. The cause is outside the item (the
engine that held it stopped), so no attempt is spent."""

from __future__ import annotations

import os
import uuid
import weakref

from ..spec import runrecord

LIVE: weakref.WeakValueDictionary = weakref.WeakValueDictionary()   # this process's engines not closed, by their id


def me(d) -> dict:
    """This engine, as its leases name it: its process (pid, start time) and an id of its own (one process may hold
    several engines); registered live until ``closed``."""
    got = {"pid": os.getpid(), "start": runrecord.start_time(os.getpid()), "id": uuid.uuid4().hex}
    LIVE[got["id"]] = d
    return got


def closed(d) -> None:
    LIVE.pop(d.me["id"], None)


def owner_gone(d, lease: dict) -> bool:
    """Whether the engine that took the lease is gone: its process gone (``runrecord.state``), or, in this process,
    closed (or exec'd over: a hard restart keeps the pid). Never this engine, nor when the lease names none (taken
    before owners were named) or it cannot be told (unknown is never gone)."""
    o = lease.get("engine")
    if not isinstance(o, dict) or not isinstance(o.get("id"), str) or o["id"] == d.me["id"]:
        return False
    now = runrecord.state(o)
    if now == "alive" and o.get("pid") == os.getpid():
        return o["id"] not in LIVE
    return now == "gone"


def local(d, lease: dict):
    """The block of the lease, when it is one this engine runs here with a run record of its own: else None."""
    name = lease.get("block")
    b = next((x for x in d.blocks if x.name == name), None)
    return None if b is None or b.params.get("daemon") else b


def why(d, lease: dict, first: bool) -> str | None:
    """Why the run's lease is released now, or None to leave it held."""
    run = lease["holder"]
    if run in d.ours or run in d.ending or any(g["run"] == run for g in d.going_runs()) or not owner_gone(d, lease):
        return None
    now = runrecord.look(d.p.dir, run)
    if now == "gone":
        return f"its run {run}'s process is gone (ended, or its pid is another process's now): given back uncounted"
    if now == "none" and first:
        return f"its run {run} no longer exists (no run record as this engine started): given back uncounted"
    return None


def released(d, it, lease: dict, first: bool) -> bool:
    """End the lease when its run is gone; whether it was ended."""
    b = local(d, lease)
    said = why(d, lease, first) if b is not None else None
    return bool(said) and d.release(b, it, lease, said)
