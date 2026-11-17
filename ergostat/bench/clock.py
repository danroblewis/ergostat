"""The benchmark's clock: ergostat stamps what it records with ``time.time()``; a benchmark replays hours of record
in seconds, so while it acts at a moment of that record (a proposal made, a judgement, Accept) the clock reads that
moment, and everything recorded then is stamped with it."""

from __future__ import annotations

import contextlib
import time

_real = time.time


@contextlib.contextmanager
def at(t: float | None):
    if t is None:
        yield
        return
    was = time.time
    time.time = lambda: t
    try:
        yield
    finally:
        time.time = was


def real() -> float:
    return _real()
