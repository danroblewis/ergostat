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
        self.trees: dict[str, dict[str, list]] = dict(kept.get("trees") or {})    # root → rel → [kind, hash | target]
        here = {str(Path(p).parent) for p in self.files} | set(self.dirs) | {k.split("\n")[0] for k in self.globs} | \
            set(self.trees)
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


class TreeRefused(Exception):
    """A folder ``tree`` will not read whole: an entry of a kind not allowed, or over a cap (the reason)."""


def _walk(root: str, max_entries: int, max_bytes: int) -> dict[str, tuple[str, bytes | str]]:
    if not stat.S_ISDIR(os.lstat(root).st_mode):         # (missing: FileNotFoundError)
        raise TreeRefused(f"{root} is not a folder")
    out: dict[str, tuple[str, bytes | str]] = {}
    total, todo = 0, [""]
    while todo:
        d = todo.pop()
        for name in sorted(os.listdir(os.path.join(root, d))):
            rel = f"{d}/{name}" if d else name
            p = os.path.join(root, rel)
            m = os.lstat(p).st_mode
            if len(out) >= max_entries:
                raise TreeRefused(f"more than {max_entries} entries (the cap)")
            if stat.S_ISDIR(m):
                out[rel] = ("dir", b"")
                todo.append(rel)
            elif stat.S_ISLNK(m):
                out[rel] = ("link", os.readlink(p))
            elif not stat.S_ISREG(m):
                raise TreeRefused(f"{rel}: not a regular file, a folder or a link")
            else:
                fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    st, buf, want = os.fstat(fd), bytearray(), max_bytes - total + 1
                    if not stat.S_ISREG(st.st_mode):
                        raise TreeRefused(f"{rel}: not a regular file")
                    while len(buf) < want and (got := os.read(fd, min(1 << 20, want - len(buf)))):
                        buf += got
                finally:
                    os.close(fd)
                total += len(buf)
                if total > max_bytes:
                    raise TreeRefused(f"more than {max_bytes} bytes (the cap)")
                out[rel] = ("exec" if st.st_mode & stat.S_IXUSR else "file", bytes(buf))
    return out


def tree(root, max_entries: int, max_bytes: int) -> dict[str, tuple[str, bytes | str]]:
    """Every entry under ``root``, by its path relative to it: ``(kind, bytes)`` for a ``file`` or ``exec`` file,
    ``("link", target)``, ``("dir", b"")``. Walked with ``lstat``, never following a link; anything else (a FIFO, a
    socket, a device) refused unopened, as is more than ``max_entries`` entries or ``max_bytes`` bytes. Noted: the
    listing in ``Reads.trees``, each file's bytes in ``Reads.files``; a replay answers both from the snapshot."""
    root, r = str(root), _NOW.get()
    if r is None:
        return _walk(root, max_entries, max_bytes)
    if r.replay:
        if root not in r.trees:
            raise NotKept(f"{root}: not in the last good model's snapshot")
        return {rel: (k, r.ask("files", os.path.join(root, rel), None) if k in ("file", "exec") else v or b"")
                for rel, (k, v) in r.trees[root].items()}
    got = _walk(root, max_entries, max_bytes)
    r.trees[root] = {rel: [k, hashlib.sha256(v).hexdigest() if k in ("file", "exec") else v if k == "link" else ""]
                     for rel, (k, v) in got.items()}
    r.files.update({os.path.join(root, rel): v for rel, (k, v) in got.items() if k in ("file", "exec")})
    return got


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
