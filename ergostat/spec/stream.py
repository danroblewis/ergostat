"""A machine block's run, its standard output taken as it arrives (SPEC §9.1).

The run writes its output to its run log file (``runrecord.py``: no pipe the engine holds), and the thread that started
the run follows that file: it reads what is new, and looks again a moment later when nothing is (``FIRST``, growing to
``SLOW``), so a run still costs one thread (docs/proposals/latency.md: 500 runs at once were 1,500 threads). The lines
read are handed, in the order printed, to the caller's ``take`` in batches: one line when they come slowly, up to
``BATCH`` at once when they come faster than they are taken, so a run printing thousands of lines is recorded in a few
transactions, not thousands. A partial line waits for the rest of it (or for the end of the run). The run has ended
when its process has and its process group is empty, or ``GRACE`` after its process ended (what it started may still
be writing): the file is then read to its end. The timeout kills the run's process group; what it printed before
that has been taken already."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable

from .. import runner as old

BATCH = 500                 # the most lines taken in one batch
GRACE = 2.0                 # seconds its file is still read once it ended, while what it started lives on
FIRST, SLOW = 0.001, 0.05  # seconds before the file is looked at again: soon after output, then less often
CHUNK = 65536


def follow(proc: subprocess.Popen, path, timeout: float | None, take: Callable[[list[str]], None],
           leave: threading.Event | None = None, start: int | None = None) -> bool | None:
    """Take ``proc``'s output lines from the file ``path`` as they are written, until it ends. Returns whether its
    timeout stopped it; None when ``leave`` was set while it still went (the engine stopping, its run kept going by
    its keeper): what it printed by then is taken, all but a last half line, and the rest is left in its file.
    ``start``: read from that byte on, each batch handed with where each of its lines ends in the file
    (``take(lines, ends)``: a kept run's journal, SPEC §9.1)."""
    deadline = time.monotonic() + timeout if timeout else None
    killed, wait, partial, ended_at, left = False, FIRST, b"", None, False
    base = start or 0                                    # (where ``partial`` begins in the file)
    try:
        with open(path, "rb") as f:
            f.seek(base)
            while True:
                if deadline is not None and not killed and time.monotonic() >= deadline:
                    killed = True
                    old._kill(proc)
                if proc.poll() is not None and ended_at is None:
                    ended_at = time.monotonic()
                # (looked at before the read: nothing written before it is missed)
                ended = ended_at is not None and (time.monotonic() - ended_at > GRACE or not _group_lives(proc.pid))
                chunk = f.read(CHUNK)
                if chunk:
                    partial += chunk
                    if b"\n" in partial:
                        *whole, partial = partial.split(b"\n")
                        lines = [x.decode("utf-8", "replace") + "\n" for x in whole]
                        ends = []
                        for x in whole:
                            base += len(x) + 1
                            ends.append(base)
                        for i in range(0, len(lines), BATCH):
                            take(lines[i:i + BATCH], *(() if start is None else (ends[i:i + BATCH],)))
                    wait = FIRST
                    continue
                if ended:
                    if partial:
                        take([partial.decode("utf-8", "replace")], *(() if start is None else ([base + len(partial)],)))
                    break
                if leave is not None and leave.is_set() and ended_at is None:
                    left = True
                    return None
                gap = deadline - time.monotonic() if deadline is not None and not killed else SLOW
                time.sleep(max(0.0, min(wait, gap)))
                wait = min(SLOW, wait * 2)
    finally:
        if not left:
            proc.wait()
    return killed


def _group_lives(pgid: int | None) -> bool:
    if not pgid or pgid < 0:                             # (a run taken up with no pid known: never our own group)
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:                                      # (a member not ours to signal: there all the same)
        pass
    return True
