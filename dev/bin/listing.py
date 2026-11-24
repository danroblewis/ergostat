"""One recent listing of a kind, shared by the measure sensors (measure.py) that read it within SHARE seconds of each
other: the first lists the kind (fac.items, about 20 calls for the gaps) and keeps what it got under the engine's state
folder (``$ERGOSTAT_STATE_DIR/listings/KIND.json``); the others, waiting on that kind's lock meanwhile, read it.

- The lock is held across the look, the listing and the write, so readings of one kind at once make one listing.
- A kept listing is used only while its age (from when its listing began) is from 0 to SHARE seconds: an older one, a
  stamp that is not a number, or one from the future (a clock set back), is listed again.
- A listing that fails raises and writes nothing: the next reading lists again.
- Outside a run by the engine (no ``ERGOSTAT_STATE_DIR``), or for a kind that is not a plain name, nothing is shared."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

SHARE = 120.0           # seconds a listing is shared for: the oldest a measure's reading of it may be
KIND = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def items(kind: str, folder: str | os.PathLike | None = None, window: float = SHARE) -> list[dict]:
    """The items of a kind, from a listing begun at most ``window`` seconds ago."""
    folder = folder or os.environ.get("ERGOSTAT_STATE_DIR")
    if not folder or not KIND.fullmatch(kind):
        return fac.items(kind)
    d = Path(folder) / "listings"
    d.mkdir(parents=True, exist_ok=True)
    kept = d / f"{kind}.json"
    with open(d / f"{kind}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)               # (released when the file closes, or the process ends)
        got = fresh(kept, window)
        if got is not None:
            return got
        begun = time.time()
        rows = fac.items(kind)                           # (a failure raises here: nothing kept)
        tmp = d / f"{kind}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps({"kind": kind, "begun": begun, "items": rows}))
        os.replace(tmp, kept)
        return rows


def fresh(kept: Path, window: float, now: float | None = None) -> list[dict] | None:
    """What a kept listing holds, when it began 0 to ``window`` seconds ago; else None (missing, unreadable, too old,
    from the future, or not a listing)."""
    try:
        got = json.loads(kept.read_text())
        begun = float(got["begun"])
        rows = got["items"]
    except (OSError, ValueError, TypeError, KeyError):
        return None
    age = (time.time() if now is None else now) - begun
    if not math.isfinite(age) or not 0 <= age <= window or not isinstance(rows, list):
        return None
    return rows
