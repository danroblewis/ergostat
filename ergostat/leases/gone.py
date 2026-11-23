"""A lease whose run is gone is released (SPEC §9.5, *A run gone*): on each watchdog pass, a lease held by a run this
engine is not following (a previous engine's, left behind by a restart or a crash) is ended, given back uncounted,
when its run's record (``runs/RUN.json``: its pid and that pid's start time, ``spec/runrecord.py``) says its process
is gone: no such pid, a zombie, or another process under that pid. On the engine's first pass a lease whose run has no
record at all is ended too: the run no longer exists (its end was read and its files removed, or it never started).
Left alone: a run this engine follows (its own end ends it), a block's daemon's run and a block this engine does not
run (remote, or no longer in the model: no record of theirs is here), a live run, and one whose record or process
cannot be read (unknown is never gone). The cause is outside the item (the engine that held it stopped), so no
attempt is spent."""

from __future__ import annotations

from ..spec import runrecord


def local(d, lease: dict):
    """The block of the lease, when it is one this engine runs here with a run record of its own: else None."""
    name = lease.get("block")
    b = next((x for x in d.blocks if x.name == name), None)
    return None if b is None or b.params.get("daemon") else b


def why(d, run: str, first: bool) -> str | None:
    """Why the run's lease is released now, or None to leave it held."""
    if run in d.ours or run in d.ending or any(g["run"] == run for g in d.going_runs()):
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
    said = why(d, lease["holder"], first) if b is not None else None
    return bool(said) and d.release(b, it, lease, said)
