"""A run whose lease expired is stopped (SPEC §9.5, *Fencing*; the owner, 2026-11-18): its item is back in the queue,
so nothing it still does is wanted. Its process group and every descendant get SIGTERM, then SIGKILL after the grace
(``ERGOSTAT_KILL_GRACE``, seconds) for whatever is left (``library/reap.py``), and ``ergostat.run.killed`` is
recorded. Only a run this engine started is signalled (one left behind by an engine that stopped is not its to
kill). The run then ends as any run does: ``agent.failed``, its note why, its resources and cost measured."""

from __future__ import annotations

import os
import threading
import time

from ..library import reap

KILLED = "ergostat.run.killed"
GRACE = float(os.environ.get("ERGOSTAT_KILL_GRACE") or 10.0)


def kill(eng, run: str, why: str, item: str | None = None, fence: int | None = None, block: str | None = None) -> bool:
    """Stop the run ``run`` (its id: the lease's holder) when this engine started it and it still goes. Returns
    whether it was asked to stop; the stopping goes on in a thread of its own."""
    with eng.lock:
        proc = eng.live.get(run)
        if proc is None or proc.poll() is not None or run in eng.killing:
            return False
        eng.killing[run] = why
    threading.Thread(target=_stop, args=(eng, proc, run, why, item, fence, block), daemon=True,
                     name="lease-kill").start()
    return True


def _stop(eng, proc, run, why, item, fence, block) -> None:
    t0 = time.monotonic()
    pids = reap.stop(proc.pid, grace=GRACE, also_group=True)
    sig = "TERM" if time.monotonic() - t0 < GRACE else "KILL"     # (TERM was enough when it ended inside the grace)
    eng.p.events.add(KILLED, item=block, source="ergostat", causedby=run,
                     data={"run": run, "why": why, "signal": sig, "pids": sorted(pids), "grace": GRACE,
                           **({"item": item, "fence": fence} if item else {})})
    eng.say(f"{block}: killed its run on {item} (SIG{sig}): {why}")
