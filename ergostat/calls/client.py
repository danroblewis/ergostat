"""The client end of the engine's socket (``server.py``): one JSON line asked, one JSON line answered. The standard
library only, so a step's own Python can use it as it is:

    from ergostat.calls.client import call
    call("event", events=[{"event": "ticket.noted", "item": "ticket/12", "data": {...}}])

``Unavailable`` when no engine listens (the caller does what it did before). A run's call (``ERGOSTAT_SOCKET`` set)
first tries again with backoff for ``ERGOSTAT_CALL_RETRY`` seconds (default 2 minutes), so an engine restarting does
not fail it (never where the run's state folder is gone: a socket of another machine, or of a project removed; and
for ``GONE`` seconds only once its socket is removed, a clean stop, where a killed engine leaves it behind); each
call's key makes what it records happen once however often it is asked (``ops.py``)."""

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
GONE = 10.0                      # seconds a call waits for a socket removed (a clean stop) to be made again (a restart)


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
    """How long a run's call tries again while no engine answers (an engine restarting): ``ERGOSTAT_CALL_RETRY``
    seconds, default 2 minutes, at most an hour. 0 for a command not run by an engine (no ``ERGOSTAT_SOCKET``)."""
    if not os.environ.get("ERGOSTAT_SOCKET"):
        return 0.0
    try:
        got = float(os.environ.get("ERGOSTAT_CALL_RETRY") or RETRY)
    except ValueError:
        return RETRY
    return min(max(got, 0.0), MOST_RETRY) if got == got else RETRY


def call(op: str, path: str | None = None, timeout: float = 60.0, retry: float | None = None, **args) -> dict:
    """Ask the engine; its answer. Unavailable when nothing listens, after trying again with backoff for ``retry``
    seconds (``bound()`` unless given); Refused when it says no. Every try carries the same key (``call``), so the
    engine records what one call asks once, however often it is asked (``ops.py``)."""
    path = path or find()
    if not path:
        raise Unavailable("no engine socket")
    args.setdefault("call", uuid.uuid4().hex)
    end = time.monotonic() + (bound() if retry is None else min(max(retry, 0.0), MOST_RETRY))
    pause, gone = 0.05, None
    while True:
        try:
            return once(op, path, timeout, args)
        except Elsewhere:
            raise
        except Unavailable:
            now = time.monotonic()
            gone = None if os.path.exists(path) else gone or now      # (a killed engine leaves its socket behind)
            if now >= end or gone is not None and now - gone >= GONE or not owner(path).is_dir():
                raise
            time.sleep(min(pause, end - now))
            pause = min(pause * 2, 2.0)


def owner(path: str) -> Path:
    """The folder whose engine answers at ``path``: the run's state directory when the socket is its own, else the
    socket's folder. Gone: no engine comes back there (an inherited socket of another machine or container)."""
    from .server import path_for
    here = os.environ.get("ERGOSTAT_STATE_DIR")
    return Path(here) if here and str(path_for(Path(here))) == path else Path(path).parent


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
