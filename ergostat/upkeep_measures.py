"""ergostat's own upkeep, measured (SPEC §2a, *Upkeep*): ``ergostat.upkeep.index-files``, the live item-index files
under ``<state>/items``, and ``ergostat.upkeep.retired-index-files``, the retired ones (``spec/itemindex.files``);
``ergostat.upkeep.heartbeat-age``, the seconds since the last pass ``<state>/heartbeat.json`` gives
(``spec/watchdog.heartbeat``); ``ergostat.upkeep.stalls``, the ``ergostat.engine.stalled`` events over the last hour,
and ``ergostat.upkeep.restarts``, the ``ergostat.engine.restarted`` ones over the last day.

A record kept nowhere on disk (for the files or the heartbeat), an items folder that cannot be listed, a heartbeat
missing, unreadable or stamped in the future, or an event log that cannot be read gives no reading (None, said on
standard error, the sensor's log), never 0: a goal held at "few files", "fresh" or "no stalls" is never met by
something nobody could look at. The heartbeat's age is a drawing, not a protection: a frozen engine reads nothing,
and the outer watcher acts. The two event counts read a log kept only in memory too: it holds the events it counts,
unlike a folder or file not there."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

from .spec import itemindex

WINDOWS = {"stalls": ("ergostat.engine.stalled", 3600.0), "restarts": ("ergostat.engine.restarted", 86400.0)}


def _state(p) -> Path | None:
    d = getattr(p, "dir", None)
    return Path(d) if d is not None else itemindex.state_dir(p.events)


def heartbeat_age(p, name: str, now: float | None = None) -> float | None:
    d = _state(p)
    if d is None:
        print(f"{name}: the record is kept nowhere on disk, so it has no heartbeat", file=sys.stderr)
        return None
    try:
        got = json.loads((d / "heartbeat.json").read_text())
        passed = got["pass"]
    except (OSError, ValueError, TypeError, KeyError) as e:
        print(f"{name}: {d / 'heartbeat.json'} cannot be read ({type(e).__name__}: {e})", file=sys.stderr)
        return None
    if not isinstance(passed, int | float) or isinstance(passed, bool) or not math.isfinite(passed):
        print(f"{name}: {d / 'heartbeat.json'} gives no time for its last pass ({passed!r})", file=sys.stderr)
        return None
    age = (time.time() if now is None else now) - passed
    if age < 0:                                    # (stamped in the future: no reading, never "fresh")
        print(f"{name}: {d / 'heartbeat.json'} gives a last pass {-age:.0f}s in the future", file=sys.stderr)
        return None
    return round(age, 3)


def events(p, name: str, now: float | None = None) -> float | None:
    kind, over = WINDOWS[name.rsplit(".", 1)[1]]
    now = time.time() if now is None else now
    try:
        return float(len(p.events.query(n=None, type=kind, since=now - over)))
    except Exception as e:                         # (a log missing or unreadable: no reading, never 0)
        print(f"{name}: the event log cannot be read ({type(e).__name__}: {e})", file=sys.stderr)
        return None


def measure(p, name: str) -> float | None:
    if name.endswith(".heartbeat-age"):
        return heartbeat_age(p, name)
    if name.endswith((".stalls", ".restarts")):
        return events(p, name)
    d = itemindex.state_dir(p.events)
    if d is None:
        print(f"{name}: the record is kept nowhere on disk, so it has no index files to count", file=sys.stderr)
        return None
    try:
        live, retired = itemindex.files(d / "items")
    except OSError as e:
        print(f"{name}: {d / 'items'} cannot be listed ({type(e).__name__}: {e})", file=sys.stderr)
        return None
    return float(len(retired if name.endswith("retired-index-files") else live))
