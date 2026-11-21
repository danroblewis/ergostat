"""A run whose lease expired is stopped (SPEC §9.5, *Fencing*; the owner, 2026-11-18): its item is back in the queue,
so nothing it still does is wanted. Its process group and every descendant get SIGTERM, then SIGKILL after the grace
(``ERGOSTAT_KILL_GRACE``, seconds) for whatever is left (``library/reap.py``): those its ``Watch`` saw too (one
detached, its parent gone), each only while it is still the process seen (a pid used again is left alone), and
``ergostat.run.killed`` is
recorded. Only a run this engine started is signalled (one left behind by an engine that stopped is not its to
kill). The run then ends as any run does: ``agent.failed``, its note why, its resources and cost measured."""

from __future__ import annotations

import os
import threading
import time

from ..library import reap

KILLED = "ergostat.run.killed"
GRACE = None                     # seconds; None: ERGOSTAT_KILL_GRACE, read at each kill, else 10


def grace() -> float:
    if GRACE is not None:
        return GRACE
    try:
        g = float(os.environ.get("ERGOSTAT_KILL_GRACE") or 10.0)
    except ValueError:
        return 10.0
    return g if 0 <= g < 3600 else 10.0


def kill(eng, run: str, why: str, item: str | None = None, fence: int | None = None, block: str | None = None) -> bool:
    """Stop the run ``run`` (its id: the lease's holder) when this engine started it and it still goes. Returns
    whether it was asked to stop; the stopping goes on in a thread of its own. A run a daemon holds is sent
    ``cancel`` instead, and its daemon restarted if it holds it past the grace (daemons/supervise.py)."""
    if getattr(eng, "daemons", None) is not None and eng.daemons.cancel(run, why, killing=True):
        eng.p.events.add(KILLED, item=block, source="ergostat", causedby=run,
                         data={"run": run, "why": why, "signal": "cancel", "grace": grace(),
                               **({"item": item, "fence": fence} if item else {})})
        return True
    with eng.lock:
        proc = eng.live.get(run)
        if proc is None or proc.poll() is not None or run in eng.killing:
            return False
        eng.killing[run] = why
    threading.Thread(target=_stop, args=(eng, proc, run, why, item, fence, block), daemon=True,
                     name="lease-kill").start()
    return True


def _stop(eng, proc, run, why, item, fence, block) -> None:
    with eng.lock:                                  # (ended meanwhile: nothing to signal)
        if eng.live.get(run) is not proc or proc.poll() is not None:
            return
    g, t0 = grace(), time.monotonic()
    watch = getattr(proc, "watch", None)            # every process the run was seen to start, its own pid among them
    if watch is not None:
        watch.look()

    def also() -> set[int]:                         # those still the process seen (no pid used again), and the run's own
        mine = {proc.pid} if proc.poll() is None else set()   # while unwaited (never another's): even if ``ps`` fails
        return (watch.still() if watch is not None else set()) | mine
    pids = reap.stop(proc.pid, grace=g, also_group=True, also=also)   # (the run itself waited on too)
    sig = "TERM" if time.monotonic() - t0 < g else "KILL"     # (TERM was enough when it ended inside the grace)
    eng.p.events.add(KILLED, item=block, source="ergostat", causedby=run,
                     data={"run": run, "why": why, "signal": sig, "pids": sorted(pids), "grace": g,
                           **({"item": item, "fence": fence} if item else {})})
    eng.say(f"{block}: killed its run on {item} (SIG{sig}): {why}")
