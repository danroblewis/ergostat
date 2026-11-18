"""A machine block's run, its standard output taken as it arrives (SPEC §9.1).

The run's input is written by a thread of its own and its output read by another, so neither a large output nor a
program that reads its input slowly can stall the other. The lines read are handed, in the order printed, to the
caller's ``take`` in batches: one line when they come slowly, up to ``BATCH`` at once when they come faster than they
are taken, so a run printing thousands of lines is recorded in a few transactions, not thousands. A partial line waits
for the rest of it (or for the end of the output). The timeout kills the run's process group; what it printed before
that has been taken already."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Callable

from .. import runner as old

BATCH = 500           # the most lines taken in one batch
GRACE = 2.0           # seconds a killed run's output is still read for (something it started may hold the pipe open)


def pump(proc: subprocess.Popen, stdin: str, timeout: float | None, take: Callable[[list[str]], None]) -> bool:
    """Feed ``proc`` its input, take its output lines as they arrive, wait for it to end. Returns whether its timeout
    stopped it."""
    killed = threading.Event()

    def kill() -> None:
        killed.set()
        old._kill(proc)

    timer = threading.Timer(timeout, kill) if timeout else None
    if timer:                                        # before its input: a full pipe cannot dodge it
        timer.daemon = True
        timer.start()

    def feed() -> None:
        try:
            if stdin:
                proc.stdin.write(stdin)
            proc.stdin.close()
        except (OSError, ValueError):               # it stopped reading, or ended, first
            pass

    lines: queue.SimpleQueue = queue.SimpleQueue()

    def read() -> None:
        try:
            for raw in proc.stdout:
                lines.put(raw)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)

    threading.Thread(target=feed, daemon=True).start()
    threading.Thread(target=read, daemon=True).start()
    ended_at = None
    try:
        while True:
            try:
                first = lines.get(timeout=0.5)
            except queue.Empty:
                if proc.poll() is not None and proc.returncode < 0:   # killed: what it left behind has a moment
                    ended_at = ended_at or time.monotonic()
                    if time.monotonic() - ended_at > GRACE:
                        break
                continue
            batch = [first]
            while len(batch) < BATCH:
                try:
                    batch.append(lines.get_nowait())
                except queue.Empty:
                    break
            done = None in batch
            got = batch[:batch.index(None)] if done else batch
            if got:
                take(got)
            if done:
                break
    finally:
        proc.wait()
        if timer:
            timer.cancel()
    return killed.is_set()

