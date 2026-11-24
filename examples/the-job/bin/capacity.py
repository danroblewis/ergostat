"""The drafting capacity: how many alert companions may draft at once (rhythm.yaml, the capacity law).

    capacity.py read START   the sensor: the setting now, or START when none is stored or it can't be read
    capacity.py step START   the law: u_k = u_(k-1) + gain * e_k on the alert backlog's error, its deadband,
                             resolution and limits read from the block's params; prints the step, or nothing

Nothing but its own file under run/ is written. A missing, stale or non-number error reading steps nothing, and
JOB_POLICY=off steps nothing (the setting held fixed, to compare the law off and on)."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "run" / "capacity.json"


def number(v) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) else None


def setting(start: float, path: Path = FILE) -> float:
    """What is stored, else the start value: the pool is never left unread for want of a file."""
    try:
        v = number(json.loads(path.read_text()).get("setting"))
    except (OSError, ValueError, AttributeError):
        v = None
    return start if v is None else v


def law(ctx: dict, was: float) -> float | None:
    """The setting after this run's step, or None for no step (no reading, inside the deadband, rounded to none)."""
    p = ctx.get("params") or {}
    gain, band, res, lim = number(p.get("gain")), number(p.get("deadband", 0)), number(p.get("resolution")), p.get("limits")
    got = list((ctx.get("inputs") or {}).values())      # its one input: the backlog's error (the model's in:)
    e = number(got[0]) if len(got) == 1 else None
    if e is None or ctx.get("stale") or None in (gain, band, res) or not res or not isinstance(lim, list) or len(lim) != 2:
        return None
    lo, hi = number(lim[0]), number(lim[1])
    if lo is None or hi is None or abs(e) <= band:
        return None
    now = min(hi, max(lo, math.floor((was + gain * e) / res + 0.5) * res))
    return None if now == was else now


def main() -> int:
    what, start = sys.argv[1], float(sys.argv[2])
    was = setting(start)
    if what == "read":
        print(f"{was:g}")
        return 0
    if os.environ.get("JOB_POLICY") == "off":           # the law off: the setting stays where it is, nothing moves
        return 0
    now = law(json.loads(sys.stdin.read() or "{}"), was)
    if now is None:
        return 0
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"setting": now}))
    tmp.replace(FILE)
    print(json.dumps({"moved": now - was}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
