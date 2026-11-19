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
    try:
        path = os.environ.get("ERGOSTAT_SOCKET") or find(here)
        if not path:
            return None
        return ask(op, path=path, timeout=timeout, root=str(root), **kw)
    except Unavailable:
        return None


def env() -> dict:
    """What a run's call says of the run (its lease, its actions file)."""
    keys = ("ERGOSTAT_ITEM", "ERGOSTAT_LEASE", "ERGOSTAT_RUN", "ERGOSTAT_ACTIONS", "ERGOSTAT_SANDBOX")
    return {k: os.environ[k] for k in keys if os.environ.get(k)}
