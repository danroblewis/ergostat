"""Run ergostat with lightweight timings of the engine's parts, for scripts/scale_bench.py (docs/proposals/scale.md).

    ERGOSTAT_TIMINGS=out.json uv run python scripts/scale_probe.py -C DIR run --foreground --no-web

Without ERGOSTAT_TIMINGS it is plain ``python -m ergostat``. With it, the engine's parts are wrapped (nothing in
ergostat is changed): each call's wall time and the CPU time of the thread that made it (``time.thread_time``, so
time waiting for the GIL or a lock is not counted as CPU), summed by part, with the wall times of the engine's pass
(``evaluate``) and the dispatcher's look (``dispatch.tick``) kept for their percentiles. Written to the file every
ten seconds, and at the end.

Parts: ``evaluate`` (the pass after every reading and every second: measure, goals, built-ins, which machine blocks
are due), ``measure`` and ``goals`` (inside it), ``sensor.<kind>`` (one reading: items counted, a command run, a
built-in measure, a change), ``fold.catch_up`` (the item index following the record), ``items.project`` (every item
of a kind, read), ``dispatch.tick`` (which items each block takes now), ``dispatch.watch`` (the lease watchdog),
``dispatch.take`` (one lease and its run started), ``run_block`` (a machine block's run, its process included),
``judge`` (the judge's pass), ``sweep`` (messages, workspaces, actions)."""

from __future__ import annotations

import atexit
import functools
import json
import os
import random
import sys
import threading
import time

OUT = os.environ.get("ERGOSTAT_TIMINGS")
KEEP = 20000                       # wall times kept per part with percentiles (a reservoir)
TIMED = ("evaluate", "dispatch.tick")
lock = threading.Lock()
parts: dict[str, dict] = {}
samples: dict[str, list[float]] = {k: [] for k in TIMED}
seen: dict[str, int] = {k: 0 for k in TIMED}
started = time.time()


def note(name: str, wall: float, cpu: float) -> None:
    with lock:
        p = parts.setdefault(name, {"calls": 0, "wall": 0.0, "cpu": 0.0, "max": 0.0})
        p["calls"] += 1
        p["wall"] += wall
        p["cpu"] += cpu
        p["max"] = max(p["max"], wall)
        if name in samples:
            seen[name] += 1
            s = samples[name]
            if len(s) < KEEP:
                s.append(wall)
            else:
                j = random.randrange(seen[name])
                if j < KEEP:
                    s[j] = wall


def wrap(owner, attr: str, name: str | None = None, by=None) -> None:
    f = getattr(owner, attr)

    @functools.wraps(f)
    def timed(*a, **k):
        w, c = time.perf_counter(), time.thread_time()
        try:
            return f(*a, **k)
        finally:
            note(by(*a, **k) if by else (name or attr), time.perf_counter() - w, time.thread_time() - c)
    setattr(owner, attr, timed)


def sensor_kind(spec, s, *a, **k) -> str:
    return "sensor." + ("changes" if s.changes is not None else "items" if s.items is not None else
                        "query" if s.query is not None else "builtin" if getattr(s, "builtin", None) else "run")


def dump() -> None:
    with lock:
        out = {"since": started, "at": time.time(), "parts": {k: dict(v) for k, v in parts.items()},
               "samples": {k: list(v) for k, v in samples.items()}}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f)
    os.replace(tmp, OUT)


def install() -> None:
    from ergostat.leases import dispatch
    from ergostat.spec import engine, itemindex, items
    E, D = engine.Engine, dispatch.Dispatcher
    for attr in ("evaluate", "measure", "goals", "judge", "_sweep", "run_block"):
        wrap(E, attr, {"_sweep": "sweep"}.get(attr, attr))
    for attr in ("tick", "watch", "take"):
        wrap(D, attr, f"dispatch.{attr}")
    wrap(engine, "read_sensor", by=sensor_kind)
    wrap(itemindex.Index, "catch_up", "fold.catch_up")
    wrap(items, "project", "items.project")
    dispatch.its.project = items.project                 # (the dispatcher's own name for it)

    def every() -> None:
        while True:
            time.sleep(10)
            try:
                dump()
            except Exception as e:                       # a measurement never stops the engine
                print(f"timings: {e}", file=sys.stderr)
    threading.Thread(target=every, daemon=True).start()
    atexit.register(dump)


if __name__ == "__main__":
    if OUT:
        install()
    from ergostat.cli import main
    sys.exit(main(sys.argv[1:]))
