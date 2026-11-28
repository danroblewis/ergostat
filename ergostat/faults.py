"""The engine's own faults (SPEC §9.1, *The engine's own faults*): a part of its loop that raised (the joins, a
projection's emit outbox, the triggers, the schedules, the messages' sweep, the workspaces, the actions, the
evaluation) or a step after a block's run (its costs, its claims, its workspace's release), recorded on change only:

- ``ergostat.fault.started`` when one begins, with its part, why, and since when;
- ``ergostat.fault.changed`` when its why changes while it lasts;
- ``ergostat.fault.cleared`` when the part next succeeds, with how long it lasted.

Each about its item, ``ergostat.fault/<part>``: its history on the Events page. A pass that fails the same way again
records nothing. What is open now is kept in ``<state>/faults.json`` (written on change, read by the snapshot), where the
page's faults show it beside the failing sensors; the engine reads it back when it starts, so a fault open when it
stopped is cleared on its first good pass."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

FAULT = "ergostat.fault"
STATE = "faults.json"
SOURCE = "ergostat"


def item_of(part: str) -> str:
    return f"{FAULT}/{part}"


def why_of(e) -> str:
    return (f"{type(e).__name__}: {e}" if isinstance(e, BaseException) else str(e or ""))[:500]


def read_state(state_dir) -> dict[str, dict]:
    """The faults open now, by part: ``{part: {why, since, what, link}}``."""
    try:
        got = json.loads((Path(state_dir) / STATE).read_text())
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


class Faults:
    """The engine's, one for its life: ``failed(part, e)`` and ``ok(part)`` from each place that used to only log."""

    def __init__(self, p, say=None):
        self.p, self.say = p, say or (lambda s: None)
        self.lock = threading.Lock()
        self.open: dict[str, dict] = read_state(p.dir) if getattr(p, "dir", None) else {}

    def failed(self, part: str, e, what: str | None = None) -> bool:
        """``part`` raised ``e`` (or said why): recorded when it starts or its why changes; logged then too. ``what``:
        how the owner reads the part ("emit for projection deploy"). Whether anything was recorded."""
        why, now = why_of(e), time.time()
        with self.lock:
            was = self.open.get(part)
            if was is not None and was.get("why") == why:
                return False
            x = {"part": part, "what": what or part, "why": why, "since": (was or {}).get("since") or now}
            self.open[part] = x
            self._write()
        self.say(f"{what or part}: {why}")
        self._record("changed" if was is not None else "started", part, x)
        return True

    def ok(self, part: str) -> bool:
        """``part`` succeeded: a fault open on it is cleared (recorded, with how long it lasted)."""
        if part not in self.open:                       # (the common case: read without the lock)
            return False
        with self.lock:
            x = self.open.pop(part, None)
            if x is None:
                return False
            self._write()
        lasted = round(time.time() - float(x.get("since") or time.time()), 3)
        self.say(f"{x.get('what') or part}: recovered after {lasted:g} s")
        self._record("cleared", part, {**x, "lasted": lasted})
        return True

    def _record(self, step: str, part: str, data: dict) -> None:
        try:
            self.p.events.add(f"{FAULT}.{step}", item=item_of(part), source=SOURCE, data=data)
        except Exception as e:                          # noqa: BLE001  (noting a fault never makes another)
            self.say(f"{part}: its fault could not be recorded: {type(e).__name__}: {e}")

    def _write(self) -> None:
        d = getattr(self.p, "dir", None)
        if d is None:
            return
        path = Path(d) / STATE
        try:
            if not self.open:
                path.unlink(missing_ok=True)
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(self.open))
            os.replace(tmp, path)
        except OSError:
            pass


def rows(open_: dict[str, dict]) -> list[dict]:
    """The open faults (``read_state``) as the page's fault rows: what, since when, why, linked to its history."""
    from urllib.parse import quote
    out = []
    for part, x in sorted(open_.items()):
        since = time.strftime("%H:%M", time.localtime(float(x.get("since") or time.time())))
        out.append({"level": "bad", "what": f"engine {x.get('what') or part}", "fault": part,
                    "link": f"/events?item={quote(item_of(part), safe='')}",
                    "says": f"{x.get('what') or part} failing since {since}: {x.get('why')}"})
    return out
