"""The world, kept between the programs ergostat runs: its state in run/world/state.json, what happened appended to
run/world/feed.jsonl (the way a real factory has its tracker's API and a stream of changes). Whoever reads it first
advances it to now under a lock: the world is a function of the clock.

The clock: a factory hour every COORD_HOUR seconds (30 by default, so a factory day is 12 minutes). The policy is
COORD_POLICY (`designed`, the default; `harness`, the harness as it was), the seed COORD_SEED.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from world.plant import STEP, Plant, fresh

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "run" / "world"
HOUR = float(os.environ.get("COORD_HOUR", "30"))
POLICY = os.environ.get("COORD_POLICY", "designed")
SEED = int(os.environ.get("COORD_SEED", "1"))
CATCH_UP = 2.0                     # factory hours: a longer gap (nothing ran) is a pause, not time passing


@contextmanager
def advanced(now: float | None = None):
    """The world moved on to now; yields the plant, then saves it and appends what happened to the feed."""
    RUN.mkdir(parents=True, exist_ok=True)
    now = time.time() if now is None else now
    with open(RUN / ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = RUN / "state.json"
        s = json.loads(path.read_text()) if path.exists() else {**fresh(SEED, POLICY), "t0": now}
        p = Plant(s)
        target = s["t_start"] + (now - s["t0"]) / HOUR
        if target - p.t > CATCH_UP:                       # stopped for a while: the world waited
            s["t0"] += (target - p.t - CATCH_UP) * HOUR
            target = p.t + CATCH_UP
        while p.t < target - 1e-9:
            p.step(min(STEP, target - p.t))
        yield p
        feed, s["feed"] = s["feed"], []
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(s))
        tmp.replace(path)
        if feed:
            with open(RUN / "feed.jsonl", "a") as f:
                for e in feed:
                    f.write(json.dumps(e) + "\n")


def feed(after: int) -> tuple[list[dict], int]:
    """What the feed has said since byte offset `after`, and the new offset."""
    path = RUN / "feed.jsonl"
    if not path.exists():
        return [], 0
    with open(path, "rb") as f:
        f.seek(after)
        data = f.read()
    end = data.rfind(b"\n") + 1
    return [json.loads(x) for x in data[:end].splitlines() if x.strip()], after + end
