"""The kept slot (dev/README.md, *The kept slot*): while approved gaps wait and no queue run holds its slot, a suite in
[suites] slot (fac.suite, inside gate()) does not take the last of the [suites] slots. Taken: the suites ps sees and the
factory's too new for ps (a file each in run/slots/, by pid), looked at and written under run/slots.lock (lesson 1)."""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

import fac

SETTLE = 60.0                           # seconds: a suite past the gate is seen by ps by then (its container, its pytest)


def approved() -> bool:
    """Approved gaps wait. Unreadable, they do: the worst case for the queue, so the slot is kept."""
    try:
        return bool(fac.items("gap", "approved"))
    except Exception:                   # (no instance, a failed read, bad JSON: never read as none approved)
        return True


def queue_holds(cfg: dict) -> bool:
    """A queue run holds its slot: its suites under way (run/queue.json's `running`, written once its own wait is over)
    and the queue's lock held. Unreadable, or a `running` left by a run that died (the lock free): not held."""
    try:
        if not (json.loads((fac.run_dir(cfg) / "queue.json").read_text()) or {}).get("running"):
            return False
        with open(fac.path(cfg, "queue_lock"), "a") as f:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
    except BlockingIOError:
        return True
    except (OSError, ValueError, AttributeError):
        pass
    return False


def unseen(d: Path, now: float) -> int:
    """The factory's suites past the gate in the last SETTLE seconds and not ended (a dead pid's file cleared)."""
    n = 0
    for p in d.iterdir():
        try:
            os.kill(int(p.name.split("-")[0]), 0)
            n += now - p.stat().st_mtime < SETTLE
        except (OSError, ValueError):
            p.unlink(missing_ok=True)
    return n


@contextmanager
def gate(cfg: dict):
    """Held around one suite in [suites] slot: entered once it may take a slot (waited for, the lease renewed), its
    file removed on any way out. Off with [load] wait = false (the tests' machine is not the factory's)."""
    if cfg.get("load", {}).get("wait", True) is False:
        yield
        return
    d, poll = fac.run_dir(cfg, "slots"), float(cfg.get("load", {}).get("wait_poll", 20))
    mine = d / f"{os.getpid()}-{time.monotonic_ns()}"
    with open(d.parent / "slots.lock", "a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fac.renew()
                time.sleep(min(poll, 1.0))
                continue
            try:
                full = fac.suites_running() + unseen(d, time.time()) >= fac.slot_count(cfg) - 1   # (a look and a take
                if not (full and approved() and not queue_holds(cfg)):                             # under the lock)
                    mine.touch()
                    break
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
            fac.renew()
            time.sleep(poll)
    try:
        yield
    finally:
        mine.unlink(missing_ok=True)
