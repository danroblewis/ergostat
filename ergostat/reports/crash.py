"""ergostat's own crashes, drafted as reports (SPEC §12m): an unhandled exception in the engine, the page server or
``check``, one report a stack signature. The same crash again counts on the report it already has (``.seen``, once
a process), so a loop that fails every pass drafts one report, not thousands. Never raises: a crash noted is a crash
that already happened, and noting it must not make another."""

from __future__ import annotations

import sqlite3
import threading

from .kind import REPORT

_SEEN: set[tuple[str, str]] = set()          # (state folder, signature): noted by this process already
_LOCK = threading.Lock()
WHERE = {"engine": "the engine", "web": "the page server", "check": "ergostat check", "runner": "the runner"}


def environmental(exc: BaseException) -> bool:
    """Not ergostat's fault: the machine or the world (a disk, a socket, a locked database, a stop)."""
    if isinstance(exc, (KeyboardInterrupt, SystemExit, MemoryError, OSError)):
        return True
    return isinstance(exc, sqlite3.OperationalError) and any(w in str(exc) for w in ("locked", "busy", "disk", "readonly"))


def noted(where, exc: BaseException, part: str = "engine") -> dict | None:
    """Draft a report for this crash, or count it on the one it has. ``where``: the project, or what holds it (the page
    server's ``live``, with ``get()``)."""
    try:
        if environmental(exc):
            return None
        p = where.get() if not hasattr(where, "events") and hasattr(where, "get") else where
        if p is None or getattr(p, "dir", None) is None:
            return None
        from . import record
        from .trace import signature
        sig = signature(exc)
        key = (str(p.dir), sig)
        with _LOCK:
            if key in _SEEN:
                return None
            _SEEN.add(key)
        rid = record.item_of(f"crash-{sig[:10]}")
        got = record.get(p, rid)
        if got is not None:
            return record.seen(p, rid)
        return record.draft(p, "", origin="crash", by="ergostat", exc=exc, signature=sig, rid=rid,
                            details=f"An unhandled exception in {WHERE.get(part, part)}.")
    except Exception:                                      # noqa: BLE001  (noting a crash never makes another)
        return None


def forget() -> None:
    """For tests: this process has noted nothing yet."""
    with _LOCK:
        _SEEN.clear()


__all__ = ["REPORT", "environmental", "forget", "noted"]
