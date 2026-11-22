"""This ergostat's instance id (SPEC §4c, *A remote composed of remotes*): ``<state>/instance``, 16 lowercase hex
and a newline, made once and kept. A remote's parts are served with the chain of instance ids they came through, so
a consumer can cut a part that comes back to it.

Only a missing file is made, and never by an exclusive create followed by a write (a racer would read it empty):
the id is written whole to a temp file of its own, published with ``os.link`` (which fails if another won), and the
file read again, so every racer returns what the file holds. A file that is there but empty, malformed or
unreadable is refused (``InstanceError``), never rewritten."""

from __future__ import annotations

import contextlib
import os
import re
import secrets
from pathlib import Path

FILE = "instance"
ID = re.compile(r"^[0-9a-f]{16}$")


class InstanceError(Exception):
    """The instance file is there but cannot be taken: why."""


def is_id(x) -> bool:
    return isinstance(x, str) and bool(ID.fullmatch(x))


def _fill(path: Path, text: str) -> None:
    """The id written to its temp file, and on disk before it is published."""
    with open(path, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def _read(f: Path) -> str:
    try:
        text = f.read_text()
    except FileNotFoundError:
        raise
    except OSError as e:
        raise InstanceError(f"{f}: {e.strerror or e}") from e
    except UnicodeDecodeError as e:
        raise InstanceError(f"{f}: not text") from e
    if text == "":
        raise InstanceError(f"{f} is empty")
    got = text[:-1] if text.endswith("\n") else text
    if not ID.fullmatch(got):
        raise InstanceError(f"{f} does not hold 16 lowercase hex characters")
    return got


def own(state) -> str:
    """The id of the ergostat whose state folder is ``state``, made when the file is not there."""
    f = Path(state) / FILE
    try:
        return _read(f)
    except FileNotFoundError:
        pass
    tmp = f.with_name(f"{FILE}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        _fill(tmp, secrets.token_hex(8) + "\n")
        with contextlib.suppress(FileExistsError):       # another process published first: theirs stands
            os.link(tmp, f)
    except OSError as e:
        raise InstanceError(f"{f}: cannot be made ({e.strerror or e})") from e
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()
    try:
        return _read(f)
    except FileNotFoundError as e:
        raise InstanceError(f"{f}: not there after it was made") from e
