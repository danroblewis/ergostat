"""The client end of the engine's socket (``server.py``): one JSON line asked, one JSON line answered. The standard
library only, so a step's own Python can use it as it is:

    from ergostat.calls.client import call
    call("event", events=[{"event": "ticket.noted", "item": "ticket/12", "data": {...}}])

``Unavailable`` when no engine listens (the caller does what it did before), a run's after ``bound()`` s of retries."""

from __future__ import annotations

import json
import os
import re
import socket
import time
import uuid
from pathlib import Path

from . import POINTER, SOCKET


class Unavailable(OSError):
    """No engine answers here."""


class Elsewhere(Unavailable):
    """The engine there runs another project (never asked again)."""


RETRY = 120.0                    # seconds a run's call tries again while no engine answers (ERGOSTAT_CALL_RETRY)
MOST_RETRY = 3600.0
GONE = 10.0                      # seconds a call waits for a socket removed (a final stop; a restart leaves it) to come back


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


def bound() -> float:
    """A run's call tries again for ``ERGOSTAT_CALL_RETRY`` s (default 2 min, at most 1 h); 0 with no ERGOSTAT_SOCKET."""
    try:
        got = float(os.environ.get("ERGOSTAT_CALL_RETRY") or RETRY) if os.environ.get("ERGOSTAT_SOCKET") else 0.0
    except ValueError:
        return RETRY
    return min(max(got, 0.0), MOST_RETRY) if got == got else RETRY


def call(op: str, path: str | None = None, timeout: float = 60.0, retry: float | None = None, **args) -> dict:
    """Ask the engine, retried for ``retry`` s (``bound()``) with one key; Unavailable, or Refused when it says no."""
    path = path or find()
    if not path:
        raise Unavailable("no engine socket")
    args.setdefault("call", uuid.uuid4().hex)
    end = time.monotonic() + (bound() if retry is None else min(max(retry, 0.0), MOST_RETRY))
    pause, gone = 0.05, None
    while True:
        try:
            return once(op, path, timeout, args)
        except Unavailable as e:
            now = time.monotonic()
            gone = None if os.path.exists(path) else gone or now      # (a killed or restarting engine leaves it)
            if isinstance(e, Elsewhere) or now >= end or gone is not None and now - gone >= GONE or not owner(path).is_dir():
                raise
            time.sleep(min(pause, end - now))
            pause = min(pause * 2, 2.0)


def owner(path: str) -> Path:
    """The folder whose engine answers at ``path`` (the run's state dir, else the socket's); gone: none comes back.
    The run's state dir when the socket is the whole engine's, or a shard's (SPEC §9.8): in it, or its short one."""
    from .server import path_for, short
    here = os.environ.get("ERGOSTAT_STATE_DIR")
    if here and (str(path_for(Path(here))) == path or Path(path).parent in (Path(here), short())):
        return Path(here)
    return Path(path).parent


def once(op: str, path: str, timeout: float, args: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    buf = b""
    try:
        try:
            s.connect(path)
        except OSError as e:
            raise Unavailable(str(e)) from None
        try:
            s.sendall(json.dumps({"op": op, **args}, default=str).encode() + b"\n")
            while not buf.endswith(b"\n"):
                got = s.recv(65536)
                if not got:
                    break
                buf += got
        except ConnectionError:                          # it stopped before it answered: asked again
            buf = b""
    finally:
        s.close()
    if not buf.endswith(b"\n"):
        raise Unavailable("the engine closed the connection")
    out = json.loads(buf)
    if "elsewhere" in out:
        raise Elsewhere(f"the engine there runs {out['elsewhere']}")
    if "error" in out:
        raise Refused(out["error"], int(out.get("code") or 2))
    return out
