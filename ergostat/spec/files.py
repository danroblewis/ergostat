"""Every file the model's loading reads, through one place (SPEC §9.1): read from disk and noted, so the model the
engine takes can be kept whole (``ergostat/goodmodel.py``); or, for the command line's fallback, answered only from
what was kept, never from disk, with nothing opened in the model's folders and nothing run while it loads."""

from __future__ import annotations

import contextlib
import contextvars
import glob as _glob
import hashlib
import os
import stat
import sys
from pathlib import Path

_NOW: contextvars.ContextVar[Reads | None] = contextvars.ContextVar("ergostat_files", default=None)
_RUNS = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "socket.connect",
         "urllib.Request")
_LISTS = ("open", "glob.glob", "pathlib.Path.glob", "pathlib.Path.rglob")   # (not os.listdir: imports list folders)


class NotKept(Exception):
    """The last good model asked for what its snapshot does not hold (or tried to run something): never read live."""


class Reads:
    """What one load read: each file's bytes (None: looked for, not a file), each folder looked for, each glob's hits.
    ``kept``: a snapshot, answered from these alone, each file's bytes fetched by its hash."""

    def __init__(self, kept: dict | None = None, fetch=None):
        kept = kept or {}
        self.replay, self.fetch, self.fetching = bool(fetch), fetch, False
        self.files: dict[str, bytes | str | None] = dict(kept.get("files") or {})    # (replay: the hashes)
        self.dirs: dict[str, bool] = dict(kept.get("dirs") or {})
        self.globs: dict[str, list[str]] = {k: list(v) for k, v in (kept.get("globs") or {}).items()}
        here = {str(Path(p).parent) for p in self.files} | set(self.dirs) | {k.split("\n")[0] for k in self.globs}
        self.guarded = tuple(sorted(here))

    def ask(self, table: str, key: str, live):
        t = getattr(self, table)
        if self.replay:
            if key not in t:
                raise NotKept(f"{key}: not in the last good model's snapshot")
            if table == "files" and t[key] is not None:
                self.fetching = True                    # (the store's own file: not the model's folders)
                try:
                    got = self.fetch(t[key])
                finally:
                    self.fetching = False
                if got is None or hashlib.sha256(got).hexdigest() != t[key]:
                    raise NotKept(f"{key}: its kept copy is missing or altered")
                return got
            return t[key]
        t[key] = got = live()
        return got

    def blocks(self, path: str) -> bool:
        """Whether opening or listing ``path`` while the snapshot loads would read the model's folders live."""
        p = os.path.abspath(path)
        if self.fetching or p.endswith((".py", ".pyc", ".so")) or p.startswith(_EXEMPT):
            return False
        return any(p == g or p.startswith(g.rstrip(os.sep) + os.sep) for g in self.guarded)


_EXEMPT = tuple({sys.prefix + os.sep, sys.base_prefix + os.sep, str(Path(__file__).resolve().parents[1]) + os.sep})


def _bytes(path: str) -> bytes | None:
    try:
        return Path(path).read_bytes() if os.path.isfile(path) else None
    except OSError:
        return None


def read_text(path) -> str:
    """The file's text, as ``Path.read_text``; a missing one raises FileNotFoundError, noted as missing."""
    r = _NOW.get()
    got = _bytes(str(path)) if r is None else r.ask("files", str(path), lambda: _bytes(str(path)))
    if got is None:
        raise FileNotFoundError(2, "No such file", str(path))
    return got.decode("utf-8")


def is_file(path) -> bool:
    r = _NOW.get()
    return (os.path.isfile(path) if r is None else r.ask("files", str(path), lambda: _bytes(str(path))) is not None)


def is_dir(path) -> bool:
    r = _NOW.get()
    return os.path.isdir(path) if r is None else r.ask("dirs", str(path), lambda: os.path.isdir(path))


def glob(base, pattern: str) -> list[Path]:
    """What ``pattern`` (``**`` recursive) matches under ``base``, sorted."""
    r, live = _NOW.get(), lambda: sorted(_glob.glob(pattern, root_dir=base, recursive=True))
    return [Path(base) / h for h in (live() if r is None else r.ask("globs", f"{base}\n{pattern}", live))]


def replaying() -> bool:
    r = _NOW.get()
    return r is not None and r.replay


@contextlib.contextmanager
def noting():
    """Note what is read in here (``Reads``); inside a replay, the replay's own."""
    r = _NOW.get()
    if r is not None and r.replay:
        yield r
        return
    tok = _NOW.set(r := Reads())
    try:
        yield r
    finally:
        _NOW.reset(tok)


_HOOKED: list = []


def _guard(event: str, args) -> None:
    r = _NOW.get()
    if r is None or not r.replay:
        return
    if event.startswith(_RUNS):
        raise NotKept(f"the last good model is read without running anything ({event})")
    if event in _LISTS and args and isinstance(args[0], (str, bytes, os.PathLike)) and r.blocks(os.fsdecode(args[0])):
        raise NotKept(f"{os.fsdecode(args[0])}: read live while the last good model loads")


@contextlib.contextmanager
def replay(kept: dict, fetch):
    """Answer every read in here from ``kept`` (a manifest: ``files`` path → hash or None, ``dirs``, ``globs``), each
    file's bytes from ``fetch(hash)``; anything else raises NotKept, as does any open or glob in the model's
    folders, or a process or connection started, while it runs (a Python audit hook, added once)."""
    if not _HOOKED:
        sys.addaudithook(_guard)
        _HOOKED.append(1)
    tok = _NOW.set(Reads(kept, fetch))
    try:
        yield
    finally:
        _NOW.reset(tok)


class TreeError(ValueError):
    """A library copy refused at ``path``: ``code`` bad-library-tree (a kind or shape not allowed) or library-too-big."""

    def __init__(self, code: str, path: str, why: str):
        super().__init__(f"{code}: {path!r}: {why}")
        self.code, self.path = code, path


_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
DEPTH = 64


def tree(root, max_entries: int = 2000, max_bytes: int = 20_000_000) -> dict[str, tuple[str, bytes | str | None]]:
    """Every entry under ``root`` by its ``/``-joined path: (``dir``, None), (``file`` or ``exec``, its bytes) or
    (``link``, its target). Walked with lstat through folder handles opened O_NOFOLLOW; a FIFO, socket or device is
    refused unopened; a file is opened O_NOFOLLOW|O_NONBLOCK and refused unless its handle is S_ISREG. Past
    ``max_entries``, ``max_bytes`` read or ``DEPTH`` folders is refused; never read while the last good model loads."""
    if replaying():
        raise NotKept(f"{root}: a library copy is not read while the last good model loads")
    out: dict = {}
    top = os.open(root, _DIR)
    try:
        _walk(top, "", out, max_entries, [max_bytes], 0)
    finally:
        os.close(top)
    return out


def _walk(fd: int, at: str, out: dict, cap: int, left: list, depth: int) -> None:
    if depth >= DEPTH:
        raise TreeError("library-too-big", at, f"more than {DEPTH} folders deep")
    for name in sorted(os.listdir(fd)):
        p = at + name
        if len(out) >= cap:
            raise TreeError("library-too-big", p, f"more than {cap} entries")
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISLNK(st.st_mode):
            out[p] = ("link", os.readlink(name, dir_fd=fd))
        elif stat.S_ISDIR(st.st_mode):
            out[p] = ("dir", None)
            sub = os.open(name, _DIR, dir_fd=fd)
            try:
                _walk(sub, p + "/", out, cap, left, depth + 1)
            finally:
                os.close(sub)
        elif stat.S_ISREG(st.st_mode):
            h = os.open(name, _FILE, dir_fd=fd)
            try:
                hs = os.fstat(h)
                if not stat.S_ISREG(hs.st_mode):
                    raise TreeError("bad-library-tree", p, "not a regular file once opened")
                data = bytearray()
                while len(data) <= left[0] and (b := os.read(h, min(1 << 20, left[0] + 1 - len(data)))):
                    data += b
            finally:
                os.close(h)
            if len(data) > left[0]:
                raise TreeError("library-too-big", p, "past the byte cap")
            left[0] -= len(data)
            out[p] = ("exec" if hs.st_mode & 0o111 else "file", bytes(data))
        else:
            raise TreeError("bad-library-tree", p, "a FIFO, socket or device")
