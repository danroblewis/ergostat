"""Wake-ups when the record is written (docs/proposals/latency.md): what waits for new events (the dispatcher, the
engine's loop, the approvals it follows, a call waiting for an action's answer) waits on its record's ``Board``
instead of looking again every quarter second.

- **In this process**, every write to a record (``store.Events``, ``segments.Segments``) tells its board at once: a
  condition variable, so a waiter wakes as soon as the event is written.
- **From other processes** (a command run from a shell, a step's own ``ergostat event --add``), a thread per board
  follows the record's files with the kernel's file notifications (``kqueue`` on macOS and the BSDs). Where there is
  none (Linux has no inotify in the standard library), a waiter wakes on its own timeout: the check it made before.

A board counts writes; ``wait(mark, timeout)`` returns as soon as the count passes ``mark`` (or at the timeout) with
the count now, so nothing written between two waits is missed."""

from __future__ import annotations

import os
import select
import threading
from pathlib import Path

_lock = threading.Lock()
_boards: dict[str, Board] = {}


class Board:
    def __init__(self, key: str):
        self.key = key
        self.cond = threading.Condition()
        self.n = 0
        self.watching: tuple[str, ...] = ()
        self.watcher: threading.Thread | None = None

    def written(self) -> None:
        with self.cond:
            self.n += 1
            self.cond.notify_all()

    def wait(self, mark: int, timeout: float) -> int:
        """Until a write after ``mark`` (the count a waiter last saw), or ``timeout`` seconds; the count now."""
        with self.cond:
            if self.n == mark:
                self.cond.wait(timeout)
            return self.n

    def watch(self, paths: list[Path]) -> None:
        """Follow these files and directories for other processes' writes (once; kqueue only)."""
        if self.watcher is not None or not hasattr(select, "kqueue"):
            return
        self.watching = tuple(str(p) for p in paths)
        self.watcher = threading.Thread(target=self._follow, name=f"ergostat-notify-{Path(self.key).name}", daemon=True)
        self.watcher.start()

    def _follow(self) -> None:
        flags = select.KQ_NOTE_WRITE | select.KQ_NOTE_EXTEND | select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME
        while True:
            kq, fds = select.kqueue(), []
            try:
                for p in self.watching:
                    try:
                        fds.append(os.open(p, os.O_RDONLY | getattr(os, "O_EVTONLY", 0)))
                    except OSError:
                        continue
                if not fds:
                    threading.Event().wait(1.0)
                    continue
                kq.control([select.kevent(fd, filter=select.KQ_FILTER_VNODE, flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                                          fflags=flags) for fd in fds], 0, 0)
                again = False
                while not again:
                    got = kq.control(None, 8, 5.0)       # (a timeout now and then: a file replaced is opened again)
                    if got:
                        self.written()
                    again = any(e.fflags & (select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME) for e in got) or not got
            except OSError:
                threading.Event().wait(1.0)
            finally:
                kq.close()
                for fd in fds:
                    os.close(fd)


def key_of(directory: Path | str) -> str:
    return str(Path(directory).resolve())


def written(key: str) -> None:
    """A write to the record kept under ``key`` (``key_of`` its state directory): its waiters in this process wake.
    Nothing when none waits here."""
    b = _boards.get(key)
    if b is not None:
        b.written()


def board(key: Path | str) -> Board:
    """The board of the record kept under ``key`` (its state directory), one per process."""
    k = key_of(key)
    with _lock:
        b = _boards.get(k)
        if b is None:
            b = _boards[k] = Board(k)
        return b


def of(events) -> Board | None:
    """The board of a record (an ``Events`` backend), following its files for other processes' writes; None for a
    record that has none (a stand-in in a test): its waiters look again on their timeout."""
    get = getattr(events, "board", None)
    return get() if callable(get) else None
