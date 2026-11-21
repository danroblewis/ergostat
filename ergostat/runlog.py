"""Each run's own log (SPEC §4b, §12r): ``logs/runs/<block>/<seq>-<id12>.log``, the run's standard error and the
lines it printed that were not events, and nothing of any other run. When the run ends its entry goes into the block's
log (``logs/<block>.log``) whole, in one locked append, and the oldest run files past ``storage: logs: runs:`` are
pruned, ordered by their start ``seq``.

Every path is opened by descriptor, relative to its parent (``dir_fd``) and without following links, so a link put in
``logs/runs`` never has anything written through it. Locks (``flock``): a run holds a shared lock on its own file for
its whole life (a child that leaves a process behind keeps it, through the standard error it inherited, and its file is
then kept); ``logs/runs/<block>/.lock`` is held over a file's create-and-lock and over the prune's list-and-unlink;
``logs/<block>.log.lock`` over the block log's trim-and-append."""

from __future__ import annotations

import fcntl
import os
import re
import time
from pathlib import Path

from .storage import LOGS, trim
from .storage import RUNS_MOST as MOST

NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
OURS = re.compile(r"^(\d+)-[0-9a-f]{12}(-[2-9])?\.log$|^run-(\d+)-[0-9a-f]+\.log$")    # only these are ever pruned
DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class RunLogError(Exception):
    """The run's log could not be made safely: the run does not start."""


def keep(n=None) -> int:
    """How many run files a block keeps (``storage: logs: runs:``), held to 1 to 1000 again when used."""
    try:
        return min(max(int(n if n is not None else LOGS["runs"]), 1), MOST)
    except (TypeError, ValueError):
        return int(LOGS["runs"])


def _lock(fd: int, how: int) -> None:
    fcntl.flock(fd, how)


def _created(name: str) -> None:
    """(Between a run file's create and its shared lock: a seam for the tests.)"""


def _append(fd: int, data: bytes) -> None:
    while data:
        data = data[os.write(fd, data):]


def _sub(parent: int, name: str) -> int:
    """A directory under ``parent``, made when missing, opened without following a link."""
    try:
        return os.open(name, DIR, dir_fd=parent)
    except FileNotFoundError:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        return os.open(name, DIR, dir_fd=parent)


def _dirs(p, block: str) -> tuple[int, int]:
    """``logs/`` (the owner's) and ``logs/runs/<block>``, as descriptors; RunLogError when unsafe."""
    if not NAME.match(block) or ".." in block:
        raise RunLogError(f"{block!r} is not a name a log can be kept under")
    logs = Path(p.dir) / "logs"
    lfd = bfd = rfd = -1
    try:
        logs.mkdir(exist_ok=True)
        lfd = os.open(logs, os.O_RDONLY | os.O_DIRECTORY)
        rfd = _sub(lfd, "runs")
        bfd = _sub(rfd, block)
        return lfd, bfd
    except OSError as e:
        for fd in (lfd, bfd):
            if fd >= 0:
                os.close(fd)
        raise RunLogError(f"logs/runs/{block}: {e.strerror or e}") from e
    finally:
        if rfd >= 0:
            os.close(rfd)


class Run:
    """A run's open file, under its shared lock until ``close``. ``file`` is what its child's standard error and
    ``take`` write to; ``rel`` its path from the state directory."""

    def __init__(self, p, block: str, run_id: str, lfd: int, bfd: int, fd: int, name: str):
        self.block, self.id, self.lfd, self.bfd, self.fd, self.name = block, run_id, lfd, bfd, fd, name
        self.log = Path(p.dir) / "logs" / f"{block}.log"
        self.rel = f"logs/runs/{block}/{name}"
        self.file = os.fdopen(os.dup(fd), "a", encoding="utf-8", errors="replace")

    def tail(self, chars: int) -> str:
        """Its last ``chars`` characters, read from its own descriptor."""
        self.file.flush()
        size = os.fstat(self.fd).st_size
        got = os.pread(self.fd, chars * 4, max(0, size - chars * 4))
        return got.decode("utf-8", "replace")[-chars:]

    def close(self) -> None:
        for f in (self.file.close, lambda: os.close(self.fd), lambda: os.close(self.bfd), lambda: os.close(self.lfd)):
            try:
                f()
            except OSError:
                pass


def open_run(p, block: str, seq, run_id: str) -> Run:
    """The run's own file, created under the block directory's lock and locked shared before that lock is let go."""
    if not isinstance(seq, int):
        raise RunLogError("no start seq")
    if not re.fullmatch(r"[0-9a-f]{12,64}", str(run_id)):
        raise RunLogError("its run id is not hex")
    lfd, bfd = _dirs(p, block)
    names = [f"{seq}-{run_id[:12]}.log", *(f"{seq}-{run_id[:12]}-{i}.log" for i in range(2, 10)),
             f"run-{seq}-{run_id}.log"]
    dl = -1
    try:
        dl = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=bfd)
        _lock(dl, fcntl.LOCK_EX)
        for name in names:
            try:                       # (read too, so its tail is read from this descriptor: O_RDWR, not O_WRONLY)
                fd = os.open(name, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=bfd)
            except FileExistsError:
                continue
            try:
                _created(name)
                _lock(fd, fcntl.LOCK_SH)
            except BaseException:
                os.close(fd)
                raise
            return Run(p, block, run_id, lfd, bfd, fd, name)
        raise RunLogError(f"logs/runs/{block}: every name for it is taken")
    except BaseException as e:
        os.close(bfd)
        os.close(lfd)
        if isinstance(e, OSError):
            raise RunLogError(f"logs/runs/{block}: {e.strerror or e}") from e
        raise
    finally:
        if dl >= 0:
            os.close(dl)               # (its lock let go)


def finish(run: Run, began: float, why: str, cap: float) -> None:
    """The run's entry appended to its block's log in one write, header and body, with the trim, under the block log's
    lockfile: the run file's last ``cap`` bytes, with where the rest is when it is longer."""
    run.file.flush()
    size = os.fstat(run.fd).st_size
    body = os.pread(run.fd, int(cap), max(0, size - int(cap)))
    if size > len(body):
        body = f"({size - len(body)} bytes earlier: {run.rel})\n".encode() + body
    if body and not body.endswith(b"\n"):
        body += b"\n"
    head = f"--- {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(began))} run {run.id[:8]} ({why})\n"
    lk = os.open(f"{run.block}.log.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=run.lfd)
    try:
        _lock(lk, fcntl.LOCK_EX)
        trim(run.log, cap)
        fd = os.open(f"{run.block}.log", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644, dir_fd=run.lfd)
        try:
            _append(fd, head.encode() + body)
        finally:
            os.close(fd)
    finally:
        os.close(lk)                   # (its lock let go)


def prune(p, block: str, n=None) -> list[str]:
    """The block's run files past the newest ``n`` by start seq, oldest first, unlinked when no run holds them;
    only names ergostat gives them. Returns what was removed."""
    lfd, bfd = _dirs(p, block)
    gone: list[str] = []
    dl = -1
    try:
        dl = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=bfd)
        _lock(dl, fcntl.LOCK_EX)
        files = sorted((int(m[1] or m[3]), name) for name in os.listdir(bfd) if (m := OURS.match(name)))
        for _, name in files[:max(0, len(files) - keep(n))]:
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=bfd)
            except OSError:
                continue
            try:
                _lock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:            # a run still has it (or a child it left behind): kept
                os.close(fd)
                continue
            try:
                os.unlink(name, dir_fd=bfd)
                gone.append(name)
            finally:
                os.close(fd)
    finally:
        for fd in (dl, bfd, lfd):
            if fd >= 0:
                os.close(fd)
    return gone
