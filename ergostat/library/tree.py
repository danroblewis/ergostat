"""A library's copy: ``extract`` reads a tar stream into a new folder, keeping it all inside; ``digest`` hashes a copy.
A link's target is walked step by step from its folder, names case- and NFC-folded, and refused if a ``..`` leaves the
copy or a step lands on any link; walked as it arrives and again once all links exist (so member order does not
matter), then each link's realpath is checked."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import tarfile
import unicodedata

from ergostat.spec import files
from ergostat.spec.files import TreeError

ENTRIES, BYTES = 2000, 20_000_000
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_NEW = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


def digest(root, max_entries: int = ENTRIES, max_bytes: int = BYTES) -> str:
    """The sha256 of the copy at ``root`` (``files.tree``): for each path in byte order, the path, its kind (``dir``,
    ``file``, ``exec``, ``link``), then its bytes or link target, each length-prefixed."""
    h, walked = hashlib.sha256(), files.tree(root, max_entries, max_bytes)
    for p in sorted(walked, key=os.fsencode):
        kind, body = walked[p]
        for b in (os.fsencode(p), kind.encode(), body if isinstance(body, bytes) else os.fsencode(body or "")):
            h.update(len(b).to_bytes(8, "big") + b)
    return h.hexdigest()


def _fold(s: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", s).casefold())


def _declared(m: tarfile.TarInfo) -> int:
    return m.size


def extract(stream, dest, max_entries: int = ENTRIES, max_bytes: int = BYTES) -> None:
    """Read the tar ``stream`` into ``dest``, made here. Refused (TreeError, ``dest`` removed): any kind but folder,
    file and link; an absolute name or a ``.``/``..``/empty step; two names folding the same; a member under a link or
    file; a link leaving the copy or passing through a link; past either cap, by bytes declared or written."""
    os.mkdir(dest, 0o700)
    try:
        links = _extract(stream, dest, max_entries, max_bytes)
        for at, target in links.items():
            _inside(at, target, links)
        top = os.path.realpath(dest)
        for at in links:
            real = os.path.realpath(os.path.join(dest, *at[1]))
            if real != top and not real.startswith(top + os.sep):
                raise TreeError("bad-library-tree", "/".join(at[1]), "its realpath leaves the copy")
    except (tarfile.TarError, OSError) as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise TreeError("bad-library-tree", str(getattr(e, "filename", "") or ""), str(e)) from e
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise


def _extract(stream, dest, cap: int, most: int) -> dict:
    seen: dict[tuple, tuple] = {}      # folded steps -> (kind, the steps as written)
    links: dict[tuple, str] = {}       # (folded steps, steps as written) -> target
    declared = written = 0
    with tarfile.open(fileobj=stream, mode="r|*") as tf:
        for m in tf:
            name = m.name.rstrip("/") if m.isdir() else m.name
            parts = tuple(name.split("/"))
            if name.startswith("/") or any(s in ("", ".", "..") for s in parts):
                raise TreeError("bad-library-tree", name, "an absolute name or a '.', '..' or empty step")
            folded = tuple(_fold(s) for s in parts)
            for i in range(1, len(parts)):
                was = seen.setdefault(folded[:i], ("dir", parts[:i]))
                if was != ("dir", parts[:i]):
                    raise TreeError("bad-library-tree", name, "under a link, a file or a folder named otherwise")
            kind = "dir" if m.isdir() else "file" if m.isreg() else "link" if m.issym() else None
            if kind is None:
                raise TreeError("bad-library-tree", name, "a hardlink, device, FIFO or other kind not allowed")
            if folded in seen and not (kind == "dir" and seen[folded] == ("dir", parts)):
                raise TreeError("bad-library-tree", name, "a second entry for one name (case- and NFC-folded)")
            seen[folded] = (kind, parts)
            if len(seen) > cap:
                raise TreeError("library-too-big", name, f"more than {cap} entries")
            fd = _parent(dest, parts[:-1])
            try:
                if kind == "dir":
                    try:
                        os.mkdir(parts[-1], 0o755, dir_fd=fd)
                    except FileExistsError:
                        os.close(os.open(parts[-1], _DIR, dir_fd=fd))
                elif kind == "link":
                    if not m.linkname or m.linkname.startswith("/"):
                        raise TreeError("bad-library-tree", name, "an empty or absolute link target")
                    links[(folded, parts)] = m.linkname
                    _inside((folded, parts), m.linkname, links)
                    os.symlink(m.linkname, parts[-1], dir_fd=fd)
                else:
                    declared += _declared(m)
                    if declared > most:
                        raise TreeError("library-too-big", name, "past the byte cap (declared)")
                    src, h = tf.extractfile(m), os.open(parts[-1], _NEW, 0o600, dir_fd=fd)
                    try:
                        while b := src.read(1 << 20):
                            written += len(b)
                            if written > most:
                                raise TreeError("library-too-big", name, "past the byte cap (written)")
                            os.write(h, b)
                        os.fchmod(h, 0o755 if m.mode & 0o111 else 0o644)
                    finally:
                        os.close(h)
            finally:
                os.close(fd)
    return links


def _parent(dest, steps: tuple) -> int:
    """A handle on ``dest``/``steps``, each folder made if missing and opened O_NOFOLLOW (a link on the way fails)."""
    fd = os.open(dest, _DIR)
    for s in steps:
        try:
            with contextlib.suppress(FileExistsError):
                os.mkdir(s, 0o755, dir_fd=fd)
            nxt = os.open(s, _DIR, dir_fd=fd)
        finally:
            os.close(fd)
        fd = nxt
    return fd


def _inside(at: tuple, target: str, links: dict) -> None:
    """Refuse the link ``at`` if walking ``target`` from its folder steps above the copy or onto any link."""
    folded = {k[0] for k in links}
    here = list(at[0][:-1])
    for s in target.split("/"):
        if s in ("", "."):
            continue
        if s == "..":
            if not here:
                raise TreeError("bad-library-tree", "/".join(at[1]), "its target leaves the copy")
            here.pop()
        else:
            here.append(_fold(s))
            if tuple(here) in folded:
                raise TreeError("bad-library-tree", "/".join(at[1]), "its target passes through a link")
