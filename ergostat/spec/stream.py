"""A machine block's run, its standard output taken as it arrives (SPEC §9.1).

One thread does it all, the thread that started the run: it writes the run's input and reads its output as each is
ready (a selector over the two pipes), so neither a large output nor a program that reads its input slowly can stall
the other, and a run costs one thread, not three (docs/proposals/latency.md: 500 runs at once were 1,500 threads).
The lines read are handed, in the order printed, to the caller's ``take`` in batches: one line when they come slowly,
up to ``BATCH`` at once when they come faster than they are taken, so a run printing thousands of lines is recorded
in a few transactions, not thousands. A partial line waits for the rest of it (or for the end of the output). The
timeout kills the run's process group; what it printed before that has been taken already."""

from __future__ import annotations

import os
import selectors
import subprocess
import time
from collections.abc import Callable

from .. import runner as old

BATCH = 500           # the most lines taken in one batch
GRACE = 2.0           # seconds a killed run's output is still read for (something it started may hold the pipe open)
CHUNK = 65536


def pump(proc: subprocess.Popen, stdin: str, timeout: float | None, take: Callable[[list[str]], None]) -> bool:
    """Feed ``proc`` its input, take its output lines as they arrive, wait for it to end. Returns whether its timeout
    stopped it. ``proc``'s pipes may be text or bytes: they are read and written underneath, as bytes."""
    deadline = time.monotonic() + timeout if timeout else None
    killed = False
    ended_at = None
    sel = selectors.DefaultSelector()
    out = proc.stdout.fileno()
    os.set_blocking(out, False)
    sel.register(out, selectors.EVENT_READ)
    feed = (stdin or "").encode()
    if proc.stdin is not None:
        if feed:
            os.set_blocking(proc.stdin.fileno(), False)
            sel.register(proc.stdin.fileno(), selectors.EVENT_WRITE)
        else:
            _close(proc.stdin)
    partial = b""
    lines: list[str] = []
    try:
        while True:
            wait = 0.5
            if deadline is not None and not killed:
                wait = max(0.0, min(wait, deadline - time.monotonic()))
            eof = False
            for key, _ in sel.select(wait):
                if key.fd == out:
                    try:
                        chunk = os.read(out, CHUNK)
                    except BlockingIOError:
                        continue
                    except OSError:
                        chunk = b""
                    if not chunk:
                        eof = True
                        continue
                    partial += chunk
                    if b"\n" in partial:
                        *whole, partial = partial.split(b"\n")
                        lines.extend(x.decode("utf-8", "replace") + "\n" for x in whole)
                else:
                    try:
                        n = os.write(key.fd, feed[:CHUNK])
                        feed = feed[n:]
                    except BlockingIOError:
                        continue
                    except OSError:                     # it stopped reading, or ended, first
                        feed = b""
                    if not feed:
                        sel.unregister(key.fd)
                        _close(proc.stdin)
            while lines:
                take(lines[:BATCH])
                del lines[:BATCH]
            if eof:
                if partial:
                    take([partial.decode("utf-8", "replace")])
                break
            if deadline is not None and not killed and time.monotonic() >= deadline:
                killed = True
                old._kill(proc)
            if proc.poll() is not None and proc.returncode < 0:   # killed: what it left behind has a moment
                ended_at = ended_at or time.monotonic()
                if time.monotonic() - ended_at > GRACE:
                    break
    finally:
        sel.close()
        if proc.stdin is not None:
            _close(proc.stdin)
        proc.wait()
    return killed


def _close(f) -> None:
    try:
        f.close()
    except (OSError, ValueError):
        pass
