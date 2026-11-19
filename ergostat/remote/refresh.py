"""Keeping each remote's model current while ergostat runs (SPEC §4c): a thread in the runner and in the page's
server asks each remote for its model when its ``every`` comes round (conditionally: an unchanged model is a 304).
A new version is written to the cache, which is one of the model's files, so the model reloads as for an edit."""

from __future__ import annotations

import threading
from pathlib import Path

from . import cache

TICK = 2.0


def once(project) -> None:
    spec = getattr(project.model, "spec", None)
    for r in (getattr(spec, "remotes", None) or {}).values():
        try:
            cache.refresh(Path(r["dir"]), r["url"], r.get("token_file"), spec.root, r["every"])
        except Exception:                      # one remote's trouble never stops the others
            continue


def start(get_project, stop: threading.Event | None = None) -> threading.Event:
    """Refresh every remote of the model ``get_project()`` returns (asked each time: the model may reload)."""
    stop = stop or threading.Event()

    def loop():
        while not stop.wait(TICK):
            try:
                once(get_project())
            except Exception:
                continue
    threading.Thread(target=loop, name="ergostat-remotes", daemon=True).start()
    return stop
