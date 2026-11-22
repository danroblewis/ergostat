"""A fetched library's copy (SPEC §2a): ``extract`` writes ``git archive``'s tar stream into a new folder, allowing only
folders, regular files (their exec bit kept) and links that stay inside it (by their text, names compared as a
case-insensitive file system sees them, and then by where they resolve on disk); ``read`` lists a copy and hashes it. Fetch
and load share one walker (``files.tree``, which ``read`` wraps) and one hash (``digest``), under the same caps."""

from __future__ import annotations

import hashlib
import os
import stat
import tarfile
import unicodedata

from ..spec import files

MAX_ENTRIES = 2000
MAX_BYTES = 20 << 20
FILE_KINDS = ("file", "exec")


class Refused(Exception):
    """The archive holds what a copy may not: the member and why."""


def digest(listing: dict) -> str:
    """``sha256:`` of the entries in sorted path order, each its kind, then its path and its bytes (or link target),
    each length-prefixed: no two listings encode the same."""
    h = hashlib.sha256()
    for rel in sorted(listing):
        kind, v = listing[rel]
        r, b = rel.encode("utf-8", "surrogateescape"), v if isinstance(v, bytes) else os.fsencode(v)
        h.update(kind.encode() + b"\0" + len(r).to_bytes(8, "big") + r + len(b).to_bytes(8, "big") + b)
    return "sha256:" + h.hexdigest()


def read(root) -> tuple[dict, str]:
    """The copy's listing (``files.tree``, noted at load) and its hash; raises ``files.TreeRefused`` past a cap."""
    got = files.tree(root, MAX_ENTRIES, MAX_BYTES)
    return got, digest(got)


def declared(m: tarfile.TarInfo) -> int:
    """The size a member's header says it has (checked before it is read)."""
    return m.size


def _name(m: tarfile.TarInfo, strip: str) -> str | None:
    """The member's path in the copy (None: the stripped folder itself), or refused."""
    n = m.name.rstrip("/") if m.isdir() else m.name
    if strip:
        if n == strip:
            return None
        if not n.startswith(strip + "/"):
            raise Refused(f"{m.name}: outside {strip}")
        n = n[len(strip) + 1:]
    parts = n.split("/")
    if n.startswith("/") or any(p in ("", ".", "..") for p in parts) or "\0" in n:
        raise Refused(f"{m.name}: not a plain relative path")
    return n


def _folders(dest: str, rel: str) -> None:
    """The folders above ``rel``, made in ``dest`` as needed; one that is not a plain folder is refused."""
    at = dest
    for p in rel.split("/")[:-1]:
        at = os.path.join(at, p)
        try:
            if not stat.S_ISDIR(os.lstat(at).st_mode):
                raise Refused(f"{rel}: under {p}, which is not a folder")
        except FileNotFoundError:
            os.mkdir(at, 0o755)


def _key(rel: str) -> str:
    """A name as a case- and normalization-insensitive file system (APFS) sees it: ``x/S`` and ``x/s`` are one."""
    return unicodedata.normalize("NFC", rel).casefold()


def _inside(rel: str, to: str, linked: set) -> None:
    """``rel``'s target walked a step at a time from ``rel``'s folder: refused if a step goes above the copy or passes
    through another link member (``linked`` holds their ``_key``s; that link's own target would move the walk)."""
    at, steps = rel.split("/")[:-1], [p for p in to.split("/") if p not in ("", ".")]
    for i, p in enumerate(steps):
        if p != "..":
            at.append(p)
            if i < len(steps) - 1 and _key("/".join(at)) in linked:
                raise Refused(f"{rel}: a link through another link ({to})")
        elif not at:
            raise Refused(f"{rel}: a link out of the copy ({to})")
        else:
            at.pop()


def extract(stream, dest: str, strip: str = "") -> None:
    """``stream`` (a tar, read once, mode ``r|``) into the new folder ``dest``, ``strip/`` taken off each name."""
    os.mkdir(dest, 0o755)
    links: list[tuple[str, str]] = []
    names: list[str] = []
    count = said = wrote = 0
    with tarfile.open(fileobj=stream, mode="r|") as tf:
        for m in tf:
            count += 1
            if count > MAX_ENTRIES:
                raise Refused(f"more than {MAX_ENTRIES} entries in the archive (the cap)")
            rel = _name(m, strip)
            if rel is None:
                continue
            names.append(rel)
            path = os.path.join(dest, rel)
            if m.isdir():
                _folders(dest, rel)
                os.mkdir(path, 0o755)
            elif m.isreg():
                said += declared(m)
                if said > MAX_BYTES:
                    raise Refused(f"{m.name}: more than {MAX_BYTES} bytes (the cap), by the headers")
                _folders(dest, rel)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755 if m.mode & 0o111 else 0o644)
                src = tf.extractfile(m)
                with os.fdopen(fd, "wb") as out:
                    while chunk := src.read(1 << 16):
                        wrote += len(chunk)
                        if wrote > MAX_BYTES:
                            raise Refused(f"{m.name}: more than {MAX_BYTES} bytes (the cap), as written")
                        out.write(chunk)
            elif m.issym():
                if m.linkname.startswith("/"):
                    raise Refused(f"{m.name}: a link out of the copy ({m.linkname})")
                links.append((rel, m.linkname))
            else:
                raise Refused(f"{m.name}: not a folder, a regular file or a link")
    linked, keys = {_key(rel) for rel, _ in links}, [_key(n) for n in names]
    for rel, to in links:
        if any(n.startswith(_key(rel) + "/") for n in keys):
            raise Refused(f"{rel}: a link with members under it")
        _inside(rel, to, linked)
    for rel, to in links:                                  # last: nothing is written through one
        _folders(dest, rel)
        os.symlink(to, os.path.join(dest, rel))
    top = os.path.realpath(dest)                           # then where each leads on this disk, every link resolved
    for rel, to in links:
        if os.path.commonpath([top, os.path.realpath(os.path.join(dest, rel))]) != top:
            raise Refused(f"{rel}: a link out of the copy on disk ({to})")
