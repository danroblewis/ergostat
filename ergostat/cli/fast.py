"""The commands a step calls (``event --add``, ``act``, ``lease --renew`` / ``--nack``, ``item ID --json``) answered by
the running engine over its socket (``calls/``), without loading the model; None when no engine listens for this
project (or ``ERGOSTAT_NO_SOCKET`` is set), and the command does what it always did."""

from __future__ import annotations

import os
from pathlib import Path


def call(cli, op: str, timeout: float = 60.0, **kw) -> dict | None:
    if os.environ.get("ERGOSTAT_NO_SOCKET"):
        return None
    from ..calls.client import Unavailable, find, root_of
    from ..calls.client import call as ask
    here = Path(cli.C).resolve() if getattr(cli, "C", None) else Path.cwd()
    root = root_of(here)
    if root is None or (root / "ergostat.toml").is_file() and not (root / "ergostat.yaml").is_file():
        return None
    journal = os.environ.get("ERGOSTAT_JOURNAL") if op == "event" or kw.get("how") == "nack" else None
    try:
        path = os.environ.get("ERGOSTAT_SOCKET") or find(here)
        if not path:
            return journaled(journal, op, kw)
        return ask(op, path=path, timeout=timeout, root=str(root), **({"retry": 0.0} if journal else {}), **kw)
    except Unavailable:
        return journaled(journal, op, kw)


def journaled(path: str | None, op: str, kw: dict) -> dict | None:
    """No engine answers a kept run's call that only records (SPEC §9.1): its line, as the run would print it, appended
    to the run's journal in one write, for the engine that reads it. None (do what it always did) with no journal,
    or one that cannot be written (the run read to its end already: the engine made it, and has removed it)."""
    import json
    import time
    if not path:
        return None
    if op == "event":
        lines = [{k: v for k, v in e.items() if v is not None} for e in kw["events"]]
    else:
        lines = [{"nack": {"why": kw.get("why") or "given back", "count": kw.get("count", True),
                           **({"after": f"{kw['after']:g}s"} if kw.get("after") is not None else {})}}]
    data = "".join(json.dumps(x, default=str) + "\n" for x in lines).encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND)          # (never made here: the journal is the engine's to make)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
    except OSError:
        return None
    now = time.time()
    if op == "event":
        return {"journal": path, "events": [{"type": x["event"], "item": x.get("item"), "data": x.get("data") or {},
                                             "time": now, "source": "journal", "patch": x.get("patch"), "set": x.get("set")}
                                            for x in lines]}
    return {"journal": path, "event": {"type": "nack", "item": os.environ.get("ERGOSTAT_ITEM"), "time": now}}


def key() -> str:
    import uuid
    return uuid.uuid4().hex


def env() -> dict:
    """What a run's call says of the run (its lease, its actions file)."""
    keys = ("ERGOSTAT_ITEM", "ERGOSTAT_LEASE", "ERGOSTAT_RUN", "ERGOSTAT_ACTIONS", "ERGOSTAT_SANDBOX")
    return {k: os.environ[k] for k in keys if os.environ.get(k)}
