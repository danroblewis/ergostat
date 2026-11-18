"""The client end of the engine's socket (``server.py``): one JSON line asked, one JSON line answered. The standard
library only, so a step's own Python can use it as it is:

    from ergostat.calls.client import call
    call("event", events=[{"event": "ticket.noted", "item": "ticket/12", "data": {...}}])

``Unavailable`` when no engine listens (the caller does what it did before)."""

from __future__ import annotations

import json
import os
import re
import socket
from pathlib import Path

from . import POINTER, SOCKET


class Unavailable(OSError):
    """No engine answers here."""


class Refused(Exception):
    """The engine answered: refused (what the command line says, and the exit it gives)."""

    def __init__(self, why: str, code: int = 2):
        super().__init__(why)
        self.code = code


def find(start: Path | None = None) -> str | None:
    """The socket of the engine running this project: ``ERGOSTAT_SOCKET`` (a run's), else the project's state
    directory (found without loading the model: its main file's ``name:``)."""
    got = os.environ.get("ERGOSTAT_SOCKET")
    if got:
        return got
    d = state_of(start or Path.cwd())
    if d is None:
        return None
    ptr = d / POINTER
    if ptr.is_file():
        return ptr.read_text().strip() or None
    return str(d / SOCKET) if (d / SOCKET).exists() else None


NAME = re.compile(r"""^name:\s*(?:"([^"]*)"|'([^']*)'|([^\s#'"][^#]*?))\s*(?:#.*)?$""", re.M)


def root_of(start: Path) -> Path | None:
    """The folder of the project's main file at or above ``start`` (as ``model.find`` finds it)."""
    here = start.resolve()
    for d in (here, *here.parents):
        if (d / "ergostat.yaml").is_file() or (d / "ergostat.toml").is_file():
            return d
    return None


def state_of(start: Path) -> Path | None:
    """The state directory of the project at or above ``start``, as ``store.Project`` names it, read cheaply; None when
    it cannot be told without the model (no ergostat.yaml, or a name it cannot read)."""
    import hashlib
    home = Path(os.environ.get("ERGOSTAT_HOME") or Path.home() / ".ergostat")      # (as store.home)
    here = start.resolve()
    for d in (here, *here.parents):
        main = d / "ergostat.yaml"
        if main.is_file():
            try:
                m = NAME.search(main.read_text(encoding="utf-8"))
            except OSError:
                return None
            name = next((g for g in m.groups() if g is not None), None) if m else d.name
            if not name:
                return None
            key = f"{name}-{hashlib.sha256(str(d.resolve()).encode()).hexdigest()[:8]}"
            sd = home / key
            return sd if sd.is_dir() else None
        if (d / "ergostat.toml").is_file():
            return None
    return None


def call(op: str, path: str | None = None, timeout: float = 60.0, **args) -> dict:
    """Ask the engine; its answer. Unavailable when nothing listens; Refused when it says no."""
    path = path or find()
    if not path:
        raise Unavailable("no engine socket")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        try:
            s.connect(path)
        except OSError as e:
            raise Unavailable(str(e)) from None
        s.sendall(json.dumps({"op": op, **args}, default=str).encode() + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            got = s.recv(65536)
            if not got:
                break
            buf += got
    finally:
        s.close()
    if not buf:
        raise Unavailable("the engine closed the connection")
    out = json.loads(buf)
    if "elsewhere" in out:
        raise Unavailable(f"the engine there runs {out['elsewhere']}")
    if "error" in out:
        raise Refused(out["error"], int(out.get("code") or 2))
    return out
